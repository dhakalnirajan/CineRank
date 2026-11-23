"""Weighted reciprocal-rank fusion followed by genre-aware MMR selection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import math


@dataclass(frozen=True)
class Candidate:
    title_id: str
    score: float
    source: str
    genres: str = ""
    model_index: Optional[int] = None
    source_item_id: Optional[int] = None


@dataclass
class RankedItem:
    title_id: str
    final_score: float
    sources: List[str]
    genres: str


class ProductionRanker:
    """Fuse independent candidate lists without comparing incompatible scores.

    Each source is ranked independently. Weighted RRF then combines rank
    positions; the fused relevance is normalized before MMR so genre redundancy
    is on a comparable [0, 1] scale. The serving model may itself be a trained
    hybrid (ALS/BPR/ItemKNN/content/attention); this outer layer combines that
    release with catalogue-derived candidate sources.
    """

    DEFAULT_SOURCE_WEIGHTS = {
        "attention": 1.00, "als": 1.00, "bpr": 0.90,
        "itemknn": 0.80, "content": 0.75, "content_cold_start": 0.75,
        "hybrid_model": 1.00, "popularity": 0.40,
        "catalogue_popularity": 0.40,
    }

    def __init__(self, source_weights: Optional[Dict[str, float]] = None,
                 relevance_lambda: float = 0.85, rrf_constant: int = 60):
        self.source_weights = dict(self.DEFAULT_SOURCE_WEIGHTS)
        if source_weights:
            self.source_weights.update({str(k): float(v) for k, v in source_weights.items()})
        self.relevance_lambda = min(1.0, max(0.0, relevance_lambda))
        self.rrf_constant = max(1, int(rrf_constant))

    @staticmethod
    def _genres(value: str) -> set[str]:
        return {part.strip().casefold() for part in (value or "").replace(",", "|").split("|") if part.strip()}

    @staticmethod
    def _genre_similarity(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def rank(self, candidates: List[Candidate], k: int = 5,
             seen: Optional[set[str]] = None) -> List[RankedItem]:
        if not candidates or k <= 0:
            return []
        seen = seen or set()
        by_source: Dict[str, Dict[str, Candidate]] = {}
        for candidate in candidates:
            if (not candidate.title_id or candidate.title_id in seen
                    or not math.isfinite(candidate.score)):
                continue
            source_map = by_source.setdefault(candidate.source, {})
            current = source_map.get(candidate.title_id)
            if current is None or candidate.score > current.score:
                source_map[candidate.title_id] = candidate

        aggregate: Dict[str, dict] = {}
        for source, source_candidates in by_source.items():
            ranked = sorted(source_candidates.values(), key=lambda c: (-c.score, c.title_id))
            weight = max(0.0, float(self.source_weights.get(source, 0.03)))
            for position, candidate in enumerate(ranked, start=1):
                row = aggregate.setdefault(candidate.title_id, {
                    "score": 0.0, "sources": [], "genres": candidate.genres,
                })
                row["score"] += weight / (self.rrf_constant + position)
                row["sources"].append(source)
                if candidate.genres:
                    row["genres"] = candidate.genres

        if not aggregate:
            return []
        max_relevance = max(data["score"] for data in aggregate.values()) or 1.0
        pool = sorted(aggregate.items(), key=lambda pair: (-pair[1]["score"], pair[0]))
        selected: List[RankedItem] = []
        selected_genres: List[set[str]] = []
        while pool and len(selected) < k:
            best_position = None
            best_value = -float("inf")
            for position, (_title_id, data) in enumerate(pool):
                genres = self._genres(data["genres"])
                redundancy = max(
                    (self._genre_similarity(genres, prior) for prior in selected_genres),
                    default=0.0,
                )
                relevance = data["score"] / max_relevance
                mmr = self.relevance_lambda * relevance - (1.0 - self.relevance_lambda) * redundancy
                if mmr > best_value:
                    best_position, best_value = position, mmr
            if best_position is None:
                break
            title_id, data = pool.pop(best_position)
            genres = self._genres(data["genres"])
            selected.append(RankedItem(
                title_id=title_id,
                final_score=float(best_value),
                sources=sorted(set(data["sources"])),
                genres=data["genres"],
            ))
            selected_genres.append(genres)
        return selected
