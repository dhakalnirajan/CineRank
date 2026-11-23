import hashlib
import json
from pathlib import Path

import numpy as np

from app.ml.portable_models import PortableModelRegistry


def _write_checksums(directory: Path) -> None:
    lines = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (directory / "SHA256SUMS").write_text("".join(lines))


def _make_bundle(model_dir: Path, bundle_id: str) -> Path:
    bundle = model_dir / "bundles" / bundle_id
    bundle.mkdir(parents=True)
    np.savez(bundle / "rec-pop-v1.npz", scores=np.array([0.25, 0.75], dtype=np.float32))
    (bundle / "manifest.json").write_text(json.dumps({
        "bundle_format": "cinerank-portable-v1",
        "bundle_id": bundle_id,
        "n_users": 1,
        "n_items": 2,
    }))
    (bundle / "id-maps-v1.json").write_text(json.dumps({
        "schema_version": 2,
        "matrix_orientation": "users_by_items",
        "idx_to_source_user_id": [1],
        "idx_to_movielens_movie_id": [10, 20],
        "source_user_id_to_idx": {"1": 0},
        "movielens_movie_id_to_idx": {"10": 0, "20": 1},
    }))
    _write_checksums(bundle)
    return bundle


def test_missing_pointer_recovers_single_valid_bundle(tmp_path):
    bundle = _make_bundle(tmp_path, "a" * 32)

    registry = PortableModelRegistry(tmp_path)
    registry.load()

    assert (tmp_path / "ACTIVE_BUNDLE").read_text() == bundle.name
    assert registry.model_dir == bundle
    assert registry.is_ready
    assert registry.ready_models == {"popularity"}


def test_missing_pointer_does_not_guess_between_bundles(tmp_path):
    _make_bundle(tmp_path, "a" * 32)
    _make_bundle(tmp_path, "b" * 32)

    registry = PortableModelRegistry(tmp_path)
    registry.load()

    assert not (tmp_path / "ACTIVE_BUNDLE").exists()
    assert not registry.is_ready
