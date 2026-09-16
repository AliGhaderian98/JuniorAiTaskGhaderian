# Implementation Plan: CDM RAG API

Status: implemented. This plan was written before and during implementation.
§3 (scope) and §9 (retrieval) contain the final, measured decisions. Where other
sections differ from the code, **§17 "Differences from the final implementation"**
is authoritative.

## 1. Project goal

A small FastAPI service that answers natural-language questions about Microsoft
Common Data Model (CDM) entities. Examples: attributes, descriptions, and
relationships. Answers use only CDM definitions retrieved from a local vector
store. If the retrieved context is insufficient, the service says so instead of
guessing.

## 2. Environment findings (checked 2026-09-16)

| Item | Finding |
|---|---|
| `ASSIGNMENT.md` | **Not present.** The prompt's requirement text is the only source used. |
| Git | Repo at `JuniorAiTaskGhaderian/JuniorAiTaskGhaderian/`, branch `main`, **no commits**. Remote `origin` = `https://github.com/AliGhaderian98/JuniorAiTaskGhaderian.git` (already set, will not be changed). The outer Desktop folder is *not* a repo. |
| Python | 3.14 is the default. **3.12.10 is also installed** (`py -3.12`). |
| uv / pip | uv 0.11.16, pip 26.1.1. Poetry is not installed. |
| Docker | 29.4.3. Daemon is running. |
| GitHub CLI (`gh`) | **Not installed.** Pushing uses plain `git`. |
| LaTeX (pdflatex/xelatex/latexmk) | **Not installed.** PDF compilation is currently NOT possible locally (see §13 and §17). |
| `OPENAI_API_KEY` | Set in the environment. The value was not printed. |

## 3. Assumptions and scope

**Data source:** the official repo `github.com/microsoft/CDM`, branch `master`,
pinned to commit `dd21d715e05ebf740a11356c80b5c3b4c38a89c2` (2025-01-22) for
reproducibility.

**Observations about "Banking Model" (Phase 2, documented in the README):**
- The repository contains **two** banking-related models:
  1. `schemaDocuments/core/applicationCommon/foundationCommon/crmCommon/accelerators/financialServices/banking/`:
     the **Banking accelerator** ("CDM Solution for the 'BANKING' CDS Solution",
     24 entities). It builds on the common CDM entities (its `Account` *extends*
     the common `Account`), and its manifest lists **534 explicit
     relationships**.
  2. `schemaDocuments/FinancialServices/RetailBankingCoreDataModel/` (21
     entities). It is a separate, flat model: its `Account.cdm.json` is a stub
     with a single attribute (`accountId`), it does not extend the common
     entities, and its manifest has **no** relationships section.
- **Chosen: the Banking accelerator (1).** It connects directly to the common
  entities the assignment mentions (Account, Contact, Lead, Product), and it has
  real relationship data. Model (2) is not indexed. This is a documented scope
  choice, not an omission.
- Files come in versioned copies (`Account.1.3.cdm.json`, …). Only the
  **unversioned** file is ingested.
- In CDM, `Organization` is the *Dynamics 365 top-level business hierarchy*
  ("Top level of the Microsoft Dynamics 365 business hierarchy…"), not "a
  company". **The data has no direct Contact → Organization relationship.**
  Contact relates to Account through `parentCustomerId` and `employerId`.
  Organization is referenced by the banking process entities (`organizationId`)
  and by `BusinessUnit.organizationId`. The demo uses only relationships
  confirmed here.

**Final scope (27 entities; 40 entity/import files + 2 manifests):**
1. The 24 banking entities listed in `banking.manifest.cdm.json`: Account, Bank,
   Branch, BusinessCheckingAccount, CertificateOfDeposit, Collateral,
   CommercialDeposit, CommercialLoan, Company360, CompanyOnboarding, Contact,
   ContactOnboardingFromProspect, Customer360Person, CustomerJourney,
   FinancialProduct, KYC, Lead, LeadToOpportunitySalesProcess, Limit,
   MortgageApplication, Opportunity, Product, RequestedFacility, Syndicates.
2. Their **inheritance parents**. Example: banking `Account` →
   crmCommon `Account` → foundationCommon `Account` → applicationCommon
   `Account` (120 attributes total). Parents are merged into the child entity,
   **not** indexed as separate entities.
3. Three common entities referenced by the banking model: `Organization`,
   `BusinessUnit`, `Currency` (from `core/applicationCommon/`).

User, Team, SLA, PriceList and similar targets are **not** indexed. They still
appear as relationship target names. The API will not claim to know their
attributes.

License of the source data: **CC-BY-4.0** (attribution in the README).

## 4. Minimal architecture

```
scripts/build_index.py (run once)
  download pinned CDM files -> data/cdm/...        (cdm_loader.py)
  parse JSON -> EntityDocument objects             (cdm_parser.py)
  build chunk text + metadata                      (cdm_parser.py)
  embed chunks (sentence-transformers)             (embeddings.py)
  store in persistent Chroma collection            (vector_store.py)

FastAPI (app/main.py)
  POST /ask -> retriever.py: exact-name match + vector search + threshold
            -> rag_service.py: build context, call OpenAI, return answer + sources
  GET /health -> index loaded? entity count? LLM key configured?
```

No LangChain, agents, graph DB, frontend, auth, or compose.

## 5. Technologies (each has one concrete reason)

| Dependency | Why |
|---|---|
| FastAPI + Pydantic | Required by the assignment. Swagger UI at `/docs` serves as the demo UI. |
| sentence-transformers | Local embeddings: no API cost, deterministic, and the data never leaves the machine for indexing. |
| Embedding model **`BAAI/bge-small-en-v1.5`** (384-dim, ~130 MB) | Small, runs on CPU, and has good English retrieval quality. Its **512-token input limit** matters: `all-MiniLM-L6-v2` truncates at 256 tokens, which would silently cut off long attribute lists. The choice will be checked against measured chunk lengths in Phase 4. |
| **Chroma** (persistent, local) | Stores vectors **and** metadata (entity name, source path, relationship targets) in one place. FAISS would need a separate metadata file and our own ID mapping. The data is small (hundreds of chunks), so FAISS's speed advantage doesn't matter here. |
| `openai` SDK | One LLM provider. The key is already available. The model name comes from the env var `OPENAI_MODEL`; the default is chosen after checking current docs in Phase 7. Temperature is 0. |
| `requests` or stdlib `urllib` | Downloads the pinned raw files. The stdlib is preferred if it stays readable. |
| pytest | Unit tests. |

Runtime: **Python 3.12** for both the local venv and the Docker image
(`python:3.12-slim`). This avoids wheel-availability problems with 3.14 for
torch/chromadb and keeps local and container behavior identical.

## 6. Ingestion strategy

- `cdm_loader.py`: an explicit list of relative CDM paths → download each file
  from `raw.githubusercontent.com/microsoft/CDM/<pinned-sha>/schemaDocuments/...`
  into `data/cdm/` (skipped if already present). The raw JSON is **committed**,
  so tests, Docker builds, and demos work offline (CC-BY-4.0, attributed).
- The file list is **resolved and pinned in code**: manifests + entity files +
  the `_allImports.cdm.json` of each folder on an inheritance chain, plus the two manifests (42 files).
- `cdm_parser.py` works on the real structure. Shapes were counted across all
  scoped files:
  - `definitions[]`: the item with `entityName` (+ `extendsEntity`,
    `description`, `displayName`).
  - `hasAttributes[]` → `attributeGroupReference.members[]` (37 groups).
  - Member with `dataType` string (1087) → `Attribute(name, data_type, description)`.
  - Member with `dataType` object (166) → type = `dataType.dataTypeReference`
    (e.g. `listLookup`).
  - Member with `entity` (149 + 1 polymorphic) → attribute of type
    `lookup` with the target name(s). The **relationship** itself comes from the
    manifest (§8).
  - String member (4×, `customerIdAttribute`): a well-known CDS attribute group
    that is not defined in these files. Skipped here; the relationship it
    represents (`customerId → Account | Contact`) is still in the manifest.
- Inheritance: `extendsEntity: "base_Account/Account"` → look up moniker
  `base_Account` in the folder's `_allImports.cdm.json` → load the parent file →
  repeat until the root (`CdsStandard` / `CdmEntity`). Attributes from all
  layers are merged. Each attribute remembers the source file it came from, and
  on a name clash the most specific (child) layer wins.
- Not resolved: the generic system attributes inherited from `CdsStandard`
  (`createdOn`, `ownerId`, …, defined in `wellKnownCDSAttributeGroups`). This
  is a documented limitation. Their ownership/audit relationships still come in
  through the manifest.
- Normalized models (simple Pydantic models):
  - `Attribute(name, data_type, description)`
  - `Relationship(source_entity, attribute_name, target_entity, source_path)`
  - `EntityDocument(entity_name, model, description, extends, attributes, relationships, source_path)`
- Inheritance (`extendsEntity`) is recorded as metadata/text only. It is **not**
  resolved recursively. That is a documented limitation.

## 7. Chunking / retrieval-document strategy

Entity-aware chunks, not fixed token windows:

1. **Overview chunk** (one per entity): name, model, description, extends, all
   relationships written as explicit lines (`Account -> Contact via
   primaryContact`), and the attribute *names*. Almost every question type can
   hit this chunk.
2. **Attribute chunks**: attributes with type and description, split into
   ordered groups (e.g. 20 attributes each) **only** when the entity is too long
   for the model's 512-token limit. Each chunk repeats the entity name in its
   header so it is still self-describing.

Every chunk has this metadata: `entity_name`, `model`, `chunk_type`,
`source_path`, `related_entities` (comma-separated).

Why: an entity boundary already carries business meaning. Fixed 500-token
windows would cut an attribute list mid-entity and lose the entity name.

## 8. Relationship strategy

**Source: the official manifests' `relationships` arrays.** Each entry is
already explicit:

```json
{"fromEntity": "Contact.cdm.json/Contact", "fromEntityAttribute": "parentCustomerId",
 "toEntity": "Account.cdm.json/Account", "toEntityAttribute": "accountId"}
```

- Banking manifest (534 entries) plus `applicationCommon.manifest.cdm.json`
  (only entries whose `fromEntity` is Organization/BusinessUnit/Currency).
- Kept: entries whose **from-entity is indexed**. Target names are taken from
  the last path segment. Duplicates are removed (e.g. `createdBy → User` appears
  twice with two different User paths).
- `Relationship(source_entity, source_attribute, target_entity, target_attribute)`.
- Grouped in text as **business relationships** vs. **system relationships**.
  System relationships are a fixed, documented list of attribute names:
  `createdBy, modifiedBy, createdOnBehalfBy, modifiedOnBehalfBy, ownerId,
  owningUser, owningTeam, owningBusinessUnit`. This keeps audit links from
  drowning out links like `Contact.parentCustomerId → Account`.
- **Incoming** relationships are computed by reversing the kept list. Example:
  `Contact` overview also shows "referenced by FinancialProduct.customerId,
  KYC.primaryContactId, …".

Why the manifest and not the entity attributes? The manifest also includes
relationships that come from inherited attributes and well-known attribute
groups (`customerId`). Those are **not** visible in the entity files without a
full CDM resolver. So the manifest is both more complete and much simpler to
parse.

Relationships are used in two places:
1. **Text**: explicit lines in the overview chunk (`Contact.parentCustomerId ->
   Account.accountId`), so semantic search can match "how does X relate to Y".
2. **Retrieval**: if the question names two known entities, the retriever
   includes the overview chunks of **both**. The context then contains the link
   from either side (outgoing *and* incoming references).

No graph database. With tens of entities and one-hop questions, explicit
metadata plus both-side retrieval is enough. A graph DB would help with
multi-hop path questions ("how is Fi_card connected to Branch through 3
entities?") at a much larger scale.

## 9. Retrieval strategy (implemented in Phase 6, values measured)

```
question
  1. entity-name match (case-insensitive, plural "s", "financial product" = FinancialProduct,
     longest name wins) -> overview + referenced_by chunks of up to 3 named entities
  2. embed question (with BGE query instruction) -> Chroma top_k = 5 (cosine)
  3. keep vector hits with score >= 0.63
  4. merge: name matches first, no duplicates
  5. nothing left -> abstain without calling the LLM
```

Why each step (measurements with the real index):
- **Name matching.** For "How does a Contact relate to an Account?", pure vector
  search returned only attribute chunks in the top 5. The overview chunks that
  list the relationships were missing. Name matching guarantees they are
  included.
- **BGE query instruction.** Recommended by the model card. On 12 in-scope and
  12 off-topic questions it improved expected-entity ranks (Organization 2→1,
  FinancialProduct 3→2) and lowered the highest off-topic top-1 score from
  0.658 to 0.610. The lowest in-scope top-1 score was 0.663.
- **min_score = 0.63.** Sits between those two values. Small sample, so it is a
  first layer only: near-domain questions that pass it must be caught by the
  prompt (§10).
- **top_k = 5.** Enough to include the named entities' most similar attribute
  chunks, and keeps the context at ≤ ~10 chunks (≈ 3–4k tokens).

`scripts/evaluate_retrieval.py`: **17/18 checks pass.** Known failure: "assets
pledged to secure a loan" does not retrieve `Collateral` (vocabulary mismatch
between question and CDM text). Possible fixes, not implemented: hybrid
BM25+vector search, a reranker, or a larger embedding model.

Known side effect: common English words that are also entity names ("bank",
"product", "limit", "contact") trigger name matching. That only adds context.
The prompt still decides whether it answers the question.

## 10. Grounded generation

- System prompt: answer only from the provided CDM context; do not invent
  entities, attributes, or relationships; if the context is insufficient, say
  "The indexed CDM context does not contain enough information…"; name source
  entities/files.
- Context is written in clearly delimited blocks, each labeled with entity +
  model + source path.
- `temperature=0`.
- Response model:
  `{question, answer, sources: [{entity_name, model, source_path, chunk_type, score}], retrieved_entities: [...]}`.
- Missing `OPENAI_API_KEY` → `/ask` returns HTTP 503 with a clear message.
  `/health` still works.

## 11. Test strategy

`pytest`, no network, no OpenAI, fast:

- `tests/test_cdm_parser.py`: small JSON fixtures copied from real file
  structures. They cover entity parsing, plain attributes, group-wrapped
  attributes, core-style relationships, banking `source`-style relationships,
  polymorphic relationships, missing descriptions, and non-entity definitions
  being ignored.
- `tests/test_retrieval.py`: a **fake deterministic embedder** (keyword/hash
  based) plus an in-memory Chroma client. Tests: exact entity match is returned
  first; a relationship question returns both entities; an off-topic question
  returns nothing (abstain); deduplication; empty question is rejected.
- `tests/test_api.py` (small): `/health`; `/ask` with the RAG service mocked;
  503 when the key is missing.
- One optional integration test (marked, skipped by default) runs against the
  real index.

## 12. Demo strategy

Swagger UI (`/docs`) plus curl, using 4–5 questions,
**each confirmed against the indexed data**: Account attributes, one
real relationship, one semantic question (e.g. "Which entity stores a
customer's loans and savings?"), and one off-topic question for abstention.
Backup if OpenAI is down: `/ask` returns `retrieved_entities` and `sources`
anyway, so retrieval can still be shown. There will also be a
`scripts/query_index.py` (retrieval only) to run locally.

## 13. Documentation strategy

- `README.md`: the 16 sections requested. Short and factual.
- `docs/VALIDATION_REPORT.md` (PASS / FAIL / NOT VERIFIED with commands).
- `docs/presentation.tex` (≤ 3 Beamer slides).
- **LaTeX is not installed.** Options: (a) you install MiKTeX / TeX Live, or
  (b) compile inside a Docker TeX image (e.g. `texlive/texlive`, several GB).

## 14. Planned structure

```
app/ __init__.py main.py config.py models.py cdm_loader.py cdm_parser.py
     embeddings.py vector_store.py retriever.py rag_service.py
scripts/ build_index.py query_index.py
data/cdm/            (pinned raw JSON, committed)
tests/ test_cdm_parser.py test_retrieval.py test_api.py fixtures/
docs/  IMPLEMENTATION_PLAN.md VALIDATION_REPORT.md presentation.tex
Dockerfile .dockerignore .env.example .gitignore README.md requirements.txt
```

Files may be merged during implementation if they turn out trivial (e.g.
`embeddings.py` into `vector_store.py`).

**Docker plan:** `python:3.12-slim`, CPU-only torch wheel (avoids a ~2 GB CUDA
download), model **downloaded at build time** and index **built at build time**.
The container then starts offline and fast. `OPENAI_API_KEY` is passed only at
`docker run -e`.

`chroma_db/` (the generated index) is git-ignored and rebuilt with
`python scripts/build_index.py`.

## 15. Acceptance criteria

The checklist in the task prompt (§25) is the acceptance criteria. In short:
real CDM data is ingested with scope documented; attributes and relationships
are parsed and covered by tests; retrieval works for attribute, relationship,
and semantic questions; off-topic questions abstain; `/health` and `/ask` work
locally and in Docker; all unit tests pass; README / validation
report are accurate; slides ≤ 3; no secrets in Git.

## 16. Phases

1 plan (this) → 2 inspect CDM + fix scope → 3 models + parser → 4 chunk docs →
5 embeddings + Chroma → 6 retriever + threshold calibration → 7 RAG service →
8 FastAPI → 9 tests/edge cases → 10 Docker + README → 11 end-to-end validation →
12 slides → 13 final audit + commits.

## 17. Differences from the final implementation

| Plan said | Final implementation |
|---|---|
| `EntityDocument(entity_name, model, extends, ...)` | `app/models.py`: `Entity(name, description, source_path, inheritance_chain, attributes, relationships, referenced_by)`, `Attribute(name, data_type, description, source_path)` |
| `Relationship(source_entity, attribute_name, target_entity, ...)` | `Relationship(from_entity, from_attribute, to_entity, to_attribute)` |
| Chunk text built in `cdm_parser.py`; attribute groups of ~20 only when needed | Separate `app/documents.py` with three chunk types: `overview`, `referenced_by`, `attributes` (always 12 per chunk). Measured: one chunk per entity reached 700 tokens (limit 512); largest chunk now 416 |
| `embeddings.py` might be merged into `vector_store.py` | Kept separate (lazy import of sentence-transformers keeps tests fast) |
| `scripts/query_index.py` for retrieval-only checks | Not built. Replaced by `POST /retrieve` and `scripts/evaluate_retrieval.py` |
| OpenAI default model chosen later | `gpt-4.1-mini` (compared with `gpt-5.4-mini`, see README §12) |
| Tests: parser, retrieval, small API test, optional marked integration test | Parser, documents, vector store, retrieval, RAG service, API, real-data checks (`tests/test_real_cdm_data.py`); no pytest marker, the real-index check is `scripts/evaluate_retrieval.py` |
| LaTeX: install MiKTeX/TeX Live or compile in Docker | Compiled with the TeX Live Docker image (`texlive/texlive:latest-medium`) to `docs/presentation.pdf`, 3 pages, visually checked. See `docs/VALIDATION_REPORT.md` |
| — | Added: `requirements-dev.txt`, `.gitattributes` (LF), `.dockerignore`, `HF_HUB_OFFLINE=1` in the Docker image |
