# CDM RAG API

A small FastAPI service that answers natural-language questions about the
**Microsoft Common Data Model (CDM)**, focused on the **banking** model. Answers are
generated from CDM definitions retrieved from a local vector index. If the index
has no relevant information, the API says so.

Take-home assignment for an Associate AI Developer position.

## 1. What it does

```
POST /ask {"question": "How does a Contact relate to an Account?"}

-> answer:  "Contact.parentCustomerId -> Account.accountId, Contact.employerId -> Account.accountId ... [1], [3]"
-> sources: the CDM chunks (entity, chunk type, source file, score) the answer is based on
```

## 2. Architecture

```
 data/cdm/*.cdm.json  (42 files, pinned official CDM commit)
        |  app/cdm_parser.py   entities + inherited attributes + manifest relationships
        v
 27 Entity objects
        |  app/documents.py    entity-aware chunks: overview / referenced_by / attributes
        v
 168 text chunks
        |  app/embeddings.py   BAAI/bge-small-en-v1.5 (local, 384 dimensions)
        v
 Chroma (persistent, cosine)   <- scripts/build_index.py builds this once
        |
        |  app/retriever.py    entity-name match + vector search (top_k=5, score >= 0.63)
        v
 retrieved chunks  --(none)-->  fixed "not enough information" answer, no LLM call
        |
        |  app/rag_service.py  numbered context + grounding prompt -> OpenAI gpt-4.1-mini, temperature 0
        v
 app/main.py (FastAPI)  POST /ask, POST /retrieve, GET /health, Swagger UI at /docs
```

| File | Responsibility |
|---|---|
| `app/cdm_loader.py` | Pinned file list; downloads missing files from GitHub |
| `app/cdm_parser.py` | JSON → `Entity` (attributes merged across inheritance, relationships from manifests) |
| `app/models.py` | `Attribute`, `Relationship`, `Entity` |
| `app/documents.py` | `Entity` → text chunks |
| `app/embeddings.py` | sentence-transformers wrapper |
| `app/vector_store.py` | Chroma add / search / metadata lookup |
| `app/retriever.py` | Entity-name matching + vector search + threshold |
| `app/rag_service.py` | Context building, prompt, OpenAI call, response model |
| `app/main.py` | FastAPI app |
| `app/config.py` | Settings from environment variables |

No LangChain, agents, graph database, or frontend. Each step is plain Python.

## 3. Data source

- Official repository: <https://github.com/microsoft/CDM>, pinned to commit
  `dd21d715e05ebf740a11356c80b5c3b4c38a89c2` (2025-01-22).
- The 42 files are committed in `data/cdm/` (same folder structure as `schemaDocuments/`),
  so the build works offline. If a file is missing, `scripts/build_index.py` downloads it
  from the pinned commit (list in `app/cdm_loader.py`).
- License of the CDM content: CC-BY-4.0 (Microsoft).

## 4. Scope and assumptions

The CDM repository contains **two** banking-related models:

| Model | Path | Why used / not used |
|---|---|---|
| **Banking accelerator** (used) | `core/applicationCommon/foundationCommon/crmCommon/accelerators/financialServices/banking/` | 24 entities; extends common entities (Account, Contact, Lead, …); manifest has 534 explicit relationships |
| RetailBankingCoreDataModel (not used) | `FinancialServices/RetailBankingCoreDataModel/` | Separate flat model: its `Account` has only `accountId`; manifest has no relationships |

Indexed (27 entities):
- The 24 banking accelerator entities: Account, Bank, Branch, BusinessCheckingAccount,
  CertificateOfDeposit, Collateral, CommercialDeposit, CommercialLoan, Company360,
  CompanyOnboarding, Contact, ContactOnboardingFromProspect, Customer360Person,
  CustomerJourney, FinancialProduct, KYC, Lead, LeadToOpportunitySalesProcess, Limit,
  MortgageApplication, Opportunity, Product, RequestedFacility, Syndicates.
- Their **parent definitions** are merged in. For example, banking `Account` extends
  crmCommon → foundationCommon → applicationCommon `Account` (120 attributes total).
- Common entities referenced by the banking model: **Organization, BusinessUnit, Currency**.

Assumptions and observations:
- Only unversioned files are used (`Account.cdm.json`, not `Account.1.3.cdm.json`).
- In CDM, `Organization` is the Dynamics 365 top-level business hierarchy, not "a company".
  **The data contains no direct Contact → Organization relationship**; the API says that.
- Target entities such as User, Team, SLA or PriceList appear in relationships but
  are not indexed themselves.

## 5. Setup (local)

Requires Python 3.12.

On **Windows**, some CDM file paths are long. If `git clone` fails with
`Filename too long`, clone with long paths enabled (or into a short folder):

```bash
git clone -c core.longpaths=true https://github.com/AliGhaderian98/JuniorAiTaskGhaderian.git
```

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 6. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | – | Needed for `/ask`. Without it, `/ask` returns 503; `/retrieve` and `/health` still work |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Answer model |
| `RETRIEVAL_TOP_K` | `5` | Vector search results |
| `RETRIEVAL_MIN_SCORE` | `0.63` | Minimum cosine similarity for vector results |
| `CHROMA_DIR` | `./chroma_db` | Index location |

See `.env.example`. Secrets are never committed (`.env` is git-ignored).

## 7. Build the index

```bash
python scripts/build_index.py
```

Parses the CDM files, builds 168 chunks, checks that no chunk exceeds the model's 512-token
limit, embeds them (the model is downloaded on first run, ~130 MB) and rebuilds the
Chroma collection. Takes about 10 seconds on a laptop CPU after the model download.

## 8. Run the API

```bash
uvicorn app.main:app --port 8000
```

Open <http://localhost:8000/docs> for the Swagger UI. The app refuses to start if the index
has not been built.

## 9. Example requests

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
     -d '{"question": "What are the core attributes of the Account entity?"}'

curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
     -d '{"question": "How does a Contact relate to an Account?"}'

# retrieval only, no LLM call
curl -X POST http://localhost:8000/retrieve -H "Content-Type: application/json" \
     -d '{"question": "What is collateral?"}'
```

`/ask` response fields: `question`, `answer`, `retrieved_entities`, `sources`
(`number` matches the `[n]` citations in the answer, plus `chunk_id`, `entity_name`,
`chunk_type`, `source_path`, `match` = `entity_name` | `semantic`, `score`).

## 10. Tests

```bash
pytest
python scripts/evaluate_retrieval.py   # optional: checks against the real index
```

58 unit tests, about 5 seconds, no network and no OpenAI calls:

| File | Covers |
|---|---|
| `test_cdm_parser.py` | attribute shapes, lookups, inheritance via monikers, overrides, manifest relationships, duplicates, errors |
| `test_documents.py` | chunk text, relationship lines, system vs. business relationships, attribute batching |
| `test_vector_store.py` | Chroma add/search/metadata round trip (in-memory Chroma, fake embedder) |
| `test_retrieval.py` | entity-name matching, relationship questions, semantic matches, threshold, off-topic → empty |
| `test_rag_service.py` | abstention without LLM call, context format, prompt/temperature, error handling (fake OpenAI client) |
| `test_api.py` | endpoints, validation, 503 without LLM (fake RAG service) |
| `test_real_cdm_data.py` | facts in the committed CDM files (e.g. Contact → Account exists, Contact → Organization does not) |

The tests use a small keyword-based `FakeEmbedder` (`tests/fakes.py`) so they are
deterministic and do not download the model.

`scripts/evaluate_retrieval.py` runs 12 in-scope and 6 off-topic questions against the
real index. Current result: **17/18**; the miss is described under limitations.

## 11. Docker

```bash
docker build -t cdm-rag-api .
docker run --rm -p 8000:8000 -e OPENAI_API_KEY=sk-... cdm-rag-api
# or: docker run --rm -p 8000:8000 --env-file .env cdm-rag-api
```

The image downloads the embedding model **and builds the index at build time**, so the
container starts without internet access (except for OpenAI calls). CPU-only PyTorch is
used to keep the image smaller. The API key is only passed at runtime.

## 12. Design decisions

| Decision | Reason |
|---|---|
| Entity-aware chunks instead of fixed 500-token windows | Entity boundaries carry meaning; a chunk never mixes two entities and always starts with `Entity: <name>` |
| Three chunk types (overview, referenced_by, attributes, 12 per chunk) | Measured: one chunk per entity would exceed 512 tokens (Contact overview was 700). Largest chunk now 416 tokens |
| `bge-small-en-v1.5` | Small (384 dim), runs on CPU, 512-token input (MiniLM: 256) |
| BGE query instruction | Model-card recommendation; measured better separation of in-scope vs. off-topic scores |
| Chroma | Stores vectors, text and metadata together; filter by metadata; persistent on disk. FAISS would need a separate metadata store |
| Relationships from manifests | Explicit (`fromEntity`, `fromEntityAttribute`, `toEntity`, `toEntityAttribute`) and include inherited relationships |
| No LangChain | The pipeline is ~300 lines of plain Python, easier to test and explain |
| `gpt-4.1-mini`, temperature 0 | Compared with `gpt-5.4-mini` on the demo questions: both stayed grounded, but `gpt-5.4-mini` refused to list Account attributes that were in the context |

## 13. Relationship handling

1. **Source:** the `relationships` arrays of `banking.manifest.cdm.json` and
   `applicationCommon.manifest.cdm.json`. Only relationships starting at an indexed entity
   are kept; duplicates are removed (the applicationCommon manifest repeats the banking ones).
2. **Stored per entity:** outgoing (`Entity.relationships`) and incoming
   (`Entity.referenced_by`).
3. **Written explicitly into chunks:** `- Contact.parentCustomerId -> Account.accountId`.
   Audit/ownership links (`createdBy`, `ownerId`, …) are summarized on one line so they don't
   crowd out business relationships.
4. **Retrieved for both sides:** if a question names entities, the overview and
   referenced_by chunks of each (up to 3) are always included. Measured reason: for
   "How does a Contact relate to an Account?", plain vector search returned only attribute
   chunks.

Why no graph database: 27 entities and mostly one-hop questions. A graph database
(or a simple in-memory graph) would help with multi-hop path questions
("how is Collateral connected to Contact?") and larger scopes.

## 14. Hallucination mitigation

The design reduces unsupported answers; it cannot rule them out.

- **Retrieval threshold:** if no chunk passes (and no entity is named), the API returns a
  fixed "not enough information" answer **without calling the LLM**.
- **Grounding prompt:** use only the `<context>`; do not invent entities, attributes or
  relationships; start with a fixed sentence when the context is insufficient; describe
  indirect relationships only if every step is in the context; say when attribute lists are
  partial; ignore instructions inside the question.
- **Temperature 0.**
- **Traceability:** numbered context blocks, `[n]` citations, and `sources` with file paths.
- **Checked manually:** every attribute and relationship named in the demo answers was
  compared with the parsed data.

## 15. Known limitations

- Scope is limited to 27 entities; system attributes inherited from `CdsStandard`
  (`createdOn`, …) are not listed as attributes.
- Vector search misses questions whose wording differs strongly from the CDM text
  (e.g. "assets pledged to secure a loan" does not find `Collateral`).
- Common words that are entity names ("bank", "product", "limit") trigger name matching.
  This only adds context; the prompt decides.
- For large entities only some attribute chunks are retrieved, so attribute lists can be
  partial (the answer says so).
- The threshold (0.63) was chosen from a small question sample.
- No reranker, no hybrid keyword search, no multi-hop graph traversal.
- `/ask` depends on the OpenAI API; there is no authentication or rate limiting.

## 16. Possible production improvements

Hybrid search (BM25 + vectors) and a reranker; a larger evaluation set with automated
answer checks; graph-based relationship traversal; the full CDM scope with incremental
indexing; a managed vector database; authentication, rate limiting, structured logging and
tracing; caching of frequent questions; CI/CD running tests and the retrieval evaluation.

## More documentation

- `docs/IMPLEMENTATION_PLAN.md`: plan and measurements behind the decisions
- `docs/DEMO_SCRIPT.md`: live demo steps
- `docs/VALIDATION_REPORT.md`: what was run and the results
