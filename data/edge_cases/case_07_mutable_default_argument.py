"""Edge Case 07: Mutable default argument accumulator state leak.

Category: Function Signature & State Pollution
Vulnerability: Persistent state leaking across unrelated function invocations via default list/dict.
SteerLM / Fuzzer relevance: AST Linter and SteerLM verifier detect mutable defaults in AST function definitions.
"""

from typing import List, Optional, Any

EDGE_CASE_METADATA = {
    "case_id": "EC-007",
    "name": "mutable_default_argument",
    "category": "state_leak",
    "vulnerability_type": "Data Pollution / Cross-Request State Leak",
    "trigger_input": "Consecutive calls relying on default argument [] or {}",
    "expected_exception": "AssertionError",
    "description": "Using mutable containers (list, dict, set) as default parameter values.",
    "remediation": "Set default to None and initialize a new container inside the function body."
}


def buggy_append_log(message: str, tags: List[str] = []) -> List[str]:  # Danger: mutable default!
    """Buggy log accumulator: shares tags list across all callers that omit tags."""
    tags.append(message)
    return tags


def safe_append_log(message: str, tags: Optional[List[str]] = None) -> List[str]:
    """Defensive log accumulator: allocates a fresh list per call when tags is None."""
    if tags is None:
        tags_list = []
    else:
        tags_list = list(tags)  # Defensive copy

    if message is not None:
        tags_list.append(str(message))
    return tags_list


def test_edge_case():
    # In buggy version, call 1 affects call 2
    b1 = buggy_append_log("log_one")
    b2 = buggy_append_log("log_two")
    # b1 and b2 reference the EXACT SAME list object
    assert b1 is b2
    assert "log_one" in b2  # Leak!

    # In safe version, calls are completely isolated
    s1 = safe_append_log("log_one")
    s2 = safe_append_log("log_two")
    assert s1 is not s2
    assert s1 == ["log_one"]
    assert s2 == ["log_two"]
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-007 passed verification.")
