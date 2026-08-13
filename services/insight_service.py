# Core service for insights
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rag.retrieval import search

app = FastAPI(title="Insighterz Insight Service - RAG MVP")


class QuestionRequest(BaseModel):
    question: str
    tenant_id: str
    n_results: int = 5


class RetrievedItem(BaseModel):
    text: str
    metadata: dict
    similarity_distance: float


class QuestionResponse(BaseModel):
    question: str
    tenant_id: str
    results: list[RetrievedItem]


@app.get("/health")
def health_check():
    """Simple check to confirm the service is running."""
    return {"status": "ok"}


@app.post("/insights/qualitative", response_model=QuestionResponse)
def ask_qualitative_question(request: QuestionRequest):
    """
    Handles qualitative/text questions (e.g. 'why are customers unhappy?')
    by running tenant-scoped semantic search over the RAG collection.

    Structured/numeric questions (e.g. 'what was total revenue last month?')
    are NOT handled here — those go through the existing SQL-over-Gold-layer
    path elsewhere in the Insight Service, per the architecture split.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if not request.tenant_id.strip():
        raise HTTPException(status_code=400, detail="tenant_id is required.")

    results = search(
        question=request.question,
        tenant_id=request.tenant_id,
        n_results=request.n_results
    )

    return QuestionResponse(
        question=request.question,
        tenant_id=request.tenant_id,
        results=results
    )