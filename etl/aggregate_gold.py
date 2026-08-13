from collections import defaultdict
from datetime import datetime, timezone
from db.database import SessionLocal, SilverOrder, GoldMetric, init_db


def aggregate_gold(tenant_id: str | None = None):
    """Reads all Silver rows (optionally filtered to one tenant) and computes
    a fixed set of summary metrics into gold_metrics.

    Metrics computed:
      - revenue_by_month      : total amount_usd, keyed by order_month (e.g. "2026-03")
      - aov_by_month          : average order value (amount_usd), keyed by order_month
      - guest_vs_registered   : order count, keyed by "guest" / "registered"
      - order_count_by_tier   : order count, keyed by order_value_tier ("low"/"medium"/"high")

    Idempotent via clear-and-reload: existing Gold rows for this tenant (or
    all tenants, if none given) are deleted first, then rebuilt fresh from
    current Silver data. Safe to re-run any time Silver changes.
    """
    session = SessionLocal()
    try:
        silver_query = session.query(SilverOrder)
        if tenant_id:
            silver_query = silver_query.filter(SilverOrder.tenant_id == tenant_id)
        silver_rows = silver_query.all()

        if not silver_rows:
            print("No Silver rows found. Nothing to aggregate.")
            return

        # Clear existing Gold rows for this scope before reloading
        gold_delete_query = session.query(GoldMetric)
        if tenant_id:
            gold_delete_query = gold_delete_query.filter(GoldMetric.tenant_id == tenant_id)
        deleted_count = gold_delete_query.delete()

        # Group rows by tenant so a multi-tenant future doesn't mix numbers together
        rows_by_tenant = defaultdict(list)
        for row in silver_rows:
            rows_by_tenant[row.tenant_id].append(row)

        now = datetime.now(timezone.utc)
        new_metrics = []

        for this_tenant_id, rows in rows_by_tenant.items():
            # --- revenue_by_month + aov_by_month ---
            revenue_by_month = defaultdict(float)
            count_by_month = defaultdict(int)
            for row in rows:
                if row.order_month is None or row.amount_usd is None:
                    continue
                revenue_by_month[row.order_month] += row.amount_usd
                count_by_month[row.order_month] += 1

            for month, total in revenue_by_month.items():
                new_metrics.append(GoldMetric(
                    tenant_id=this_tenant_id,
                    metric_name="revenue_by_month",
                    metric_key=month,
                    metric_value=round(total, 2),
                    computed_at=now,
                ))
                aov = total / count_by_month[month] if count_by_month[month] else 0.0
                new_metrics.append(GoldMetric(
                    tenant_id=this_tenant_id,
                    metric_name="aov_by_month",
                    metric_key=month,
                    metric_value=round(aov, 2),
                    computed_at=now,
                ))

            # --- guest_vs_registered ---
            guest_count = sum(1 for row in rows if row.is_guest_checkout)
            registered_count = sum(1 for row in rows if not row.is_guest_checkout)
            new_metrics.append(GoldMetric(
                tenant_id=this_tenant_id,
                metric_name="guest_vs_registered",
                metric_key="guest",
                metric_value=float(guest_count),
                computed_at=now,
            ))
            new_metrics.append(GoldMetric(
                tenant_id=this_tenant_id,
                metric_name="guest_vs_registered",
                metric_key="registered",
                metric_value=float(registered_count),
                computed_at=now,
            ))

            # --- order_count_by_tier ---
            count_by_tier = defaultdict(int)
            for row in rows:
                if row.order_value_tier:
                    count_by_tier[row.order_value_tier] += 1
            for tier, count in count_by_tier.items():
                new_metrics.append(GoldMetric(
                    tenant_id=this_tenant_id,
                    metric_name="order_count_by_tier",
                    metric_key=tier,
                    metric_value=float(count),
                    computed_at=now,
                ))

        session.add_all(new_metrics)
        session.commit()
        print(
            f"Gold aggregation complete: {len(new_metrics)} metrics computed, "
            f"{deleted_count} old metrics cleared first."
        )

    except Exception as e:
        session.rollback()
        print(f"Error during Gold aggregation: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    aggregate_gold()