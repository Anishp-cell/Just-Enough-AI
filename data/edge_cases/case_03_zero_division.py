"""Edge Case 03: Zero division and empty collection arithmetic.

Category: Arithmetic & Numeric Robustness
Vulnerability: ZeroDivisionError on empty collections, zero values, or canceled out terms.
SteerLM / Fuzzer relevance: Fuzzer supplies 0, -0.0, and [] to numeric functions.
"""

from typing import List, Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-003",
    "name": "zero_division_guard",
    "category": "numeric_robustness",
    "vulnerability_type": "ZeroDivisionError",
    "trigger_input": "values = [] or weights sum to 0 or total_count = 0",
    "expected_exception": "ZeroDivisionError",
    "description": "Calculating weighted mean or percentage without checking if denominator is zero or empty.",
    "remediation": "Guard against zero sum/length explicitly, returning fallback default (0.0) or raising ValueError."
}


def buggy_weighted_average(values: List[float], weights: List[float]) -> float:
    """Buggy weighted average: crashes on empty lists or when weights sum to zero."""
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    total_weight = sum(weights)
    return weighted_sum / total_weight  # ZeroDivisionError if total_weight == 0 or empty


def safe_weighted_average(
    values: Optional[List[float]],
    weights: Optional[List[float]],
    default: float = 0.0,
) -> float:
    """Defensive weighted average: guards against None, length mismatch, and zero denominator."""
    if not values or not weights or len(values) != len(weights):
        return default
    total_weight = sum(weights)
    if total_weight == 0.0:
        return default
    weighted_sum = sum(v * w for v, w in zip(values, weights))
    return weighted_sum / total_weight


def test_edge_case():
    try:
        buggy_weighted_average([], [])
        assert False, "Expected ZeroDivisionError"
    except ZeroDivisionError:
        pass

    try:
        buggy_weighted_average([10.0, 20.0], [1.0, -1.0])
        assert False, "Expected ZeroDivisionError"
    except ZeroDivisionError:
        pass

    assert safe_weighted_average([], []) == 0.0
    assert safe_weighted_average([10.0, 20.0], [1.0, -1.0]) == 0.0
    assert safe_weighted_average([10.0, 20.0], [1.0, 1.0]) == 15.0
    assert safe_weighted_average(None, None) == 0.0
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-003 passed verification.")
