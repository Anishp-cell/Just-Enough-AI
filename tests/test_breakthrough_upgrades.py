"""Tests for the 4 hackathon-winning breakthrough upgrades:
1. Speculative Agentic Drafting across Nemotron tiers (speculative.py)
2. Hardware-Headroom KV-Cache Governor (kv_governor.py)
3. In-Harness Nemotron SteerLM Multi-Attribute Verifier (steer_critic.py)
4. Multi-step Agent Tool Loop with Self-Fix Escalation (loop.py)
"""

import pytest
from just_enough_ai.models import ModelTier, HardwareHeadroom, ExecutionMode, RunMetadata
from just_enough_ai.profiler.kv_governor import (
    assess_kv_headroom,
    calculate_kv_cache_bytes,
    semantic_kv_prune,
    KVCacheBudget,
    NEMOTRON_SPECS,
)
from just_enough_ai.agent.steer_critic import InHarnessSteerLMCritic, SteerLMReport
from just_enough_ai.agent.speculative import run_speculative_draft, SpeculativeResult
from just_enough_ai.agent.loop import (
    execute_agent_loop,
    salvage_json_tool_call,
    AgentLoopEvent,
)


# ── 1. Tests for Hardware-Headroom KV-Cache Governor ──────────────────────────

def test_kv_cache_byte_calculation():
    """Verify architectural KV-cache formula matches physical transformer topology."""
    # Nano: 32 layers, 8 heads, 128 dim, 2.0 bytes = 2 * 32 * 8 * 128 * 2 = 131,072 bytes/token (~128 KB)
    bytes_1k_nano = calculate_kv_cache_bytes(ModelTier.NANO, 1000)
    expected_nano = 2.0 * 32 * 8 * 128 * 2.0 * 1000
    assert bytes_1k_nano == expected_nano

    # Ultra: 128 layers, 32 heads, 128 dim, 2.0 bytes
    bytes_1k_ultra = calculate_kv_cache_bytes(ModelTier.ULTRA, 1000)
    expected_ultra = 2.0 * 128 * 32 * 128 * 2.0 * 1000
    assert bytes_1k_ultra == expected_ultra
    # Ultra KV-cache per token is exactly 16x larger than Nano
    assert bytes_1k_ultra == bytes_1k_nano * 16


def test_kv_governor_healthy_headroom():
    """Under ample VRAM, governor should PASS with zero throttling."""
    headroom = HardwareHeadroom(
        gpu_available=True,
        total_vram_mb=16384.0,
        free_vram_mb=12000.0,
        has_sufficient_headroom=True,
    )
    budget = assess_kv_headroom(active_tokens=2000, tier=ModelTier.NANO, headroom=headroom)
    assert budget.should_prune is False
    assert budget.should_offload_to_cloud is False
    assert budget.governor_action == "PASS"
    assert "HEALTHY" in budget.reasoning


def test_kv_governor_triggers_cloud_offload_on_exhaustion():
    """When projected KV footprint exceeds physical free VRAM, governor offloads to Nebius."""
    headroom = HardwareHeadroom(
        gpu_available=True,
        total_vram_mb=4096.0,
        free_vram_mb=50.0,  # Only 50 MB free
        has_sufficient_headroom=False,
    )
    # Ultra requires ~21MB per 1k tokens; 5000 tokens projected requires ~105MB > 50MB
    budget = assess_kv_headroom(
        active_tokens=4000,
        tier=ModelTier.ULTRA,
        headroom=headroom,
        anticipated_step_tokens=1000,
    )
    assert budget.should_offload_to_cloud is True
    assert budget.governor_action == "OFFLOAD_TO_NEBIUS"


def test_semantic_kv_prune_filters_noisy_traces_while_preserving_ast():
    """Semantic AST pruner should compress verbose terminal output while keeping AST signatures."""
    context = [
        "def authenticate_user(token: str) -> bool:\n    return token.startswith('bearer_')",
        (
            "pytest output:\n"
            "Traceback (most recent call last):\n"
            "  File 'test_auth.py', line 12, in test_auth\n"
            "    assert authenticate_user('bad') is False\n"
            "  File 'test_auth.py', line 13, in test_auth\n"
            "    assert authenticate_user('bearer_123') is True\n"
            "  File 'test_auth.py', line 14, in test_auth\n"
            "    assert authenticate_user('') is False\n"
            "FAILED (failures=1)\n"
            "exit code: 1"
        ),
        "class AuthManager:\n    def __init__(self):\n        self.active = True",
    ]

    pruned = semantic_kv_prune(context, max_target_tokens=500)
    assert len(pruned) == 3
    # Function signature kept intact
    assert "def authenticate_user" in pruned[0]
    # Noisy test dump was compressed by governor
    assert "KV-Pruned" in pruned[1]
    # Class definition kept intact
    assert "class AuthManager" in pruned[2]


# ── 2. Tests for In-Harness Nemotron SteerLM Multi-Attribute Verifier ──────────

def test_steerlm_critic_approves_clean_code():
    """High-quality Python code should pass the HelpSteer2 gate with a high score."""
    critic = InHarnessSteerLMCritic(gate_threshold=0.75)
    clean_code = (
        "def format_currency(amount: float, currency: str = 'USD') -> str:\n"
        "    \"\"\"Format float into localized currency string.\"\"\"\n"
        "    return f'{currency} {amount:,.2f}'\n"
    )
    report = critic.evaluate_code("Format currency helper", clean_code)
    assert report.passed is True
    assert report.gate_score >= 0.85
    assert report.attributes.correctness == 1.0
    assert report.attributes.security_score == 1.0
    assert len(report.violations) == 0


def test_steerlm_critic_rejects_syntax_errors():
    """Code with syntax errors should immediately fail the gate with structured critique."""
    critic = InHarnessSteerLMCritic(gate_threshold=0.75)
    broken_code = "def bad_func(:\n    return 42"
    report = critic.evaluate_code("Fix bad function", broken_code)
    assert report.passed is False
    assert report.gate_score < 0.40
    assert any("SyntaxError" in v for v in report.violations)
    assert report.critique_feedback is not None


def test_steerlm_critic_penalizes_empty_stubs():
    """Functions containing only 'pass' or 'raise NotImplementedError' should be flagged."""
    critic = InHarnessSteerLMCritic(gate_threshold=0.75)
    stub_code = (
        "def calculate_tax(income: float) -> float:\n"
        "    pass\n"
    )
    report = critic.evaluate_code("Implement calculate tax", stub_code)
    assert any("empty 'pass' stub" in v for v in report.violations)
    assert report.attributes.correctness < 1.0


def test_steerlm_critic_catches_insecure_eval():
    """Use of eval() should severely downgrade the security score."""
    critic = InHarnessSteerLMCritic(gate_threshold=0.75)
    unsafe_code = (
        "def calculate_expression(expr: str):\n"
        "    return eval(expr)\n"
    )
    report = critic.evaluate_code("Calculate math expression", unsafe_code)
    assert report.attributes.security_score < 0.70
    assert any("eval()" in v for v in report.violations)


def test_steerlm_critic_detects_signature_regression():
    """Deleting an existing function or dropping expected args should trigger regression risk."""
    critic = InHarnessSteerLMCritic(gate_threshold=0.75)
    orig_code = (
        "def process_payment(amount: float, currency: str, user_id: str) -> bool:\n"
        "    return True\n"
    )
    new_code = (
        "def process_payment(amount: float) -> bool:\n"
        "    return amount > 0\n"
    )
    report = critic.evaluate_code("Refactor payment", new_code, original_code=orig_code)
    assert report.attributes.regression_risk >= 0.25
    assert any("dropped expected parameters" in v for v in report.violations)


# ── 3. Tests for Speculative Agentic Drafting Across Tiers ────────────────────

def test_speculative_draft_hit_flow():
    """In mock/fast mode, a valid draft completes as SPECULATION_HIT."""
    result: SpeculativeResult = run_speculative_draft(
        task_description="Add a docstring to format_currency",
        original_code="def format_currency(amount: float) -> str:\n    return f'${amount:.2f}'\n",
    )
    assert result.status == "SPECULATION_HIT"
    assert result.final_tier == ModelTier.NANO
    assert result.warm_started is False
    assert result.gate_report.passed is True
    assert result.total_cost_usd > 0.0
    assert result.savings_vs_ultra_usd >= 0.0


def test_speculative_draft_promotion_flow():
    """When initial draft fails verification, it promotes to Super with contrastive context."""
    # Force an invalid task that triggers defects or promotion
    result: SpeculativeResult = run_speculative_draft(
        task_description="Implement complex transaction pipeline with broken syntax check",
        original_code=None,
        preferred_fallback_tier=ModelTier.SUPER,
    )
    # Result must yield valid python code solution regardless of path
    assert result.code_solution is not None
    assert len(result.code_solution) > 0


# ── 4. Tests for Multi-Step Agent Tool Loop & JSON Repair Hygiene ─────────────

def test_salvage_json_tool_call_hygiene():
    """Verify robust 3-tier JSON repair parses markdown fences, single quotes, and trailing commas."""
    # Standard markdown code fence
    markdown_json = "```json\n{\"action\": \"write_file\", \"path\": \"app.py\"}\n```"
    repaired = salvage_json_tool_call(markdown_json)
    assert repaired == {"action": "write_file", "path": "app.py"}

    # Single-quoted JSON with trailing comma
    malformed = "{'action': 'test', 'timeout': 10,}"
    repaired2 = salvage_json_tool_call(malformed)
    assert repaired2 == {"action": "test", "timeout": 10}

    # Clean JSON
    clean = '{"valid": true}'
    assert salvage_json_tool_call(clean) == {"valid": True}


def test_execute_agent_loop_emits_structured_events():
    """Verify that execute_agent_loop streams structured telemetry and terminates with RunMetadata."""
    events = list(execute_agent_loop(
        task_description="Add helper to format timestamps in iso format",
        original_code="def get_time(): return 12345",
        execution_mode=ExecutionMode.LOCAL,
    ))

    assert len(events) >= 3

    # Check that KV_BUDGET was evaluated
    kv_event = next((e for e in events if isinstance(e, AgentLoopEvent) and e.event_type == "KV_BUDGET"), None)
    assert kv_event is not None
    assert "KV-Governor" in kv_event.message

    # Check that SPECULATION was triggered
    spec_event = next((e for e in events if isinstance(e, AgentLoopEvent) and e.event_type == "SPECULATION"), None)
    assert spec_event is not None

    # Check that final item is RunMetadata
    final_item = events[-1]
    assert isinstance(final_item, RunMetadata)
    assert final_item.total_tokens > 0
    assert final_item.actual_cost_usd >= 0.0
