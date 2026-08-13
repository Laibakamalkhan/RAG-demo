import json
import requests
from etl.gold_queries import list_available_metrics

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma2:2b"

# Fixed fallback used whenever the planner can't confidently route the
# question (invalid/malformed model output, or a metric/key not in the
# whitelist). Per the MVP plan: fixed message, not a clarifying-question
# flow — a 2B model isn't trusted with that yet.
FALLBACK_ROUTE = {"route": "unknown"}


def build_whitelist(tenant_id: str) -> dict:
    """Groups the flat list of (metric_name, metric_key) pairs from Gold
    into {metric_name: [key1, key2, ...]} — more compact for the prompt,
    and easier to validate against. Always built fresh from live data,
    never hardcoded, so it reflects whatever months/metrics actually exist.
    """
    grouped: dict[str, list[str]] = {}
    for entry in list_available_metrics(tenant_id):
        grouped.setdefault(entry["metric_name"], []).append(entry["metric_key"])
    return grouped


def build_prompt(question: str, whitelist: dict) -> str:
    """Builds the instruction sent to gemma2:2b. Keeps the model's job
    narrow: classify the route, and if quantitative, pick the metric_name
    and metric_key from the exact whitelist given — no free-form values."""
    whitelist_text = json.dumps(whitelist, indent=2)

    return f"""You are a query router for an e-commerce analytics tool. Given a
user's question, decide whether it should be answered with a specific
pre-computed number (quantitative) or with a text search over reviews/
support tickets (qualitative).

Only these metric_name/metric_key combinations exist right now:
{whitelist_text}

Respond with ONLY a JSON object, no other text, in one of these two shapes:

If the question asks for one of the exact numbers above:
{{"route": "quantitative", "metric_name": "<one of the keys above>", "metric_key": "<one of its listed values>"}}

If the question is qualitative/opinion-based (e.g. about reviews, complaints,
why customers feel a certain way) or asks for something not in the list above:
{{"route": "qualitative"}}

User question: "{question}"

JSON response:"""


def call_ollama_planner(prompt: str) -> str:
    """Sends the prompt to the local Ollama gemma2:2b model and returns
    the raw text of its response. format='json' asks Ollama to force
    syntactically valid JSON, but the CONTENT still needs validation --
    the model can return valid JSON with made-up values."""
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["response"]


def validate_plan(raw_response: str, whitelist: dict) -> dict:
    """Parses and validates the model's raw response against the real
    whitelist. Never raises -- always returns a safe dict. This is the
    function most worth testing carefully, since it's the only thing
    standing between a hallucinated model answer and a wrong number
    being shown to the user.
    """
    try:
        plan = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return {**FALLBACK_ROUTE, "reason": "malformed_json"}

    if not isinstance(plan, dict):
        return {**FALLBACK_ROUTE, "reason": "not_a_json_object"}

    route = plan.get("route")

    if route == "qualitative":
        return {"route": "qualitative"}

    if route == "quantitative":
        metric_name = plan.get("metric_name")
        metric_key = plan.get("metric_key")

        if metric_name not in whitelist:
            return {**FALLBACK_ROUTE, "reason": "unknown_metric_name"}
        if metric_key not in whitelist[metric_name]:
            return {**FALLBACK_ROUTE, "reason": "unknown_metric_key"}

        return {
            "route": "quantitative",
            "metric_name": metric_name,
            "metric_key": metric_key,
        }

    # route was missing, or some other unexpected value
    return {**FALLBACK_ROUTE, "reason": "invalid_or_missing_route"}


def plan_query(question: str, tenant_id: str) -> dict:
    """Main entry point: given a question, decides how it should be
    answered. Always returns a dict with at least a 'route' key
    ('quantitative', 'qualitative', or 'unknown'). Never raises --
    a planner failure (bad model output, Ollama unreachable, etc.)
    degrades to {'route': 'unknown'} rather than crashing the request.
    """
    whitelist = build_whitelist(tenant_id)

    if not whitelist:
        # No Gold data at all for this tenant -- nothing quantitative to route to.
        return {**FALLBACK_ROUTE, "reason": "no_gold_data_for_tenant"}

    prompt = build_prompt(question, whitelist)

    try:
        raw_response = call_ollama_planner(prompt)
    except requests.RequestException as e:
        return {**FALLBACK_ROUTE, "reason": f"ollama_unreachable: {e}"}

    return validate_plan(raw_response, whitelist)


if __name__ == "__main__":
    TEST_TENANT = "shop_demo_001"

    print("=== Live test against Ollama (requires Ollama running with gemma2:2b) ===")
    for q in [
        "What was total revenue in January 2026?",
        "Why are customers unhappy with their orders?",
    ]:
        print(f"\nQuestion: {q}")
        print(plan_query(q, TEST_TENANT))