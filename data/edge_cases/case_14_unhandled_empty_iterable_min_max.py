"""Edge Case 14: Unhandled empty iterable in min() / max() aggregations.

Category: Builtin Aggregators & Empty Sequences
Vulnerability: ValueError: min() arg is an empty sequence.
SteerLM / Fuzzer relevance: Fuzzer tests filtered empty streams and empty lists against aggregators.
"""

from typing import List, Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-014",
    "name": "empty_iterable_min_max",
    "category": "builtin_aggregators",
    "vulnerability_type": "ValueError",
    "trigger_input": "Empty list [] or generator where all items are filtered out",
    "expected_exception": "ValueError",
    "description": "Calling min() or max() on filtered iterables without specifying default argument.",
    "remediation": "Always pass default=None or default value, or check sequence length beforehand."
}


def buggy_find_cheapest_in_stock(prices: List[float], in_stock: List[bool]) -> float:
    """Buggy min finder: crashes with ValueError when no items are in stock."""
    # Generator comprehension has no matching items if in_stock is all False
    available = (p for p, s in zip(prices, in_stock) if s)
    return min(available)  # ValueError if empty!


def safe_find_cheapest_in_stock(
    prices: Optional[List[float]],
    in_stock: Optional[List[bool]],
    fallback: float = 0.0,
) -> float:
    """Defensive min finder: uses default argument to handle empty candidates gracefully."""
    if not prices or not in_stock:
        return fallback

    available = [
        p for p, s in zip(prices, in_stock)
        if s and isinstance(p, (int, float)) and p >= 0
    ]
    return min(available, default=fallback)


def test_edge_case():
    # When no items in stock, buggy raises ValueError
    try:
        buggy_find_cheapest_in_stock([29.99, 49.99], [False, False])
        assert False, "Expected ValueError"
    except ValueError:
        pass

    # Safe cleanly returns fallback
    assert safe_find_cheapest_in_stock([29.99, 49.99], [False, False]) == 0.0
    assert safe_find_cheapest_in_stock([29.99, 19.99], [False, True]) == 19.99
    assert safe_find_cheapest_in_stock([], []) == 0.0
    assert safe_find_cheapest_in_stock(None, None) == 0.0
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-014 passed verification.")
