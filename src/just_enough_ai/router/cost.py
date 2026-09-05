"""Nebius Token Factory pricing tiers and cost calculations."""

from ..models import ModelTier

# Nebius Token Factory pricing (USD per 1M tokens)
# Format: {"input": float, "output": float, "blended": float}
PRICING_TABLE = {
    ModelTier.NANO: {
        "model_id": "nvidia/nemotron-3-nano-omni",
        "input_per_1m": 0.06,
        "output_per_1m": 0.24,
        "blended_per_1m": 0.15,
    },
    ModelTier.SUPER: {
        "model_id": "nvidia/nemotron-3-super-120b-a12b",
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
        "blended_per_1m": 0.375,
    },
    ModelTier.ULTRA: {
        "model_id": "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1",
        "input_per_1m": 0.80,
        "output_per_1m": 2.80,
        "blended_per_1m": 1.80,
    },
}


def calculate_cost(tier: ModelTier, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate exact USD cost for a token completion."""
    tier_info = PRICING_TABLE[tier]
    input_cost = (prompt_tokens / 1_000_000.0) * tier_info["input_per_1m"]
    output_cost = (completion_tokens / 1_000_000.0) * tier_info["output_per_1m"]
    return round(input_cost + output_cost, 6)


def calculate_savings_vs_ultra(tier: ModelTier, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate USD savings compared to running the same task on Nemotron Ultra."""
    cost_actual = calculate_cost(tier, prompt_tokens, completion_tokens)
    cost_ultra = calculate_cost(ModelTier.ULTRA, prompt_tokens, completion_tokens)
    return max(0.0, round(cost_ultra - cost_actual, 6))
