"""Build the Chroma index from the pinned CDM files.

Usage:  python scripts/build_index.py
"""

import sys
import time
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.cdm_loader import download_cdm_files
from app.cdm_parser import load_cdm_entities
from app.documents import build_chunks
from app.embeddings import Embedder
from app.vector_store import add_chunks, get_collection


def main() -> None:
    start = time.time()
    downloaded = download_cdm_files(config.CDM_DATA_DIR)
    print(f"CDM files downloaded: {downloaded} (others already present)")

    entities = load_cdm_entities(config.CDM_DATA_DIR)
    chunks = build_chunks(entities)
    print(f"Entities: {len(entities)}, chunks: {len(chunks)}")

    embedder = Embedder(config.EMBEDDING_MODEL)
    too_long = [c.id for c in chunks if embedder.count_tokens(c.text) > config.EMBEDDING_MAX_TOKENS]
    if too_long:
        raise SystemExit(f"Chunks longer than {config.EMBEDDING_MAX_TOKENS} tokens would be truncated: {too_long}")

    embeddings = embedder.embed_documents([c.text for c in chunks])

    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    if config.COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(config.COLLECTION_NAME)  # full rebuild, no stale chunks
    collection = get_collection(client, config.COLLECTION_NAME)
    add_chunks(collection, chunks, embeddings)

    print(f"Indexed {collection.count()} chunks into {config.CHROMA_DIR} in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
