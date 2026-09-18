# Implementation Plan

This document explains **why** the solution is designed this way. `README.md` describes how to
run it; `VALIDATION_REPORT.md` records what was executed and verified.

## 1. Objective and Scope

The task was a RAG-based API that answers natural-language questions about the Microsoft
Common Data Model (CDM), focused on banking, with answers grounded in retrieved definitions.

The repository contains two banking models. I indexed the **Banking accelerator**
(`core/.../accelerators/financialServices/banking/`) because it extends the common business
entities (Account, Contact, Lead, Product) and its manifest declares 534 explicit
relationships. The alternative, `RetailBankingCoreDataModel`, is flat: its `Account` has one
attribute and its manifest has no relationships, so "What are the core attributes of Account?"
could not be answered from it.

The indexed scope is **27 entities**: the 24 banking entities plus `Organization`,
`BusinessUnit` and `Currency`, which the banking model references. Their 42 files come from a
pinned commit (`dd21d715e05ebf740a11356c80b5c3b4c38a89c2`) and are committed here, so
indexing, tests and Docker builds are reproducible and offline. The scope is bounded
deliberately: broad enough for attribute, relationship and semantic questions, small enough to
verify answers against the source data.

## 2. Architecture

```
Microsoft CDM files (data/cdm)
    -> CDM parser (entities, attributes, relationships)
    -> normalized entity documents (168 text chunks)
    -> embeddings (local model)
    -> vector store (Chroma, cosine)
    -> retriever (entity-name match + semantic search)
    -> retrieved context (numbered, with source paths)
    -> LLM (constrained prompt)
    -> FastAPI response (answer + sources)
```

Indexing and answering are separate: `scripts/build_index.py` builds the index once, and the
API loads it with the embedding model at startup. Each stage is a small module with one
responsibility and no orchestration framework, which keeps the flow easy to test and explain.

## 3. Data Ingestion and CDM Modeling

Each entity file becomes an `Entity` with name, description, attributes and relationships.
Source paths are kept per entity and per attribute, so answers can be traced to the exact file.

- **Attributes** come from `hasAttributes`, usually inside `attributeGroupReference.members`,
  in three shapes: a `dataType` string, a `dataType` object (its `dataTypeReference`), and
  entity references recorded as `lookup -> Target`, keeping all options when polymorphic.
- **Inheritance** is resolved, because a banking entity declares only what it adds. The
  `extendsEntity` moniker (`base_Account/Account`) is resolved through the folder's
  `_allImports.cdm.json` up to the root type, then attributes are merged downwards so a child
  overrides a parent attribute of the same name. `Account` resolves to 120 attributes from
  four files.

Scope assumption: system attributes inherited from `CdsStandard` (`createdOn` and similar) are
defined outside these files and are not listed.

## 4. Retrieval Strategy

**Entity-aware documents.** An entity is a natural unit of meaning in structured data, while
fixed-size chunks would mix entities or lose the entity name. Each entity yields an `overview`
chunk (description, inheritance, outgoing relationships), a `referenced_by` chunk (incoming
relationships) and `attributes` chunks of 12 attributes each, all starting with
`Entity: <name>`. Three types instead of one was a measured constraint: a single chunk per
entity reached 700 tokens against the model limit of 512. The largest is now 416 tokens, and
the build fails if a chunk would be truncated.

**Embedding model and vector store.** `BAAI/bge-small-en-v1.5` runs locally on CPU, is small
(384 dimensions) and accepts 512 tokens; `all-MiniLM-L6-v2` truncates at 256 and would
silently cut attribute lists. Queries use the instruction prefix from the model card. Chroma
stores vectors, text and metadata together and filters by metadata, which the retriever needs.
A local store is sufficient at this size.

**Two steps.** If a question names an indexed entity (case-insensitive, allowing a plural "s"
and spaced CamelCase such as "financial product"), the `overview` and `referenced_by` chunks
of up to three named entities are always included. This was added because pure vector search
returned only attribute chunks for "How does a Contact relate to an Account?", leaving out the
relationships. Semantic search then adds the top 5 hits scoring at least 0.63, keeping the
context near ten chunks. The threshold comes from a small sample of 12 in-scope and 12
off-topic questions (in-scope top-1 at least 0.66, off-topic at most 0.61); given that sample
size it is a first filter, not a tuned constant, and both values are configurable.

## 5. Relationship Handling

Relationships come from the `relationships` arrays of the official manifests, which name
source entity, source attribute, target entity and target attribute. The manifests also cover
relationships introduced by inherited attributes and well-known attribute groups, which the
entity files do not show without a full CDM resolver. Only relationships starting at an
indexed entity are kept, and duplicates across manifests are removed.

Each entity stores outgoing and incoming relationships, written into the chunk text as
explicit lines (`Contact.parentCustomerId -> Account.accountId`). Ownership and audit links
(`createdBy`, `ownerId`, …) are summarized in one line so they do not crowd out business
relationships. A question naming two entities retrieves the chunks of both, so a relationship
is available from either direction.

A graph database was unnecessary for 27 entities and mostly one-hop questions. It would help
with reliable multi-hop questions ("how is Collateral connected to Contact?") or a much larger
scope.

## 6. Grounding and Reliability

The retrieved context is the only permitted source. Blocks are numbered and labeled with
entity, chunk type and source path, and generation runs at temperature 0. The prompt requires
the model to use only that context, invent no entities, attributes or relationships, name the
linking attribute for relationship questions, describe an indirect path only if every step is
in the context, and say when an attribute list is partial.

When retrieval returns nothing, the API answers "not enough information" **without calling the
LLM**. When chunks are retrieved but do not answer the question, the prompt requires the model
to say so; this second layer matters because a similarity threshold alone cannot separate
near-domain questions. Responses include `sources` (citation number, chunk id, entity, chunk
type, source path, match type, score), and `POST /retrieve` exposes retrieval without the LLM.
These measures reduce hallucination but do not eliminate it.

## 7. Testing and Validation

58 tests run in seconds without network or LLM calls, using a deterministic keyword embedder,
an in-memory vector store and a fake OpenAI client. They cover the parser (attribute shapes,
inheritance, duplicate relationships, error cases), chunk construction, vector store round
trips, retrieval (name matching, relationship questions, threshold, off-topic questions),
grounding (no LLM call without context, prompt and temperature) and the API, plus facts in the
committed CDM data that the demo relies on.

`scripts/evaluate_retrieval.py` runs 12 in-scope and 6 off-topic questions against the real
index and passes 17 of 18. It is a small hand-written check for retrieval regressions, not a
benchmark. Execution results are in `VALIDATION_REPORT.md`.

## 8. Limitations and Possible Improvements

- Bounded scope: 27 of many CDM entities; inherited system attributes are not listed.
- Retrieval can miss wording far from the CDM text: "assets pledged to secure a loan" does not
  find `Collateral` (the documented evaluation failure).
- Entity names that are common words ("bank", "product") trigger name matching and add
  context; the prompt then decides whether it answers.
- Attribute lists can be partial for large entities, which the answer states.
- The evaluation set is small, so retrieval quality is only loosely measured.
- One-hop relationships only; no graph traversal, hybrid search or reranker.
- `POST /ask` depends on the OpenAI API; there is no authentication or rate limiting.

Natural next steps: a larger evaluation set that also checks the names an answer mentions,
hybrid or reranked retrieval for the vocabulary mismatch, and graph traversal if multi-hop
questions become relevant.
