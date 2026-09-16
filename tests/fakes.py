"""Test doubles shared by the retrieval tests."""

import math
import re
import uuid

import chromadb

from app.vector_store import get_collection

VOCABULARY = ["account", "contact", "branch", "bank", "loan", "customer", "relate", "address", "weather"]


class FakeEmbedder:
    """Deterministic 'embedding': one dimension per vocabulary word.

    Texts that share words get similar vectors. Good enough to test the
    retrieval logic without downloading a real model.
    """

    def _embed(self, text: str) -> list[float]:
        words = re.findall(r"[a-z]+", text.lower())
        vector = [float(sum(w.startswith(v) for w in words)) for v in VOCABULARY]
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector] if norm else vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def new_collection() -> chromadb.Collection:
    # In-memory clients share state within a process, so use a unique name per test.
    return get_collection(chromadb.EphemeralClient(), f"test-{uuid.uuid4().hex}")
