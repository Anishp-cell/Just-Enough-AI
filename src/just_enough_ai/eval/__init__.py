"""Evaluation and benchmarking module for Just-Enough-AI."""

from .models import (
    BaselineModel,
    BASELINE_PRICING,
    TaskEvalResult,
    TierMetrics,
    ProviderBenchmarkResult,
    BenchmarkSuiteReport,
)
from .runner import (
    evaluate_single_task,
    run_benchmark_suite,
    run_provider_resilience_benchmark,
    generate_markdown_report,
    generate_provider_markdown_report,
)

__all__ = [
    "BaselineModel",
    "BASELINE_PRICING",
    "TaskEvalResult",
    "TierMetrics",
    "ProviderBenchmarkResult",
    "BenchmarkSuiteReport",
    "evaluate_single_task",
    "run_benchmark_suite",
    "run_provider_resilience_benchmark",
    "generate_markdown_report",
    "generate_provider_markdown_report",
]
