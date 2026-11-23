#!/usr/bin/env python3
"""Train the canonical portable model bundle and optionally import it into the backend.

The training itself executes the standalone `training/train_all_models.ipynb`
notebook, so it works without importing any app/ modules. It never drops tables.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-users", default="10000", help="sample count or 'none'")
    parser.add_argument("--min-movie-ratings", type=int, default=20)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "training")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--no-import", action="store_true", help="only create the portable bundle")
    args = parser.parse_args()
    if args.min_movie_ratings < 1:
        parser.error("--min-movie-ratings must be >= 1")

    output_dir = args.output_dir or (ROOT / "artifacts" / "training-runs" / uuid.uuid4().hex)
    output_dir = output_dir.resolve()
    runner = ROOT / "scripts" / "run_training_notebook.py"
    command = [sys.executable, str(runner), "--output-dir", str(output_dir),
               "--data-dir", str(args.data_dir.resolve()), "--target-users", str(args.target_users),
               "--min-movie-ratings", str(args.min_movie_ratings)]
    subprocess.run(command, cwd=ROOT, check=True)

    bundle_zip = output_dir.parent / f"{output_dir.name}.zip"
    if not args.no_import:
        importer = ROOT / "scripts" / "import_colab_bundle.py"
        subprocess.run([sys.executable, str(importer), "--bundle", str(bundle_zip)], cwd=ROOT, check=True)
    print("Training output:", output_dir)
    print("Portable bundle:", bundle_zip)
    if args.no_import:
        print("Bundle not imported. Import with scripts/import_colab_bundle.py --bundle <bundle.zip>.")


if __name__ == "__main__":
    main()
