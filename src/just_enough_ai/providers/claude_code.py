"""Claude Code CLI non-interactive execution adapter.

Task L-15: Enables developers with Claude Code CLI installed to leverage its
free-tier model within the Just-Enough-AI harness.
Spawns claude CLI with non-interactive flags, strips ANSI/VT100 codes,
and extracts verified code patches.
"""

from __future__ import annotations

import re
import shutil
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import settings
from ..models import ModelTier
from ..agent.mock import get_mock_completion
from ..security.cli_sandbox import run_provider_cli, strip_ansi_sequences
from .base import ProviderAdapter, ProviderResponse, RateLimitStatus

logger = logging.getLogger(__name__)


class ClaudeCodePtyAdapter(ProviderAdapter):
    """Adapter executing tasks through the installed Claude Code CLI."""

    def __init__(
        self,
        cli_path: Optional[str] = None,
        model_name: str = "anthropic/claude-code-cli",
        tier: ModelTier = ModelTier.SUPER,
    ):
        self.cli_path = cli_path or shutil.which("claude")
        self.model_name = model_name
        self.tier = tier
        self._rate_limited_until: float = 0.0

    def is_available(self) -> bool:
        """Available if claude executable is on PATH or mock mode is enabled."""
        if settings.mock_mode:
            return True
        return bool(self.cli_path and Path(self.cli_path).exists())

    def get_model_name(self) -> str:
        return self.model_name

    def get_estimated_tier(self) -> ModelTier:
        return self.tier

    def get_rate_limit_status(self) -> RateLimitStatus:
        now = time.monotonic()
        if now < self._rate_limited_until:
            retry_in = self._rate_limited_until - now
            return RateLimitStatus(
                has_capacity=False,
                retry_after_seconds=retry_in,
                error_message=f"Claude Code quota exhausted. Retry in {retry_in:.1f}s",
            )
        return RateLimitStatus(has_capacity=True)

    def _extract_code_from_output(self, raw_output: str) -> str:
        """Strip ANSI escapes and pull markdown code blocks."""
        cleaned = strip_ansi_sequences(raw_output).strip()

        # Find code blocks
        code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", cleaned, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()

        return cleaned

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        """Execute claude CLI task non-interactively."""
        status = self.get_rate_limit_status()
        if not status.has_capacity:
            raise RuntimeError(f"Claude Code is rate-limited: {status.error_message}")

        start_ms = time.monotonic() * 1000

        full_prompt = prompt
        if files_context:
            context_blocks = "\n\n".join(
                f"--- FILE: {path} ---\n{content}" for path, content in files_context.items()
            )
            full_prompt = f"FILES CONTEXT:\n{context_blocks}\n\nTASK:\n{prompt}"

        # ── Mock Mode Fallback ───────────────────────────────────────────────
        if settings.mock_mode or not self.cli_path:
            time.sleep(0.06)
            completion_text = get_mock_completion(full_prompt, self.tier)
            latency = (time.monotonic() * 1000) - start_ms

            return ProviderResponse(
                text=completion_text,
                model_name=self.model_name,
                cost_usd=0.0,  # Zero-cost free tier
                latency_ms=round(latency, 2),
                is_free_tier=True,
                raw_metadata={"backend": "claude_code_mock", "tier": self.tier.value},
            )

        # ── Live claude CLI Subprocess Execution ─────────────────────────────
        cmd = [
            self.cli_path,
            "-p", full_prompt,
            "--dangerously-skip-permissions",
        ]

        result = run_provider_cli(
            cmd=cmd,
            cwd=".",
            timeout_seconds=60,
        )

        latency = (time.monotonic() * 1000) - start_ms
        combined_output = (result.stdout + "\n" + result.stderr).lower()

        # Check for rate limit or quota exhaustion
        if "rate limit" in combined_output or "usage limit" in combined_output or "resets at" in combined_output:
            self._rate_limited_until = time.monotonic() + 60.0
            logger.warning("[CLAUDE_CODE] Rate limit detected. Backing off 60s.")
            raise RuntimeError("Claude Code free-tier rate limit or session quota exceeded.")

        if result.timed_out:
            raise TimeoutError("Claude Code execution timed out after 60s.")

        if result.exit_code != 0:
            raise RuntimeError(f"Claude Code CLI failed (exit {result.exit_code}): {result.stderr}")

        extracted_code = self._extract_code_from_output(result.stdout)

        return ProviderResponse(
            text=extracted_code,
            model_name=self.model_name,
            cost_usd=0.0,
            latency_ms=round(latency, 2),
            is_free_tier=True,
            raw_metadata={"backend": "claude_code_cli", "exit_code": result.exit_code},
        )
