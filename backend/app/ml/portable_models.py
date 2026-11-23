"""Load and score the framework-neutral artifact bundle produced by the Colab notebook."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch
from torch import nn
from scipy.sparse import load_npz, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.config import settings

logger = logging.getLogger("cinerank.models")


def _verify_artifact_checksums(directory: Path) -> None:
    """Validate immutable artifacts before a bundle is loaded or activated."""
    import hashlib

    sums_path = directory / "SHA256SUMS"
    if not sums_path.is_file():
        logger.warning("Artifact checksums are absent in %s", directory)
        return
    root = directory.resolve()
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, filename = line.split(None, 1)
        filename = filename.strip()
        path = (directory / filename).resolve()
        if root not in path.parents:
            raise ValueError(f"Unsafe checksum path: {filename}")
        if not path.is_file():
            raise FileNotFoundError(f"Missing model artifact: {filename}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"Artifact checksum mismatch: {filename}")


def _recover_active_bundle(model_dir: Path) -> Optional[Path]:
    """Restore a missing ACTIVE_BUNDLE pointer only when one valid bundle exists."""
    bundles_dir = model_dir / "bundles"
    if not bundles_dir.is_dir():
        return None

    candidates: List[Path] = []
    for candidate in sorted(bundles_dir.iterdir()):
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue
        manifest_path = candidate / "manifest.json"
        maps_path = candidate / f"{settings.ID_MAPS}.json"
        if not manifest_path.is_file() or not maps_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable model bundle %s: %s", candidate, exc)
            continue
        if manifest.get("bundle_format") != "cinerank-portable-v1":
            continue
        if manifest.get("bundle_id") != candidate.name:
            continue
        try:
            _verify_artifact_checksums(candidate)
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring invalid model bundle %s: %s", candidate, exc)
            continue
        candidates.append(candidate)

    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warning(
            "ACTIVE_BUNDLE is missing and multiple valid bundles exist; leaving it unset: %s",
            ", ".join(path.name for path in candidates),
        )
        return None

    selected = candidates[0]
    pointer = model_dir / "ACTIVE_BUNDLE"
    pointer_tmp = model_dir / "ACTIVE_BUNDLE.tmp"
    pointer_tmp.write_text(selected.name, encoding="utf-8")
    pointer_tmp.replace(pointer)
    logger.warning("Recovered missing ACTIVE_BUNDLE pointer to %s", selected.name)
    return selected


class TargetAwareAttention(nn.Module):
    """Must match the ``target_aware_attention_v1`` notebook architecture exactly."""
    def __init__(self, n_items: int, emb_dim: int, max_history: int):
        super().__init__()
        self.item_embedding = nn.Embedding(n_items + 1, emb_dim, padding_idx=0)
        self.attention = nn.Sequential(
            nn.Linear(emb_dim * 2, emb_dim), nn.ReLU(), nn.Linear(emb_dim, 1)
        )
        self.scorer = nn.Sequential(
            nn.Linear(emb_dim * 3, emb_dim), nn.ReLU(), nn.Linear(emb_dim, 1)
        )
        self.max_history = max_history
        self.emb_dim = emb_dim

    def forward(self, histories: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        h = self.item_embedding(histories)
        t = self.item_embedding(targets).unsqueeze(1)
        logits = self.attention(torch.cat([h, t.expand_as(h)], dim=-1)).squeeze(-1)
        mask = histories.ne(0)
        logits = logits.masked_fill(~mask, -1e9)
        weights = torch.softmax(logits, dim=1)
        weights = torch.where(mask.any(dim=1, keepdim=True), weights, torch.zeros_like(weights))
        context = torch.sum(weights.unsqueeze(-1) * h, dim=1)
        target = t.squeeze(1)
        return self.scorer(torch.cat([context, target, context * target], dim=-1)).squeeze(-1)


class PortableModelRegistry:
    """Read-only model registry. No notebook-local classes or pickle deserialization."""
    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = Path(model_dir or settings.MODEL_DIR)
        self.manifest: dict = {}
        self.id_maps: dict = {}
        self.idx_to_movie: List[int] = []
        self.user_to_idx: Dict[str, int] = {}
        self.movie_to_idx: Dict[int, int] = {}
        self.n_items = 0
        self.n_users = 0
        self.popularity: Optional[np.ndarray] = None
        self.content: Optional[csr_matrix] = None
        self.content_vectorizer: Optional[TfidfVectorizer] = None
        self.itemknn: Optional[csr_matrix] = None
        self.als_user: Optional[np.ndarray] = None
        self.als_item: Optional[np.ndarray] = None
        self.bpr_user: Optional[np.ndarray] = None
        self.bpr_item: Optional[np.ndarray] = None
        self.attention: Optional[TargetAwareAttention] = None
        self.hybrid: dict = {}
        self.ready_models: set[str] = set()

    @property
    def is_ready(self) -> bool:
        return bool(self.popularity is not None or self.ready_models)

    def load(self) -> None:
        pointer = self.model_dir / "ACTIVE_BUNDLE"
        if not pointer.is_file():
            _recover_active_bundle(self.model_dir)
        if pointer.is_file():
            bundle_id = pointer.read_text(encoding="utf-8").strip()
            if not bundle_id or any(ch not in "0123456789abcdef-" for ch in bundle_id.lower()):
                raise ValueError("Invalid ACTIVE_BUNDLE pointer")
            self.model_dir = self.model_dir / "bundles" / bundle_id
            if not self.model_dir.is_dir():
                raise FileNotFoundError(f"Active model bundle directory missing: {self.model_dir}")
        manifest_path = self.model_dir / "manifest.json"
        maps_path = self.model_dir / f"{settings.ID_MAPS}.json"
        if not manifest_path.exists() or not maps_path.exists():
            logger.warning("Portable artifacts not found under %s", self.model_dir)
            return
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if self.manifest.get("bundle_format") != "cinerank-portable-v1":
            raise ValueError("Unsupported model artifact bundle format.")
        self._verify_checksums()
        self.id_maps = json.loads(maps_path.read_text(encoding="utf-8"))
        if self.id_maps.get("schema_version") != 2 or self.id_maps.get("matrix_orientation") != "users_by_items":
            raise ValueError("Unsupported or inconsistent ID map schema.")

        self.idx_to_movie = [int(x) for x in self.id_maps["idx_to_movielens_movie_id"]]
        self.movie_to_idx = {movie_id: i for i, movie_id in enumerate(self.idx_to_movie)}
        self.user_to_idx = {str(k): int(v) for k, v in self.id_maps["source_user_id_to_idx"].items()}
        self.n_items = len(self.idx_to_movie)
        self.n_users = len(self.id_maps["idx_to_source_user_id"])

        def load_npz_array(name: str, key: str):
            path = self.model_dir / name
            if not path.exists():
                return None
            with np.load(path, allow_pickle=False) as data:
                result = np.asarray(data[key], dtype=np.float32)
            return result

        self.popularity = load_npz_array(f"{settings.WEIGHT_POP}.npz", "scores")
        if self.popularity is not None:
            self.ready_models.add("popularity")
        content_path = self.model_dir / f"{settings.WEIGHT_CONTENT}.npz"
        if content_path.exists():
            self.content = load_npz(content_path).tocsr().astype(np.float32)
            metadata_path = self.model_dir / f"{settings.WEIGHT_CONTENT}-meta.json"
            if metadata_path.is_file():
                meta = json.loads(metadata_path.read_text(encoding="utf-8"))
                vocabulary = {str(k): int(v) for k, v in meta["vocabulary"].items()}
                self.content_vectorizer = TfidfVectorizer(
                    vocabulary=vocabulary,
                    ngram_range=tuple(meta.get("ngram_range", [1, 2])),
                    stop_words=meta.get("stop_words", "english"),
                    norm=meta.get("norm", "l2"),
                    dtype=np.float32,
                )
                # Explicit vocabulary is restored without fitting on any live catalogue data.
                self.content_vectorizer.fit(["cinerank vocabulary bootstrap"])
                self.content_vectorizer.idf_ = np.asarray(meta["idf"], dtype=np.float32)
                if len(self.content_vectorizer.idf_) != self.content.shape[1]:
                    raise ValueError("TF-IDF IDF vector and content matrix dimensions differ")
            self.ready_models.add("content")
        knn_path = self.model_dir / f"{settings.WEIGHT_ITEMKNN}.npz"
        if knn_path.exists():
            self.itemknn = load_npz(knn_path).tocsr().astype(np.float32)
            self.ready_models.add("itemknn")

        als_path = self.model_dir / f"{settings.WEIGHT_ALS}.npz"
        if als_path.exists():
            with np.load(als_path, allow_pickle=False) as data:
                self.als_user = np.asarray(data["user_factors"], dtype=np.float32)
                self.als_item = np.asarray(data["item_factors"], dtype=np.float32)
            self.ready_models.add("als")
        bpr_path = self.model_dir / f"{settings.WEIGHT_BPR}.npz"
        if bpr_path.exists():
            with np.load(bpr_path, allow_pickle=False) as data:
                self.bpr_user = np.asarray(data["user_factors"], dtype=np.float32)
                self.bpr_item = np.asarray(data["item_factors"], dtype=np.float32)
            self.ready_models.add("bpr")

        attention_path = self.model_dir / f"{settings.WEIGHT_ATTN}.pt"
        if attention_path.exists():
            # weights_only avoids arbitrary object deserialization on supported PyTorch versions.
            try:
                payload = torch.load(attention_path, map_location="cpu", weights_only=True)
            except TypeError:  # Compatibility fallback for older PyTorch; file is locally produced.
                payload = torch.load(attention_path, map_location="cpu")
            if payload.get("architecture") != "target_aware_attention_v1":
                raise ValueError("Unknown attention architecture in model artifact.")
            self.attention = TargetAwareAttention(
                int(payload["n_items"]), int(payload["emb_dim"]), int(payload["max_history"])
            )
            self.attention.load_state_dict(payload["state_dict"])
            self.attention.eval()
            self.ready_models.add("attention")

        hybrid_path = self.model_dir / f"{settings.WEIGHT_HYBRID}.json"
        if hybrid_path.exists():
            self.hybrid = json.loads(hybrid_path.read_text(encoding="utf-8"))
        self._validate_shapes()
        logger.info("Portable model registry loaded: %s", sorted(self.ready_models))

    def _verify_checksums(self) -> None:
        """Validate immutable artifacts before loading weights from disk."""
        _verify_artifact_checksums(self.model_dir)

    def transform_content(self, titles: List[str]):
        if self.content_vectorizer is None:
            return None
        safe_texts = [str(value or "") for value in titles]
        return self.content_vectorizer.transform(safe_texts).tocsr().astype(np.float32)

    def score_cold_start(self, history_indices: List[int], history_texts: List[str],
                         candidate_texts: List[str]) -> np.ndarray:
        """Score catalogue items absent from training using their TF-IDF content.

        This supports item cold-start, not collaborative-factor extrapolation. The
        content vectorizer's frozen training vocabulary/IDF is used so daily title
        additions do not require a retrain or alter the model feature space.
        """
        if self.content is None or self.content_vectorizer is None:
            return np.zeros(len(candidate_texts), dtype=np.float32)
        profile_parts = []
        valid = [int(i) for i in history_indices if 0 <= int(i) < self.n_items]
        if valid:
            profile_parts.append(self.content[np.asarray(valid, dtype=np.int64)])
        if history_texts:
            extra = self.transform_content(history_texts)
            if extra is not None and extra.shape[0]:
                profile_parts.append(extra)
        if not profile_parts:
            return np.zeros(len(candidate_texts), dtype=np.float32)
        from scipy.sparse import vstack
        profile = vstack(profile_parts).mean(axis=0)
        profile = csr_matrix(profile)
        norm = float(np.sqrt(profile.multiply(profile).sum()))
        if norm > 0:
            profile = profile * (1.0 / norm)
        candidates = self.transform_content(candidate_texts)
        if candidates is None:
            return np.zeros(len(candidate_texts), dtype=np.float32)
        return np.asarray(candidates.dot(profile.T).toarray()).ravel().astype(np.float32)

    def _validate_shapes(self) -> None:
        for name, arr in (("popularity", self.popularity),):
            if arr is not None and arr.shape != (self.n_items,):
                raise ValueError(f"{name} item dimension does not match id maps")
        for name, matrix in (("content", self.content), ("itemknn", self.itemknn)):
            if matrix is not None and matrix.shape[0] != self.n_items:
                raise ValueError(f"{name} item dimension does not match id maps")
        for name, arr in (("ALS item factors", self.als_item), ("BPR item factors", self.bpr_item)):
            if arr is not None and arr.shape[0] != self.n_items:
                raise ValueError(f"{name} item dimension does not match id maps")
        for name, arr in (("ALS user factors", self.als_user), ("BPR user factors", self.bpr_user)):
            if arr is not None and arr.shape[0] != self.n_users:
                raise ValueError(f"{name} user dimension does not match ID maps")

    @staticmethod
    def _top(scores: np.ndarray, k: int, seen: set[int]) -> Tuple[np.ndarray, np.ndarray]:
        values = np.asarray(scores, dtype=np.float32).reshape(-1).copy()
        if seen:
            valid_seen = np.fromiter((x for x in seen if 0 <= x < len(values)), dtype=np.int64)
            if valid_seen.size:
                values[valid_seen] = -np.inf
        finite = np.flatnonzero(np.isfinite(values))
        if finite.size == 0:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)
        take = min(max(1, k), finite.size)
        chosen = finite[np.argpartition(values[finite], -take)[-take:]]
        chosen = chosen[np.argsort(values[chosen])[::-1]]
        return chosen.astype(np.int64), values[chosen]

    def _factor_scores(self, user_factors: Optional[np.ndarray], item_factors: Optional[np.ndarray],
                       user_idx: Optional[int], history: List[int]) -> Optional[np.ndarray]:
        if item_factors is None:
            return None
        user_vec = None
        if user_idx is not None and user_factors is not None and 0 <= user_idx < len(user_factors):
            user_vec = user_factors[user_idx]
        if history:
            hist = np.asarray([i for i in history if 0 <= i < len(item_factors)], dtype=np.int64)
            if hist.size:
                history_vec = item_factors[hist].mean(axis=0)
                user_vec = history_vec if user_vec is None else (0.5 * user_vec + 0.5 * history_vec)
        if user_vec is None:
            return None
        return item_factors @ user_vec

    def score_attention(self, history: List[int], batch_size: int = 2048) -> Optional[np.ndarray]:
        if self.attention is None:
            return None
        max_hist = self.attention.max_history
        valid = [int(x) + 1 for x in history if 0 <= int(x) < self.n_items][-max_hist:]
        padded = np.zeros(max_hist, dtype=np.int64)
        if valid:
            padded[-len(valid):] = valid
        scores = np.empty(self.n_items, dtype=np.float32)
        with torch.inference_mode():
            hist_tensor = torch.as_tensor(padded, dtype=torch.long).view(1, -1)
            for start in range(0, self.n_items, batch_size):
                end = min(self.n_items, start + batch_size)
                candidates = torch.arange(start + 1, end + 1, dtype=torch.long)
                h = hist_tensor.expand(end - start, -1)
                scores[start:end] = self.attention(h, candidates).cpu().numpy()
        return scores

    def recommend_sources(self, source_user_id: Optional[str], history: List[int],
                          k: int = 100) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        user_idx = self.user_to_idx.get(str(source_user_id)) if source_user_id is not None else None
        seen = set(map(int, history))
        output: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

        if self.popularity is not None:
            output["popularity"] = self._top(self.popularity, k, seen)
        if self.content is not None:
            if history:
                profile = self.content[np.asarray(history, dtype=np.int64)].mean(axis=0)
            else:
                profile = self.content.mean(axis=0)
            scores = np.asarray(self.content.dot(np.asarray(profile).T)).ravel()
            output["content"] = self._top(scores, k, seen)
        if self.itemknn is not None:
            if history:
                scores = np.asarray(self.itemknn[np.asarray(history, dtype=np.int64)].sum(axis=0)).ravel()
            else:
                scores = self.popularity if self.popularity is not None else np.zeros(self.n_items)
            output["itemknn"] = self._top(scores, k, seen)

        als_scores = self._factor_scores(self.als_user, self.als_item, user_idx, history)
        if als_scores is not None:
            output["als"] = self._top(als_scores, k, seen)
        bpr_scores = self._factor_scores(self.bpr_user, self.bpr_item, user_idx, history)
        if bpr_scores is not None:
            output["bpr"] = self._top(bpr_scores, k, seen)
        attention_scores = self.score_attention(history, settings.ATTENTION_SCORE_BATCH_SIZE)
        if attention_scores is not None:
            output["attention"] = self._top(attention_scores, k, seen)
        return output
