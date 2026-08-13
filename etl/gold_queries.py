from db.database import SessionLocal, GoldMetric


def get_metric(metric_name: str, metric_key: str, tenant_id: str) -> float | None:
    """Looks up a single pre-computed Gold metric.

    Example: get_metric("revenue_by_month", "2026-01", "shop_demo_001") -> 26633.06

    Returns None if no matching row exists (unknown metric_name, unknown
    metric_key, or wrong tenant_id) — callers (including the query planner
    in Batch 5) should treat None as "no data for that", not crash on it.
    """
    session = SessionLocal()
    try:
        row = (
            session.query(GoldMetric)
            .filter(
                GoldMetric.metric_name == metric_name,
                GoldMetric.metric_key == metric_key,
                GoldMetric.tenant_id == tenant_id,
            )
            .first()
        )
        return row.metric_value if row else None
    finally:
        session.close()


def list_available_metrics(tenant_id: str) -> list[dict]:
    """Returns every distinct (metric_name, metric_key) pair that actually
    exists in Gold for this tenant. This is what Batch 5's query planner
    will use to build its whitelist dynamically — never hardcode the list
    of valid months/metrics, since it should always reflect real data.
    """
    session = SessionLocal()
    try:
        rows = (
            session.query(GoldMetric.metric_name, GoldMetric.metric_key)
            .filter(GoldMetric.tenant_id == tenant_id)
            .distinct()
            .all()
        )
        return [{"metric_name": name, "metric_key": key} for name, key in rows]
    finally:
        session.close()


if __name__ == "__main__":
    # Quick manual smoke test — run this file directly to sanity-check it works.
    TEST_TENANT = "shop_demo_001"

    print("Known metric, known key (expect a number):")
    print(get_metric("revenue_by_month", "2026-01", TEST_TENANT))

    print("\nKnown metric, unknown key (expect None):")
    print(get_metric("revenue_by_month", "1999-01", TEST_TENANT))

    print("\nUnknown metric entirely (expect None):")
    print(get_metric("nonexistent_metric", "whatever", TEST_TENANT))

    print("\nAll available metrics for this tenant:")
    for m in list_available_metrics(TEST_TENANT):
        print(m)