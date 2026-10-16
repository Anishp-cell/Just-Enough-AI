"""Comprehensive test suite for Workstream 2: The Sentinel (Cybersecurity Lead).

Validates:
M-1: Subprocess execution sandbox (run_in_sandbox)
M-2: Path traversal guard (validate_safe_path)
M-3: AST security invariant linter (lint_code_security)
M-4: Adversarial boundary fuzzer (fuzz_generated_code)
M-5: Telemetry secret masking (mask_secrets & logger filter)
M-6: Differential AST Scope Lock (apply_ast_scope_lock)
"""

import sys
import os
import logging
import tempfile
from pathlib import Path

# Ensure src is in sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from just_enough_ai.agent.sandbox import run_in_sandbox, validate_safe_path, SandboxResult
from just_enough_ai.security.linter import lint_code_security, LintResult
from just_enough_ai.security.fuzzer import fuzz_generated_code, FuzzResult
from just_enough_ai.telemetry.logger import mask_secrets, logger
from just_enough_ai.security.ast_lock import apply_ast_scope_lock, ScopeLockResult


# ── M-1: Subprocess Execution Sandbox Tests ─────────────────────────────────

def test_sandbox_runs_command_and_captures_output():
    """Verify clean command execution with captured stdout/stderr."""
    res = run_in_sandbox([sys.executable, "-c", "import sys; sys.stdout.write('hello'); sys.stderr.write('world')"])
    assert res.stdout == "hello"
    assert res.stderr == "world"
    assert res.exit_code == 0
    assert res.timed_out is False


def test_sandbox_enforces_hard_timeout():
    """Verify processes exceeding timeout are killed and marked as timed out."""
    res = run_in_sandbox(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        timeout_seconds=1,
    )
    assert res.timed_out is True
    assert res.exit_code == -1


def test_sandbox_enforces_allowed_root():
    """Verify cwd restriction blocks directories outside allowed root."""
    with tempfile.TemporaryDirectory() as tmp_root:
        inside = Path(tmp_root) / "sub"
        inside.mkdir()
        outside = Path(tmp_root).parent

        # Safe directory inside allowed root succeeds
        res = run_in_sandbox(
            [sys.executable, "-c", "print('inside')"],
            cwd=str(inside),
            allowed_root=tmp_root,
        )
        assert res.exit_code == 0
        assert "inside" in res.stdout

        # Directory outside allowed root raises PermissionError
        with pytest.raises(PermissionError):
            run_in_sandbox(
                [sys.executable, "-c", "print('outside')"],
                cwd=str(outside),
                allowed_root=tmp_root,
            )


# ── M-2: Path Traversal Defense Tests ───────────────────────────────────────

def test_path_traversal_allows_safe_relative_paths(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    file_path = root / "src" / "agent.py"
    file_path.parent.mkdir()
    file_path.touch()

    assert validate_safe_path("src/agent.py", project_root=str(root)) is True
    assert validate_safe_path(".", project_root=str(root)) is True
    assert validate_safe_path("src", project_root=str(root)) is True


def test_path_traversal_blocks_parent_directory_escapes(tmp_path):
    root = tmp_path / "project"
    root.mkdir()

    assert validate_safe_path("../outside.txt", project_root=str(root)) is False
    assert validate_safe_path("../../etc/passwd", project_root=str(root)) is False
    assert validate_safe_path("sub/../../outside.txt", project_root=str(root)) is False


def test_path_traversal_blocks_absolute_paths_outside_root(tmp_path):
    root = tmp_path / "project"
    root.mkdir()

    if sys.platform == "win32":
        assert validate_safe_path("C:\\Windows\\System32\\cmd.exe", project_root=str(root)) is False
    else:
        assert validate_safe_path("/etc/passwd", project_root=str(root)) is False


def test_path_traversal_blocks_null_bytes(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    assert validate_safe_path("test.txt\x00.evil", project_root=str(root)) is False


def test_path_traversal_blocks_symlink_escapes(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("API_KEY=123")

    link = root / "escape_link"
    try:
        os.symlink(str(secret), str(link))
        assert validate_safe_path("escape_link", project_root=str(root)) is False
    except (OSError, NotImplementedError):
        # On Windows, symlink creation might require privileges; skip if cannot create
        pass


# ── M-3: AST Security Invariant Linter Tests ────────────────────────────────

def test_linter_allows_safe_code():
    safe_code = """
def calculate_sum(a: int, b: int) -> int:
    result = a + b
    return result

class DataProcessor:
    def __init__(self, multiplier: int = 1):
        self.multiplier = multiplier

    def process(self, values):
        return [v * self.multiplier for v in values]
"""
    res = lint_code_security(safe_code)
    assert res.passed is True
    assert len(res.violations) == 0


def test_linter_blocks_dynamic_code_execution():
    code_eval = "def run():\n    return eval('2 + 2')"
    res = lint_code_security(code_eval)
    assert res.passed is False
    assert any("eval" in v for v in res.violations)

    code_exec = "def run(c):\n    exec(c)"
    res = lint_code_security(code_exec)
    assert res.passed is False
    assert any("exec" in v for v in res.violations)

    code_import = "def run():\n    return __import__('os')"
    res = lint_code_security(code_import)
    assert res.passed is False
    assert any("__import__" in v for v in res.violations)


def test_linter_blocks_dangerous_imports():
    code_socket = "import socket\ndef ping(): pass"
    res = lint_code_security(code_socket)
    assert res.passed is False
    assert any("socket" in v for v in res.violations)

    code_pty = "from pty import fork\ndef shell(): pass"
    res = lint_code_security(code_pty)
    assert res.passed is False
    assert any("pty" in v for v in res.violations)

    code_ctypes = "import ctypes\ndef crash(): pass"
    res = lint_code_security(code_ctypes)
    assert res.passed is False
    assert any("ctypes" in v for v in res.violations)


def test_linter_blocks_shell_execution():
    code_os_sys = "import os\ndef bad():\n    os.system('rm -rf /')"
    res = lint_code_security(code_os_sys)
    assert res.passed is False
    assert any("os.system" in v for v in res.violations)

    code_subproc = "import subprocess\ndef bad():\n    subprocess.Popen('ls', shell=True)"
    res = lint_code_security(code_subproc)
    assert res.passed is False
    assert any("shell=True" in v for v in res.violations)


def test_linter_blocks_hardcoded_credentials():
    code_sk = 'OPENAI_KEY = "sk-abcdef1234567890abcdef12345678901234"'
    res = lint_code_security(code_sk)
    assert res.passed is False
    assert any("credential" in v.lower() for v in res.violations)

    code_token = 'token = "1234567890abcdef1234567890"'
    res = lint_code_security(code_token)
    assert res.passed is False
    assert any("token" in v.lower() or "credential" in v.lower() for v in res.violations)


# ── M-4: Adversarial Boundary Fuzzer Tests ─────────────────────────────────

def test_fuzzer_passes_resilient_function():
    code = """
def safe_divide(a: int, b: int) -> float:
    if b == 0 or b is None or a is None:
        raise ValueError("Invalid divisor or input")
    try:
        return float(a) / float(b)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Conversion error")
"""
    res = fuzz_generated_code(code, timeout_seconds=5)
    assert res.passed is True
    assert res.total_cases > 0
    assert len(res.failed_cases) == 0


def test_fuzzer_catches_unhandled_crash_exception():
    fragile_code = """
def fragile_lookup(items: list, index: int):
    # Unhandled IndexError and TypeError when input is None or empty list
    return items[index]
"""
    res = fuzz_generated_code(fragile_code, timeout_seconds=5)
    assert res.passed is False
    assert len(res.failed_cases) > 0
    assert any("IndexError" in d or "TypeError" in d for d in res.error_details) or \
           any("IndexError" in f or "TypeError" in f for f in res.failed_cases)



def test_fuzzer_handles_syntax_error():
    syntax_error_code = "def bad_syntax(a, b: return a +"
    res = fuzz_generated_code(syntax_error_code, timeout_seconds=2)
    assert res.passed is False
    assert any("syntax" in v.lower() for v in res.failed_cases)


# ── M-5: Telemetry Secret Masking Tests ─────────────────────────────────────

def test_mask_secrets_redacts_credentials():
    raw_text = (
        "Connected with key sk-proj1234567890abcdef1234567890 and "
        "token ghp_123456789012345678901234567890123456 and "
        "header Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    )
    masked = mask_secrets(raw_text)
    assert "sk-proj1234567890" not in masked
    assert "ghp_1234567890" not in masked
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in masked
    assert "[REDACTED_SECRET]" in masked


def test_logging_filter_automatically_masks_secrets(caplog):
    caplog.set_level(logging.INFO)
    logger.info("Executing task with token: sk-live987654321098765432109876543210")
    for record in caplog.records:
        assert "sk-live" not in record.message
        assert "[REDACTED_SECRET]" in record.message


# ── M-6: Differential AST Scope Lock Tests ─────────────────────────────────

def test_ast_scope_lock_allows_in_scope_edits():
    original = """
def target_function(x: int) -> int:
    return x + 1

def immutable_function(y: int) -> int:
    return y * 2
"""
    proposed = """
def target_function(x: int) -> int:
    return x + 100

def immutable_function(y: int) -> int:
    return y * 2
"""
    res = apply_ast_scope_lock(original, proposed, target_symbol_names=["target_function"])
    assert len(res.unauthorized_mutations_reverted) == 0
    assert "x + 100" in res.applied_code
    assert "y * 2" in res.applied_code


def test_ast_scope_lock_reverts_unauthorized_modifications():
    original = """
def target_function(x: int) -> int:
    return x + 1

def immutable_function(y: int) -> int:
    return y * 2
"""
    # Malicious or hallucinatory mutation modifying immutable_function
    proposed = """
def target_function(x: int) -> int:
    return x + 100

def immutable_function(y: int) -> int:
    return 0  # Collateral mutation!
"""
    res = apply_ast_scope_lock(original, proposed, target_symbol_names=["target_function"])
    assert len(res.unauthorized_mutations_reverted) == 1
    assert "immutable_function" in res.unauthorized_mutations_reverted[0]
    # Verify the immutable function was reverted back to original y * 2
    assert "y * 2" in res.applied_code
    assert "return 0" not in res.applied_code
    # Verify in-scope function keeps the modification
    assert "x + 100" in res.applied_code


def test_ast_scope_lock_restores_deleted_symbols():
    original = """
def target_function():
    return 1

def critical_security_check():
    return True
"""
    # Proposed accidentally drops critical_security_check
    proposed = """
def target_function():
    return 42
"""
    res = apply_ast_scope_lock(original, proposed, target_symbol_names=["target_function"])
    assert len(res.unauthorized_mutations_reverted) == 1
    assert "critical_security_check" in res.unauthorized_mutations_reverted[0]
    assert "critical_security_check" in res.applied_code
    assert "return True" in res.applied_code
