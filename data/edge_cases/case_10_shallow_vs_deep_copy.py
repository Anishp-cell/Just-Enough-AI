"""Edge Case 10: Shallow vs deep copy nested state corruption.

Category: Object Identity & State Isolation
Vulnerability: Mutating nested structures in shallow copies corrupts shared original state.
SteerLM / Fuzzer relevance: Differential AST scope lock and SteerLM check for collateral state damage.
"""

import copy
from typing import Dict, Any, Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-010",
    "name": "shallow_vs_deep_copy",
    "category": "state_isolation",
    "vulnerability_type": "Corrupted Shared State / Side Effect",
    "trigger_input": "Mutating nested dict/list in shallow copied configuration",
    "expected_exception": "AssertionError",
    "description": "Using dict.copy() or dict() on nested structures: nested objects remain shared references.",
    "remediation": "Use copy.deepcopy() for nested state duplication or immutable data models."
}


def buggy_clone_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Buggy clone: performs shallow copy; nested structures remain shared."""
    return dict(config)  # Shallow!


def safe_clone_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Defensive clone: deep copy guarantees complete isolation of nested structures."""
    if not isinstance(config, dict):
        return {}
    return copy.deepcopy(config)


def test_edge_case():
    original = {"env": "prod", "db": {"host": "localhost", "port": 5432}}

    # Buggy shallow copy allows mutation of nested db dict in original
    shallow = buggy_clone_config(original)
    shallow["db"]["host"] = "compromised-host"
    assert original["db"]["host"] == "compromised-host"  # Side effect!

    # Safe deep copy isolates modifications completely
    clean_original = {"env": "prod", "db": {"host": "localhost", "port": 5432}}
    deep = safe_clone_config(clean_original)
    deep["db"]["host"] = "isolated-host"
    assert clean_original["db"]["host"] == "localhost"  # Pristine!
    assert safe_clone_config(None) == {}
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-010 passed verification.")
