"""Mock inference runner for offline testing without burning Nebius credits."""

from typing import Generator
from ..models import RoutingDecision


def run_mock_task(task_description: str, decision: RoutingDecision) -> Generator[str, None, None]:
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
