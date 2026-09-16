import pytest

from app.documents import Chunk
from app.vector_store import add_chunks, get_chunks_for_entity, search
from tests.fakes import FakeEmbedder, new_collection

CHUNKS = [
    Chunk(id="Account:overview", entity_name="Account", chunk_type="overview",
          source_path="banking/Account.cdm.json", related_entities=["Contact"],
          text="Entity: Account. A company that is a customer of the bank."),
    Chunk(id="Account:attributes:1", entity_name="Account", chunk_type="attributes",
          source_path="banking/Account.cdm.json", text="Entity: Account. Attributes: accountId, address"),
    Chunk(id="Branch:overview", entity_name="Branch", chunk_type="overview",
          source_path="banking/Branch.cdm.json", text="Entity: Branch. Location of a bank branch."),
]


@pytest.fixture
def collection():
    collection = new_collection()
    add_chunks(collection, CHUNKS, FakeEmbedder().embed_documents([c.text for c in CHUNKS]))
    return collection


def test_search_returns_most_similar_chunk_first_with_cosine_score(collection):
    results = search(collection, FakeEmbedder().embed_query("branch"), top_k=2)

    assert results[0].chunk.id == "Branch:overview"
    assert results[0].score > results[1].score
    assert 0.0 <= results[1].score <= results[0].score <= 1.0 + 1e-6


def test_search_restores_chunk_metadata(collection):
    result = search(collection, FakeEmbedder().embed_query("account customer"), top_k=1)[0]

    assert result.chunk == CHUNKS[0]  # all fields, including related_entities


def test_empty_related_entities_survive_round_trip(collection):
    chunk = get_chunks_for_entity(collection, "Branch", ["overview"])[0]
    assert chunk.related_entities == []


def test_get_chunks_for_entity_filters_by_name_and_type_in_given_order(collection):
    chunks = get_chunks_for_entity(collection, "Account", ["overview", "attributes"])
    assert [c.id for c in chunks] == ["Account:overview", "Account:attributes:1"]

    assert get_chunks_for_entity(collection, "Account", ["referenced_by"]) == []
    assert get_chunks_for_entity(collection, "Unknown", ["overview"]) == []
