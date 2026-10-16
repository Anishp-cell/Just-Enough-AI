"""Provider CLI Sandbox Isolation & ANSI Sanitizer.

Mayank (Security Lead) — Task M-7:
Ensures external CLI agent processes (claude, agy, opencode) run in clean,
isolated subprocesses without credential leakage, and sanitizes all terminal
escape sequences from stdout before any further processing.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Dict, List, Optional

from just_enough_ai.agent.sandbox import SandboxResult, run_in_sandbox

# ── ANSI / terminal escape sequence patterns ─────────────────────────────────

# Full VT100 / ANSI escape sequence: ESC followed by various control sequences
_ANSI_ESCAPE = re.compile(
    r"\x1B"           # ESC character
    r"(?:"
    r"[@-Z\\-_]"      # Two-character sequences (e.g. ESC[ ESC] ESC c ...)
    r"|"
    r"\[[0-?]*[ -/]*[@-~]"  # CSI sequences: ESC [ ... final-byte
    r")"
)

# OSC sequences: ESC ] ... ST  (window titles, hyperlinks, etc.)
_OSC_ESCAPE = re.compile(r"\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)")

# Carriage-return progress wipes: lines ending in \r (spinner ticks)
_CR_WIPE = re.compile(r"[^\n]*\r(?!\n)")

# ── Essential environment variable whitelists ─────────────────────────────────

_WINDOWS_WHITELIST = {
    "PATH",
    "PATHEXT",
    "COMSPEC",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
    "WINDIR",
    "PROGRAMFILES",
    "PROGRAMDATA",
    "USERNAME",       # Non-sensitive identity for tooling that needs it
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "COLORTERM",
    "WT_SESSION",     # Windows Terminal session ID (harmless)
}

_POSIX_WHITELIST = {
    "PATH",
    "HOME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "COLORTERM",
    "TMPDIR",
    "USER",
    "LOGNAME",
}

# Credential-bearing prefixes we always scrub regardless of whitelist
_CREDENTIAL_PREFIXES = (
    "OPENAI_",
    "ANTHROPIC_",
    "NEBIUS_",
    "GITHUB_",
    "GITLAB_",
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_",
    "SECRET",
    "TOKEN",
    "KEY",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "API_KEY",
    "PRIVATE_",
    "CLAUDE_",
    "AGY_",
)

# ── Public API ────────────────────────────────────────────────────────────────


def sanitize_provider_env(
    custom_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Whitelist only essential system variables, scrubbing parent-shell credentials.

    Args:
        custom_env: Optional dict of additional environment variables to merge in
                    AFTER sanitization (caller's explicit additions are trusted).

    Returns:
        A clean environment dict safe for subprocess execution.
    """
    whitelist = _WINDOWS_WHITELIST if sys.platform == "win32" else _POSIX_WHITELIST

    clean: Dict[str, str] = {}
    for key, value in os.environ.items():
        key_upper = key.upper()

        # Reject any variable whose name starts with a credential prefix
        if any(key_upper.startswith(pfx.upper()) for pfx in _CREDENTIAL_PREFIXES):
            continue

        # Only pass variables in the platform whitelist
        if key_upper in whitelist:
            clean[key] = value

    # Merge caller-provided overrides (they've already been intentionally set)
    if custom_env:
        clean.update(custom_env)

    return clean


def strip_ansi_sequences(raw_text: str) -> str:
    """Strip ANSI color codes, terminal control sequences, and spinner ticks.

    Processing order:
    1. Remove OSC sequences (window titles, hyperlinks)
    2. Remove CSI / VT100 escape sequences (colors, cursor movement)
    3. Discard carriage-return progress lines (spinner ticks like "...\r")
    4. Normalize Windows line endings

    Args:
        raw_text: Raw subprocess stdout/stderr string.

    Returns:
        Clean plain-text string with no terminal formatting.
    """
    if not raw_text:
        return raw_text

    text = raw_text
    # 1. OSC sequences first (they can contain ESC internally)
    text = _OSC_ESCAPE.sub("", text)
    # 2. ANSI / CSI escape sequences
    text = _ANSI_ESCAPE.sub("", text)
    # 3. Carriage-return spinner wipes — lines ending in bare \r get dropped
    text = _CR_WIPE.sub("", text)
    # 4. Normalize Windows CRLF → LF
    text = text.replace("\r\n", "\n")
    # 5. Remove any remaining stray \r
    text = text.replace("\r", "")
    return text


def run_provider_cli(
    cmd: List[str],
    cwd: str,
    timeout_seconds: int = 60,
    custom_env: Optional[Dict[str, str]] = None,
) -> SandboxResult:
    """Execute an external CLI agent tool inside a sanitized sandbox environment.

    Guarantees:
    - Subprocess inherits only a whitelisted environment (no credential bleed).
    - stdout/stderr are ANSI-stripped before returning.
    - Hard timeout kills the process if it exceeds `timeout_seconds`.

    Args:
        cmd:             Command and arguments, e.g. ["claude", "--task", "..."].
        cwd:             Working directory for the subprocess.
        timeout_seconds: Kill the process if it runs longer than this.
        custom_env:      Optional explicit environment overrides to inject.

    Returns:
        SandboxResult with clean (ANSI-free) stdout/stderr and exit metadata.
    """
    safe_env = sanitize_provider_env(custom_env)

    import subprocess

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=safe_env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        raw_stdout, raw_stderr = proc.communicate(timeout=timeout_seconds)

        return SandboxResult(
            stdout=strip_ansi_sequences(raw_stdout or ""),
            stderr=strip_ansi_sequences(raw_stderr or ""),
            exit_code=proc.returncode if proc.returncode is not None else 0,
            timed_out=False,
        )

    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            raw_stdout, raw_stderr = proc.communicate(timeout=2)
        except Exception:
            raw_stdout, raw_stderr = "", ""
        return SandboxResult(
            stdout=strip_ansi_sequences(raw_stdout or ""),
            stderr=strip_ansi_sequences(raw_stderr or "") or "Execution timed out.",
            exit_code=-1,
            timed_out=True,
        )
    except FileNotFoundError as e:
        return SandboxResult(
            stdout="",
            stderr=f"Command not found: {cmd[0]!r}. Ensure the tool is installed and on PATH.",
            exit_code=127,
            timed_out=False,
        )
    except Exception as e:
        return SandboxResult(
            stdout="",
            stderr=str(e),
            exit_code=1,
            timed_out=False,
        )
