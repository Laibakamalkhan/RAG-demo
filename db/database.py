import os
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("SQLITE_DB_PATH", "./insighterz_etl.db")
engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class BronzeOrder(Base):
    """Raw, untouched JSON exactly as received from Shopify."""
    __tablename__ = "bronze_orders"

    order_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    raw_json = Column(Text, nullable=False)      # the full JSON response, stored as text
    ingested_at = Column(DateTime, nullable=False)
    source = Column(String, nullable=False, default="shopify_live")


class SilverOrder(Base):
    """Normalized, cleaned structured order data."""
    __tablename__ = "silver_orders"

    order_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    order_name = Column(String)
    created_at = Column(DateTime)
    amount = Column(Float)
    currency = Column(String)
    amount_usd = Column(Float)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    is_guest_checkout = Column(Boolean)
    order_month = Column(String)          # e.g. "2026-03"
    order_weekday = Column(String)        # e.g. "Sunday"
    order_value_tier = Column(String)     # e.g. "low" / "medium" / "high"


class GoldMetric(Base):
    """Pre-aggregated metrics for fast structured-query answers."""
    __tablename__ = "gold_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)   # e.g. "revenue_by_month"
    metric_key = Column(String, nullable=False)     # e.g. "2026-03"
    metric_value = Column(Float, nullable=False)
    computed_at = Column(DateTime, nullable=False)


def init_db():
    """Creates all tables if they don't already exist."""
    Base.metadata.create_all(engine)