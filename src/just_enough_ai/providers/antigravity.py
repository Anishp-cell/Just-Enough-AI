"""Google Antigravity headless CLI inference adapter.

Task L-14: Enables developers with Antigravity installed to utilize its
underlying free-tier model for drafting and refactoring without a paid API key.
Spawns agy CLI headless process in Mayank's sandbox and normalizes outputs.
"""

from __future__ import annotations

import os
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


class AntigravityCliAdapter(ProviderAdapter):
    """Headless CLI adapter for Google Antigravity (agy)."""

    def __init__(
        self,
        cli_path: Optional[str] = None,
        model_name: str = "google/antigravity-agent",
        tier: ModelTier = ModelTier.NANO,
    ):
        self.cli_path = cli_path or self._find_agy_binary()
        self.model_name = model_name
        self.tier = tier
        self._rate_limited_until: float = 0.0

    @staticmethod
    def _find_agy_binary() -> Optional[str]:
        """Check PATH or default installation directory for agy binary."""
        found = shutil.which("agy")
        if found:
            return found

        # Check default Windows / Posix install locations
        home = Path.home()
        candidates = [
            home / ".gemini" / "antigravity-ide" / "bin" / "agy.exe",
            home / ".gemini" / "antigravity-ide" / "agy.exe",
            home / ".local" / "bin" / "agy",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity" / "agy.exe",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return None

    def is_available(self) -> bool:
        """Available if agy binary is present or mock mode is enabled."""
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
                error_message=f"Antigravity quota limit hit. Retry in {retry_in:.1f}s",
            )
        return RateLimitStatus(has_capacity=True)

    def _extract_code_from_output(self, raw_output: str) -> str:
        """Extract clean code blocks or clean text from agy CLI output."""
        cleaned = strip_ansi_sequences(raw_output).strip()

        # Match markdown ```python ... ``` blocks
        code_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", cleaned, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()

        # Fallback to entire stripped output
        return cleaned

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        """Execute headless agy task in isolated subprocess and normalize output."""
        status = self.get_rate_limit_status()
        if not status.has_capacity:
            raise RuntimeError(f"Antigravity is rate-limited: {status.error_message}")

        start_ms = time.monotonic() * 1000

        full_prompt = prompt
        if files_context:
            context_blocks = "\n\n".join(
                f"--- FILE: {path} ---\n{content}" for path, content in files_context.items()
            )
            full_prompt = f"FILES CONTEXT:\n{context_blocks}\n\nTASK:\n{prompt}"

        # ── Mock Mode Fallback ───────────────────────────────────────────────
        if settings.mock_mode or not self.cli_path or not Path(self.cli_path).exists():
            time.sleep(0.06)  # Simulate CLI spinup
            completion_text = get_mock_completion(full_prompt, self.tier)
            latency = (time.monotonic() * 1000) - start_ms

            return ProviderResponse(
                text=completion_text,
                model_name=self.model_name,
                cost_usd=0.0,  # Zero-cost free tier
                latency_ms=round(latency, 2),
                is_free_tier=True,
                raw_metadata={"backend": "antigravity_mock", "tier": self.tier.value},
            )

        # ── Live agy Subprocess Execution ────────────────────────────────────
        cmd = [self.cli_path, "run", "--prompt", full_prompt, "--headless"]
        if system_prompt:
            cmd.extend(["--system", system_prompt])

        result = run_provider_cli(
            cmd=cmd,
            cwd=".",
            timeout_seconds=45,
        )

        latency = (time.monotonic() * 1000) - start_ms
        combined_output = (result.stdout + "\n" + result.stderr).lower()

        # Check for quota or rate limit indicators
        if "rate limit" in combined_output or "quota exceeded" in combined_output or result.exit_code == 429:
            self._rate_limited_until = time.monotonic() + 60.0
            logger.warning("[ANTIGRAVITY] Quota or rate limit exceeded. Backing off 60s.")
            raise RuntimeError("Antigravity free-tier rate limit or quota exceeded.")

        if result.timed_out:
            raise TimeoutError("Antigravity CLI execution timed out after 45 seconds.")

        if result.exit_code != 0:
            raise RuntimeError(f"Antigravity CLI failed (exit {result.exit_code}): {result.stderr}")

        extracted_code = self._extract_code_from_output(result.stdout)

        return ProviderResponse(
            text=extracted_code,
            model_name=self.model_name,
            cost_usd=0.0,  # 100% Free IDE Tier
            latency_ms=round(latency, 2),
            is_free_tier=True,
            raw_metadata={"backend": "antigravity_cli", "exit_code": result.exit_code},
        )
