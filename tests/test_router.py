"""Tests for the routing engine decision matrix."""

from just_enough_ai.models import (
    ModelTier, ExecutionMode, HardwareHeadroom, MemoryContext
)
from just_enough_ai.router import determine_route


def test_routing_to_nano_when_high_confidence_and_headroom():
    headroom = HardwareHeadroom(
        gpu_available=True,
        total_vram_mb=8192.0,
        free_vram_mb=6500.0,
        has_sufficient_headroom=True,
    )
    memory = MemoryContext(
        query="Write a helper function",
        confidence_score=0.85,
        context_chunks=["function already exists in utils.py"],
        has_high_confidence=True,
    )

    decision = determine_route("Write a helper function", headroom, memory)
    assert decision.selected_tier == ModelTier.NANO
    assert "nano" in decision.model_id.lower()
    assert decision.execution_mode == ExecutionMode.LOCAL


def test_routing_to_ultra_when_low_confidence_and_no_headroom():
    headroom = HardwareHeadroom(
        gpu_available=False,
        has_sufficient_headroom=False,
    )
    memory = MemoryContext(
        query="Refactor entire distributed transaction coordinator",
        confidence_score=0.2,
        context_chunks=[],
        has_high_confidence=False,
    )

    decision = determine_route("Refactor coordinator", headroom, memory)
    assert decision.selected_tier == ModelTier.ULTRA
    assert "ultra" in decision.model_id.lower()


def test_routing_to_super_when_moderate():
    headroom = HardwareHeadroom(
        gpu_available=True,
        has_sufficient_headroom=False,
    )
    memory = MemoryContext(
        query="Add user authentication endpoint",
        confidence_score=0.55,
        context_chunks=["user model defined"],
    )

    decision = determine_route("Add auth", headroom, memory)
    assert decision.selected_tier == ModelTier.SUPER
    assert "super" in decision.model_id.lower()


def test_cloud_mode_routes_to_nano_even_without_local_gpu():
    """In cloud mode, lack of local GPU should NOT force expensive tiers."""
    headroom = HardwareHeadroom(
        gpu_available=False,
        total_vram_mb=0.0,
        free_vram_mb=0.0,
        has_sufficient_headroom=False,
    )
    memory = MemoryContext(
        query="Implement simple utility",
        confidence_score=0.88,
        context_chunks=["found in core.py"],
        has_high_confidence=True,
    )

    decision = determine_route(
        "Implement simple utility",
        headroom,
        memory,
        mode=ExecutionMode.REMOTE_CLOUD,
    )
    assert decision.selected_tier == ModelTier.NANO
    assert decision.execution_mode == ExecutionMode.REMOTE_CLOUD
    assert "[CLOUD MODE]" in decision.reasoning


def test_cloud_mode_routes_to_ultra_when_low_confidence():
    headroom = HardwareHeadroom(gpu_available=False, has_sufficient_headroom=False)
    memory = MemoryContext(query="Unknown task", confidence_score=0.15)

    decision = determine_route(
        "Unknown task",
        headroom,
        memory,
        mode=ExecutionMode.REMOTE_CLOUD,
    )
    assert decision.selected_tier == ModelTier.ULTRA
    assert decision.execution_mode == ExecutionMode.REMOTE_CLOUD


def test_force_tier_override():
    headroom = HardwareHeadroom(gpu_available=False, has_sufficient_headroom=False)
    memory = MemoryContext(query="Low conf task", confidence_score=0.1)

    # Even with low confidence and no GPU, forcing NANO must assign NANO
    decision = determine_route(
        "Low conf task",
        headroom,
        memory,
        force_tier=ModelTier.NANO,
    )
    assert decision.selected_tier == ModelTier.NANO
    assert decision.force_tier == ModelTier.NANO
    assert "Manual override" in decision.reasoning
