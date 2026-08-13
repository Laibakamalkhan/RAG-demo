import json
from datetime import datetime, timezone
from db.database import SessionLocal, BronzeOrder, SilverOrder, init_db


# Static placeholder FX rates (same values already used in the synthetic
# dataset's amount_usd field, reverse-engineered from data/rag_ready_orders.json).
# USD is the base currency, so its rate is 1.0.
FX_RATES_TO_USD = {
    "USD": 1.0,
    "CAD": 0.74,
    "EUR": 1.09,
    "GBP": 1.27,
}


def parse_created_at(raw_value: str) -> datetime | None:
    """Shopify sends timestamps like '2026-01-01T20:05:22Z'. Convert to a
    real Python datetime we can do date math on."""
    if not raw_value:
        return None
    # Python's fromisoformat doesn't like a trailing 'Z', so swap it for +00:00
    cleaned = raw_value.replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned)


def compute_order_value_tier(amount_usd: float) -> str:
    """Same thresholds already present in the synthetic dataset:
    low < $500, medium $500-$2000, high > $2000."""
    if amount_usd < 500:
        return "low"
    elif amount_usd <= 2000:
        return "medium"
    else:
        return "high"


def transform_bronze_row(bronze_row: BronzeOrder) -> SilverOrder | None:
    """Takes one raw Bronze row and turns it into a clean SilverOrder.
    Returns None if the row is malformed and should be skipped."""
    try:
        raw = json.loads(bronze_row.raw_json)
    except (json.JSONDecodeError, TypeError):
        print(f"Skipping {bronze_row.order_id}: raw_json is not valid JSON.")
        return None

    created_at = parse_created_at(raw.get("createdAt"))

    money = raw.get("totalPriceSet", {}).get("shopMoney", {})
    currency = money.get("currencyCode")
    amount_raw = money.get("amount")

    try:
        amount = float(amount_raw) if amount_raw not in (None, "") else 0.0
    except ValueError:
        amount = 0.0

    fx_rate = FX_RATES_TO_USD.get(currency, 1.0)  # unknown currency -> assume 1:1, don't crash
    amount_usd = round(amount * fx_rate, 2)

    customer = raw.get("customer")
    is_guest_checkout = customer is None

    if customer:
        first = customer.get("firstName") or ""
        last = customer.get("lastName") or ""
        customer_name = f"{first} {last}".strip() or None
        customer_email = customer.get("email")
    else:
        customer_name = None
        customer_email = None

    order_month = created_at.strftime("%Y-%m") if created_at else None
    order_weekday = created_at.strftime("%A") if created_at else None

    return SilverOrder(
        order_id=bronze_row.order_id,
        tenant_id=bronze_row.tenant_id,
        order_name=raw.get("name"),
        created_at=created_at,
        amount=amount,
        currency=currency,
        amount_usd=amount_usd,
        customer_name=customer_name,
        customer_email=customer_email,
        is_guest_checkout=is_guest_checkout,
        order_month=order_month,
        order_weekday=order_weekday,
        order_value_tier=compute_order_value_tier(amount_usd),
    )


def transform_silver(tenant_id: str | None = None):
    """Reads every Bronze row (optionally filtered to one tenant), converts
    each into a SilverOrder, and reloads the silver_orders table.

    Idempotent via clear-and-reload: for the given tenant (or all tenants,
    if none given), existing Silver rows are deleted first, then rebuilt
    fresh from current Bronze data. Safe to re-run any time Bronze changes.
    """
    session = SessionLocal()
    try:
        bronze_query = session.query(BronzeOrder)
        if tenant_id:
            bronze_query = bronze_query.filter(BronzeOrder.tenant_id == tenant_id)
        bronze_rows = bronze_query.all()

        if not bronze_rows:
            print("No Bronze rows found. Nothing to transform.")
            return

        # Clear existing Silver rows for this scope before reloading
        silver_delete_query = session.query(SilverOrder)
        if tenant_id:
            silver_delete_query = silver_delete_query.filter(SilverOrder.tenant_id == tenant_id)
        deleted_count = silver_delete_query.delete()

        inserted_count = 0
        skipped_count = 0

        for bronze_row in bronze_rows:
            silver_row = transform_bronze_row(bronze_row)
            if silver_row is None:
                skipped_count += 1
                continue
            session.add(silver_row)
            inserted_count += 1

        session.commit()
        print(
            f"Silver transform complete: {inserted_count} inserted, "
            f"{skipped_count} skipped, {deleted_count} old rows cleared first."
        )

    except Exception as e:
        session.rollback()
        print(f"Error during Silver transform: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    transform_silver()