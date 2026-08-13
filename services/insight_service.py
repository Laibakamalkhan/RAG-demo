# Core service for insights
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from rag.retrieval import search
from rag.query_planner import plan_query
from etl.gold_queries import get_metric

app = FastAPI(title="Insighterz Insight Service - RAG MVP")

FALLBACK_MESSAGE = "I don't have that specific data yet. Try asking about revenue, average order value, or guest vs. registered checkouts for a specific month."


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


class MetricLookupRequest(BaseModel):
    metric_name: str
    metric_key: str
    tenant_id: str


class MetricResponse(BaseModel):
    metric_name: str
    metric_key: str
    tenant_id: str
    value: float | None


class MetricResult(BaseModel):
    metric_name: str
    metric_key: str
    value: float


class AskResponse(BaseModel):
    question: str
    tenant_id: str
    route: str                              # "quantitative" | "qualitative" | "unknown"
    metric: MetricResult | None = None       # populated only when route == "quantitative"
    results: list[RetrievedItem] | None = None  # populated only when route == "qualitative"
    message: str | None = None               # populated only when route == "unknown"


def _validate_request(question: str, tenant_id: str):
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if not tenant_id.strip():
        raise HTTPException(status_code=400, detail="tenant_id is required.")


@app.get("/health")
def health_check():
    """Simple check to confirm the service is running."""
    return {"status": "ok"}


@app.post("/insights/qualitative", response_model=QuestionResponse)
def ask_qualitative_question(request: QuestionRequest):
    """
    Handles qualitative/text questions (e.g. 'why are customers unhappy?')
    by running tenant-scoped semantic search over the RAG collection.

    Kept as a standalone endpoint (alongside /insights/ask) so you can debug
    the RAG path in isolation from the planner.
    """
    _validate_request(request.question, request.tenant_id)

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


@app.post("/insights/quantitative", response_model=MetricResponse)
def ask_quantitative_question(request: MetricLookupRequest):
    """
    Direct lookup of a single Gold metric, bypassing the planner entirely.
    Kept as a standalone endpoint (alongside /insights/ask) so you can debug
    the Gold path in isolation -- e.g. to confirm a bad /insights/ask answer
    is a planner bug and not a data bug.
    """
    value = get_metric(
        metric_name=request.metric_name,
        metric_key=request.metric_key,
        tenant_id=request.tenant_id,
    )
    return MetricResponse(
        metric_name=request.metric_name,
        metric_key=request.metric_key,
        tenant_id=request.tenant_id,
        value=value,
    )


@app.post("/insights/ask", response_model=AskResponse)
def ask(request: QuestionRequest):
    """
    Unified entry point: takes a natural-language question, runs the query
    planner to decide the route, then fetches the answer from either the
    Gold layer (quantitative) or RAG search (qualitative). Always returns
    one consistent response shape -- the caller doesn't need to know which
    path was used internally.
    """
    _validate_request(request.question, request.tenant_id)

    plan = plan_query(request.question, request.tenant_id)
    route = plan.get("route", "unknown")

    if route == "quantitative":
        value = get_metric(
            metric_name=plan["metric_name"],
            metric_key=plan["metric_key"],
            tenant_id=request.tenant_id,
        )
        if value is None:
            # Planner said this metric/key was in the whitelist, but the
            # lookup still came back empty -- treat as a planner failure
            # rather than trusting a half-broken plan.
            return AskResponse(
                question=request.question,
                tenant_id=request.tenant_id,
                route="unknown",
                message=FALLBACK_MESSAGE,
            )
        return AskResponse(
            question=request.question,
            tenant_id=request.tenant_id,
            route="quantitative",
            metric=MetricResult(
                metric_name=plan["metric_name"],
                metric_key=plan["metric_key"],
                value=value,
            ),
        )

    if route == "qualitative":
        results = search(
            question=request.question,
            tenant_id=request.tenant_id,
            n_results=request.n_results,
        )
        return AskResponse(
            question=request.question,
            tenant_id=request.tenant_id,
            route="qualitative",
            results=results,
        )

    # route == "unknown" -- planner couldn't confidently classify the question
    return AskResponse(
        question=request.question,
        tenant_id=request.tenant_id,
        route="unknown",
        message=FALLBACK_MESSAGE,
    )