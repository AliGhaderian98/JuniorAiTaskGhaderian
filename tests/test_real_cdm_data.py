"""Checks against the committed CDM files in data/cdm (no network).

These protect facts the demo relies on, e.g. that the parser still finds
Contact -> Account and that no direct Contact -> Organization link exists.
"""

import pytest

from app.cdm_parser import load_cdm_entities
from app.config import CDM_DATA_DIR


@pytest.fixture(scope="module")
def entities():
    return {entity.name: entity for entity in load_cdm_entities(CDM_DATA_DIR)}


def test_scope_contains_banking_and_common_entities(entities):
    assert len(entities) == 27
    for name in ["Account", "Contact", "FinancialProduct", "KYC", "Organization", "BusinessUnit"]:
        assert name in entities


def test_account_includes_inherited_and_banking_attributes(entities):
    account = entities["Account"]
    names = {a.name for a in account.attributes}
    assert "accountId" in names          # from core/applicationCommon/Account.cdm.json
    assert "annualReviewDate" in names   # added by the banking accelerator
    assert len(account.inheritance_chain) == 3


def test_contact_relates_to_account(entities):
    links = {(r.from_attribute, r.to_entity) for r in entities["Contact"].relationships}
    assert ("parentCustomerId", "Account") in links
    assert ("employerId", "Account") in links


def test_no_direct_contact_organization_relationship(entities):
    assert all(r.to_entity != "Organization" for r in entities["Contact"].relationships)
    assert all(r.from_entity != "Contact" for r in entities["Organization"].referenced_by)
