"""Edge Case 02: Missing null/None check in nested structure navigation.

Category: Null Reference & Defensive Access
Vulnerability: TypeError: 'NoneType' object is not subscriptable.
SteerLM / Fuzzer relevance: Fuzzer tests None and {"nested": None} inputs.
"""

from typing import Dict, Any, Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-002",
    "name": "missing_null_check",
    "category": "null_pointer_trap",
    "vulnerability_type": "TypeError / AttributeError",
    "trigger_input": "payload = None or payload = {'user': None}",
    "expected_exception": "TypeError",
    "description": "Accessing nested dictionary keys directly assuming intermediate dictionaries are never None.",
    "remediation": "Use safe traversal helper or explicit isinstance/None validation on each tier."
}


def buggy_get_user_theme(payload: Dict[str, Any]) -> str:
    """Buggy extractor: crashes when payload or user or settings is None."""
    # Assumes 'user' and 'settings' keys exist and are dicts
    return payload["user"]["settings"]["theme"]


def safe_get_user_theme(payload: Optional[Dict[str, Any]], default: str = "dark") -> str:
    """Defensive extractor: navigates nested dict safely even with None intermediaries."""
    if not isinstance(payload, dict):
        return default
    user = payload.get("user")
    if not isinstance(user, dict):
        return default
    settings = user.get("settings")
    if not isinstance(settings, dict):
        return default
    theme = settings.get("theme")
    return str(theme) if theme is not None else default


def test_edge_case():
    # Buggy fails on None or partial None
    try:
        buggy_get_user_theme({"user": None})  # type: ignore
        assert False, "Expected TypeError"
    except TypeError:
        pass

    # Safe handles all variants gracefully
    assert safe_get_user_theme(None) == "dark"
    assert safe_get_user_theme({"user": None}) == "dark"
    assert safe_get_user_theme({"user": {"settings": None}}) == "dark"
    assert safe_get_user_theme({"user": {"settings": {"theme": "light"}}}) == "light"
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-002 passed verification.")
