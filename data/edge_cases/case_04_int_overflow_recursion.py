"""Edge Case 04: Unbounded recursion and integer exponential explosion.

Category: Resource Exhaustion & Recursion Limits
Vulnerability: RecursionError on deep structures, or memory exhaustion on exponential terms.
SteerLM / Fuzzer relevance: Fuzzer provides huge integers (2147483647) and nested recursive calls.
"""

from typing import Dict, Any, Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-004",
    "name": "unbounded_recursion_depth",
    "category": "resource_exhaustion",
    "vulnerability_type": "RecursionError",
    "trigger_input": "Circular references or deeply nested structures (depth > 1000)",
    "expected_exception": "RecursionError",
    "description": "Recursive tree traversal without visited-set cycle detection or maximum depth bound.",
    "remediation": "Use an explicit iterative stack with a visited identity set and hard maximum depth limit."
}


def buggy_tree_depth(node: Dict[str, Any]) -> int:
    """Buggy tree depth: crashes with RecursionError on cyclic or deep graphs."""
    children = node.get("children", [])
    if not children:
        return 1
    return 1 + max(buggy_tree_depth(c) for c in children)


def safe_tree_depth(node: Optional[Dict[str, Any]], max_depth: int = 100) -> int:
    """Defensive tree depth: iterative DFS with cycle detection and depth cutoff."""
    if not isinstance(node, dict):
        return 0

    visited_nodes = set()
    stack = [(node, 1)]
    maximum_seen_depth = 0

    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            return max_depth

        current_id = id(current)
        if current_id in visited_nodes:
            continue  # Cycle detected, break infinite loop
        visited_nodes.add(current_id)

        if depth > maximum_seen_depth:
            maximum_seen_depth = depth

        children = current.get("children")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    stack.append((child, depth + 1))

    return maximum_seen_depth


def test_edge_case():
    # Cyclic tree triggers RecursionError in buggy version
    cyclic_node: Dict[str, Any] = {"children": []}
    cyclic_node["children"].append(cyclic_node)

    try:
        buggy_tree_depth(cyclic_node)
        assert False, "Expected RecursionError"
    except RecursionError:
        pass

    # Safe version terminates cleanly and handles cycle
    assert safe_tree_depth(cyclic_node) == 1
    assert safe_tree_depth(None) == 0
    normal_tree = {"children": [{"children": [{"children": []}]}]}
    assert safe_tree_depth(normal_tree) == 3
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-004 passed verification.")
