"""Download the pinned subset of the official Microsoft CDM repository.

Only this module touches the network. The parser works on the local copy.
"""

import urllib.request
from pathlib import Path

# Pinned commit of https://github.com/microsoft/CDM so the data never changes under us.
CDM_COMMIT = "dd21d715e05ebf740a11356c80b5c3b4c38a89c2"
RAW_BASE_URL = f"https://raw.githubusercontent.com/microsoft/CDM/{CDM_COMMIT}/schemaDocuments"

APP_COMMON = "core/applicationCommon"
BANKING_DIR = f"{APP_COMMON}/foundationCommon/crmCommon/accelerators/financialServices/banking"
BANKING_MANIFEST = f"{BANKING_DIR}/banking.manifest.cdm.json"
APP_COMMON_MANIFEST = f"{APP_COMMON}/applicationCommon.manifest.cdm.json"

BANKING_ENTITIES = [
    "Account", "Bank", "Branch", "BusinessCheckingAccount", "CertificateOfDeposit",
    "Collateral", "CommercialDeposit", "CommercialLoan", "Company360", "CompanyOnboarding",
    "Contact", "ContactOnboardingFromProspect", "Customer360Person", "CustomerJourney",
    "FinancialProduct", "KYC", "Lead", "LeadToOpportunitySalesProcess", "Limit",
    "MortgageApplication", "Opportunity", "Product", "RequestedFacility", "Syndicates",
]
COMMON_ENTITIES = ["Organization", "BusinessUnit", "Currency"]

# Parent definitions that banking entities extend, plus the _allImports files
# that map "base_Account" style monikers to those parent files.
INHERITANCE_FILES = [
    f"{BANKING_DIR}/_allImports.cdm.json",
    f"{APP_COMMON}/foundationCommon/crmCommon/_allImports.cdm.json",
    f"{APP_COMMON}/foundationCommon/_allImports.cdm.json",
    f"{APP_COMMON}/foundationCommon/crmCommon/Account.cdm.json",
    f"{APP_COMMON}/foundationCommon/crmCommon/Contact.cdm.json",
    f"{APP_COMMON}/foundationCommon/crmCommon/Lead.cdm.json",
    f"{APP_COMMON}/foundationCommon/crmCommon/sales/Opportunity.cdm.json",
    f"{APP_COMMON}/foundationCommon/crmCommon/solutions/marketing/CustomerJourney.cdm.json",
    f"{APP_COMMON}/foundationCommon/Account.cdm.json",
    f"{APP_COMMON}/foundationCommon/Contact.cdm.json",
    f"{APP_COMMON}/foundationCommon/Product.cdm.json",
    f"{APP_COMMON}/Account.cdm.json",
    f"{APP_COMMON}/Contact.cdm.json",
]

# The entity files that become indexed entities (parents are merged into them).
ENTITY_FILES = [f"{BANKING_DIR}/{name}.cdm.json" for name in BANKING_ENTITIES] + [
    f"{APP_COMMON}/{name}.cdm.json" for name in COMMON_ENTITIES
]
MANIFEST_FILES = [BANKING_MANIFEST, APP_COMMON_MANIFEST]
CDM_FILES = MANIFEST_FILES + ENTITY_FILES + INHERITANCE_FILES


def download_cdm_files(target_dir: Path, paths: list[str] = CDM_FILES) -> int:
    """Download missing files into target_dir. Returns how many were downloaded."""
    downloaded = 0
    for path in paths:
        local_file = target_dir / path
        if local_file.exists():
            continue
        local_file.parent.mkdir(parents=True, exist_ok=True)
        url = f"{RAW_BASE_URL}/{path}"
        print(f"Downloading {url}")
        urllib.request.urlretrieve(url, local_file)
        downloaded += 1
    return downloaded
