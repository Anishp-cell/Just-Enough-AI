"""Tests for the codebase memory grounding bridge and AST symbol fallback."""

from just_enough_ai.bridge.devmind import query_codebase_memory
from just_enough_ai.models import ExecutionMode, HardwareHeadroom, ModelTier
from just_enough_ai.router import determine_route


def test_known_symbol_hit_yields_high_confidence():
    """Querying a real function in the repo should produce high confidence and snippet chunks."""
    memory = query_codebase_memory("Refactor calculate_cost calculation")
    assert memory.confidence_score >= 0.70
    assert memory.has_high_confidence is True
    assert len(memory.context_chunks) > 0
    # One of the chunks should mention calculate_cost
    assert any("calculate_cost" in chunk for chunk in memory.context_chunks)


def test_known_class_hit_yields_high_confidence():
    """Querying a known class like RoutingDecision should extract the class chunk."""
    memory = query_codebase_memory("Update RoutingDecision model fields")
    assert memory.confidence_score >= 0.70
    assert memory.has_high_confidence is True
    assert any("RoutingDecision" in chunk for chunk in memory.context_chunks)


def test_unknown_symbol_yields_low_confidence():
    """Querying an unknown distributed system should yield very low grounding."""
    memory = query_codebase_memory("Implement Paxos consensus state machine with Raft election")
    assert memory.confidence_score < 0.35
    assert memory.has_high_confidence is False


def test_memory_grounding_drives_router_to_nano():
    """When a task targets an existing function, memory grounding should route it to Nano."""
    task = "Add docstring to calculate_cost in router"
    headroom = HardwareHeadroom(
        gpu_available=True,
        total_vram_mb=8192.0,
        free_vram_mb=6500.0,
        has_sufficient_headroom=True,
    )
    memory = query_codebase_memory(task)
    decision = determine_route(task, headroom, memory, mode=ExecutionMode.LOCAL)

    assert decision.selected_tier == ModelTier.NANO
    assert "Nano" in decision.reasoning or "nano" in decision.selected_tier.value


def test_cloud_mode_with_memory_hit_routes_to_nano():
    """In cloud mode, memory grounding alone should route to Nano without checking local GPU."""
    task = "Fix typo in calculate_savings_vs_ultra"
    headroom = HardwareHeadroom(gpu_available=False, has_sufficient_headroom=False)
    memory = query_codebase_memory(task)
    decision = determine_route(task, headroom, memory, mode=ExecutionMode.REMOTE_CLOUD)

    assert decision.selected_tier == ModelTier.NANO
    assert decision.execution_mode == ExecutionMode.REMOTE_CLOUD
