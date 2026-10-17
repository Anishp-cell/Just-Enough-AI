"""Local Ollama HTTP inference adapter.

Task L-13: Connects to local Ollama daemon at http://localhost:11434.
Enables 100% offline, privacy-first, zero-subscription inference using local
weights (e.g., nemotron-mini, qwen2.5-coder, llama3.2).
"""

from __future__ import annotations

import json
import time
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from ..config import settings
from ..models import ModelTier
from ..agent.mock import get_mock_completion
from .base import ProviderAdapter, ProviderResponse, RateLimitStatus

logger = logging.getLogger(__name__)


class OllamaLocalAdapter(ProviderAdapter):
    """Local inference client communicating with the Ollama HTTP daemon."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "nemotron-mini:latest",
        tier: ModelTier = ModelTier.NANO,
        timeout_seconds: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.tier = tier
        self.timeout_seconds = timeout_seconds
        self._is_live_cache: Optional[bool] = None
        self._last_check: float = 0.0

    def is_available(self) -> bool:
        """Check if local Ollama daemon is running on base_url."""
        if settings.mock_mode:
            return True

        now = time.monotonic()
        if self._is_live_cache is not None and (now - self._last_check) < 10.0:
            return self._is_live_cache

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"User-Agent": "Just-Enough-AI"},
            )
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check if our model is pulled, or if any models exist
                    self._is_live_cache = len(models) > 0
                    self._last_check = now
                    return self._is_live_cache
        except Exception:
            pass

        self._is_live_cache = False
        self._last_check = now
        return False

    def get_model_name(self) -> str:
        return self.model_name

    def get_estimated_tier(self) -> ModelTier:
        return self.tier

    def get_rate_limit_status(self) -> RateLimitStatus:
        # Local daemon has infinite quota (bounded only by local hardware compute)
        return RateLimitStatus(has_capacity=True)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        """Send completion request to Ollama HTTP API."""
        start_ms = time.monotonic() * 1000

        full_prompt = prompt
        if files_context:
            context_blocks = "\n\n".join(
                f"--- FILE: {path} ---\n{content}" for path, content in files_context.items()
            )
            full_prompt = f"FILES CONTEXT:\n{context_blocks}\n\nTASK:\n{prompt}"

        # ── Mock Fallback if daemon is not running ───────────────────────────
        if settings.mock_mode or not self.is_available():
            time.sleep(0.04)
            completion_text = get_mock_completion(full_prompt, self.tier)
            latency = (time.monotonic() * 1000) - start_ms

            return ProviderResponse(
                text=completion_text,
                model_name=f"ollama/{self.model_name}",
                cost_usd=0.0,  # 100% Free
                latency_ms=round(latency, 2),
                is_free_tier=True,
                raw_metadata={
                    "backend": "ollama_mock",
                    "tier": self.tier.value,
                    "prompt_length": len(full_prompt),
                },
            )

        # ── Live Ollama HTTP Call ───────────────────────────────────────────
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result.get("response", "")
                latency = (time.monotonic() * 1000) - start_ms

                return ProviderResponse(
                    text=text,
                    model_name=f"ollama/{self.model_name}",
                    cost_usd=0.0,  # Zero-cost local inference
                    latency_ms=round(latency, 2),
                    is_free_tier=True,
                    raw_metadata={
                        "backend": "ollama_daemon",
                        "total_duration": result.get("total_duration"),
                        "eval_count": result.get("eval_count"),
                    },
                )
        except urllib.error.URLError as e:
            logger.error(f"[OLLAMA] Failed to connect to Ollama daemon: {e}")
            raise RuntimeError(f"Ollama daemon connection failed: {e}") from e
