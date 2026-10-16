"""AST Security Invariant Linter.

Mayank (Security Lead): Statically scan agent-generated code using Python's `ast` module
to block dangerous Python constructs before they are ever executed.
"""

from dataclasses import dataclass, field
from typing import List
import ast
import re


@dataclass
class LintResult:
    passed: bool
    violations: List[str] = field(default_factory=list)


DANGEROUS_BUILTINS = {"eval", "exec", "compile", "__import__"}
DANGEROUS_MODULES = {"pty", "socket", "ctypes"}
DANGEROUS_OS_CALLS = {
    "system",
    "popen",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
}
SUBPROCESS_CALLS = {"Popen", "run", "call", "check_call", "check_output"}

CREDENTIAL_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "Hardcoded OpenAI/Nebius secret key pattern (sk-...)"),
    (re.compile(r"token\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE), "Hardcoded token assignment"),
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"), "Hardcoded GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{22,}"), "Hardcoded GitHub Personal Access Token"),
    (re.compile(r"Bearer\s+['\"]?[A-Za-z0-9\-_\.=]{16,}", re.IGNORECASE), "Hardcoded Bearer authentication token"),
    (
        re.compile(r"(?:api[_-]?key|secret|password|access_token)\s*=\s*['\"][A-Za-z0-9_\-\.]{16,}['\"]", re.IGNORECASE),
        "Hardcoded API credential assignment",
    ),
]


class SecurityASTVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in DANGEROUS_MODULES:
                self.violations.append(
                    f"Disallowed import '{alias.name}' at line {node.lineno}: import of {base_mod} is blocked."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in DANGEROUS_MODULES:
                self.violations.append(
                    f"Disallowed import from '{node.module}' at line {node.lineno}: import from {base_mod} is blocked."
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 1. Direct calls like eval(...), exec(...), compile(...), __import__(...)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in DANGEROUS_BUILTINS:
                self.violations.append(
                    f"Disallowed call to '{func_name}()' at line {node.lineno}: execution of dynamic code is prohibited."
                )
        # 2. Attribute calls like os.system(...), builtins.eval(...)
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in DANGEROUS_BUILTINS:
                self.violations.append(
                    f"Disallowed call to '{attr_name}()' at line {node.lineno}: execution of dynamic code is prohibited."
                )

            # Check os.system, os.popen, etc.
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                if attr_name in DANGEROUS_OS_CALLS:
                    self.violations.append(
                        f"Disallowed shell execution via 'os.{attr_name}()' at line {node.lineno}."
                    )

            # Check subprocess calls
            is_subprocess = (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
                and attr_name in SUBPROCESS_CALLS
            )
            if is_subprocess or attr_name in SUBPROCESS_CALLS:
                for kw in node.keywords:
                    if kw.arg == "shell":
                        # Check if shell is Truthy
                        if isinstance(kw.value, ast.Constant) and bool(kw.value.value):
                            self.violations.append(
                                f"Disallowed raw shell execution 'shell=True' in '{attr_name}()' at line {node.lineno}."
                            )

        # Also check any keyword argument shell=True in any function call
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and bool(kw.value.value):
                msg = f"Disallowed raw shell execution 'shell=True' at line {node.lineno}."
                if msg not in self.violations:
                    self.violations.append(msg)

        self.generic_visit(node)


def lint_code_security(code: str) -> LintResult:
    """Statically scan code for security invariant violations before execution."""
    violations: List[str] = []

    # 1. AST Parsing & Syntax Validation
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return LintResult(
            passed=False,
            violations=[f"Syntax error at line {e.lineno}: {e.msg}"],
        )

    # 2. AST Visitor checks
    visitor = SecurityASTVisitor()
    visitor.visit(tree)
    violations.extend(visitor.violations)

    # 3. Credential & Secret scanning
    for pattern, desc in CREDENTIAL_PATTERNS:
        matches = pattern.findall(code)
        if matches:
            violations.append(f"Hardcoded credential detected ({desc}).")

    return LintResult(
        passed=len(violations) == 0,
        violations=violations,
    )
