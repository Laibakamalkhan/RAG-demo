# Insighterz — AI-Powered E-Commerce Analytics (MVP)

Insighterz is an AI-powered analytics tool for e-commerce stores. Ask it a
plain-English question and it automatically figures out whether you need a
**number** (revenue, average order value, etc.) or a **text answer** (why
customers are unhappy, common complaints, etc.) — and routes the question
to the right place.

This repo is the MVP: connectors + ETL pipeline (Bronze/Silver/Gold) + a
RAG (retrieval-augmented generation) system + a lightweight local AI query
planner that decides which path a question should take.

> A separate, much larger real-product architecture (multi-tenant, Postgres,
> Redis/Celery workers, React SPA, full AI Insight Engine) exists as a
> future direction — this repo is **not** that. This is strictly the MVP.

---

## How it works

Two parallel answer paths, tied together by one query planner:

- **Structured/numeric questions** (*"what was total revenue last month?"*)
  → looked up from a pre-aggregated **Gold** layer (SQLite)
- **Qualitative/text questions** (*"why are customers unhappy?"*)
  → semantic search (embed → retrieve) over unstructured text (reviews,
  support tickets) stored in a **Chroma** vector database

A small local LLM (`gemma2:2b` via [Ollama](https://ollama.com)) reads the
question and decides which path to take. Its answer is **never trusted
blindly** — it's validated against a live whitelist of metrics that
actually exist in the data before being used, so it can't hallucinate a
number that doesn't exist.

```
question
   │
   ▼
Query Planner (gemma2:2b) ──► validated against real Gold metrics
   │
   ├── quantitative ──► Gold layer lookup (SQLite)
   │
   └── qualitative  ──► semantic search (Chroma + embeddinggemma)
```

---

## Data

- **Real data:** pulled live from the Shopify GraphQL Admin API
  (`connectors/shopify_connector.py`)
- **Synthetic-augmented data:** 100 records shaped like real Shopify orders,
  with fabricated (but realistic) product descriptions, reviews, and
  support tickets — used because the connected test store currently has
  very limited real order/review volume. Every record clearly separates
  `original` (real-shaped fields) from `synthetic` (fabricated fields), and
  every Bronze row is tagged with a `source` column
  (`shopify_live` vs `shopify_augmented`) so provenance is never lost.

---

## Tech stack

| Layer | Tech |
|---|---|
| API | FastAPI |
| Relational DB | SQLite (via SQLAlchemy) |
| Vector DB | Chroma (embedded/local, `PersistentClient`) |
| Embeddings model | Ollama — `embeddinggemma:latest` |
| Query planner model | Ollama — `gemma2:2b` (JSON-mode output) |
| Tenant isolation | `tenant_id` filter on every Chroma and SQL query |

---

## Project structure

```
insighterz-rag/
├── connectors/
│   └── shopify_connector.py     # Pulls live orders from Shopify -> Bronze
├── db/
│   └── database.py               # SQLAlchemy models: Bronze/Silver/Gold
├── etl/
│   ├── backfill_bronze.py        # One-time: loads synthetic dataset -> Bronze
│   ├── transform_silver.py       # Bronze -> Silver (cleaned, normalized)
│   ├── aggregate_gold.py         # Silver -> Gold (pre-computed metrics)
│   └── gold_queries.py           # get_metric() / list_available_metrics()
├── rag/
│   ├── embeddings.py             # Ollama embedding calls (doc + query prefixes)
│   ├── retrieval.py              # Tenant-scoped semantic search over Chroma
│   └── query_planner.py          # gemma2:2b routing + whitelist validation
├── services/
│   └── insight_service.py        # FastAPI app: /insights/ask + debug endpoints
├── ingestion/
│   └── load_orders.py            # Embeds + loads the dataset into Chroma
├── pipeline_runner.py             # One-command setup: connector -> Bronze -> Silver -> Gold -> Chroma
├── tests/
│   ├── test_retrieval.py
│   ├── test_etl.py
│   └── test_query_planner.py
├── data/
│   └── rag_ready_orders.json     # 100 synthetic-augmented records
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Setup

### 1. Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com) installed and running locally
- A Shopify test store + Admin API access token (optional — the pipeline
  still works from the synthetic dataset alone if this isn't set up)

### 2. Pull the required Ollama models
```bash
ollama pull embeddinggemma:latest
ollama pull gemma2:2b
```

### 3. Clone and set up the environment
```bash
git clone <this-repo-url>
cd insighterz-rag
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 4. Configure environment variables
Copy `.env.example` to `.env` and fill in your own values:
```bash
cp .env.example .env
```

| Variable | Required? | Notes |
|---|---|---|
| `SHOPIFY_SHOP_DOMAIN` | Optional | Only needed for the live connector step |
| `SHOPIFY_ACCESS_TOKEN` | Optional | Only needed for the live connector step |
| `CHROMA_DB_PATH` | Optional | Defaults to `./chroma_data` |
| `SQLITE_DB_PATH` | Optional | Defaults to `./insighterz_etl.db` |

### 5. Run the full pipeline (one command)
```bash
python -m pipeline_runner
```
This chains: Shopify connector → Bronze backfill → Silver transform →
Gold aggregation → Chroma ingestion. Safe to re-run any time — every step
is idempotent.

### 6. Start the API
```bash
uvicorn services.insight_service:app --reload
```
Open `http://127.0.0.1:8000/docs` to try it interactively.

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /insights/ask` | Main endpoint — ask any natural-language question, get routed automatically |
| `POST /insights/quantitative` | Direct Gold metric lookup, bypassing the planner (debugging) |
| `POST /insights/qualitative` | Direct semantic search, bypassing the planner (debugging) |
| `GET /health` | Health check |

Example — `POST /insights/ask`:
```json
{
  "question": "What was total revenue in January 2026?",
  "tenant_id": "shop_demo_001"
}
```
```json
{
  "route": "quantitative",
  "metric": {
    "metric_name": "revenue_by_month",
    "metric_key": "2026-01",
    "value": 26633.06
  }
}
```

---

## Running tests

```bash
pytest -v
```

- `test_etl.py` — checks Bronze/Silver/Gold stay numerically consistent
  with each other (row counts, revenue sums, etc.)
- `test_query_planner.py` — tests the planner's validation logic against
  mocked model responses (valid output, hallucinated metrics, malformed
  JSON) — the live model isn't called here since its output isn't
  deterministic
- `test_retrieval.py` — live integration tests against Chroma + Ollama
  (skips gracefully instead of failing if Ollama isn't running)

---

## Current scope (MVP)

**In scope:**
- Single demo tenant (`shop_demo_001`)
- Shopify orders only (`first: 50`, no pagination)
- Local models only (Ollama) — no external API costs

**Out of scope for this MVP (planned for the full product):**
- WooCommerce connector
- Multi-tenant support
- Clarifying-question flow in the planner (fixed fallback message for now)
- Row-level security / Postgres / Redis-Celery workers / React SPA
- Claude-based AI Insight Engine (this MVP substitutes a local `gemma2:2b`
  planner as a deliberate simplification)
