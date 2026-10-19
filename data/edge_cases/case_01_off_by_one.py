"""Edge Case 01: Off-by-one boundary error in binary search and indexing.

Category: Boundary Condition & Index Handling
Vulnerability: Index out of bounds or missing extreme elements on empty/single-element sequences.
SteerLM / Fuzzer relevance: Boundary fuzzer tests empty list [] and out-of-range index.
"""

from typing import List, Optional, Any

EDGE_CASE_METADATA = {
    "case_id": "EC-001",
    "name": "off_by_one_boundary",
    "category": "boundary_condition",
    "vulnerability_type": "IndexError / Infinite Loop",
    "trigger_input": "Empty list [] or single-element target at boundary",
    "expected_exception": "IndexError",
    "description": "Binary search using while low < high instead of <= and mid calculation that overflows or misses last element.",
    "remediation": "Use while low <= high and handle empty sequence guard at entry."
}


def buggy_binary_search(arr: List[int], target: int) -> int:
    """Buggy binary search: crashes on empty list with IndexError or misses target."""
    if len(arr) == 0:
        # Subtle bug: tries accessing arr[0] before checking, or returns -1 after unhandled access
        return arr[0]  # IndexError: list index out of range
    low = 0
    high = len(arr)  # Off by one: high should be len(arr) - 1
    while low < high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid
    return -1


def safe_binary_search(arr: Optional[List[int]], target: Optional[int]) -> int:
    """Defensive binary search: handles None, empty lists, and boundary elements safely."""
    if not arr or target is None:
        return -1
    low = 0
    high = len(arr) - 1
    while low <= high:
        mid = low + (high - low) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1


def test_edge_case():
    # Buggy fails on empty list
    try:
        buggy_binary_search([], 42)
        assert False, "Expected IndexError"
    except IndexError:
        pass

    # Safe passes on empty list, None, and normal cases
    assert safe_binary_search([], 42) == -1
    assert safe_binary_search(None, 42) == -1
    assert safe_binary_search([10], 10) == 0
    assert safe_binary_search([10, 20, 30], 30) == 2
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-001 passed verification.")
