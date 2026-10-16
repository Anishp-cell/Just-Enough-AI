"""Subprocess execution sandbox.

Mayank (Security Lead): Subprocess execution sandbox & path traversal defense.
Requirements:
1. `validate_safe_path`: Prevent directory traversal attacks (e.g. `../`, symlinks escaping project root).
2. `run_in_sandbox`: Execute command in isolated subprocess with hard execution timeout,
   working directory restriction, and captured stdout/stderr.
"""

from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path
import subprocess


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def validate_safe_path(path: str, project_root: str = ".") -> bool:
    """Return True if path stays strictly within project_root. Blocks ../ escapes."""
    try:
        if not path or "\x00" in path:
            return False
        root = Path(project_root).resolve()
        p = Path(path)
        if p.is_absolute():
            target = p.resolve()
        else:
            target = (root / p).resolve()

        return target.is_relative_to(root)
    except (ValueError, OSError):
        return False


def run_in_sandbox(
    cmd: List[str],
    cwd: str = ".",
    timeout_seconds: int = 10,
    allowed_root: Optional[str] = None,
) -> SandboxResult:
    """Run command in isolated subprocess with hard timeout and output capture."""
    if allowed_root is not None:
        if not validate_safe_path(cwd, allowed_root):
            raise PermissionError(
                f"Working directory '{cwd}' is not within allowed root '{allowed_root}'."
            )

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return SandboxResult(
            stdout=stdout or "",
            stderr=stderr or "",
            exit_code=proc.returncode if proc.returncode is not None else 0,
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except Exception:
            stdout, stderr = "", ""
        return SandboxResult(
            stdout=stdout or "",
            stderr=stderr or "Execution timed out.",
            exit_code=-1,
            timed_out=True,
        )
    except Exception as e:
        return SandboxResult(
            stdout="",
            stderr=str(e),
            exit_code=1,
            timed_out=False,
        )
