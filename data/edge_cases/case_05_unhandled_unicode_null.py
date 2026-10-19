"""Edge Case 05: Embedded null bytes and astral Unicode surrogate handling.

Category: String Sanitization & Binary Injection
Vulnerability: ValueError: embedded null byte when interacting with OS/C-bindings or file paths.
SteerLM / Fuzzer relevance: Fuzzer supplies '\x00', emojis, and multi-byte surrogate sequences.
"""

from typing import Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-005",
    "name": "embedded_null_byte_unicode",
    "category": "string_sanitization",
    "vulnerability_type": "ValueError / UnicodeDecodeError",
    "trigger_input": "raw_input = 'config\x00.json' or invalid surrogate pairs",
    "expected_exception": "ValueError",
    "description": "Processing filenames or identifiers without stripping embedded null bytes (\\x00).",
    "remediation": "Strip null bytes and control characters, validate against allowed character set."
}


def buggy_sanitize_identifier(raw: str) -> str:
    """Buggy sanitizer: leaves null bytes intact, which breaks filesystem/OS APIs."""
    # Only strips whitespace, failing to sanitize embedded null bytes or control codes
    return raw.strip().lower()


def safe_sanitize_identifier(raw: Optional[str], fallback: str = "default") -> str:
    """Defensive sanitizer: strips null bytes, control characters, and normalizes UTF-8."""
    if not isinstance(raw, str):
        return fallback

    # Strip null bytes and control characters (ASCII 0-31, except standard whitespace)
    cleaned = "".join(
        ch for ch in raw
        if ch != "\x00" and (ch >= " " or ch in "\t\n\r")
    ).strip()

    if not cleaned:
        return fallback

    # Normalize unicode to NFKC form
    import unicodedata
    normalized = unicodedata.normalize("NFKC", cleaned)
    return normalized


def test_edge_case():
    bad_name = "database\x00_override.db"
    # Buggy leaves null byte in place
    assert "\x00" in buggy_sanitize_identifier(bad_name)

    # Safe strips null byte
    sanitized = safe_sanitize_identifier(bad_name)
    assert "\x00" not in sanitized
    assert sanitized == "database_override.db"
    assert safe_sanitize_identifier(None) == "default"
    assert safe_sanitize_identifier("\x00\x00") == "default"
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-005 passed verification.")
