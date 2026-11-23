#!/usr/bin/env python3
"""Compatibility entry point for the controlled TMDB metadata backfill."""
from pathlib import Path
import sys

BACKEND_SCRIPTS = Path(__file__).resolve().parent / "backend" / "scripts"
sys.path.insert(0, str(BACKEND_SCRIPTS))

from backfill_tmdb_metadata import main  # noqa: E402

if __name__ == "__main__":
    main()
