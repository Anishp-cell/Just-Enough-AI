"""Mock inference runner for offline testing without burning Nebius credits."""

from typing import Generator, Union
from ..models import RoutingDecision, RunMetadata
from ..router.cost import calculate_cost, calculate_savings_vs_ultra


def run_mock_task(
    task_description: str,
    decision: RoutingDecision,
) -> Generator[Union[str, RunMetadata], None, None]:
    """Simulate streaming inference from the selected Nemotron tier."""
    header = (
        f"[SIMULATED {decision.selected_tier.value.upper()} INFERENCE]\n"
        f"Model: {decision.model_id}\n"
        f"Route Reasoning: {decision.reasoning}\n"
        f"Estimated Blended Cost: ${decision.estimated_cost_per_1m_tokens:.3f} / 1M tokens\n"
        "--------------------------------------------------\n"
    )
    yield header

    body = (
        f"Task: {task_description}\n\n"
        f"Analysis from {decision.selected_tier.value.upper()} tier:\n"
        "- Verified hardware headroom and memory grounding.\n"
        "- Solution synthesized according to repository conventions.\n"
        "- Implementation plan ready for execution.\n"
    )
    for line in body.split("\n"):
        yield line + "\n"

    # Simulate token count for mock telemetry
    prompt_tokens = max(10, len(task_description.split()) * 2)
    completion_tokens = 75
    total_tokens = prompt_tokens + completion_tokens
    actual_cost = calculate_cost(decision.selected_tier, prompt_tokens, completion_tokens)
    savings = calculate_savings_vs_ultra(decision.selected_tier, prompt_tokens, completion_tokens)

    yield RunMetadata(
        model_id=decision.model_id,
        tier=decision.selected_tier,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        actual_cost_usd=actual_cost,
        savings_vs_ultra_usd=savings,
        latency_ms=45.0,
        execution_mode=decision.execution_mode,
    )
