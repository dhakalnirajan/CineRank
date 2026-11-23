"""Versioned, read-only inference adapter for CineRank v2 model releases."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from app.core.config import settings
from app.ml.cinerank_inference import FastRecommender


class ProductionModelRegistry:
    """Own one immutable, checksum-verified inference release per API process."""

    def __init__(self, release_dir: Path | None = None):
        self.release_dir = Path(release_dir or settings.MODEL_RELEASE_DIR)
        self.engine = FastRecommender(
            str(self.release_dir),
            use_gpu=settings.MODEL_INFERENCE_USE_GPU,
            require_gpu=settings.MODEL_INFERENCE_REQUIRE_GPU,
            cache_size=settings.MODEL_INFERENCE_CACHE_SIZE,
            verify_checksums=True,
            require_complete=True,
            warmup=True,
        )
        self.manifest = self.engine.release.manifest
        self.release_id = str(self.manifest.get("release_id", "unknown"))
        self.ready_models = {
            name for name, item in self.manifest.get("models", {}).items()
            if item.get("status") == "available" and item.get("production_enabled") is True
        }

    def recommend_by_provider_ids(
        self,
        history: Sequence[tuple[int, float]],
        *,
        k: int,
        exclude_provider_ids: Iterable[int] | None = None,
    ) -> dict:
        """Score a user's MovieLens provider IDs and map back to provider IDs."""
        return self.engine.recommend_by_provider_ids(
            history,
            k=k,
            exclude_provider_ids=list(exclude_provider_ids or []),
        )

    def similar_by_provider_id(
        self,
        provider_id: int,
        *,
        k: int,
        exclude_provider_ids: Iterable[int] | None = None,
    ) -> dict:
        """Return semantically similar provider titles from the active release."""
        return self.engine.similar_by_provider_id(
            provider_id,
            k=k,
            exclude_provider_ids=list(exclude_provider_ids or []),
        )

    def close(self) -> None:
        self.engine.close()
