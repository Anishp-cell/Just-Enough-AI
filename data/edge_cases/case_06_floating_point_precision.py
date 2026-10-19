"""Edge Case 06: Floating point precision equality and financial rounding errors.

Category: Numerical Precision & Equality Traps
Vulnerability: Inexact float representation (0.1 + 0.2 != 0.3) causing incorrect branch execution.
SteerLM / Fuzzer relevance: Fuzzer tests NaN, Inf, and fractional float accumulators.
"""

from typing import List, Optional
import math
from decimal import Decimal, ROUND_HALF_UP

EDGE_CASE_METADATA = {
    "case_id": "EC-006",
    "name": "floating_point_equality",
    "category": "numerical_precision",
    "vulnerability_type": "AssertionError / False Logic Branch",
    "trigger_input": "0.1 + 0.2 vs 0.3 or float ledger balances",
    "expected_exception": "AssertionError",
    "description": "Comparing floating point numbers directly using == in financial or threshold checks.",
    "remediation": "Use math.isclose() with relative/absolute tolerance, or integer cents / Decimal."
}


def buggy_reconcile_balance(transactions: List[float], expected_total: float) -> bool:
    """Buggy balance reconciliation: uses strict == on float summation."""
    # 0.1 + 0.2 produces 0.30000000000000004 != 0.3
    actual = sum(transactions)
    return actual == expected_total


def safe_reconcile_balance(
    transactions: Optional[List[float]],
    expected_total: Optional[float],
    abs_tol: float = 1e-6,
) -> bool:
    """Defensive balance reconciliation: uses math.isclose or Decimal for precision."""
    if transactions is None or expected_total is None:
        return False

    # Guard against NaN / Inf values
    if math.isnan(expected_total) or math.isinf(expected_total):
        return False
    if any(math.isnan(t) or math.isinf(t) for t in transactions):
        return False

    actual = sum(transactions)
    return math.isclose(actual, expected_total, rel_tol=1e-9, abs_tol=abs_tol)


def test_edge_case():
    txs = [0.1, 0.2]
    expected = 0.3

    # Buggy fails due to IEEE 754 precision artifact
    assert buggy_reconcile_balance(txs, expected) is False

    # Safe correctly evaluates equality within tolerance
    assert safe_reconcile_balance(txs, expected) is True
    assert safe_reconcile_balance([float("nan")], 0.0) is False
    assert safe_reconcile_balance(None, 0.0) is False
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-006 passed verification.")
