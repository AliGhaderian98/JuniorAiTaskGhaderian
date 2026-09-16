"""Paths and settings. Values can be overridden with environment variables."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Local copy of the pinned CDM files (mirrors the repo's schemaDocuments/ folder).
CDM_DATA_DIR = Path(os.getenv("CDM_DATA_DIR", PROJECT_ROOT / "data" / "cdm"))
