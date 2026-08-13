# Tests for the ETL pipeline: checks that Bronze -> Silver -> Gold stay
# consistent with each other. These run against whatever database is
# currently configured (via .env / SQLITE_DB_PATH) -- run the pipeline
# (python -m pipeline_runner) before running these tests.
from db.database import SessionLocal, BronzeOrder, SilverOrder, GoldMetric


def test_bronze_and_silver_row_counts_match():
    """Every Bronze row should have produced exactly one Silver row --
    Silver shouldn't silently drop or duplicate rows during transform."""
    session = SessionLocal()
    try:
        bronze_count = session.query(BronzeOrder).count()
        silver_count = session.query(SilverOrder).count()
        assert bronze_count > 0, "No Bronze rows found -- run the pipeline first."
        assert bronze_count == silver_count
    finally:
        session.close()


def test_gold_revenue_matches_raw_silver_sum():
    """Every revenue_by_month Gold value should exactly equal summing
    amount_usd over the matching Silver rows -- catches aggregation bugs."""
    session = SessionLocal()
    try:
        revenue_metrics = (
            session.query(GoldMetric)
            .filter(GoldMetric.metric_name == "revenue_by_month")
            .all()
        )
        assert len(revenue_metrics) > 0, "No revenue_by_month metrics found -- run the pipeline first."

        for metric in revenue_metrics:
            silver_rows = (
                session.query(SilverOrder)
                .filter(
                    SilverOrder.tenant_id == metric.tenant_id,
                    SilverOrder.order_month == metric.metric_key,
                )
                .all()
            )
            expected = round(sum(r.amount_usd for r in silver_rows), 2)
            assert metric.metric_value == expected, (
                f"revenue_by_month for {metric.metric_key} was {metric.metric_value}, "
                f"expected {expected}"
            )
    finally:
        session.close()


def test_gold_aov_matches_raw_silver_average():
    """Every aov_by_month Gold value should equal the average amount_usd
    over the matching Silver rows for that month."""
    session = SessionLocal()
    try:
        aov_metrics = (
            session.query(GoldMetric)
            .filter(GoldMetric.metric_name == "aov_by_month")
            .all()
        )
        assert len(aov_metrics) > 0, "No aov_by_month metrics found -- run the pipeline first."

        for metric in aov_metrics:
            silver_rows = (
                session.query(SilverOrder)
                .filter(
                    SilverOrder.tenant_id == metric.tenant_id,
                    SilverOrder.order_month == metric.metric_key,
                )
                .all()
            )
            expected = round(sum(r.amount_usd for r in silver_rows) / len(silver_rows), 2)
            assert metric.metric_value == expected

    finally:
        session.close()


def test_gold_guest_vs_registered_totals_match_silver_count():
    """guest + registered counts in Gold should add up to the total
    number of Silver rows for that tenant -- every order counted once."""
    session = SessionLocal()
    try:
        guest_metric = (
            session.query(GoldMetric)
            .filter(GoldMetric.metric_name == "guest_vs_registered", GoldMetric.metric_key == "guest")
            .first()
        )
        registered_metric = (
            session.query(GoldMetric)
            .filter(GoldMetric.metric_name == "guest_vs_registered", GoldMetric.metric_key == "registered")
            .first()
        )
        assert guest_metric is not None
        assert registered_metric is not None

        total_silver = session.query(SilverOrder).filter(
            SilverOrder.tenant_id == guest_metric.tenant_id
        ).count()

        assert guest_metric.metric_value + registered_metric.metric_value == total_silver
    finally:
        session.close()


def test_gold_metric_lookup_returns_none_for_unknown_key():
    """get_metric() should return None (not raise) for a metric/key
    combination that doesn't exist -- required for planner fallback logic."""
    from etl.gold_queries import get_metric
    result = get_metric("revenue_by_month", "1999-01", "shop_demo_001")
    assert result is None