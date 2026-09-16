# Validation Report

Date: 2026-09-16. Machine: Windows 11, Python 3.12.10, Docker 29.4.3.
Code state: application code unchanged since commit `d32bc4e` (later commits only changed documentation), unless noted.
Every row was actually run; results are copied from the command output.

## Summary

| # | Check | Result |
|---|---|---|
| 1 | Unit tests | PASS |
| 2 | Linter (ruff, default rules) | PASS |
| 3 | Fresh clone + install + tests + index build | PASS (after long-path fix, see notes) |
| 4 | Index build | PASS |
| 5 | Retrieval evaluation | PASS with 1 documented miss (17/18) |
| 6 | API startup | PASS |
| 7 | `GET /health` | PASS |
| 8 | Swagger UI `/docs` | PASS |
| 9 | `POST /ask` attribute question | PASS |
| 10 | `POST /ask` relationship question | PASS |
| 11 | `POST /ask` non-existent direct relationship | PASS |
| 12 | `POST /ask` semantic question | PASS |
| 13 | `POST /ask` off-topic abstention (no LLM call) | PASS |
| 14 | `POST /ask` LLM-level abstention | PASS |
| 15 | `POST /retrieve` | PASS |
| 16 | Input validation (422) | PASS |
| 17 | Missing OpenAI key → 503 | PASS |
| 18 | Missing index → startup fails with message | PASS |
| 19 | Answer facts checked against parsed data | PASS |
| 20 | Docker build | PASS |
| 21 | Docker run + requests inside container | PASS |
| 22 | Docker without network | PASS |
| 23 | Secrets / ignored files | PASS |
| 24 | LaTeX presentation compilation | NOT VERIFIED (source only, static checks PASS) |

## Details

### 1. Unit tests — PASS
```
.venv\Scripts\python -m pytest -q
58 passed, 1 warning in 7.80s
```
The warning is a `DeprecationWarning` inside Starlette's `testclient.py` (library code, not ours).

### 2. Linter — PASS
No linter is configured in the project; ruff was run as an extra check without adding a dependency.
```
uvx ruff@latest check --isolated app scripts tests      # ruff 0.16.7
All checks passed!
```
First run found 13 fixable issues (import formatting, unused `noqa` comments); fixed with `--fix` in commit `d32bc4e`, tests re-run afterwards.

### 3. Fresh clone — PASS (after fix)
First attempt, cloning into a very deep folder:
```
git clone <repo> <long scratch path>\fresh_clone
fatal: cannot create directory at 'data/cdm/core/.../banking': Filename too long
```
Fix: documented in README §5. Second attempt (commit `9a77196`):
```
git clone -c core.longpaths=true <repo> %TEMP%\cdmfresh
py -3.12 -m venv .venv && pip install -r requirements-dev.txt   -> pip install OK
pytest -q                                                       -> 58 passed in 7.56s
python scripts/build_index.py                                   -> Entities: 27, chunks: 168
                                                                   Indexed 168 chunks ... in 34.6s
```

### 4. Index build — PASS
```
python scripts/build_index.py
CDM files downloaded: 0 (others already present)
Entities: 27, chunks: 168
Indexed 168 chunks into ...\chroma_db in 8.6s
```
Run twice: still 168 chunks (full rebuild, no duplicates). Token check: largest chunk 416 tokens (limit 512).

### 5. Retrieval evaluation — 17/18
```
python scripts/evaluate_retrieval.py
FAIL  What information is kept about assets pledged to secure a loan?
17/18 checks passed (top_k=5, min_score=0.63)
```
All 12 in-scope questions except this one retrieve the expected entities; all 6 off-topic
questions retrieve nothing. The miss is a known limitation (wording differs from "Collateral").

### 6–16. Local API — PASS
```
uvicorn app.main:app --port 8010      (port 8000 was used by another process on this machine)
INFO:     Uvicorn running on http://127.0.0.1:8010
```

| Request | HTTP | Observed |
|---|---|---|
| `GET /health` | 200 | `{"status":"ok","indexed_chunks":168,"indexed_entities":27,"llm_model":"gpt-4.1-mini","llm_configured":true}` |
| `GET /docs` | 200 | Swagger UI |
| `/ask` "What are the core attributes of the Account entity?" | 200 | 28 attributes with types, "partial list … total 120 attributes"; sources: Account overview, referenced_by, 5 attribute chunks (scores 0.78–0.81) |
| `/ask` "How does a Contact relate to an Account?" | 200 | `Contact.parentCustomerId -> Account.accountId`, `Contact.employerId -> Account.accountId`, reverse `Account.primaryContactId -> Contact.contactId` |
| `/ask` "How does Contact relate to Organization?" | 200 | "does not contain a direct relationship"; indirect via `ContactOnboardingFromProspect.contactId` / `.organizationId` |
| `/ask` "Which entity stores the products a customer holds with the bank?" | 200 | FinancialProduct (`FinancialProduct:overview`, semantic, 0.742) |
| `/ask` "What is the capital of France?" | 200 | fixed "not enough information" answer, `sources: []`, 0.0 s (no LLM call) |
| `/ask` "Which bank offers the best interest rate for savings?" | 200 | Bank chunks retrieved (name match), LLM answer: "does not contain enough information … no information about interest rates" |
| `/retrieve` "What is collateral?" | 200 | `Collateral:overview` (entity_name), `Collateral:attributes:1` (semantic) |
| `/ask` `""`, `"   "`, 501 chars, `{}` | 422 | validation errors |

### 17. Missing OpenAI key — PASS
```
OPENAI_API_KEY= uvicorn app.main:app --port 8011
GET /health -> "llm_configured": false
POST /ask "What is an Account?" -> 503 {"detail":"OPENAI_API_KEY is not set, so no answer can be generated. Use POST /retrieve to see the retrieved context."}
POST /ask off-topic -> 200 (abstains without LLM)
POST /retrieve -> 200
```
Also verified in Docker (`docker run` without `-e OPENAI_API_KEY`) → same 503.

### 18. Missing index — PASS
```
CHROMA_DIR=<empty folder> uvicorn app.main:app --port 8012
RuntimeError: No index found in <empty folder>. Run: python scripts/build_index.py
ERROR:    Application startup failed. Exiting.
```

### 19. Answer facts vs. data — PASS
Script parsed the `/ask` answers and compared them with `load_cdm_entities()`:
```
claimed: 28          (Account attributes named in the answer)
not in data: []
type mismatches: []
relationship ('Contact', 'parentCustomerId', 'Account', 'accountId') exists
relationship ('Contact', 'employerId', 'Account', 'accountId') exists
relationship ('Account', 'primaryContactId', 'Contact', 'contactId') exists
relationship ('ContactOnboardingFromProspect', 'contactId', 'Contact', 'contactId') exists
relationship ('ContactOnboardingFromProspect', 'organizationId', 'Organization', 'organizationId') exists
```
This covers the demo answers observed; it does not prove every possible answer is correct.

### 20–21. Docker — PASS
```
docker build -t cdm-rag-api .                         -> exit 0; build log: "Indexed 168 chunks into /app/chroma_db"
docker images cdm-rag-api                             -> 669MB
docker run -d --rm -p 8020:8000 -e OPENAI_API_KEY cdm-rag-api
GET  /health  -> {"status":"ok","indexed_chunks":168,"indexed_entities":27,...,"llm_configured":true}
GET  /docs    -> HTTP 200
POST /ask "How does a Contact relate to an Account?" -> entities ['Contact','Account'], answer contains parentCustomerId and employerId
POST /ask "What is the capital of France?"          -> sources [], "The indexed CDM context does not contain enough information"
docker exec <container> whoami                      -> appuser
```

### 22. Docker without network — PASS
Tested on the image built from commit `9a77196` (same runtime code as `d32bc4e`, which only
changed formatting in scripts/tests and the README).
```
docker run -d --rm --network none -e OPENAI_API_KEY cdm-rag-api
```
- Before adding `ENV HF_HUB_OFFLINE=1`: startup took ~146 s (repeated attempts to reach huggingface.co).
- After: startup ~9 s, 0 network retries logged.
- `GET /health` 200; `POST /retrieve` 200; off-topic `/ask` 200;
  `/ask` needing OpenAI → 503 `OpenAI request failed (APIConnectionError). Use POST /retrieve ...`

### 23. Secrets and ignored files — PASS
```
git ls-files | grep -v ^data/cdm/ | xargs grep -nIE "sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY\s*=\s*\S+"
```
Only placeholders (`sk-...`) in the README, a comment in the Dockerfile and
`os.getenv("OPENAI_API_KEY")` in `app/config.py`. No key-like strings in `data/cdm`.
`git check-ignore`: `.env`, `chroma_db/`, `.venv/` are ignored; none are tracked.
`.dockerignore` excludes `.env`, `.venv`, `chroma_db`.

### 24. LaTeX presentation — NOT VERIFIED
`pdflatex`, `xelatex` and `latexmk` are not installed on this machine, and by decision only the
`.tex` source is delivered. No PDF exists, so page count and overflowing text were **not** checked.

Command to compile (from `docs/`):
```
pdflatex presentation.tex && pdflatex presentation.tex        # expect 3 pages
```

What was checked instead (a script, not a LaTeX run):
```
python check_tex.py presentation.tex
frames: 3 | environments balanced: True | braces balanced: True
possibly unescaped _ : [] | unescaped & : [] | unescaped # : []
```
