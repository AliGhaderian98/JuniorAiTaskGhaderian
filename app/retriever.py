"""Find the CDM chunks that are relevant for a question.

Two simple steps, combined:
1. Entity name matching: if the question names an indexed entity ("Account"),
   its overview and referenced_by chunks are always included. Pure vector search
   tends to rank attribute chunks above the overview that lists relationships.
2. Vector search: the top_k most similar chunks with a cosine score >= min_score.
   This finds entities the user describes without naming them ("collateral").

If both steps return nothing, the result is empty and the caller should abstain.
"""

import re

import chromadb
from pydantic import BaseModel

from app.documents import Chunk
from app.embeddings import Embedder
from app.vector_store import get_chunks_for_entity, search

MAX_NAMED_ENTITIES = 3
NAMED_ENTITY_CHUNK_TYPES = ["overview", "referenced_by"]


class RetrievedChunk(BaseModel):
    chunk: Chunk
    match: str  # "entity_name" or "semantic"
    score: float | None = None  # only set for semantic matches


def entity_name_pattern(name: str) -> re.Pattern:
    """'FinancialProduct' matches 'financial product', 'FinancialProduct' and 'financial products'."""
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)
    return re.compile(r"\b" + r"\s*".join(words) + r"s?\b", re.IGNORECASE)


def find_entity_names(question: str, known_names: list[str]) -> list[str]:
    """Entity names mentioned in the question, in order of appearance.

    Longer names are checked first and their matched text is removed, so
    "contact onboarding from prospect" does not also count as "Contact".
    """
    remaining = question
    found = []  # (position, name)
    for name in sorted(known_names, key=len, reverse=True):
        match = entity_name_pattern(name).search(remaining)
        if match:
            found.append((match.start(), name))
            remaining = remaining[:match.start()] + " " * len(match.group()) + remaining[match.end():]
    return [name for _, name in sorted(found)]


class Retriever:
    def __init__(self, collection: chromadb.Collection, embedder: Embedder, top_k: int, min_score: float):
        self.collection = collection
        self.embedder = embedder
        self.top_k = top_k
        self.min_score = min_score
        overviews = collection.get(where={"chunk_type": "overview"}, include=["metadatas"])
        self.entity_names = sorted(m["entity_name"] for m in overviews["metadatas"])

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        if not question.strip():
            raise ValueError("Question must not be empty")

        results: dict[str, RetrievedChunk] = {}  # chunk id -> result, keeps insertion order

        for name in find_entity_names(question, self.entity_names)[:MAX_NAMED_ENTITIES]:
            for chunk in get_chunks_for_entity(self.collection, name, NAMED_ENTITY_CHUNK_TYPES):
                results[chunk.id] = RetrievedChunk(chunk=chunk, match="entity_name")

        query_embedding = self.embedder.embed_query(question)
        for hit in search(self.collection, query_embedding, self.top_k):
            if hit.score >= self.min_score and hit.chunk.id not in results:
                results[hit.chunk.id] = RetrievedChunk(chunk=hit.chunk, match="semantic", score=hit.score)

        return list(results.values())
