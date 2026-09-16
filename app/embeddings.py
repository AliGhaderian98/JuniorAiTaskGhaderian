"""Local text embeddings with sentence-transformers."""

# Recommended by the BGE model card for short questions searching longer passages.
# Measured on our data: it widened the gap between in-scope and off-topic scores.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class Embedder:
    """Turns text into normalized vectors (length 1), so cosine similarity works directly.

    Tests replace this class with a small fake that has the same two methods.
    """

    def __init__(self, model_name: str):
        # Imported here because importing it loads torch (~15 s). Modules that
        # only need the Embedder type, and the unit tests, don't pay that cost.
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode_document(texts, normalize_embeddings=True, batch_size=32)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode_query([text], prompt=QUERY_INSTRUCTION, normalize_embeddings=True)[0]
        return vector.tolist()

    def count_tokens(self, text: str) -> int:
        return len(self.model.tokenizer(text)["input_ids"])
