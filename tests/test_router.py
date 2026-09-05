"""Tests for the routing engine decision matrix."""

from just_enough_ai.models import ModelTier, HardwareHeadroom, MemoryContext
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
