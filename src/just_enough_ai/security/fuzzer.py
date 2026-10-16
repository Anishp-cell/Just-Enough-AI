"""Adversarial boundary fuzzer for generated code.

Mayank (Security Lead): Automatically synthesize hostile edge-case inputs for candidate functions
and execute them in the sandbox to verify crash resilience.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
import ast
import base64
import json
import sys

from just_enough_ai.agent.sandbox import run_in_sandbox


@dataclass
class FuzzResult:
    passed: bool
    total_cases: int
    failed_cases: List[str] = field(default_factory=list)
    error_details: List[str] = field(default_factory=list)


NUMERICAL_BOUNDARIES = [
    0,
    -1,
    "__NAN__",
    "__INF__",
    "__NEGINF__",
    2147483647,
    -2147483648,
]

STRING_BOUNDARIES = [
    "",
    "   ",
    "\x00",
    "A" * 10000,
    "<script>alert(1)</script>",
]

COLLECTION_BOUNDARIES = [
    None,
    [],
    [None],
    {},
    {"nested": None},
]

ALL_BOUNDARIES = (
    NUMERICAL_BOUNDARIES
    + STRING_BOUNDARIES
    + COLLECTION_BOUNDARIES
)

HARNESS_TEMPLATE = r'''
import sys
import json
import math
import base64
import inspect

b64_code = "{b64_code}"
source_code = base64.b64decode(b64_code).decode("utf-8")

namespace = {}
try:
    exec(source_code, namespace)
except Exception as e:
    print("__FUZZ_RESULT__" + json.dumps({
        "passed": False,
        "total_cases": 1,
        "failed_cases": [f"Source execution failed: {type(e).__name__}: {e}"],
        "error_details": [str(e)]
    }))
    sys.exit(0)

total_cases = 0
failed_cases = []
error_details = []

# boundary_data_json is base64-encoded JSON to safely pass None/null across process boundary
boundary_data = json.loads(base64.b64decode("{boundary_data_b64}").decode("utf-8"))

for func_name, test_cases in boundary_data.items():
    if func_name not in namespace:
        continue
    fn = namespace[func_name]
    if not callable(fn):
        continue

    for case in test_cases:
        total_cases += 1
        args = []
        for val in case:
            if val == "__NAN__":
                args.append(float("nan"))
            elif val == "__INF__":
                args.append(float("inf"))
            elif val == "__NEGINF__":
                args.append(float("-inf"))
            else:
                args.append(val)
        try:
            res = fn(*args)
            if inspect.iscoroutine(res):
                import asyncio
                asyncio.run(res)
        except (ValueError, TypeError):
            # Expected validation errors pass
            pass
        except Exception as e:
            arg_strs = []
            for a in args:
                if isinstance(a, str) and len(a) > 20:
                    arg_strs.append(f"{repr(a[:17])}...")
                else:
                    arg_strs.append(repr(a))
            call_sig = f"{func_name}({', '.join(arg_strs)})"
            failed_cases.append(f"{call_sig} -> {type(e).__name__}: {e}")
            error_details.append(f"{type(e).__name__}: {e}")

print("__FUZZ_RESULT__" + json.dumps({
    "passed": len(failed_cases) == 0,
    "total_cases": total_cases,
    "failed_cases": failed_cases,
    "error_details": error_details
}))
'''


def _get_arg_type(arg: ast.arg) -> str:
    """Infer basic category from annotation."""
    if arg.annotation:
        if isinstance(arg.annotation, ast.Name):
            name = arg.annotation.id.lower()
            if name in ("int", "float", "number"):
                return "numeric"
            if name in ("str", "text", "bytes"):
                return "string"
            if name in ("list", "dict", "set", "tuple", "sequence"):
                return "collection"
        elif isinstance(arg.annotation, ast.Subscript):
            if isinstance(arg.annotation.value, ast.Name):
                name = arg.annotation.value.id.lower()
                if name in ("list", "dict", "set", "tuple", "sequence", "optional", "union"):
                    return "collection"
    return "any"


def fuzz_generated_code(source_code: str, timeout_seconds: int = 5) -> FuzzResult:
    """Parse source_code, infer I/O contract, synthesize hostile inputs, and verify resilience."""
    # 1. Parse AST
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        return FuzzResult(
            passed=False,
            total_cases=1,
            failed_cases=["SyntaxError"],
            error_details=[f"Syntax error: {e}"],
        )

    # 2. Find all top-level functions
    funcs = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    if not funcs:
        return FuzzResult(passed=True, total_cases=0, failed_cases=[], error_details=[])

    # 3. Synthesize boundary inputs for each function
    boundary_data: Dict[str, List[List[Any]]] = {}

    for func in funcs:
        args = [a for a in func.args.args if a.arg != "self"]
        n_args = len(args)

        if n_args == 0:
            boundary_data[func.name] = [[]]
            continue

        arg_types = [_get_arg_type(a) for a in args]
        arg_boundary_lists = []
        safe_defaults = []

        for atype in arg_types:
            if atype == "numeric":
                arg_boundary_lists.append(NUMERICAL_BOUNDARIES + [None])
                safe_defaults.append(1)
            elif atype == "string":
                arg_boundary_lists.append(STRING_BOUNDARIES + [None])
                safe_defaults.append("valid_string")
            elif atype == "collection":
                arg_boundary_lists.append(COLLECTION_BOUNDARIES)
                safe_defaults.append([])
            else:
                arg_boundary_lists.append(ALL_BOUNDARIES)
                safe_defaults.append(0)

        test_cases: List[List[Any]] = []

        if n_args == 1:
            for b in arg_boundary_lists[0]:
                test_cases.append([b])
        else:
            # Single-argument perturbation
            for i in range(n_args):
                for b in arg_boundary_lists[i]:
                    case = list(safe_defaults)
                    case[i] = b
                    test_cases.append(case)

            # Uniform edge combinations
            for common_edge in [None, 0, "", [], {}]:
                test_cases.append([common_edge] * n_args)

        boundary_data[func.name] = test_cases

    # 4. Generate harness script
    b64_code = base64.b64encode(source_code.encode("utf-8")).decode("ascii")
    boundary_data_b64 = base64.b64encode(
        json.dumps(boundary_data).encode("utf-8")
    ).decode("ascii")

    harness_code = HARNESS_TEMPLATE.replace("{b64_code}", b64_code).replace(
        "{boundary_data_b64}", boundary_data_b64
    )


    # 5. Run via run_in_sandbox
    sandbox_res = run_in_sandbox(
        [sys.executable, "-c", harness_code],
        timeout_seconds=timeout_seconds,
    )

    if sandbox_res.timed_out:
        return FuzzResult(
            passed=False,
            total_cases=1,
            failed_cases=["TimeoutExpired: Fuzzing subprocess timed out."],
            error_details=[sandbox_res.stderr or "Timed out"],
        )

    # Parse JSON from stdout
    output = sandbox_res.stdout
    marker = "__FUZZ_RESULT__"
    if marker in output:
        try:
            json_str = output.split(marker, 1)[1].strip()
            data = json.loads(json_str)
            return FuzzResult(
                passed=data.get("passed", False),
                total_cases=data.get("total_cases", 0),
                failed_cases=data.get("failed_cases", []),
                error_details=data.get("error_details", []),
            )
        except Exception as e:
            return FuzzResult(
                passed=False,
                total_cases=1,
                failed_cases=["Failed to parse fuzzer harness output"],
                error_details=[f"Error: {e}, Output: {output}"],
            )

    return FuzzResult(
        passed=False,
        total_cases=1,
        failed_cases=[f"Fuzzer harness exited with code {sandbox_res.exit_code}"],
        error_details=[sandbox_res.stderr or sandbox_res.stdout],
    )
