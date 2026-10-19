"""Edge Case 11: File handle and resource leak on exception.

Category: Resource Management & Exception Safety
Vulnerability: ResourceWarning / File descriptor exhaustion when exceptions interrupt execution.
SteerLM / Fuzzer relevance: Sandbox monitors unclosed descriptors and process cleanup.
"""

import os
import tempfile
from typing import Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-011",
    "name": "unclosed_resource_leak",
    "category": "resource_leak",
    "vulnerability_type": "ResourceWarning / FD Leak",
    "trigger_input": "Exceptions thrown before file.close() or socket.close()",
    "expected_exception": "ResourceWarning",
    "description": "Opening file or socket descriptors without using context managers (with statement).",
    "remediation": "Always use with open(...) as f: context manager to ensure deterministic cleanup."
}


def buggy_read_and_process(file_path: str) -> str:
    """Buggy reader: opens file without context manager; leaks handle if an error occurs."""
    f = open(file_path, "r", encoding="utf-8")
    content = f.read()
    if "INVALID" in content:
        raise ValueError("Invalid content detected")  # Leaks f!
    f.close()
    return content


def safe_read_and_process(file_path: Optional[str]) -> Optional[str]:
    """Defensive reader: guaranteed deterministic cleanup via context manager."""
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "INVALID" in content:
                raise ValueError("Invalid content detected")
            return content
    except (OSError, UnicodeDecodeError):
        return None


def test_edge_case():
    with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
        tmp.write("VALID CONTENT")
        tmp_path = tmp.name

    try:
        res = safe_read_and_process(tmp_path)
        assert res == "VALID CONTENT"
        assert safe_read_and_process("non_existent_file.txt") is None
        assert safe_read_and_process(None) is None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-011 passed verification.")
