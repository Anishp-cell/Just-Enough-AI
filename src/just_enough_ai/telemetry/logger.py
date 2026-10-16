"""Telemetry and session logging with secret masking.

Mayank (Security Lead): Redact API keys, tokens, and credentials from all terminal logs,
JSON audit records, and SSE events.
"""

import logging
import re
from typing import Any
from rich.logging import RichHandler

SECRET_REDACTION_PATTERNS = [
    # OpenAI / Nebius sk- keys
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "[REDACTED_SECRET]"),
    # GitHub tokens
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"), "[REDACTED_SECRET]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{22,}"), "[REDACTED_SECRET]"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.=]{16,}", re.IGNORECASE), r"\g<1>[REDACTED_SECRET]"),
    # Nebius token patterns or generic API keys
    (re.compile(r"nba-[A-Za-z0-9_\-]{20,}", re.IGNORECASE), "[REDACTED_SECRET]"),
    (
        re.compile(r"((?:api[_-]?key|secret|token|password|auth_token)\s*[:=]\s*['\"])[A-Za-z0-9_\-\.]{16,}(['\"])", re.IGNORECASE),
        r"\g<1>[REDACTED_SECRET]\g<2>",
    ),
]


def mask_secrets(text: str) -> str:
    """Redact API keys, tokens, and credentials from all logs and strings."""
    if not text or not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SECRET_REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class SecretMaskingFilter(logging.Filter):
    """Custom logging filter that masks sensitive credentials in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: mask_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    mask_secrets(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


rich_handler = RichHandler(rich_tracebacks=True, show_path=False)
rich_handler.addFilter(SecretMaskingFilter())

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[rich_handler],
)

logger = logging.getLogger("just_enough_ai")
logger.addFilter(SecretMaskingFilter())
