from app.documents import ATTRIBUTES_PER_CHUNK, build_attribute_chunks, build_chunks, build_overview_chunk
from app.models import Attribute, Entity, Relationship


def make_entity(attribute_count=3, relationships=(), referenced_by=()):
    return Entity(
        name="Contact",
        description="A person.",
        source_path="banking/Contact.cdm.json",
        inheritance_chain=["base/Contact.cdm.json"],
        attributes=[Attribute(name=f"attr{i}", data_type="string", description=f"Attribute {i}.",
                              source_path="banking/Contact.cdm.json") for i in range(attribute_count)],
        relationships=list(relationships),
        referenced_by=list(referenced_by),
    )


PARENT_CUSTOMER = Relationship(from_entity="Contact", from_attribute="parentCustomerId",
                               to_entity="Account", to_attribute="accountId")
CREATED_BY = Relationship(from_entity="Contact", from_attribute="createdBy",
                          to_entity="User", to_attribute="systemUserId")
KYC_CONTACT = Relationship(from_entity="KYC", from_attribute="primaryContactId",
                           to_entity="Contact", to_attribute="contactId")


def test_overview_lists_business_relationships_explicitly():
    chunk = build_overview_chunk(make_entity(relationships=[PARENT_CUSTOMER, CREATED_BY]))

    assert chunk.id == "Contact:overview"
    assert "Entity: Contact" in chunk.text
    assert "- Contact.parentCustomerId -> Account.accountId" in chunk.text
    assert "Inherits from: base/Contact.cdm.json" in chunk.text
    assert chunk.related_entities == ["Account"]


def test_system_relationships_are_summarized_separately():
    chunk = build_overview_chunk(make_entity(relationships=[CREATED_BY]))

    assert "- Contact.createdBy" not in chunk.text
    assert "System ownership/audit relationships: createdBy -> User" in chunk.text
    assert "Relationships from Contact to other entities:\n- none" in chunk.text
    assert chunk.related_entities == []


def test_incoming_relationships_get_their_own_chunk():
    chunks = build_chunks([make_entity(referenced_by=[KYC_CONTACT])])
    referenced_by = next(c for c in chunks if c.chunk_type == "referenced_by")

    assert referenced_by.id == "Contact:referenced_by"
    assert "- KYC.primaryContactId -> Contact.contactId" in referenced_by.text
    assert referenced_by.related_entities == ["KYC"]


def test_no_referenced_by_chunk_without_incoming_relationships():
    chunks = build_chunks([make_entity()])
    assert [c.chunk_type for c in chunks] == ["overview", "attributes"]


def test_attributes_are_split_into_fixed_size_chunks_with_entity_header():
    chunks = build_attribute_chunks(make_entity(attribute_count=ATTRIBUTES_PER_CHUNK + 1))

    assert [c.id for c in chunks] == ["Contact:attributes:1", "Contact:attributes:2"]
    assert all(c.text.startswith("Entity: Contact\nAttributes (part") for c in chunks)
    assert "- attr0 (string): Attribute 0." in chunks[0].text
    assert chunks[1].text.count("\n- ") == 1


def test_entity_without_attributes_has_no_attribute_chunks():
    assert build_attribute_chunks(make_entity(attribute_count=0)) == []
