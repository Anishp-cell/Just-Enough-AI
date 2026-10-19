"""Comprehensive test suite for Data & Benchmarks deliverables.

Validates:
1. Benchmark task suite (data/benchmarks/tasks_v1.json and schema.json)
2. Edge cases corpus (data/edge_cases/)
3. Evaluation models and cost comparison calculations (src/just_enough_ai/eval/)
"""

import ast
import glob
import importlib.util
import json
from pathlib import Path
import pytest

from just_enough_ai.models import ModelTier, ExecutionMode
from just_enough_ai.router.cost import calculate_cost, calculate_savings_vs_ultra
from just_enough_ai.eval.models import (
    BaselineModel,
    BASELINE_PRICING,
    TaskEvalResult,
    TierMetrics,
    BenchmarkSuiteReport,
)
from just_enough_ai.eval.runner import (
    calculate_baseline_cost,
    evaluate_single_task,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


# ── 1. Benchmark Dataset & Schema Tests ─────────────────────────────────────

def test_benchmark_schema_validation():
    """Verify tasks_v1.json conforms strictly to data/benchmarks/schema.json."""
    tasks_file = ROOT_DIR / "data" / "benchmarks" / "tasks_v1.json"
    schema_file = ROOT_DIR / "data" / "benchmarks" / "schema.json"

    assert tasks_file.exists(), "tasks_v1.json must exist"
    assert schema_file.exists(), "schema.json must exist"

    tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
    schema_data = json.loads(schema_file.read_text(encoding="utf-8"))

    # Verify top-level required fields
    for req in schema_data.get("required", []):
        assert req in tasks_data, f"Missing required top-level property: {req}"

    assert isinstance(tasks_data["schema_version"], str)
    assert isinstance(tasks_data["description"], str)
    assert tasks_data["total_tasks"] == 50
    assert tasks_data["tier_distribution"] == {"nano": 20, "super": 20, "ultra": 10}

    # Verify task item schema requirements
    task_schema = schema_data["properties"]["tasks"]["items"]
    task_required = task_schema.get("required", [])

    for task in tasks_data["tasks"]:
        for req in task_required:
            assert req in task, f"Task {task.get('id', 'unknown')} missing required field: {req}"
        assert task["expected_tier"] in ("nano", "super", "ultra")
        assert task["difficulty"] in ("simple", "moderate", "complex")
        assert isinstance(task["evaluation_criteria"], list) and len(task["evaluation_criteria"]) >= 1

    # Optional jsonschema library validation if present
    try:
        import jsonschema
        jsonschema.validate(instance=tasks_data, schema=schema_data)
    except ImportError:
        pass


def test_benchmark_task_count_and_tier_distribution():
    """Verify exactly 50 tasks with 20 Nano, 20 Super, and 10 Ultra distribution."""
    tasks_file = ROOT_DIR / "data" / "benchmarks" / "tasks_v1.json"
    tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))

    tasks = tasks_data.get("tasks", [])
    assert len(tasks) == 50, f"Expected exactly 50 tasks, got {len(tasks)}"

    nano_count = sum(1 for t in tasks if t["expected_tier"] == "nano")
    super_count = sum(1 for t in tasks if t["expected_tier"] == "super")
    ultra_count = sum(1 for t in tasks if t["expected_tier"] == "ultra")

    assert nano_count == 20, f"Expected 20 nano tasks, got {nano_count}"
    assert super_count == 20, f"Expected 20 super tasks, got {super_count}"
    assert ultra_count == 10, f"Expected 10 ultra tasks, got {ultra_count}"


def test_benchmark_tasks_have_unique_ids_and_required_fields():
    """Verify all task IDs are unique and required fields are populated."""
    tasks_file = ROOT_DIR / "data" / "benchmarks" / "tasks_v1.json"
    tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))

    tasks = tasks_data.get("tasks", [])
    seen_ids = set()

    for idx, t in enumerate(tasks):
        task_id = t["id"]
        assert task_id not in seen_ids, f"Duplicate task ID found: {task_id}"
        seen_ids.add(task_id)

        assert len(t["prompt"].strip()) >= 10, f"Task {task_id} prompt is too short"
        assert t["expected_tier"] in ("nano", "super", "ultra")
        assert t["difficulty"] in ("simple", "moderate", "complex")
        assert t["category"], f"Task {task_id} missing category"
        assert t["description"], f"Task {task_id} missing description"
        assert t["expected_behavior"], f"Task {task_id} missing expected_behavior"
        assert isinstance(t["evaluation_criteria"], list) and len(t["evaluation_criteria"]) >= 2


# ── 2. Edge Cases Corpus Tests ──────────────────────────────────────────────

def test_edge_cases_manifest_integrity():
    """Verify data/edge_cases/manifest.json indexes all 15 edge case files."""
    manifest_file = ROOT_DIR / "data" / "edge_cases" / "manifest.json"
    assert manifest_file.exists(), "manifest.json must exist in data/edge_cases/"

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    cases = manifest.get("edge_cases", [])
    assert len(cases) == 15, f"Expected 15 edge cases in manifest, got {len(cases)}"

    for c in cases:
        case_file = ROOT_DIR / "data" / "edge_cases" / c["file"]
        assert case_file.exists(), f"Case file {c['file']} referenced in manifest does not exist"
        assert c["case_id"].startswith("EC-")
        assert c["category"]
        assert c["trigger_input"]
        assert c["expected_exception"]


def test_edge_cases_execution_and_remediation():
    """Verify each edge case file parses as valid Python and passes its test_edge_case()."""
    case_files = sorted(glob.glob(str(ROOT_DIR / "data" / "edge_cases" / "case_*.py")))
    assert len(case_files) == 15, f"Expected 15 case files, found {len(case_files)}"

    for cf in case_files:
        path = Path(cf)
        content = path.read_text(encoding="utf-8")

        # Must parse as valid Python AST
        tree = ast.parse(content, filename=str(path))
        assert tree is not None

        # Load and execute test_edge_case()
        spec = importlib.util.spec_from_file_location(path.stem, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert hasattr(mod, "EDGE_CASE_METADATA"), f"{path.name} missing EDGE_CASE_METADATA"
        assert hasattr(mod, "test_edge_case"), f"{path.name} missing test_edge_case()"
        assert mod.test_edge_case() is True, f"{path.name} test_edge_case() failed"


# ── 3. Evaluation Engine & Cost Telemetry Tests ─────────────────────────────

def test_baseline_cost_calculations():
    """Verify third-party baseline model cost formulas match standard pricing."""
    # 1M tokens (500k input, 500k output) on GPT-4o:
    # 0.5M * $2.50 + 0.5M * $10.00 = $1.25 + $5.00 = $6.25
    cost_gpt4o = calculate_baseline_cost(BaselineModel.GPT_4O, 500_000, 500_000)
    assert cost_gpt4o == 6.25

    # 1M tokens on Claude 3.5 Sonnet:
    # 0.5M * $3.00 + 0.5M * $15.00 = $1.50 + $7.50 = $9.00
    cost_claude = calculate_baseline_cost(BaselineModel.CLAUDE_35_SONNET, 500_000, 500_000)
    assert cost_claude == 9.00

    # 1M tokens on Nemotron Ultra:
    # 0.5M * $0.80 + 0.5M * $2.80 = $0.40 + $1.40 = $1.80
    cost_ultra = calculate_baseline_cost(BaselineModel.NEMOTRON_ULTRA, 500_000, 500_000)
    assert cost_ultra == 1.80


def test_evaluate_single_task_output_contract():
    """Verify evaluate_single_task produces valid telemetry, costs, and safety flags."""
    sample_task = {
        "id": "test_001",
        "prompt": "def add(a: int, b: int) -> int: return a + b",
        "expected_tier": "nano",
        "difficulty": "simple",
        "category": "test",
    }

    result = evaluate_single_task(sample_task, mode=ExecutionMode.REMOTE_CLOUD, mock_override=True)

    assert isinstance(result, TaskEvalResult)
    assert result.task_id == "test_001"
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.total_tokens == result.prompt_tokens + result.completion_tokens
    assert result.actual_cost_usd > 0.0
    assert result.cost_ultra_usd >= result.actual_cost_usd
    assert result.savings_pct_vs_ultra >= 0.0
    assert result.syntax_valid is True
    assert result.steerlm_score >= 0.75
    assert result.steerlm_passed is True
    assert result.fuzzer_passed is True
    assert result.task_success is True


def test_benchmark_results_and_reports_exist():
    """Verify that generated benchmark artifacts exist and are non-empty."""
    results_json = ROOT_DIR / "data" / "results" / "benchmark_results.json"
    report_md = ROOT_DIR / "data" / "results" / "benchmark_report.md"
    provider_md = ROOT_DIR / "data" / "results" / "provider_benchmark.md"

    assert results_json.exists(), "benchmark_results.json must exist"
    assert report_md.exists(), "benchmark_report.md must exist"
    assert provider_md.exists(), "provider_benchmark.md must exist"

    results_data = json.loads(results_json.read_text(encoding="utf-8"))
    assert results_data["total_tasks"] == 50
    assert "savings_pct_vs_ultra" in results_data
    assert "tier_metrics" in results_data
