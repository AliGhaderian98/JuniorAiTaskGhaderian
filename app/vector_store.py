"""Store and search chunks in a Chroma collection.

Embeddings are always computed by our Embedder and passed in explicitly
(embedding_function=None), so Chroma never uses a second, hidden model.
"""

import chromadb
from pydantic import BaseModel

from app.documents import Chunk


class SearchResult(BaseModel):
    chunk: Chunk
    score: float  # cosine similarity: 1.0 = same direction, around 0 = unrelated


def get_collection(client: chromadb.ClientAPI, name: str) -> chromadb.Collection:
    return client.get_or_create_collection(
        name, embedding_function=None, configuration={"hnsw": {"space": "cosine"}}
    )


def add_chunks(collection: chromadb.Collection, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    collection.add(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[{
            "entity_name": c.entity_name,
            "chunk_type": c.chunk_type,
            "source_path": c.source_path,
            # Chroma rejects empty lists in metadata, so store a placeholder.
            "related_entities": c.related_entities or [""],
        } for c in chunks],
    )


def to_chunk(chunk_id: str, text: str, metadata: dict) -> Chunk:
    return Chunk(
        id=chunk_id,
        entity_name=metadata["entity_name"],
        chunk_type=metadata["chunk_type"],
        source_path=metadata["source_path"],
        related_entities=[e for e in metadata["related_entities"] if e],
        text=text,
    )


def search(collection: chromadb.Collection, query_embedding: list[float], top_k: int) -> list[SearchResult]:
    """Return the top_k most similar chunks, best first."""
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    return [
        SearchResult(chunk=to_chunk(chunk_id, text, metadata), score=1.0 - distance)
        for chunk_id, text, metadata, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]


def get_chunks_for_entity(collection: chromadb.Collection, entity_name: str, chunk_types: list[str]) -> list[Chunk]:
    """Fetch chunks by metadata (no similarity search), in the order of chunk_types."""
    result = collection.get(
        where={"$and": [{"entity_name": entity_name}, {"chunk_type": {"$in": chunk_types}}]},
        include=["documents", "metadatas"],
    )
    chunks = [to_chunk(i, t, m) for i, t, m in zip(result["ids"], result["documents"], result["metadatas"])]
    return sorted(chunks, key=lambda c: (chunk_types.index(c.chunk_type), c.id))
