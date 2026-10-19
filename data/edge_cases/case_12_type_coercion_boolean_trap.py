"""Edge Case 12: Python type coercion boolean string trap.

Category: Type Coercion & Truth Value Testing
Vulnerability: bool("false") evaluates to True because non-empty strings are truthy.
SteerLM / Fuzzer relevance: Fuzzer tests "false", "0", "null", and "" against boolean parsers.
"""

from typing import Any, Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-012",
    "name": "boolean_coercion_trap",
    "category": "type_coercion",
    "vulnerability_type": "Logic Bug / False Positive Flag",
    "trigger_input": "env_val = 'false' or '0' evaluated via bool(env_val)",
    "expected_exception": "AssertionError",
    "description": "Calling bool(val) on strings: bool('false') and bool('0') are True in Python.",
    "remediation": "Use explicit lookup dictionary mapping known true/false literals."
}


def buggy_parse_feature_flag(val: Any) -> bool:
    """Buggy parser: bool('false') returns True, activating unintended features."""
    return bool(val)


def safe_parse_feature_flag(val: Any, default: bool = False) -> bool:
    """Defensive parser: strictly recognizes boolean literals, integers, and case-insensitive strings."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0

    if isinstance(val, str):
        normalized = val.strip().lower()
        if normalized in ("true", "1", "yes", "t", "on", "enable", "enabled"):
            return True
        if normalized in ("false", "0", "no", "f", "off", "disable", "disabled", ""):
            return False

    return default


def test_edge_case():
    # Buggy evaluates "false" as True!
    assert buggy_parse_feature_flag("false") is True  # Danger!
    assert buggy_parse_feature_flag("0") is True      # Danger!

    # Safe correctly evaluates falsy string representations
    assert safe_parse_feature_flag("false") is False
    assert safe_parse_feature_flag("0") is False
    assert safe_parse_feature_flag("no") is False
    assert safe_parse_feature_flag("true") is True
    assert safe_parse_feature_flag("1") is True
    assert safe_parse_feature_flag(None) is False
    assert safe_parse_feature_flag(True) is True
    assert safe_parse_feature_flag(False) is False
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-012 passed verification.")
