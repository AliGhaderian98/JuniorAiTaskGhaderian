"""Paths and settings. Values can be overridden with environment variables."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Local copy of the pinned CDM files (mirrors the repo's schemaDocuments/ folder).
CDM_DATA_DIR = Path(os.getenv("CDM_DATA_DIR", PROJECT_ROOT / "data" / "cdm"))

# Embedding model (see docs/IMPLEMENTATION_PLAN.md for why this model).
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_MAX_TOKENS = 512

# Persistent Chroma index, created by scripts/build_index.py.
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", PROJECT_ROOT / "chroma_db"))
COLLECTION_NAME = "cdm_chunks"
