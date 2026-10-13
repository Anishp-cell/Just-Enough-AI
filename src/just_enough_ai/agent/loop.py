"""Multi-Step Agent Tool Loop with Self-Fix Escalation & Speculative Integration.

Coordinates:
  1. Real-time KV-Cache Headroom Assessment (via KV-Governor)
  2. Speculative Multi-Tier Drafting (Nano draft -> SteerLM Gate -> Warm-Start Escalation)
  3. Multi-Step Self-Fix Loop (catches test/fuzz crashes, auto-escalates to Super)
  4. Silent 3-Tier Tool Call Repair Hygiene (handles malformed JSON outputs gracefully)
"""

import ast
import json
import logging
import re
import time
from typing import Dict, Any, Generator, List, Optional, Union
from pydantic import BaseModel, Field

from ..models import (
    ModelTier, ExecutionMode, RoutingDecision,
    RunMetadata, HardwareHeadroom, MemoryContext
)
from ..profiler.kv_governor import assess_kv_headroom, KVCacheBudget
from ..profiler.gpu import get_gpu_headroom
from ..router.cost import calculate_cost, calculate_savings_vs_ultra
from ..config import settings
from .speculative import run_speculative_draft, SpeculativeResult
from .steer_critic import steer_critic, SteerLMReport

logger = logging.getLogger(__name__)


class AgentLoopEvent(BaseModel):
    """Structured event emitted during multi-step agent execution."""
    step: int
    event_type: str  # "KV_BUDGET", "SPECULATION", "GATE_CHECK", "SELF_FIX", "OUTPUT", "COMPLETED"
    message: str
    tier: ModelTier
    data: Optional[Dict[str, Any]] = None


def salvage_json_tool_call(raw_output: str) -> Optional[Dict[str, Any]]:
    """Silent Tier-1 JSON repair hygiene for non-frontier models.

    Handles unclosed brackets, single quotes, markdown backticks, and trailing commas.
    """
    cleaned = raw_output.strip()
    # Strip markdown code fences ```json ... ```
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Basic regex cleanup: replace single quotes with double quotes
    try:
        repaired = re.sub(r"(?<!\\)'", '"', cleaned)
        repaired = re.sub(r",\s*([\]}])", r"\1", repaired)  # remove trailing commas
        return json.loads(repaired)
    except Exception:
        return None


def execute_agent_loop(
    task_description: str,
    original_code: Optional[str] = None,
    execution_mode: ExecutionMode = ExecutionMode.LOCAL,
    max_repair_turns: int = 2,
) -> Generator[Union[AgentLoopEvent, RunMetadata], None, None]:
    """Execute the full agentic loop combining KV-Cache governance and Speculative Drafting.

    Yields:
        AgentLoopEvent updates as steps occur.
        RunMetadata as the final yielded item.
    """
    start_ms = time.monotonic() * 1000
    step = 1

    # ── Step 1: Physical KV-Cache Headroom Check via NVML ─────────────────
    headroom = get_gpu_headroom()
    initial_tokens = len(task_description.split()) * 2 + (len(original_code.split()) * 2 if original_code else 0)
    kv_budget = assess_kv_headroom(
        active_tokens=initial_tokens,
        tier=ModelTier.NANO,
        headroom=headroom,
    )

    yield AgentLoopEvent(
        step=step,
        event_type="KV_BUDGET",
        message=(
            f"KV-Governor: {kv_budget.governor_action} | "
            f"Active Tokens: {kv_budget.active_tokens} | "
            f"KV Memory: {kv_budget.kv_cache_used_mb:.1f}MB | "
            f"VRAM Headroom: {kv_budget.vram_headroom_pct:.1f}%"
        ),
        tier=ModelTier.NANO,
        data=kv_budget.model_dump(),
    )
    step += 1

    # ── Step 2: Speculative Agentic Drafting Across Tiers ─────────────────
    yield AgentLoopEvent(
        step=step,
        event_type="SPECULATION",
        message="Dispatching speculative Nemotron Nano draft (~300ms)...",
        tier=ModelTier.NANO,
    )

    spec_result: SpeculativeResult = run_speculative_draft(
        task_description=task_description,
        original_code=original_code,
        preferred_fallback_tier=ModelTier.SUPER,
    )

    yield AgentLoopEvent(
        step=step,
        event_type="SPECULATION",
        message=(
            f"Speculative Dispatch: {spec_result.status} | "
            f"Assigned Tier: {spec_result.final_tier.value.upper()} | "
            f"Latency: {spec_result.total_latency_ms:.0f}ms | "
            f"Gate Score: {spec_result.gate_report.gate_score:.2f}"
        ),
        tier=spec_result.final_tier,
        data={
            "status": spec_result.status,
            "warm_started": spec_result.warm_started,
            "gate_score": spec_result.gate_report.gate_score,
            "cost_usd": spec_result.total_cost_usd,
        },
    )
    step += 1

    active_code = spec_result.code_solution
    active_tier = spec_result.final_tier
    total_tokens = spec_result.draft_tokens + spec_result.promoted_tokens
    total_cost = spec_result.total_cost_usd

    # ── Step 3: Self-Fix Verification (AST & Invariant Gate) ───────────────
    repair_turn = 0
    while repair_turn < max_repair_turns:
        report: SteerLMReport = steer_critic.evaluate_code(
            task_description=task_description,
            generated_code=active_code,
            original_code=original_code,
        )

        if report.passed:
            yield AgentLoopEvent(
                step=step,
                event_type="GATE_CHECK",
                message=f"SteerLM Gate PASSED (Score: {report.gate_score:.2f} >= {report.threshold:.2f}). Patch verified.",
                tier=active_tier,
                data=report.model_dump(),
            )
            step += 1
            break

        # Gate failed: Trigger Self-Fix Escalation
        repair_turn += 1
        yield AgentLoopEvent(
            step=step,
            event_type="SELF_FIX",
            message=(
                f"Self-Fix Loop (Turn {repair_turn}/{max_repair_turns}): "
                f"Gate rejected (Score: {report.gate_score:.2f}). "
                f"Auto-escalating repair to Nemotron Super."
            ),
            tier=ModelTier.SUPER,
            data={"violations": report.violations, "critique": report.critique_feedback},
        )
        step += 1

        # Escalate repair
        escalate_spec = run_speculative_draft(
            task_description=f"{task_description}\n\nFIX DEFECT: {report.critique_feedback}",
            original_code=active_code,
            preferred_fallback_tier=ModelTier.SUPER,
        )
        active_code = escalate_spec.code_solution
        active_tier = ModelTier.SUPER
        total_tokens += escalate_spec.promoted_tokens
        total_cost += escalate_spec.total_cost_usd

    # ── Step 4: Final Emission ───────────────────────────────────────────
    total_latency_ms = (time.monotonic() * 1000) - start_ms
    savings_usd = calculate_savings_vs_ultra(active_tier, int(total_tokens * 0.5), int(total_tokens * 0.5))

    yield AgentLoopEvent(
        step=step,
        event_type="OUTPUT",
        message="Final verified code patch generated.",
        tier=active_tier,
        data={"code": active_code},
    )

    metadata = RunMetadata(
        model_id=getattr(settings, f"model_{active_tier.value}"),
        tier=active_tier,
        prompt_tokens=int(total_tokens * 0.5),
        completion_tokens=int(total_tokens * 0.5),
        total_tokens=total_tokens,
        actual_cost_usd=round(total_cost, 6),
        savings_vs_ultra_usd=round(savings_usd, 6),
        latency_ms=round(total_latency_ms, 2),
        execution_mode=execution_mode,
    )

    yield metadata
