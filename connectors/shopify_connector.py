import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from db.database import SessionLocal, BronzeOrder, init_db

load_dotenv()

SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN")
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2024-10"
TENANT_ID = "shop_demo_001"  # matches the tenant_id used throughout your RAG system

GRAPHQL_URL = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json"

ORDERS_QUERY = """
{
  orders(first: 50) {
    edges {
      node {
        id
        name
        createdAt
        totalPriceSet {
          shopMoney {
            amount
            currencyCode
          }
        }
        customer {
          id
          firstName
          lastName
          email
        }
      }
    }
    pageInfo {
      hasNextPage
    }
  }
}
"""

def fetch_orders_from_shopify() -> dict:
    """Calls the Shopify GraphQL Admin API and returns the raw JSON response."""
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ACCESS_TOKEN
    }
    response = requests.post(
        GRAPHQL_URL,
        headers=headers,
        json={"query": ORDERS_QUERY}
    )
    response.raise_for_status()
    return response.json()

def save_to_bronze(raw_response: dict):
    """Writes each order in the raw response into the bronze_orders table, untouched."""
    session = SessionLocal()
    orders = raw_response["data"]["orders"]["edges"]

    saved_count = 0
    for edge in orders:
        order_node = edge["node"]
        order_id = order_node["id"]

        existing = session.get(BronzeOrder, order_id)
        if existing:
            print(f"Skipping {order_id} — already in Bronze.")
            continue

        bronze_record = BronzeOrder(
            order_id=order_id,
            tenant_id=TENANT_ID,
            raw_json=json.dumps(order_node),
            ingested_at=datetime.now(timezone.utc)
        )
        session.add(bronze_record)
        saved_count += 1

    session.commit()
    session.close()
    print(f"Saved {saved_count} new order(s) to Bronze.")

def run_connector():
    init_db()
    print("Fetching orders from Shopify...")
    raw_response = fetch_orders_from_shopify()
    save_to_bronze(raw_response)

if __name__ == "__main__":
    run_connector()