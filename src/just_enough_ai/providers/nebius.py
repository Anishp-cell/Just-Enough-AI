"""Nebius Token Factory direct API inference adapter.

Task L-13: Standardizes Nebius Token Factory / NVIDIA NIM API calls into
the ProviderAdapter interface, with exact token cost calculation and deterministic
mock mode fallback.
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, Optional

from ..config import settings
from ..models import ModelTier
from ..router.cost import calculate_cost, calculate_savings_vs_ultra
from ..agent.mock import get_mock_completion
from .base import ProviderAdapter, ProviderResponse, RateLimitStatus

logger = logging.getLogger(__name__)


class NebiusDirectAdapter(ProviderAdapter):
    """Direct API client for NVIDIA Nemotron models hosted on Nebius Token Factory."""

    def __init__(self, tier: ModelTier = ModelTier.NANO, model_id: Optional[str] = None):
        self.tier = tier
        if model_id:
            self.model_id = model_id
        else:
            self.model_id = getattr(settings, f"model_{tier.value}", settings.model_nano)
        self._rate_limited_until: float = 0.0

    def is_available(self) -> bool:
        """Available if mock mode is on or NEBIUS_API_KEY is configured."""
        if settings.mock_mode:
            return True
        return bool(settings.nebius_api_key)

    def get_model_name(self) -> str:
        return self.model_id

    def get_estimated_tier(self) -> ModelTier:
        return self.tier

    def get_rate_limit_status(self) -> RateLimitStatus:
        now = time.monotonic()
        if now < self._rate_limited_until:
            retry_in = self._rate_limited_until - now
            return RateLimitStatus(
                has_capacity=False,
                retry_after_seconds=retry_in,
                error_message=f"Rate limited. Retry in {retry_in:.1f}s",
            )
        return RateLimitStatus(has_capacity=True)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        """Call Nebius Token Factory chat completion API."""
        status = self.get_rate_limit_status()
        if not status.has_capacity:
            raise RuntimeError(f"Nebius provider is currently rate limited: {status.error_message}")

        start_ms = time.monotonic() * 1000

        # Construct full prompt with file context if supplied
        full_prompt = prompt
        if files_context:
            context_blocks = "\n\n".join(
                f"--- FILE: {path} ---\n{content}" for path, content in files_context.items()
            )
            full_prompt = f"FILES CONTEXT:\n{context_blocks}\n\nTASK:\n{prompt}"

        # ── Mock Mode Fallback ───────────────────────────────────────────────
        if settings.mock_mode or not settings.nebius_api_key:
            time.sleep(0.05)  # Simulate network latency
            completion_text = get_mock_completion(full_prompt, self.tier)
            latency = (time.monotonic() * 1000) - start_ms
            prompt_tokens = len(full_prompt.split()) * 2
            comp_tokens = len(completion_text.split()) * 2
            cost = calculate_cost(self.tier, prompt_tokens, comp_tokens)

            return ProviderResponse(
                text=completion_text,
                model_name=self.model_id,
                cost_usd=cost,
                latency_ms=round(latency, 2),
                is_free_tier=False,
                raw_metadata={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": comp_tokens,
                    "tier": self.tier.value,
                    "mock": True,
                },
            )

        # ── Live Nebius Token Factory Call ──────────────────────────────────
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=settings.nebius_base_url,
                api_key=settings.nebius_api_key,
            )

            sys_content = system_prompt or (
                f"You are an expert agentic coding assistant running on {self.model_id}. "
                "Provide direct, high-precision code solutions with zero hallucination."
            )

            response = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": full_prompt},
                ],
                temperature=0.2,
                max_tokens=2048,
            )

            text = response.choices[0].message.content or ""
            latency = (time.monotonic() * 1000) - start_ms

            prompt_tokens = response.usage.prompt_tokens if response.usage else len(full_prompt.split()) * 2
            comp_tokens = response.usage.completion_tokens if response.usage else len(text.split()) * 2
            cost = calculate_cost(self.tier, prompt_tokens, comp_tokens)

            return ProviderResponse(
                text=text,
                model_name=self.model_id,
                cost_usd=cost,
                latency_ms=round(latency, 2),
                is_free_tier=False,
                raw_metadata={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": comp_tokens,
                    "tier": self.tier.value,
                    "mock": False,
                },
            )

        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg:
                # Mark as rate-limited for 30 seconds
                self._rate_limited_until = time.monotonic() + 30.0
                logger.warning(f"[NEBIUS] 429 Rate limit detected. Backing off for 30s: {e}")
            raise
