"""Paths. The GRID data lives in a sibling clone and is never copied into this repo."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Licensed GRID data: read in place from the starter repo clone beside this project.
DATA_DIR = Path(os.environ.get("STL_DATA_DIR", REPO_ROOT.parent / "stl-hackathon-2026-grid-starter")).resolve()

# Everything derived from the data goes under data/, which is gitignored.
WORK_DIR = REPO_ROOT / "data"
DB_PATH = Path(os.environ.get("DRAFT_DB", WORK_DIR / "draft.duckdb"))
