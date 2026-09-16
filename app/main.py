"""FastAPI app. Run with:  uvicorn app.main:app --port 8000"""

from contextlib import asynccontextmanager
from typing import Annotated

import chromadb
from fastapi import Depends, FastAPI, HTTPException, Request
from openai import OpenAI
from pydantic import BaseModel, StringConstraints

from app import config
from app.embeddings import Embedder
from app.rag_service import AskResponse, LLMUnavailableError, RagService
from app.retriever import RetrievedChunk, Retriever
from app.vector_store import get_collection

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class QuestionRequest(BaseModel):
    question: Question


class RetrieveResponse(BaseModel):
    question: str
    retrieved_entities: list[str]
    chunks: list[RetrievedChunk]


class HealthResponse(BaseModel):
    status: str
    indexed_chunks: int
    indexed_entities: int
    llm_model: str
    llm_configured: bool


def build_rag_service() -> RagService:
    """Load the index and the embedding model once, at startup."""
    collection = get_collection(chromadb.PersistentClient(path=str(config.CHROMA_DIR)), config.COLLECTION_NAME)
    if collection.count() == 0:
        raise RuntimeError(f"No index found in {config.CHROMA_DIR}. Run: python scripts/build_index.py")

    retriever = Retriever(collection, Embedder(config.EMBEDDING_MODEL),
                          config.RETRIEVAL_TOP_K, config.RETRIEVAL_MIN_SCORE)
    openai_client = None
    if config.OPENAI_API_KEY:
        openai_client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=config.OPENAI_TIMEOUT_SECONDS)
    return RagService(retriever, openai_client, config.OPENAI_MODEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rag_service = build_rag_service()
    yield


app = FastAPI(
    title="CDM RAG API",
    description="Ask natural-language questions about Microsoft Common Data Model banking entities.",
    lifespan=lifespan,
)


def get_rag_service(request: Request) -> RagService:
    return request.app.state.rag_service


RagServiceDep = Annotated[RagService, Depends(get_rag_service)]


# Endpoints are plain "def": retrieval and the OpenAI call are blocking,
# so FastAPI runs them in a thread pool instead of blocking the event loop.

@app.get("/health")
def health(rag_service: RagServiceDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        indexed_chunks=rag_service.retriever.collection.count(),
        indexed_entities=len(rag_service.retriever.entity_names),
        llm_model=rag_service.model,
        llm_configured=rag_service.client is not None,
    )


@app.post("/ask")
def ask(request: QuestionRequest, rag_service: RagServiceDep) -> AskResponse:
    try:
        return rag_service.answer(request.question)
    except LLMUnavailableError as error:
        raise HTTPException(status_code=503, detail=f"{error} Use POST /retrieve to see the retrieved context.")


@app.post("/retrieve")
def retrieve(request: QuestionRequest, rag_service: RagServiceDep) -> RetrieveResponse:
    """Retrieval only, without the LLM. Useful for debugging and when OpenAI is unavailable."""
    results = rag_service.retriever.retrieve(request.question)
    entities = list(dict.fromkeys(r.chunk.entity_name for r in results))
    return RetrieveResponse(question=request.question, retrieved_entities=entities, chunks=results)
