"""API tests with a fake RAG service (no index, no model, no OpenAI).

TestClient is used without "with", so the lifespan (which loads the real
index and model) does not run. The dependency is overridden instead.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.documents import Chunk
from app.main import app, get_rag_service
from app.rag_service import AskResponse, LLMUnavailableError
from app.retriever import RetrievedChunk

CHUNK = Chunk(id="Account:overview", entity_name="Account", chunk_type="overview",
              source_path="banking/Account.cdm.json", text="Entity: Account")


class FakeRagService:
    def __init__(self, error=None):
        self.error = error
        self.model = "test-model"
        self.client = object()
        self.retriever = SimpleNamespace(
            collection=SimpleNamespace(count=lambda: 168),
            entity_names=["Account", "Contact"],
            retrieve=lambda question: [RetrievedChunk(chunk=CHUNK, match="entity_name")],
        )
        self.questions = []

    def answer(self, question):
        self.questions.append(question)
        if self.error:
            raise self.error
        return AskResponse(question=question, answer="Account has ...", retrieved_entities=["Account"], sources=[])


@pytest.fixture
def fake_service():
    service = FakeRagService()
    app.dependency_overrides[get_rag_service] = lambda: service
    yield service
    app.dependency_overrides.clear()


client = TestClient(app)


def test_health_reports_index_and_llm_status(fake_service):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "indexed_chunks": 168, "indexed_entities": 2,
                               "llm_model": "test-model", "llm_configured": True}


def test_ask_returns_answer_and_strips_whitespace(fake_service):
    response = client.post("/ask", json={"question": "  What is an Account?  "})

    assert response.status_code == 200
    assert response.json()["answer"] == "Account has ..."
    assert fake_service.questions == ["What is an Account?"]


@pytest.mark.parametrize("question", ["", "   ", "x" * 501])
def test_ask_rejects_empty_or_too_long_questions(fake_service, question):
    assert client.post("/ask", json={"question": question}).status_code == 422


def test_ask_returns_503_when_llm_is_unavailable(fake_service):
    fake_service.error = LLMUnavailableError("OPENAI_API_KEY is not set, so no answer can be generated.")
    response = client.post("/ask", json={"question": "What is an Account?"})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_retrieve_returns_chunks_without_llm(fake_service):
    response = client.post("/retrieve", json={"question": "What is an Account?"})

    assert response.status_code == 200
    body = response.json()
    assert body["retrieved_entities"] == ["Account"]
    assert body["chunks"][0]["chunk"]["id"] == "Account:overview"
    assert fake_service.questions == []  # the LLM path was not used
