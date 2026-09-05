"""Tests for pricing calculations."""

from just_enough_ai.models import ModelTier
from just_enough_ai.router.cost import calculate_cost, calculate_savings_vs_ultra


def test_cost_calculation():
    # 100k input, 50k output on Nano
    # input: 0.1M * $0.06 = $0.006
    # output: 0.05M * $0.24 = $0.012
    # total = $0.018
    cost_nano = calculate_cost(ModelTier.NANO, prompt_tokens=100_000, completion_tokens=50_000)
    assert cost_nano == 0.018


def test_savings_calculation():
    # On Ultra: 0.1M * 0.80 = 0.08, 0.05M * 2.80 = 0.14 -> total = $0.22
    # Nano was 0.018 -> savings = 0.22 - 0.018 = 0.202
    savings = calculate_savings_vs_ultra(ModelTier.NANO, prompt_tokens=100_000, completion_tokens=50_000)
    assert savings == 0.202
