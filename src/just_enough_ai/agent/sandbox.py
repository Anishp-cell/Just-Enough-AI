"""Subprocess execution sandbox.

Mayank (Security Lead): Implement the function bodies below.
Requirements:
1. `validate_safe_path`: Prevent directory traversal attacks (e.g. `../`, symlinks escaping project root).
2. `run_in_sandbox`: Execute command in isolated subprocess with hard execution timeout,
   working directory restriction, and captured stdout/stderr.
"""

from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def validate_safe_path(path: str, project_root: str = ".") -> bool:
    """Return True if path stays strictly within project_root. Blocks ../ escapes."""
    raise NotImplementedError("Mayank to implement validate_safe_path")


def run_in_sandbox(
    cmd: List[str],
    cwd: str = ".",
    timeout_seconds: int = 10,
    allowed_root: Optional[str] = None,
) -> SandboxResult:
    """Run command in isolated subprocess with hard timeout and output capture."""
    raise NotImplementedError("Mayank to implement run_in_sandbox")
