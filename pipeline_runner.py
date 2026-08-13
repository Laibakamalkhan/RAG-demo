"""
One-command pipeline runner for a clean demo setup on a fresh DB.

Chains, in order:
  1. Shopify connector  -> pulls the 1 real live order into Bronze
  2. Bronze backfill     -> loads the 100 synthetic-augmented records into Bronze
  3. Silver transform    -> cleans/normalizes all Bronze rows into Silver
  4. Gold aggregation    -> computes summary metrics from Silver into Gold
  5. Chroma ingestion    -> embeds and stores the 100 records for RAG search

Order matters: Silver needs Bronze rows to exist first, Gold needs Silver
rows to exist first. Steps 1-4 are all safe to re-run (idempotent). Step 5
is skipped automatically if the Chroma collection already has data, since
re-embedding is slow and unnecessary once it's been done.

Run with:  python -m pipeline_runner
"""
import os
import chromadb
from dotenv import load_dotenv

from db.database import init_db
from connectors.shopify_connector import run_connector
from etl.backfill_bronze import backfill_bronze
from etl.transform_silver import transform_silver
from etl.aggregate_gold import aggregate_gold
from ingestion.load_orders import load_orders, CHROMA_DB_PATH, COLLECTION_NAME

load_dotenv()

DATA_PATH = os.path.join("data", "rag_ready_orders.json")


def step(title: str):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def run_pipeline():
    step("0/5  Initializing database (creates tables if missing)")
    init_db()
    print("Done.")

    step("1/5  Shopify connector (live order -> Bronze)")
    try:
        run_connector()
    except Exception as e:
        # Non-fatal: no internet / bad credentials shouldn't block the rest
        # of the demo setup, since the augmented dataset carries the demo.
        print(f"WARNING: live connector step failed, continuing anyway. Reason: {e}")

    step("2/5  Bronze backfill (100 synthetic-augmented records -> Bronze)")
    backfill_bronze(DATA_PATH)

    step("3/5  Silver transform (Bronze -> Silver)")
    transform_silver()

    step("4/5  Gold aggregation (Silver -> Gold)")
    aggregate_gold()

    step("5/5  Chroma ingestion (RAG embeddings)")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    existing_collections = [c.name for c in client.list_collections()]
    already_loaded = False
    if COLLECTION_NAME in existing_collections:
        collection = client.get_collection(COLLECTION_NAME)
        if collection.count() > 0:
            already_loaded = True

    if already_loaded:
        print(f"Chroma collection '{COLLECTION_NAME}' already has data -- skipping re-embedding.")
        print("(Delete the chroma_data folder first if you want to force a fresh re-embed.)")
    else:
        load_orders()

    step("Pipeline complete")
    print("Bronze, Silver, Gold, and Chroma are all set up. You can now run:")
    print("  uvicorn services.insight_service:app --reload")


if __name__ == "__main__":
    run_pipeline()