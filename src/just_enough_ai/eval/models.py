"""Data models for evaluation and benchmarking suite."""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from ..models import ModelTier, ExecutionMode


class BaselineModel(str, Enum):
    """External baseline models used for cost comparisons."""
    NEMOTRON_ULTRA = "nemotron_ultra"
    GPT_4O = "gpt_4o"
    CLAUDE_35_SONNET = "claude_35_sonnet"


BASELINE_PRICING = {
    BaselineModel.NEMOTRON_ULTRA: {
        "name": "NVIDIA Nemotron Ultra 253B",
        "input_per_1m": 0.80,
        "output_per_1m": 2.80,
        "blended_per_1m": 1.80,
    },
    BaselineModel.GPT_4O: {
        "name": "OpenAI GPT-4o",
        "input_per_1m": 2.50,
        "output_per_1m": 10.00,
        "blended_per_1m": 6.25,
    },
    BaselineModel.CLAUDE_35_SONNET: {
        "name": "Anthropic Claude 3.5 Sonnet",
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
        "blended_per_1m": 9.00,
    },
}


class TaskEvalResult(BaseModel):
    """Evaluation result for an individual benchmark task."""
    task_id: str
    difficulty: str
    category: str
    expected_tier: ModelTier
    routed_tier: ModelTier
    routing_match: bool
    model_id: str
    execution_mode: ExecutionMode

    # Telemetry
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0

    # Costs
    actual_cost_usd: float = 0.0
    cost_ultra_usd: float = 0.0
    cost_gpt4o_usd: float = 0.0
    cost_claude_usd: float = 0.0

    # Savings
    savings_vs_ultra_usd: float = 0.0
    savings_pct_vs_ultra: float = 0.0
    savings_vs_gpt4o_usd: float = 0.0
    savings_pct_vs_gpt4o: float = 0.0

    # Quality & Safety PR gates
    syntax_valid: bool = True
    steerlm_score: float = 0.0
    steerlm_passed: bool = False
    fuzzer_passed: bool = True
    task_success: bool = True


class TierMetrics(BaseModel):
    """Aggregated metrics for a single model tier."""
    tier: ModelTier
    task_count: int = 0
    routing_accuracy_pct: float = 0.0
    avg_latency_ms: float = 0.0
    total_tokens: int = 0
    avg_tokens_per_task: float = 0.0
    total_cost_usd: float = 0.0
    avg_cost_per_task_usd: float = 0.0
    total_savings_vs_ultra_usd: float = 0.0
    savings_pct_vs_ultra: float = 0.0


class ProviderBenchmarkResult(BaseModel):
    """Telemetry result for a specific inference provider adapter."""
    provider_name: str
    adapter_type: str
    is_available: bool
    is_free_tier: bool
    cold_start_latency_ms: float = 0.0
    avg_task_latency_ms: float = 0.0
    cost_per_task_usd: float = 0.0
    rate_limit_resilient: bool = True
    failover_recovery_time_ms: Optional[float] = None


class BenchmarkSuiteReport(BaseModel):
    """Comprehensive benchmark suite evaluation report."""
    timestamp: str
    schema_version: str = "1.0"
    total_tasks: int
    execution_mode: ExecutionMode
    routing_accuracy_pct: float
    overall_task_success_pct: float
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int

    # Financial telemetry
    total_actual_cost_usd: float
    total_baseline_ultra_cost_usd: float
    total_baseline_gpt4o_cost_usd: float
    total_baseline_claude_cost_usd: float

    total_savings_vs_ultra_usd: float
    savings_pct_vs_ultra: float
    total_savings_vs_gpt4o_usd: float
    savings_pct_vs_gpt4o: float
    total_savings_vs_claude_usd: float
    savings_pct_vs_claude: float

    # Tier breakdowns
    tier_metrics: Dict[str, TierMetrics] = Field(default_factory=dict)
    task_results: List[TaskEvalResult] = Field(default_factory=list)

    # Provider evaluations
    provider_benchmarks: List[ProviderBenchmarkResult] = Field(default_factory=list)
