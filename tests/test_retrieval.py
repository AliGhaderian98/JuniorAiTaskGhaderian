import pytest

from app.documents import Chunk
from app.retriever import Retriever, find_entity_names
from app.vector_store import add_chunks
from tests.fakes import FakeEmbedder, new_collection

KNOWN_NAMES = ["Account", "Contact", "Bank", "Branch", "FinancialProduct",
               "ContactOnboardingFromProspect", "Organization"]


# --- entity name matching --------------------------------------------------------

def test_finds_entity_names_case_insensitive_and_plural():
    assert find_entity_names("list all ACCOUNTS and contacts", KNOWN_NAMES) == ["Account", "Contact"]


def test_finds_camel_case_names_written_with_spaces():
    assert find_entity_names("What is a financial product?", KNOWN_NAMES) == ["FinancialProduct"]
    assert find_entity_names("What is a FinancialProduct?", KNOWN_NAMES) == ["FinancialProduct"]


def test_longest_entity_name_wins_over_contained_shorter_name():
    question = "What does Contact Onboarding From Prospect contain?"
    assert find_entity_names(question, KNOWN_NAMES) == ["ContactOnboardingFromProspect"]


def test_does_not_match_inside_other_words():
    assert find_entity_names("Tell me about online banking and bankers", KNOWN_NAMES) == []


def test_names_are_returned_in_order_of_appearance():
    assert find_entity_names("How does Organization relate to Contact?", KNOWN_NAMES) == ["Organization", "Contact"]


# --- retrieval -----------------------------------------------------------------

def chunk(entity, chunk_type, text, number=None):
    chunk_id = f"{entity}:{chunk_type}" + (f":{number}" if number else "")
    return Chunk(id=chunk_id, entity_name=entity, chunk_type=chunk_type,
                 source_path=f"banking/{entity}.cdm.json", text=text)


CHUNKS = [
    chunk("Account", "overview", "Entity: Account. Relationships: Account.primaryContactId -> Contact"),
    chunk("Account", "referenced_by", "Entity: Account. Contact.parentCustomerId -> Account"),
    chunk("Account", "attributes", "Entity: Account attributes: address, account number", 1),
    chunk("Contact", "overview", "Entity: Contact. Relationships: Contact.parentCustomerId -> Account"),
    chunk("Contact", "attributes", "Entity: Contact attributes: contact address", 1),
    chunk("Branch", "overview", "Entity: Branch. Location of a bank branch."),
    chunk("FinancialProduct", "overview", "Entity: FinancialProduct. Loan held by a customer."),
]


def make_retriever(min_score):
    collection = new_collection()
    embedder = FakeEmbedder()
    add_chunks(collection, CHUNKS, embedder.embed_documents([c.text for c in CHUNKS]))
    return Retriever(collection, embedder, top_k=3, min_score=min_score)


@pytest.fixture
def retriever():
    return make_retriever(min_score=0.6)


def ids(results):
    return [r.chunk.id for r in results]


def test_entity_names_are_loaded_from_the_index(retriever):
    assert retriever.entity_names == ["Account", "Branch", "Contact", "FinancialProduct"]


def test_named_entity_overview_is_always_included_first(retriever):
    results = retriever.retrieve("What are the attributes of Account?")

    assert ids(results)[:2] == ["Account:overview", "Account:referenced_by"]
    assert results[0].match == "entity_name"
    assert results[0].score is None


def test_relationship_question_includes_both_entities(retriever):
    results = retriever.retrieve("How does a Contact relate to an Account?")

    assert "Contact:overview" in ids(results)
    assert "Account:overview" in ids(results)
    assert "Account:referenced_by" in ids(results)


def test_semantic_search_finds_entity_that_is_not_named(retriever):
    results = retriever.retrieve("Which record holds a customer loan?")

    assert ids(results)[0] == "FinancialProduct:overview"
    assert results[0].match == "semantic"
    assert results[0].score >= 0.6


def test_chunks_are_not_duplicated(retriever):
    results = retriever.retrieve("account")  # name match and semantic match hit the same chunks
    assert len(ids(results)) == len(set(ids(results)))


def test_off_topic_question_returns_no_context(retriever):
    assert retriever.retrieve("What will the weather be like tomorrow?") == []


def test_min_score_decides_whether_a_weak_semantic_match_is_kept():
    # "bank loan" names no indexed entity. With the fake embedder its best match,
    # FinancialProduct:overview (words "loan", "customer"), has cosine score 0.5.
    assert make_retriever(min_score=0.6).retrieve("bank loan") == []

    results = make_retriever(min_score=0.4).retrieve("bank loan")
    assert ids(results)[0] == "FinancialProduct:overview"
    assert results[0].score == pytest.approx(0.5, abs=1e-3)


def test_at_most_three_named_entities_are_expanded(retriever):
    results = retriever.retrieve("Account, Contact, Branch and FinancialProduct")
    named = {r.chunk.entity_name for r in results if r.match == "entity_name"}
    assert named == {"Account", "Contact", "Branch"}


def test_empty_question_is_rejected(retriever):
    with pytest.raises(ValueError):
        retriever.retrieve("   ")


def test_matches_acronym_and_name_with_digits():
    names = ["KYC", "Company360", "Customer360Person"]
    assert find_entity_names("What does the kyc entity store?", names) == ["KYC"]
    assert find_entity_names("Explain company 360 and Customer360Person", names) == ["Company360", "Customer360Person"]
