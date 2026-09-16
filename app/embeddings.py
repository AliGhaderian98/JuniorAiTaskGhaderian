"""Local text embeddings with sentence-transformers."""

from sentence_transformers import SentenceTransformer


class Embedder:
    """Turns text into normalized vectors (length 1), so cosine similarity works directly.

    Tests replace this class with a small fake that has the same two methods.
    """

    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name, device="cpu")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode_document(texts, normalize_embeddings=True, batch_size=32)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode_query([text], normalize_embeddings=True)[0].tolist()

    def count_tokens(self, text: str) -> int:
        return len(self.model.tokenizer(text)["input_ids"])
