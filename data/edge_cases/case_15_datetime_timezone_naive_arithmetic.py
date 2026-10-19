"""Edge Case 15: Datetime offset-naive vs offset-aware arithmetic collision.

Category: Datetime & Timezone Safety
Vulnerability: TypeError: can't subtract offset-naive and offset-aware datetimes.
SteerLM / Fuzzer relevance: Fuzzer and API middleware test timestamp parsing and session timeouts.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

EDGE_CASE_METADATA = {
    "case_id": "EC-015",
    "name": "timezone_naive_aware_collision",
    "category": "datetime_safety",
    "vulnerability_type": "TypeError",
    "trigger_input": "Subtracting datetime.now() (naive) from datetime.now(timezone.utc) (aware)",
    "expected_exception": "TypeError",
    "description": "Subtracting timezone-naive datetime from timezone-aware datetime in session/token expiry checks.",
    "remediation": "Always normalize timestamps to timezone-aware UTC before performing arithmetic."
}


def buggy_calculate_session_duration(start_time: datetime, end_time: datetime) -> float:
    """Buggy duration: raises TypeError if one timestamp is naive and the other is aware."""
    return (end_time - start_time).total_seconds()


def safe_calculate_session_duration(
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> float:
    """Defensive duration: ensures both timestamps are converted to UTC before subtraction."""
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        return 0.0

    # Normalize start_time
    if start_time.tzinfo is None or start_time.tzinfo.utcoffset(start_time) is None:
        start_utc = start_time.replace(tzinfo=timezone.utc)
    else:
        start_utc = start_time.astimezone(timezone.utc)

    # Normalize end_time
    if end_time.tzinfo is None or end_time.tzinfo.utcoffset(end_time) is None:
        end_utc = end_time.replace(tzinfo=timezone.utc)
    else:
        end_utc = end_time.astimezone(timezone.utc)

    diff = (end_utc - start_utc).total_seconds()
    return max(0.0, diff)


def test_edge_case():
    naive_time = datetime(2026, 10, 18, 12, 0, 0)
    aware_time = datetime(2026, 10, 18, 12, 5, 0, tzinfo=timezone.utc)

    # Buggy raises TypeError on naive/aware mix
    try:
        buggy_calculate_session_duration(naive_time, aware_time)
        assert False, "Expected TypeError"
    except TypeError:
        pass

    # Safe cleanly normalizes and computes duration (300.0s)
    duration = safe_calculate_session_duration(naive_time, aware_time)
    assert duration == 300.0
    assert safe_calculate_session_duration(None, aware_time) == 0.0
    assert safe_calculate_session_duration(naive_time, None) == 0.0
    return True


if __name__ == "__main__":
    test_edge_case()
    print("EC-015 passed verification.")
