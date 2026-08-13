# Tests for retrieval logic
from rag.retrieval import search

def test_search_returns_results_for_valid_tenant():
    """Basic sanity check: searching with a real tenant_id should return results."""
    results = search("Why are customers unhappy?", tenant_id="shop_demo_001", n_results=3)
    assert len(results) == 3
    for r in results:
        assert "text" in r
        assert "metadata" in r
        assert "similarity_distance" in r

def test_search_respects_tenant_isolation():
    """Searching with a tenant_id that doesn't exist should return nothing."""
    results = search("Why are customers unhappy?", tenant_id="nonexistent_tenant_xyz", n_results=3)
    assert len(results) == 0

def test_negative_reviews_are_retrievable():
    """A complaint-style question should surface at least one low-rated review."""
    results = search("Why are customers unhappy with their orders?", tenant_id="shop_demo_001", n_results=5)
    ratings = [r["metadata"].get("rating") for r in results if r["metadata"].get("rating") != "none"]
    assert any(rating is not None and int(rating) <= 2 for rating in ratings)