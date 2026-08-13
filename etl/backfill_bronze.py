import json
import os
from datetime import datetime, timezone
from db.database import SessionLocal, BronzeOrder, init_db


def backfill_bronze(file_path: str):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "records" in data:
        records = data["records"]
    elif isinstance(data, list):
        records = data
    else:
        print("Unrecognized JSON structure in the provided data file.")
        return

    session = SessionLocal()
    inserted_count = 0
    skipped_count = 0

    try:
        for record in records:
            order_id = record.get("order_id")
            tenant_id = record.get("tenant_id")
            order_name = record.get("order_name")

            original = record.get("original", {})
            derived = record.get("derived", {})

            existing = session.get(BronzeOrder, order_id)
            if existing:
                skipped_count += 1
                continue

            customer_email = original.get("customer_email")
            customer_name = original.get("customer_name") or ""

            name_parts = customer_name.split(" ", 1)
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            is_guest = derived.get("is_guest_checkout", False)

            if is_guest or not customer_email:
                customer = None
            else:
                customer = {
                    "firstName": first_name,
                    "lastName": last_name,
                    "email": customer_email
                }

            raw_payload = {
                "id": order_id,
                "name": order_name,
                "createdAt": original.get("created_at"),
                "totalPriceSet": {
                    "shopMoney": {
                        "amount": str(original.get("amount", "")),
                        "currencyCode": original.get("currency")
                    }
                },
                "customer": customer
            }

            bronze_order = BronzeOrder(
                order_id=order_id,
                tenant_id=tenant_id,
                raw_json=json.dumps(raw_payload),
                ingested_at=datetime.now(timezone.utc),
                source="shopify_augmented"
            )
            session.add(bronze_order)
            inserted_count += 1

        session.commit()
        print(f"Backfill complete: {inserted_count} inserted, {skipped_count} skipped.")

    except Exception as e:
        session.rollback()
        print(f"Error during backfill: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    file_path = os.path.join("data", "rag_ready_orders.json")
    backfill_bronze(file_path)