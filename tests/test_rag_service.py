from types import SimpleNamespace

import httpx2
import openai
import pytest

from app.documents import Chunk
from app.rag_service import NO_CONTEXT_ANSWER, SYSTEM_PROMPT, LLMUnavailableError, RagService, build_context
from app.retriever import RetrievedChunk


def retrieved(entity, chunk_type, match="entity_name", score=None):
    chunk = Chunk(id=f"{entity}:{chunk_type}", entity_name=entity, chunk_type=chunk_type,
                  source_path=f"banking/{entity}.cdm.json", text=f"Entity: {entity} ({chunk_type})")
    return RetrievedChunk(chunk=chunk, match=match, score=score)


RESULTS = [
    retrieved("Contact", "overview"),
    retrieved("Account", "overview"),
    retrieved("Contact", "attributes", match="semantic", score=0.71),
]


class FakeRetriever:
    def __init__(self, results):
        self.results = results

    def retrieve(self, question):
        return self.results


class FakeOpenAIClient:
    """Mimics client.responses.create(...) and records the call."""

    def __init__(self, output_text="Contact links to Account via parentCustomerId [1].", error=None):
        self.calls = []
        self.output_text = output_text
        self.error = error
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(output_text=self.output_text)


def test_no_retrieved_context_abstains_without_calling_llm():
    client = FakeOpenAIClient()
    response = RagService(FakeRetriever([]), client, model="test-model").answer("What is the capital of France?")

    assert response.answer == NO_CONTEXT_ANSWER
    assert response.sources == []
    assert response.retrieved_entities == []
    assert client.calls == []


def test_context_blocks_are_numbered_and_labeled_with_source():
    context = build_context(RESULTS)

    assert context.startswith("[1] entity: Contact | chunk: overview | source: banking/Contact.cdm.json\n"
                              "Entity: Contact (overview)")
    assert "[3] entity: Contact | chunk: attributes | source: banking/Contact.cdm.json" in context


def test_llm_receives_grounding_instructions_context_and_question():
    client = FakeOpenAIClient()
    RagService(FakeRetriever(RESULTS), client, model="test-model").answer("How does Contact relate to Account?")

    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["instructions"] == SYSTEM_PROMPT
    assert call["temperature"] == 0
    assert build_context(RESULTS) in call["input"]
    assert call["input"].endswith("Question: How does Contact relate to Account?")


def test_response_contains_answer_sources_and_unique_entities():
    response = RagService(FakeRetriever(RESULTS), FakeOpenAIClient(), model="m").answer("q")

    assert response.answer == "Contact links to Account via parentCustomerId [1]."
    assert response.retrieved_entities == ["Contact", "Account"]
    assert [(s.entity_name, s.chunk_type, s.match, s.score) for s in response.sources] == [
        ("Contact", "overview", "entity_name", None),
        ("Account", "overview", "entity_name", None),
        ("Contact", "attributes", "semantic", 0.71),
    ]


def test_missing_llm_client_raises_clear_error():
    with pytest.raises(LLMUnavailableError, match="OPENAI_API_KEY"):
        RagService(FakeRetriever(RESULTS), None, model="m").answer("q")


def test_openai_api_error_is_converted():
    error = openai.APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com/v1/responses"))
    with pytest.raises(LLMUnavailableError):
        RagService(FakeRetriever(RESULTS), FakeOpenAIClient(error=error), model="m").answer("q")


def test_system_prompt_contains_the_key_grounding_rules():
    prompt = SYSTEM_PROMPT.lower()
    assert "only" in prompt and "context" in prompt
    assert "do not invent" in prompt
    assert "not contain enough information" in prompt
