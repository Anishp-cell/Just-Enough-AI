"""Decision engine routing tasks across Nemotron Nano, Super, and Ultra."""

import logging
from typing import Optional
from ..models import (
    ModelTier, ExecutionMode, HardwareHeadroom,
    MemoryContext, RoutingDecision
)
from .cost import PRICING_TABLE
from ..config import settings

logger = logging.getLogger(__name__)


def determine_route(
    task_description: str,
    headroom: HardwareHeadroom,
    memory: MemoryContext,
    mode: ExecutionMode = ExecutionMode.LOCAL,
    force_tier: Optional[ModelTier] = None,
) -> RoutingDecision:
    """Route a coding task to the optimal Nemotron model tier.

    Routing Matrix (LOCAL mode):
      1. confidence >= 0.7 AND VRAM >= 6GB  →  NANO
      2. confidence < 0.4  AND VRAM < 6GB   →  ULTRA
      3. else                                →  SUPER

    Routing Matrix (REMOTE_CLOUD mode):
      Local VRAM is IGNORED. Inference always runs on Nebius cloud GPUs.
      1. confidence >= 0.7   →  NANO
      2. confidence < 0.4    →  ULTRA
      3. else                →  SUPER

    Force override:
      If force_tier is set, skip all routing logic and use that tier.
    """

    # ── Force-tier override ───────────────────────────────────────────────
    if force_tier is not None:
        tier = force_tier
        reasoning = (
            f"Manual override: user explicitly selected {tier.value.upper()} tier. "
            "Routing logic bypassed."
        )
        logger.info(f"[ROUTE] FORCE_TIER={tier.value} task={task_description[:60]!r}")

    # ── Remote / Cloud mode (laptop may be OFF) ───────────────────────────
    elif mode == ExecutionMode.REMOTE_CLOUD:
        if memory.confidence_score >= 0.7:
            tier = ModelTier.NANO
            reasoning = (
                f"[CLOUD MODE] High devmind grounding ({memory.confidence_score:.2f}). "
                "Local VRAM irrelevant — inference on Nebius cloud. "
                "Routing to Nano for maximum cost efficiency."
            )
        elif memory.confidence_score < 0.4:
            tier = ModelTier.ULTRA
            reasoning = (
                f"[CLOUD MODE] Low devmind grounding ({memory.confidence_score:.2f}). "
                "Complex or ungrounded task requires frontier reasoning. "
                "Routing to Nemotron Ultra (253B)."
            )
        else:
            tier = ModelTier.SUPER
            reasoning = (
                f"[CLOUD MODE] Moderate devmind grounding ({memory.confidence_score:.2f}). "
                "Routing to Nemotron Super (120B) for balanced reasoning."
            )
        logger.info(
            f"[ROUTE] CLOUD mode={mode.value} tier={tier.value} "
            f"confidence={memory.confidence_score:.2f}"
        )

    # ── Local mode (GPU VRAM is factored in) ─────────────────────────────
    else:
        if memory.confidence_score >= 0.7 and headroom.has_sufficient_headroom:
            tier = ModelTier.NANO
            reasoning = (
                f"High grounding ({memory.confidence_score:.2f}) and VRAM headroom "
                f"({headroom.free_vram_mb:.0f} MB free). "
                "Routing to Nano — 90%+ cost savings."
            )
        elif memory.confidence_score < 0.4 and not headroom.has_sufficient_headroom:
            tier = ModelTier.ULTRA
            reasoning = (
                f"Low grounding ({memory.confidence_score:.2f}) and constrained hardware "
                f"({headroom.free_vram_mb:.0f} MB VRAM free). "
                "Routing to Ultra for maximum reasoning."
            )
        else:
            tier = ModelTier.SUPER
            reasoning = (
                f"Moderate context confidence ({memory.confidence_score:.2f}). "
                "Routing to Super (120B) for balanced multi-file reasoning."
            )
        logger.info(
            f"[ROUTE] LOCAL tier={tier.value} confidence={memory.confidence_score:.2f} "
            f"vram_free={headroom.free_vram_mb:.0f}MB"
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
        execution_mode=mode,
        force_tier=force_tier,
    )
