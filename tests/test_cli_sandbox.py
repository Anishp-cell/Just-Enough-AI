"""Unit tests for Provider CLI Sandbox Isolation & ANSI Sanitizer (Task M-7).

Validates:
- strip_ansi_sequences: ANSI color codes, CSI cursor codes, OSC sequences, spinner carriage-return wipes.
- sanitize_provider_env: Scrubs parent shell tokens and credentials (OPENAI_, ANTHROPIC_, GITHUB_, etc.),
  preserves whitelisted system variables (PATH, HOME, USERPROFILE), and merges custom overrides.
- run_provider_cli: Executes CLI subprocesses in sanitized environment, strips terminal sequences,
  enforces timeout bounds, handles command-not-found (exit code 127), and isolates credentials.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict

# Ensure src is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from just_enough_ai.security.cli_sandbox import (
    sanitize_provider_env,
    strip_ansi_sequences,
    run_provider_cli,
)
from just_enough_ai.agent.sandbox import SandboxResult


# ── strip_ansi_sequences Tests ───────────────────────────────────────────────

def test_strip_ansi_empty_and_plain():
    """Verify clean plain text and empty strings pass through unchanged."""
    assert strip_ansi_sequences("") == ""
    assert strip_ansi_sequences("Hello, world!") == "Hello, world!"
    assert strip_ansi_sequences("Line 1\nLine 2\nLine 3") == "Line 1\nLine 2\nLine 3"


def test_strip_ansi_colors_and_styles():
    """Verify standard 3/4-bit, 8-bit (256 color), and 24-bit (RGB) ANSI codes are stripped."""
    # Red text with reset
    colored = "\x1b[31mError:\x1b[0m File not found"
    assert strip_ansi_sequences(colored) == "Error: File not found"

    # Bold, underlined, 256-color, RGB color
    complex_ansi = "\x1b[1m\x1b[4m\x1b[38;5;214mWarning\x1b[0m: \x1b[38;2;255;100;0mCritical\x1b[0m"
    assert strip_ansi_sequences(complex_ansi) == "Warning: Critical"


def test_strip_ansi_cursor_and_line_erase():
    """Verify CSI cursor positioning and line erasure codes (e.g. \x1b[2K, \x1b[1A) are removed."""
    csi_str = "Initial text\x1b[2K\x1b[1GReplaced text"
    assert strip_ansi_sequences(csi_str) == "Initial textReplaced text"


def test_strip_ansi_osc_sequences():
    """Verify OSC escape sequences (e.g. window title setting or hyperlinks) are removed."""
    osc_bell = "\x1b]0;Agent Working...\x07Task Output"
    assert strip_ansi_sequences(osc_bell) == "Task Output"

    osc_st = "\x1b]2;CLI Shell\x1b\\Command Done"
    assert strip_ansi_sequences(osc_st) == "Command Done"


def test_strip_ansi_spinner_carriage_return_wipes():
    """Verify terminal progress spinner ticks ending in carriage returns are stripped."""
    spinner_output = "Fetching [|]\rFetching [/]\rFetching [-]\rFetching [\\]\rDone!\n"
    cleaned = strip_ansi_sequences(spinner_output)
    assert cleaned == "Done!\n"


def test_strip_ansi_crlf_normalization():
    """Verify Windows CRLF endings are normalized to standard LF."""
    crlf_text = "Line 1\r\nLine 2\r\nLine 3\r\n"
    assert strip_ansi_sequences(crlf_text) == "Line 1\nLine 2\nLine 3\n"


# ── sanitize_provider_env Tests ─────────────────────────────────────────────

def test_sanitize_provider_env_preserves_system_whitelist(monkeypatch):
    """Verify essential system environment variables like PATH, HOME/USERPROFILE are kept."""
    clean_env = sanitize_provider_env()
    assert "PATH" in clean_env

    if sys.platform == "win32":
        # Windows requires SYSTEMROOT / SYSTEMDRIVE to spawn basic executables
        assert any(k in clean_env for k in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "USERPROFILE"))
    else:
        assert any(k in clean_env for k in ("HOME", "SHELL", "USER"))


def test_sanitize_provider_env_scrubs_credential_tokens(monkeypatch):
    """Verify secrets and API keys are scrubbed out of the child environment."""
    leaked_secrets = {
        "OPENAI_API_KEY": "sk-proj-supersecret12345",
        "ANTHROPIC_API_KEY": "sk-ant-admin09876",
        "GITHUB_TOKEN": "ghp_mocktoken99999",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "NEBIUS_API_KEY": "neb-fake-token",
        "AZURE_OPENAI_KEY": "az-secret-val",
        "SECRET_DATABASE_URL": "postgres://user:pass@localhost:5432/db",
        "MY_API_KEY": "key-should-be-blocked",
    }
    for k, v in leaked_secrets.items():
        monkeypatch.setenv(k, v)

    clean_env = sanitize_provider_env()

    for k in leaked_secrets:
        assert k not in clean_env, f"Credential {k} was not scrubbed from child env!"


def test_sanitize_provider_env_merges_custom_env():
    """Verify caller-provided custom environment overrides are merged in."""
    custom = {"SAFE_CLI_PARAM": "allowed_value", "EXECUTION_MODE": "isolated"}
    clean_env = sanitize_provider_env(custom_env=custom)
    assert clean_env.get("SAFE_CLI_PARAM") == "allowed_value"
    assert clean_env.get("EXECUTION_MODE") == "isolated"


# ── run_provider_cli Tests ──────────────────────────────────────────────────

def test_run_provider_cli_executes_successfully():
    """Verify running a clean CLI command returns 0 and captures stdout without ANSI."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('\\x1b[32mSUCCESS\\x1b[0m\\n'); sys.stderr.write('LOG\\n')",
        ]
        result = run_provider_cli(cmd, cwd=tmp_dir, timeout_seconds=10)

        assert isinstance(result, SandboxResult)
        assert result.exit_code == 0
        assert result.stdout.strip() == "SUCCESS"
        assert result.stderr.strip() == "LOG"
        assert result.timed_out is False


def test_run_provider_cli_enforces_credential_isolation(monkeypatch):
    """Verify child CLI process cannot see parent credential environment variables."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-parent-secret-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-parent-secret-leak")

    with tempfile.TemporaryDirectory() as tmp_dir:
        code = (
            "import os, sys\n"
            "openai = os.environ.get('OPENAI_API_KEY', 'NOT_FOUND')\n"
            "anthropic = os.environ.get('ANTHROPIC_API_KEY', 'NOT_FOUND')\n"
            "sys.stdout.write(f'{openai}|{anthropic}')\n"
        )
        cmd = [sys.executable, "-c", code]
        result = run_provider_cli(cmd, cwd=tmp_dir, timeout_seconds=10)

        assert result.exit_code == 0
        assert result.stdout == "NOT_FOUND|NOT_FOUND"


def test_run_provider_cli_timeout_enforcement():
    """Verify CLI processes exceeding timeout bounds are terminated."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
        result = run_provider_cli(cmd, cwd=tmp_dir, timeout_seconds=1)

        assert result.timed_out is True
        assert result.exit_code == -1


def test_run_provider_cli_command_not_found():
    """Verify non-existent executable returns exit code 127 and descriptive error."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = ["non_existent_provider_binary_12345", "--version"]
        result = run_provider_cli(cmd, cwd=tmp_dir, timeout_seconds=5)

        assert result.exit_code == 127
        assert "Command not found" in result.stderr
        assert result.timed_out is False


def test_run_provider_cli_custom_env_injection():
    """Verify custom environment passed to run_provider_cli is accessible to child process."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        code = "import os, sys; sys.stdout.write(os.environ.get('AGENT_RUN_ID', 'MISSING'))"
        cmd = [sys.executable, "-c", code]
        result = run_provider_cli(
            cmd,
            cwd=tmp_dir,
            timeout_seconds=5,
            custom_env={"AGENT_RUN_ID": "run-42-isolated"},
        )

        assert result.exit_code == 0
        assert result.stdout == "run-42-isolated"
