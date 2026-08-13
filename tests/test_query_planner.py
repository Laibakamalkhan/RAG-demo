# Tests for the query planner. Per the plan: the planner's Ollama call is
# MOCKED here for validation-logic tests, since live model output isn't
# deterministic. A separate live smoke test (run `python -m rag.query_planner`
# directly, with Ollama running) is enough to confirm the real connection works.
import requests
import pytest
from rag.query_planner import validate_plan, plan_query
import rag.query_planner as query_planner_module


SAMPLE_WHITELIST = {
    "revenue_by_month": ["2026-01", "2026-02"],
    "aov_by_month": ["2026-01", "2026-02"],
    "guest_vs_registered": ["guest", "registered"],
    "order_count_by_tier": ["low", "medium", "high"],
}


# --- validate_plan() tests: pure function, no mocking needed ---

def test_validate_plan_accepts_valid_quantitative():
    raw = '{"route": "quantitative", "metric_name": "revenue_by_month", "metric_key": "2026-01"}'
    result = validate_plan(raw, SAMPLE_WHITELIST)
    assert result == {
        "route": "quantitative",
        "metric_name": "revenue_by_month",
        "metric_key": "2026-01",
    }


def test_validate_plan_accepts_valid_qualitative():
    raw = '{"route": "qualitative"}'
    result = validate_plan(raw, SAMPLE_WHITELIST)
    assert result == {"route": "qualitative"}


def test_validate_plan_rejects_hallucinated_metric_name():
    """Model invents a metric_name that doesn't actually exist in Gold."""
    raw = '{"route": "quantitative", "metric_name": "total_profit", "metric_key": "2026-01"}'
    result = validate_plan(raw, SAMPLE_WHITELIST)
    assert result["route"] == "unknown"


def test_validate_plan_rejects_hallucinated_metric_key():
    """Model picks a real metric_name but an invented/nonexistent key."""
    raw = '{"route": "quantitative", "metric_name": "revenue_by_month", "metric_key": "2099-12"}'
    result = validate_plan(raw, SAMPLE_WHITELIST)
    assert result["route"] == "unknown"


def test_validate_plan_rejects_malformed_json():
    raw = "{route: quantitative,,,"
    result = validate_plan(raw, SAMPLE_WHITELIST)
    assert result["route"] == "unknown"


def test_validate_plan_rejects_missing_route():
    raw = '{"metric_name": "revenue_by_month", "metric_key": "2026-01"}'
    result = validate_plan(raw, SAMPLE_WHITELIST)
    assert result["route"] == "unknown"


def test_validate_plan_rejects_json_array():
    raw = '["quantitative"]'
    result = validate_plan(raw, SAMPLE_WHITELIST)
    assert result["route"] == "unknown"


# --- plan_query() tests: Ollama call is mocked via monkeypatch ---

def test_plan_query_uses_mocked_valid_response(monkeypatch):
    monkeypatch.setattr(query_planner_module, "build_whitelist", lambda tenant_id: SAMPLE_WHITELIST)
    monkeypatch.setattr(
        query_planner_module,
        "call_ollama_planner",
        lambda prompt: '{"route": "quantitative", "metric_name": "revenue_by_month", "metric_key": "2026-01"}',
    )
    result = plan_query("What was revenue in January?", "shop_demo_001")
    assert result["route"] == "quantitative"
    assert result["metric_name"] == "revenue_by_month"


def test_plan_query_handles_ollama_unreachable(monkeypatch):
    """If Ollama is down, plan_query should degrade to 'unknown', not crash."""
    monkeypatch.setattr(query_planner_module, "build_whitelist", lambda tenant_id: SAMPLE_WHITELIST)

    def raise_connection_error(prompt):
        raise requests.exceptions.ConnectionError("Ollama not running")

    monkeypatch.setattr(query_planner_module, "call_ollama_planner", raise_connection_error)
    result = plan_query("What was revenue in January?", "shop_demo_001")
    assert result["route"] == "unknown"


def test_plan_query_handles_empty_whitelist(monkeypatch):
    """If there's no Gold data at all for this tenant, should degrade
    gracefully instead of crashing or calling Ollama unnecessarily."""
    monkeypatch.setattr(query_planner_module, "build_whitelist", lambda tenant_id: {})
    result = plan_query("What was revenue in January?", "shop_demo_001")
    assert result["route"] == "unknown"