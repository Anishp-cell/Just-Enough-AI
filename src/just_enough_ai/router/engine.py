"""Decision engine routing tasks across Nemotron Nano, Super, and Ultra."""

from ..models import ModelTier, HardwareHeadroom, MemoryContext, RoutingDecision
from .cost import PRICING_TABLE
from ..config import settings


def determine_route(
    task_description: str,
    headroom: HardwareHeadroom,
    memory: MemoryContext,
) -> RoutingDecision:
    """Route a coding task to the optimal Nemotron model tier.

    Routing Matrix:
    1. High memory confidence (>= 0.7) + ample VRAM headroom (>= 6GB) -> NANO
       (Context is already grounded; small fast model is sufficient; saves 90%+ cost).
    2. Medium memory confidence (0.4 - 0.7) OR moderate task complexity -> SUPER
       (Balanced tier for refactoring and feature tasks).
    3. Low memory confidence (< 0.4) + complex task OR low device headroom -> ULTRA
       (Requires frontier reasoning to infer ungrounded codebase context).
    """
    # Rule 1: High confidence memory + good headroom -> Nano
    if memory.confidence_score >= 0.7 and headroom.has_sufficient_headroom:
        tier = ModelTier.NANO
        reasoning = (
            f"Grounding memory confidence is high ({memory.confidence_score:.2f}) "
            f"and VRAM headroom is sufficient ({headroom.free_vram_mb} MB free). "
            "Routing to Nemotron Nano for maximum speed and cost efficiency."
        )
    # Rule 2: Low memory confidence + low headroom -> Ultra
    elif memory.confidence_score < 0.4 and not headroom.has_sufficient_headroom:
        tier = ModelTier.ULTRA
        reasoning = (
            f"Low memory grounding ({memory.confidence_score:.2f}) and constrained hardware. "
            "Routing to Nemotron Ultra (frontier 253B) for maximum synthesis capability."
        )
    # Rule 3: Default balanced tier -> Super
    else:
        tier = ModelTier.SUPER
        reasoning = (
            f"Moderate context confidence ({memory.confidence_score:.2f}). "
            "Routing to Nemotron Super (120B) for balanced multi-file reasoning."
        )

    model_id = getattr(settings, f"model_{tier.value}", PRICING_TABLE[tier]["model_id"])
    est_cost = PRICING_TABLE[tier]["blended_per_1m"]

    return RoutingDecision(
        selected_tier=tier,
        model_id=model_id,
        reasoning=reasoning,
        estimated_cost_per_1m_tokens=est_cost,
        hardware_headroom=headroom,
        memory_context=memory,
    )
