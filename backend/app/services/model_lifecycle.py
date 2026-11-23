"""60-day challenger training, offline comparison, and atomic model promotion."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.portable_models import PortableModelRegistry
from app.models.entities import JobRun
from app.services.evaluation_service import evaluate_bundle_once

logger = logging.getLogger("cinerank.model_lifecycle")

MODEL_FILES = {
    "popularity": ["rec-pop-v1.npz"],
    "content": ["rec-content-v1.npz", "rec-content-v1-meta.json"],
    "itemknn": ["rec-itemknn-v1.npz"],
    "als": ["rec-als-v1.npz"],
    "bpr": ["rec-bpr-v1.npz"],
    "attention": ["rec-attn-v1.pt"],
}


def _bundle_dir() -> Path | None:
    pointer = settings.MODEL_DIR / "ACTIVE_BUNDLE"
    if not pointer.is_file():
        return None
    bundle_id = pointer.read_text(encoding="utf-8").strip()
    path = settings.MODEL_DIR / "bundles" / bundle_id
    return path if path.is_dir() else None


def model_refresh_due(db: Session, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    run = db.query(JobRun).filter_by(job_name="model_refresh_60d").first()
    if run and run.last_attempt_date == now.date() and run.last_status == "failed":
        return False
    if _bundle_dir() is None:
        return True
    if run is None or run.last_success_date is None:
        return False  # an installed Colab bundle is the initial trained champion
    return run.last_success_date <= (now.date() - timedelta(days=settings.MODEL_REFRESH_DAYS))


def _id_maps_equal(left: PortableModelRegistry, right: PortableModelRegistry) -> bool:
    left_bytes = json.dumps(left.id_maps, sort_keys=True, separators=(",", ":")).encode()
    right_bytes = json.dumps(right.id_maps, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(left_bytes).digest() == hashlib.sha256(right_bytes).digest()


def _hit_rate(metrics: dict, model_name: str) -> float | None:
    row = metrics.get("metrics", {}).get(model_name)
    if not row or not row.get("sample_users"):
        return None
    return float(row.get("hit_rate_at_10", 0.0))


def _write_checksums(directory: Path) -> None:
    entries = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(chunk)
            entries.append((path.name, digest.hexdigest()))
    (directory / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in entries), encoding="utf-8"
    )


def _promote_bundle(champion: Path, challenger: Path,
                    selections: dict[str, str], same_maps: bool) -> tuple[Path, dict]:
    """Build a new immutable bundle, then atomically switch the active pointer."""
    base = settings.MODEL_DIR
    bundles = base / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    temp = bundles / f".promotion-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    shutil.copytree(challenger, temp)
    if champion.exists() and same_maps:
        for model_name, source in selections.items():
            if source != "champion":
                continue
            for filename in MODEL_FILES.get(model_name, []):
                old = champion / filename
                if old.is_file():
                    shutil.copy2(old, temp / filename)
    manifest_path = temp / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_selection"] = {
        "selection_policy": "per-architecture hit_rate_at_10; compare only when model-index maps are identical",
        "same_id_maps": same_maps,
        "selected_from": selections,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "minimum_hit_rate_delta": settings.MODEL_PROMOTION_MIN_DELTA,
    }
    # Bundle identity hashes all active files except the manifest/checksum file.
    digest_parts = []
    for path in sorted(temp.iterdir()):
        if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"}:
            digest_parts.append(path.name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    manifest["bundle_id"] = hashlib.sha256(b"".join(digest_parts)).hexdigest()[:32]
    manifest["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _write_checksums(temp)

    # Verify the composed set before publishing it.
    test_registry = PortableModelRegistry(temp)
    test_registry.load()
    destination = bundles / manifest["bundle_id"]
    if destination.exists():
        shutil.rmtree(temp)
    else:
        temp.replace(destination)
    pointer_tmp = base / "ACTIVE_BUNDLE.tmp"
    pointer_tmp.write_text(manifest["bundle_id"], encoding="utf-8")
    pointer_tmp.replace(base / "ACTIVE_BUNDLE")
    return destination, manifest


def compare_and_promote(db: Session, challenger_dir: Path) -> dict:
    import pandas as pd

    challenger_registry = PortableModelRegistry(challenger_dir)
    challenger_registry.load()
    champion_dir = _bundle_dir()
    if champion_dir is None:
        challenger_metrics = evaluate_bundle_once(db, challenger_registry, persist=False)
        selections = {name: "challenger" for name in challenger_registry.ready_models if name in MODEL_FILES}
        promoted_dir, manifest = _promote_bundle(Path("/nonexistent"), challenger_dir, selections, same_maps=False)
        active_registry = PortableModelRegistry(settings.MODEL_DIR)
        active_registry.load()
        evaluate_bundle_once(db, active_registry, persist=True)
        return {"promoted": True, "reason": "No existing champion", "selections": selections,
                "bundle_id": manifest["bundle_id"], "directory": str(promoted_dir),
                "challenger_metrics": challenger_metrics}

    champion_registry = PortableModelRegistry(settings.MODEL_DIR)
    champion_registry.load()
    same_maps = _id_maps_equal(champion_registry, challenger_registry)
    old_holdout_path = champion_registry.model_dir / "holdout_sample.csv"
    new_holdout_path = challenger_registry.model_dir / "holdout_sample.csv"
    if not old_holdout_path.is_file() or not new_holdout_path.is_file():
        return {"promoted": False, "reason": "Both bundles need holdout_sample.csv for a fair comparison"}
    old_holdout = pd.read_csv(old_holdout_path)
    new_holdout = pd.read_csv(new_holdout_path)
    comparison_keys = ["source_user_id", "movielens_id"]
    old_holdout[comparison_keys] = old_holdout[comparison_keys].astype("int64")
    new_holdout[comparison_keys] = new_holdout[comparison_keys].astype("int64")
    shared_keys = old_holdout[comparison_keys].drop_duplicates().merge(
        new_holdout[comparison_keys].drop_duplicates(), on=comparison_keys, how="inner"
    )
    # Compare only users and target items represented by both model bundles.
    common_users = set(map(int, champion_registry.id_maps.get("idx_to_source_user_id", []))) & set(
        map(int, challenger_registry.id_maps.get("idx_to_source_user_id", []))
    )
    common_items = set(map(int, champion_registry.idx_to_movie)) & set(map(int, challenger_registry.idx_to_movie))
    if common_users and common_items:
        shared_keys = shared_keys[
            shared_keys["source_user_id"].isin(common_users)
            & shared_keys["movielens_id"].isin(common_items)
        ]
    if shared_keys.empty:
        return {"promoted": False, "reason": "No common held-out user/title pairs between champion and challenger"}
    common_holdout = shared_keys.merge(new_holdout, on=comparison_keys, how="left")
    challenger_metrics = evaluate_bundle_once(db, challenger_registry, persist=False,
                                               holdout_override=common_holdout)
    champion_metrics = evaluate_bundle_once(db, champion_registry, persist=False,
                                             holdout_override=common_holdout)
    selections: dict[str, str] = {}
    if same_maps:
        for model_name in MODEL_FILES:
            old_score = _hit_rate(champion_metrics, model_name)
            new_score = _hit_rate(challenger_metrics, model_name)
            if new_score is not None and (old_score is None or new_score > old_score + settings.MODEL_PROMOTION_MIN_DELTA):
                selections[model_name] = "challenger"
            else:
                selections[model_name] = "champion"
        improved = any(value == "challenger" for value in selections.values())
    else:
        old_values = [_hit_rate(champion_metrics, name) for name in MODEL_FILES]
        new_values = [_hit_rate(challenger_metrics, name) for name in MODEL_FILES]
        old_values = [value for value in old_values if value is not None]
        new_values = [value for value in new_values if value is not None]
        old_mean = sum(old_values) / len(old_values) if old_values else None
        new_mean = sum(new_values) / len(new_values) if new_values else None
        improved = new_mean is not None and (old_mean is None or new_mean > old_mean + settings.MODEL_PROMOTION_MIN_DELTA)
        selections = {name: ("challenger" if improved else "champion") for name in MODEL_FILES}
    if not improved:
        return {"promoted": False, "reason": "No challenger architecture beat its champion by the configured delta",
                "same_id_maps": same_maps, "selections": selections,
                "champion_metrics": champion_metrics, "challenger_metrics": challenger_metrics}

    promoted_dir, manifest = _promote_bundle(champion_dir, challenger_dir, selections, same_maps)
    # Benchmark the composed champion once; API processes detect the active pointer.
    active_registry = PortableModelRegistry(settings.MODEL_DIR)
    active_registry.load()
    final_metrics = evaluate_bundle_once(db, active_registry, persist=True)
    return {"promoted": True, "same_id_maps": same_maps, "selections": selections,
            "bundle_id": manifest["bundle_id"], "directory": str(promoted_dir),
            "champion_metrics": champion_metrics, "challenger_metrics": challenger_metrics,
            "promoted_metrics": final_metrics}
