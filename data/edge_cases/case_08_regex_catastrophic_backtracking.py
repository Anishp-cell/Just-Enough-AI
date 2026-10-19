"""Edge Case 08: Regular expression catastrophic backtracking (ReDoS).

Category: Algorithmic Complexity & ReDoS
Vulnerability: Exponential backtracking O(2^N) causing CPU lockup and thread exhaustion.
SteerLM / Fuzzer relevance: Fuzzer supplies long repetitive strings ('A' * 10000) to regex patterns.
"""

import re
import time
from typing import Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-008",
    "name": "regex_catastrophic_backtracking",
    "category": "algorithmic_complexity_redos",
    "vulnerability_type": "CPU DoS / Timeout",
    "trigger_input": "'a' * 25 + '!' against nested grouping regex (a+)+$",
    "expected_exception": "TimeoutError",
    "description": "Nested quantifiers without atomic grouping or input length pre-validation causing catastrophic backtracking.",
    "remediation": "Simplify regex pattern, use possessive/atomic matching or pre-validate maximum string length."
}


# Buggy regex with nested quantifiers: (a+)+$
BUGGY_REGEX = re.compile(r"^(a+)+$")

# Safe linear regex or length-guarded regex
SAFE_REGEX = re.compile(r"^a+$")


def buggy_match_pattern(text: str) -> bool:
    """Buggy matcher: susceptible to exponential backtracking on non-matching strings."""
    return bool(BUGGY_REGEX.match(text))


def safe_match_pattern(text: Optional[str], max_len: int = 500) -> bool:
    """Defensive matcher: enforces length guard and uses non-backtracking pattern."""
    if not isinstance(text, str):
        return False
    if len(text) > max_len:
        return False  # Fast reject overly long inputs
    return bool(SAFE_REGEX.match(text))


def test_edge_case():
    evil_input = "a" * 22 + "!"

    # Safe matcher returns immediately in microseconds
    t0 = time.perf_counter()
    res_safe = safe_match_pattern(evil_input)
    t_safe = time.perf_counter() - t0
    assert res_safe is False
    assert t_safe < 0.05  # Instant

    # Very long input is fast-rejected
    assert safe_match_pattern("a" * 1000) is False
    assert safe_match_pattern(None) is False
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-008 passed verification.")
