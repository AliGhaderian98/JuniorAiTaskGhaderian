"""Small retrieval check against the real index (no LLM involved).

Usage:  python scripts/evaluate_retrieval.py

For each question we list the entities that must appear in the retrieved
chunks. Off-topic questions must retrieve nothing. This is a sanity check
on a handful of questions, not a benchmark.
"""

import sys
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.embeddings import Embedder  # noqa: E402
from app.retriever import Retriever  # noqa: E402
from app.vector_store import get_collection  # noqa: E402

IN_SCOPE = [
    ("What are the core attributes of the Account entity?", {"Account"}),
    ("How does a Contact relate to an Account?", {"Contact", "Account"}),
    ("How does Contact relate to Organization?", {"Contact", "Organization"}),
    ("Which entity stores the products a customer holds with the bank?", {"FinancialProduct"}),
    ("Where do I find the risk level and identification documents of a customer?", {"KYC"}),
    ("What information is kept about assets pledged to secure a loan?", {"Collateral"}),
    ("Which entity represents a potential customer or referral?", {"Lead"}),
    ("How is a branch connected to a bank?", {"Branch", "Bank"}),
    ("What is the credit limit set up for a corporate client?", {"Limit"}),
    ("Which entities are linked to a business unit?", {"BusinessUnit"}),
    ("What currency information exists in the model?", {"Currency"}),
    ("What does a mortgage application process entity contain?", {"MortgageApplication"}),
]
OFF_TOPIC = [
    "What is the capital of France?",
    "How do I bake a chocolate cake?",
    "Give me a summary of the latest football results",
    "How do I install Python on Windows?",
    "Translate 'good morning' into Spanish",
    "What is the square root of 144?",
]


def main() -> None:
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    collection = get_collection(client, config.COLLECTION_NAME)
    retriever = Retriever(collection, Embedder(config.EMBEDDING_MODEL),
                          config.RETRIEVAL_TOP_K, config.RETRIEVAL_MIN_SCORE)

    passed = 0
    for question, expected in IN_SCOPE:
        results = retriever.retrieve(question)
        found = {r.chunk.entity_name for r in results}
        ok = expected <= found
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {question}")
        print(f"      expected={sorted(expected)} chunks={len(results)} "
              f"retrieved={[r.chunk.id + ('' if r.score is None else f' ({r.score:.2f})') for r in results]}")

    for question in OFF_TOPIC:
        results = retriever.retrieve(question)
        ok = not results
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  [off-topic] {question} -> {[r.chunk.id for r in results]}")

    total = len(IN_SCOPE) + len(OFF_TOPIC)
    print(f"\n{passed}/{total} checks passed (top_k={config.RETRIEVAL_TOP_K}, min_score={config.RETRIEVAL_MIN_SCORE})")


if __name__ == "__main__":
    main()
