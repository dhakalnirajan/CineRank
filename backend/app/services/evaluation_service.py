"""One-time post-catalogue validation and offline recommendation Pass@K metrics."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ids import is_title_id
from app.ml.portable_models import PortableModelRegistry
from app.models.entities import CatalogueSortIndex, CatalogueState, Movie, Rating, User, ModelBenchmark
from ranker.production_ranker import Candidate, ProductionRanker

logger = logging.getLogger("cinerank.evaluation")


def _metric_row(ranks: list[int], total: int, ks: list[int]) -> dict:
    metrics = {"sample_users": total, "definition": "Pass@K is HitRate@K: at least one held-out relevant item appears in top K."}
    for k in ks:
        hits = sum(1 for rank in ranks if 0 < rank <= k)
        metrics[f"pass_at_{k}"] = hits / total if total else 0.0
        metrics[f"hit_rate_at_{k}"] = hits / total if total else 0.0
        metrics[f"precision_at_{k}"] = hits / (total * k) if total else 0.0
        metrics[f"recall_at_{k}"] = hits / total if total else 0.0
        dcg = sum(1.0 / math.log2(rank + 1) for rank in ranks if 0 < rank <= k)
        metrics[f"ndcg_at_{k}"] = dcg / total if total else 0.0
    return metrics


def scan_catalogue(db: Session, registry: PortableModelRegistry) -> dict:
    """Validate permanent identities, active sort-index coverage, and cold-start features."""
    total = int(db.query(func.count(Movie.title_id)).scalar() or 0)
    invalid_ids = 0
    for (title_id,) in db.query(Movie.title_id).yield_per(5000):
        if not is_title_id(title_id):
            invalid_ids += 1
    state = db.query(CatalogueState).filter_by(id=1).first()
    version = int(state.active_version) if state else 0
    indexed = int(db.query(func.count(CatalogueSortIndex.title_id)).filter_by(version_id=version).scalar() or 0) if version else 0
    sample = db.query(Movie).filter(Movie.movielens_id.is_(None)).limit(100).all()
    coldstart_vectors = registry.transform_content([
        f"{row.title or ''} {(row.genres or '').replace('|', ' ')}" for row in sample
    ]) if sample else None
    feature_count = int(coldstart_vectors.shape[0]) if coldstart_vectors is not None else 0
    return {
        "catalogue_titles": total,
        "invalid_title_ids": invalid_ids,
        "catalogue_version": version,
        "sort_index_rows": indexed,
        "sort_index_complete": (version == 0 or indexed == total),
        "cold_start_titles_scanned": len(sample),
        "cold_start_feature_rows": feature_count,
        "cold_start_features_ready": (not sample) or feature_count == len(sample),
    }


def evaluate_bundle_once(db: Session, registry: PortableModelRegistry, persist: bool = True,
                          holdout_override: pd.DataFrame | None = None) -> dict:
    manifest = registry.manifest or {}
    bundle_id = str(manifest.get("bundle_id") or manifest.get("created_at_utc") or "unknown")
    catalogue_state = db.query(CatalogueState).filter_by(id=1).first()
    catalogue_version = int(catalogue_state.active_version) if catalogue_state else 0
    scan = scan_catalogue(db, registry)
    expected_models = [name for name in ("popularity", "content", "itemknn", "als", "bpr", "attention")
                       if name in registry.ready_models]
    if persist and expected_models:
        completed = {row[0] for row in db.query(ModelBenchmark.model_name).filter_by(
            bundle_id=bundle_id, catalogue_version=catalogue_version
        ).all()}
        if set(expected_models + ["hybrid"]).issubset(completed):
            return {"status": "already_evaluated", "bundle_id": bundle_id,
                    "catalogue_version": catalogue_version, "scan": scan}
    holdout_path = registry.model_dir / "holdout_sample.csv"
    if holdout_override is not None:
        holdout = holdout_override.copy()
    else:
        if not holdout_path.is_file():
            return {"status": "skipped", "reason": "Bundle has no holdout_sample.csv", "scan": scan}
        holdout = pd.read_csv(holdout_path)
    required = {"source_user_id", "movielens_id"}
    if not required.issubset(holdout.columns):
        return {"status": "skipped", "reason": "Holdout schema is missing source_user_id/movielens_id", "scan": scan}
    holdout = holdout.dropna(subset=["source_user_id", "movielens_id"])
    holdout["source_user_id"] = holdout["source_user_id"].astype("int64")
    holdout["movielens_id"] = holdout["movielens_id"].astype("int64")
    holdout = holdout.head(settings.MODEL_EVALUATION_MAX_USERS)
    if holdout.empty:
        return {"status": "skipped", "reason": "Holdout set is empty", "scan": scan}

    source_ids = [str(value) for value in holdout.source_user_id.unique()]
    users = db.query(User).filter(User.external_id.in_(source_ids)).all()
    user_by_source = {str(user.external_id): user.id for user in users}
    relevant = {str(row.source_user_id): int(row.movielens_id) for row in holdout.itertuples(index=False)}
    internal_user_ids = list(user_by_source.values())
    histories: dict[int, list[int]] = {user_id: [] for user_id in internal_user_ids}
    if internal_user_ids:
        rows = (db.query(Rating.user_id, Movie.movielens_id)
                .join(Movie, Rating.title_id == Movie.title_id)
                .filter(Rating.user_id.in_(internal_user_ids))
                .order_by(Rating.timestamp.asc(), Rating.id.asc()).all())
        for user_id, movie_id in rows:
            if movie_id is None:
                continue
            index = registry.movie_to_idx.get(int(movie_id))
            if index is not None:
                histories.setdefault(int(user_id), []).append(index)
    for user_id in histories:
        histories[user_id] = list(dict.fromkeys(histories[user_id]))

    ks = settings.evaluation_ks or [5, 10, 20]
    max_k = max(ks)
    model_names = [name for name in ("popularity", "content", "itemknn", "als", "bpr", "attention", "hybrid")
                   if name in registry.ready_models or (name == "hybrid" and registry.ready_models)]
    rank_positions = {name: [] for name in model_names}
    evaluated = 0

    # Use the exact held-out users and the same historical DB state for every model.
    for source_user_id, target_movie_id in relevant.items():
        internal_id = user_by_source.get(source_user_id)
        if internal_id is None:
            continue
        history = histories.get(internal_id, [])
        predictions = registry.recommend_sources(source_user_id, history, k=max_k)
        evaluated += 1
        for model_name in model_names:
            if model_name == "hybrid":
                candidates = []
                for source, (indices, scores) in predictions.items():
                    if source not in registry.ready_models:
                        continue
                    for index, score in zip(indices, scores):
                        item_index = int(index)
                        if 0 <= item_index < len(registry.idx_to_movie):
                            movie_id = int(registry.idx_to_movie[item_index])
                            candidates.append(Candidate(
                                title_id=str(movie_id), score=float(score), source=source,
                                model_index=item_index, source_item_id=movie_id,
                            ))
                ranked = ProductionRanker(
                    source_weights=(registry.hybrid or {}).get("weights")
                ).rank(candidates, k=max_k)
                top_ids = [int(item.title_id) for item in ranked]
            else:
                result = predictions.get(model_name)
                top_ids = [int(registry.idx_to_movie[int(idx)]) for idx in result[0][:max_k]] if result else []
            try:
                rank = top_ids.index(target_movie_id) + 1
            except ValueError:
                rank = 0
            rank_positions[model_name].append(rank)

    if evaluated == 0:
        return {"status": "no_evaluable_users", "bundle_id": bundle_id,
                "catalogue_version": catalogue_version, "scan": scan}

    metrics_by_model = {}
    for model_name, ranks in rank_positions.items():
        metrics = _metric_row(ranks, evaluated, ks)
        threshold = float(settings.MODEL_EVALUATION_MIN_HIT_RATE_10)
        hit_at_10 = metrics.get("hit_rate_at_10")
        passed = bool(evaluated and scan["invalid_title_ids"] == 0 and scan["sort_index_complete"]
                      and scan["cold_start_features_ready"] and hit_at_10 is not None
                      and float(hit_at_10) >= threshold)
        reasons = []
        if scan["invalid_title_ids"]:
            reasons.append("invalid title IDs found")
        if not scan["sort_index_complete"]:
            reasons.append("active catalogue sort index is incomplete")
        if not scan["cold_start_features_ready"]:
            reasons.append("cold-start content features unavailable")
        if hit_at_10 is None or float(hit_at_10) < threshold:
            reasons.append(f"HitRate@10 below configured threshold {threshold:.4f}")
        existing = db.query(ModelBenchmark).filter_by(
            bundle_id=bundle_id, model_name=model_name, catalogue_version=catalogue_version
        ).first()
        if persist and existing is None:
            db.add(ModelBenchmark(
                bundle_id=bundle_id, model_name=model_name,
                catalogue_version=catalogue_version, sample_users=evaluated,
                metrics_json=json.dumps(metrics, separators=(",", ":")),
                passed=passed, reason=None if passed else "; ".join(reasons),
            ))
            db.commit()
        metrics_by_model[model_name] = metrics

    return {
        "status": "complete" if evaluated else "no_evaluable_users",
        "bundle_id": bundle_id,
        "catalogue_version": catalogue_version,
        "evaluated_users": evaluated,
        "metrics": metrics_by_model,
        "scan": scan,
    }
