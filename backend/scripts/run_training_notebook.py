#!/usr/bin/env python3
"""Execute the self-contained Colab training notebook on a local training host.

The notebook is the canonical training implementation. This runner deliberately
strips only IPython line magics (the dependency-install cell); all model training
code is executed unchanged and does not import the backend app package.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "training" / "train_all_models.ipynb"


def safe_extract_bundle(bundle_path: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(bundle_path) as archive:
        for info in archive.infolist():
            candidate = (destination / info.filename).resolve()
            if candidate != root and root not in candidate.parents:
                raise ValueError(f"Unsafe notebook artifact path: {info.filename}")
        archive.extractall(destination)
    manifests = list(destination.rglob("manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError("Training notebook did not produce exactly one manifest.json")
    return manifests[0].parent


def execute_notebook(output_dir: Path, data_dir: Path, target_users: str, min_movie_ratings: int) -> Path:
    if not NOTEBOOK.is_file():
        raise FileNotFoundError(NOTEBOOK)
    output_dir = output_dir.resolve()
    data_dir = data_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    bundle_zip = output_dir.parent / f"{output_dir.name}.zip"
    env = os.environ.copy()
    env.update({
        "CINERANK_TRAIN_OUTPUT_DIR": str(output_dir),
        "CINERANK_TRAIN_DATA_DIR": str(data_dir),
        "CINERANK_TRAIN_BUNDLE_ZIP": str(bundle_zip),
        "CINERANK_TARGET_USERS": target_users,
        "CINERANK_MIN_MOVIE_RATINGS": str(min_movie_ratings),
    })
    previous = {key: os.environ.get(key) for key in (
        "CINERANK_TRAIN_OUTPUT_DIR", "CINERANK_TRAIN_DATA_DIR",
        "CINERANK_TRAIN_BUNDLE_ZIP", "CINERANK_TARGET_USERS",
        "CINERANK_MIN_MOVIE_RATINGS",
    )}
    os.environ.update({key: env[key] for key in previous})

    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    namespace = {
        "__name__": "__cinerank_notebook__",
        "__file__": str(NOTEBOOK),
        "display": lambda value: print(value.to_string(index=False) if hasattr(value, "to_string") else value),
    }
    try:
        for index, cell in enumerate(notebook.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            # Notebook-only install magic is intentionally not executed here.
            source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("%"))
            if not source.strip():
                continue
            print(f"\n[Notebook] Executing code cell {index}", flush=True)
            exec(compile(source, f"{NOTEBOOK.name}:cell-{index}", "exec"), namespace)
        if not bundle_zip.is_file():
            raise RuntimeError("Notebook execution completed without creating its bundle ZIP")
    except Exception:
        traceback.print_exc()
        raise
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    extracted = safe_extract_bundle(bundle_zip, output_dir.parent / f"{output_dir.name}-verified")
    print("Verified portable bundle at:", extracted)
    print("Archive at:", bundle_zip)
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "training")
    parser.add_argument("--target-users", default=os.getenv("CINERANK_TARGET_USERS", "10000"),
                        help="Integer sample size or 'none' for all MovieLens users")
    parser.add_argument("--min-movie-ratings", type=int, default=int(os.getenv("CINERANK_MIN_MOVIE_RATINGS", "20")))
    args = parser.parse_args()
    if args.min_movie_ratings < 1:
        parser.error("--min-movie-ratings must be >= 1")
    execute_notebook(args.output_dir, args.data_dir, str(args.target_users), args.min_movie_ratings)


if __name__ == "__main__":
    main()
