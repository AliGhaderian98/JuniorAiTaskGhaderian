import json
from pathlib import Path

import pytest

from app.cdm_parser import load_entities, load_entity, parse_attribute, parse_manifest_relationships

FIXTURES = Path(__file__).parent / "fixtures" / "cdm"
MANIFEST = "banking/banking.manifest.cdm.json"
ENTITY_FILES = ["banking/Account.cdm.json", "banking/Branch.cdm.json"]


def attribute_by_name(entity, name):
    return next(a for a in entity.attributes if a.name == name)


# --- single attributes -------------------------------------------------------

def test_parse_attribute_with_simple_data_type():
    member = {"name": "birthDate", "dataType": "dateTime", "description": " Date of birth. "}
    attribute = parse_attribute(member, "x.cdm.json")
    assert attribute.name == "birthDate"
    assert attribute.data_type == "dateTime"
    assert attribute.description == "Date of birth."
    assert attribute.source_path == "x.cdm.json"


def test_parse_attribute_with_data_type_object():
    member = {"name": "statusCode", "dataType": {"dataTypeReference": "listLookup"}}
    assert parse_attribute(member, "x").data_type == "listLookup"


def test_parse_lookup_attribute_and_polymorphic_lookup():
    lookup = {"name": "branch", "entity": {"entityReference": "Branch"}}
    polymorphic = {
        "name": "customer",
        "entity": {"entityReference": {"hasAttributes": [
            {"entity": {"entityReference": "Contact"}},
            {"entity": {"entityReference": "Account"}},
        ]}},
    }
    assert parse_attribute(lookup, "x").data_type == "lookup -> Branch"
    assert parse_attribute(polymorphic, "x").data_type == "lookup -> Contact | Account"


def test_string_member_is_skipped():
    # e.g. "customerIdAttribute": a group defined outside the indexed files
    assert parse_attribute("customerIdAttribute", "x") is None


# --- entities and inheritance --------------------------------------------------

def test_load_entity_reads_name_description_and_source():
    entity = load_entity(FIXTURES, "banking/Branch.cdm.json")
    assert entity.name == "Branch"
    assert entity.description.startswith("A branch is used")
    assert entity.source_path == "banking/Branch.cdm.json"
    assert entity.inheritance_chain == []
    assert [a.name for a in entity.attributes] == ["branchId"]


def test_load_entity_merges_parent_attributes_via_moniker():
    entity = load_entity(FIXTURES, "banking/Account.cdm.json")

    assert entity.inheritance_chain == ["base/Account.cdm.json"]
    names = [a.name for a in entity.attributes]
    # parent attributes first, then attributes added by the banking layer
    assert names == ["accountId", "name", "primaryContact", "annualReviewDate",
                     "accountCategoryCode", "enrollmentBranch", "parentCustomer"]
    assert attribute_by_name(entity, "accountId").source_path == "base/Account.cdm.json"
    assert attribute_by_name(entity, "annualReviewDate").source_path == "banking/Account.cdm.json"


def test_child_attribute_overrides_parent_attribute_with_same_name():
    entity = load_entity(FIXTURES, "banking/Account.cdm.json")
    name = attribute_by_name(entity, "name")
    assert name.description == "Banking description of name."
    assert name.source_path == "banking/Account.cdm.json"
    assert [a.name for a in entity.attributes].count("name") == 1


def test_child_description_is_used_over_parent():
    entity = load_entity(FIXTURES, "banking/Account.cdm.json")
    assert entity.description == "A company that represents a customer of the bank."


def test_unknown_moniker_raises_clear_error(tmp_path):
    (tmp_path / "_allImports.cdm.json").write_text(json.dumps({"imports": []}))
    (tmp_path / "Child.cdm.json").write_text(json.dumps({"definitions": [
        {"entityName": "Child", "extendsEntity": "base_Missing/Missing", "hasAttributes": []}
    ]}))
    with pytest.raises(ValueError, match="base_Missing"):
        load_entity(tmp_path, "Child.cdm.json")


def test_file_without_entity_definition_raises(tmp_path):
    (tmp_path / "Empty.cdm.json").write_text(json.dumps({"definitions": []}))
    with pytest.raises(ValueError, match="No entity definition"):
        load_entity(tmp_path, "Empty.cdm.json")


# --- relationships -------------------------------------------------------------

def test_manifest_relationships_keep_only_indexed_source_entities():
    relationships = parse_manifest_relationships(FIXTURES, MANIFEST, set(ENTITY_FILES))
    as_tuples = [(r.from_entity, r.from_attribute, r.to_entity, r.to_attribute) for r in relationships]
    assert as_tuples == [
        ("Account", "enrollmentBranchId", "Branch", "branchId"),
        ("Account", "createdBy", "User", "systemUserId"),
        ("Account", "createdBy", "User", "systemUserId"),  # second User file; removed later
    ]
    # Email is not an indexed entity, so its relationship to Account is dropped


def test_load_entities_attaches_outgoing_and_incoming_relationships():
    entities = {e.name: e for e in load_entities(FIXTURES, ENTITY_FILES, [MANIFEST])}

    account, branch = entities["Account"], entities["Branch"]
    assert [r.to_entity for r in account.relationships] == ["Branch", "User"]  # duplicate removed
    assert account.referenced_by == []
    assert [(r.from_entity, r.from_attribute) for r in branch.referenced_by] == [
        ("Account", "enrollmentBranchId")
    ]
    assert branch.relationships == []


def test_duplicate_entity_names_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        load_entities(FIXTURES, ["banking/Branch.cdm.json", "banking/Branch.cdm.json"], [MANIFEST])


def test_relationship_listed_in_two_manifests_is_attached_once():
    # The real applicationCommon manifest repeats relationships of the banking sub-manifest.
    manifests = [MANIFEST, "parent.manifest.cdm.json"]
    entities = {e.name: e for e in load_entities(FIXTURES, ENTITY_FILES, manifests)}
    assert [r.from_attribute for r in entities["Account"].relationships] == ["enrollmentBranchId", "createdBy"]
    assert len(entities["Branch"].referenced_by) == 1
