"""Agent execution and inference runners."""

from __future__ import annotations

# Sandbox utilities are always available (no heavy deps)
from .sandbox import run_in_sandbox, SandboxResult, validate_safe_path

__all__ = [
    "run_task",
    "run_mock_task",
    "steer_critic",
    "InHarnessSteerLMCritic",
    "SteerLMReport",
    "SteerLMAttributes",
    "run_speculative_draft",
    "SpeculativeResult",
    "execute_agent_loop",
    "AgentLoopEvent",
    "salvage_json_tool_call",
    "run_in_sandbox",
    "SandboxResult",
    "validate_safe_path",
]


def __getattr__(name: str):
    """Lazy-load heavy agent modules that require openai."""
    _lazy = {
        "run_task": ("just_enough_ai.agent.runner", "run_task"),
        "run_mock_task": ("just_enough_ai.agent.mock", "run_mock_task"),
        "steer_critic": ("just_enough_ai.agent.steer_critic", "steer_critic"),
        "InHarnessSteerLMCritic": ("just_enough_ai.agent.steer_critic", "InHarnessSteerLMCritic"),
        "SteerLMReport": ("just_enough_ai.agent.steer_critic", "SteerLMReport"),
        "SteerLMAttributes": ("just_enough_ai.agent.steer_critic", "SteerLMAttributes"),
        "run_speculative_draft": ("just_enough_ai.agent.speculative", "run_speculative_draft"),
        "SpeculativeResult": ("just_enough_ai.agent.speculative", "SpeculativeResult"),
        "execute_agent_loop": ("just_enough_ai.agent.loop", "execute_agent_loop"),
        "AgentLoopEvent": ("just_enough_ai.agent.loop", "AgentLoopEvent"),
        "salvage_json_tool_call": ("just_enough_ai.agent.loop", "salvage_json_tool_call"),
    }
    if name in _lazy:
        import importlib
        module_path, attr = _lazy[name]
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module 'just_enough_ai.agent' has no attribute {name!r}")
