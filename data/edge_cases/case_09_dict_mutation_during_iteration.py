"""Edge Case 09: Dictionary mutation during iteration crash.

Category: Concurrent Modification & Iterator Invalidation
Vulnerability: RuntimeError: dictionary changed size during iteration.
SteerLM / Fuzzer relevance: Fuzzer supplies dictionaries with items to be pruned or evicted.
"""

from typing import Dict, Any, Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-009",
    "name": "dict_mutation_during_iteration",
    "category": "iterator_invalidation",
    "vulnerability_type": "RuntimeError",
    "trigger_input": "Modifying or deleting dictionary keys inside a for loop over the dictionary",
    "expected_exception": "RuntimeError",
    "description": "Deleting keys directly from a dictionary while iterating over d.items() or d.keys().",
    "remediation": "Iterate over a copy of keys list(d.keys()) or use dictionary comprehension."
}


def buggy_evict_expired(cache: Dict[str, int], current_time: int) -> Dict[str, int]:
    """Buggy cleanup: mutates dictionary while iterating directly over it."""
    for key, expiry in cache.items():
        if expiry < current_time:
            del cache[key]  # RuntimeError: dictionary changed size during iteration
    return cache


def safe_evict_expired(cache: Optional[Dict[str, int]], current_time: int) -> Dict[str, int]:
    """Defensive cleanup: iterates over snapshot of keys or creates a fresh dictionary."""
    if not isinstance(cache, dict):
        return {}

    # Snapshot keys to safely delete in-place, or filter with dict comprehension
    keys_to_delete = [
        key for key, expiry in cache.items()
        if isinstance(expiry, (int, float)) and expiry < current_time
    ]
    for key in keys_to_delete:
        del cache[key]
    return cache


def test_edge_case():
    data = {"k1": 10, "k2": 5, "k3": 20}
    try:
        buggy_evict_expired(data, current_time=15)
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass

    # Safe cleanly evicts without iterator conflict
    clean_data = {"k1": 10, "k2": 5, "k3": 20}
    safe_evict_expired(clean_data, current_time=15)
    assert "k1" not in clean_data
    assert "k2" not in clean_data
    assert "k3" in clean_data
    assert safe_evict_expired(None, 10) == {}
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-009 passed verification.")
