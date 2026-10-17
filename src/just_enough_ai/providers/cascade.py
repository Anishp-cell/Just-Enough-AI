"""Zero-Cost Cascading Failover Router.

Task L-16: Orchestrates waterfall routing across Tier 0 (Ollama),
Tier 1 (Antigravity, Claude Code), and Tier 2 (Nebius Token Factory Cloud).
On rate-limit 429, session quota, or crash, automatically cascades to the
next available provider without dropping context or halting the user's task.
"""

from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..models import ModelTier
from .base import ProviderAdapter, ProviderResponse
from .registry import ProviderRegistry, provider_registry

logger = logging.getLogger(__name__)


class CascadingProviderRouter:
    """Intelligent waterfall router with transparent cascading failover."""

    def __init__(self, registry: Optional[ProviderRegistry] = None):
        self.registry = registry or provider_registry

    def _determine_provider_chain(
        self,
        tier: ModelTier,
        preferred_provider: Optional[str] = None,
    ) -> List[Tuple[str, ProviderAdapter]]:
        """Order available providers according to tier and zero-cost waterfall logic."""
        # Ensure registry has auto-discovered default adapters
        if not self.registry.list_providers():
            self.registry.auto_discover()

        available = self.registry.get_available_providers()
        if not available:
            # Force auto-discover if registry was empty
            self.registry.auto_discover()
            available = self.registry.get_available_providers()

        # If user explicitly preferred a provider, prioritize it first
        if preferred_provider:
            favored = []
            rest = []
            for name, adapter in available:
                if name.lower() == preferred_provider.lower():
                    favored.append((name, adapter))
                else:
                    rest.append((name, adapter))
            available = favored + rest

        # Order by tier appropriateness:
        # For NANO: Tier 0 (ollama) -> Tier 1 (antigravity) -> Tier 2 (nebius)
        # For SUPER: Tier 1 (claude_code) -> Tier 0 (ollama) -> Tier 2 (nebius)
        # For ULTRA: Tier 2 (nebius) -> Tier 1 (claude_code)
        def tier_sort_key(item: Tuple[str, ProviderAdapter]) -> int:
            name, adapter = item
            est_tier = adapter.get_estimated_tier()

            if tier == ModelTier.NANO:
                if name == "ollama":
                    return 0
                if name == "antigravity":
                    return 1
                if name == "nebius":
                    return 2
                return 3

            elif tier == ModelTier.SUPER:
                if name == "claude_code":
                    return 0
                if name == "nebius":
                    return 1
                if name == "ollama":
                    return 2
                return 3

            else:  # ULTRA
                if name == "nebius":
                    return 0
                if name == "claude_code":
                    return 1
                return 2

        sorted_chain = sorted(available, key=tier_sort_key)
        return sorted_chain

    async def dispatch(
        self,
        prompt: str,
        tier: ModelTier = ModelTier.NANO,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
        preferred_provider: Optional[str] = None,
    ) -> ProviderResponse:
        """Attempt task execution across the provider cascade until successful."""
        chain = self._determine_provider_chain(tier, preferred_provider)
        if not chain:
            raise RuntimeError("No available inference providers registered or reachable.")

        cascade_history: List[Dict[str, Any]] = []
        last_error: Optional[Exception] = None

        for name, adapter in chain:
            status = adapter.get_rate_limit_status()
            if not status.has_capacity:
                logger.info(f"[CASCADE] Skipping '{name}' due to rate limit: {status.error_message}")
                cascade_history.append({"provider": name, "status": "rate_limited", "error": status.error_message})
                continue

            try:
                logger.info(f"[CASCADE] Dispatching task to provider '{name}' ({adapter.get_model_name()})...")
                response = await adapter.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    files_context=files_context,
                )

                # Attach cascade telemetry
                cascade_history.append({
                    "provider": name,
                    "status": "success",
                    "latency_ms": response.latency_ms,
                    "is_free_tier": response.is_free_tier,
                })
                response.raw_metadata["cascade_history"] = cascade_history
                response.raw_metadata["active_provider"] = name

                if len(cascade_history) > 1:
                    logger.warning(
                        f"[CASCADE_FAILOVER] Successfully recovered task via '{name}' "
                        f"after {len(cascade_history) - 1} provider(s) cascaded."
                    )
                return response

            except Exception as e:
                err_msg = str(e)
                logger.warning(f"[CASCADE_FAILOVER] Provider '{name}' failed: {err_msg}. Cascading to next provider...")
                cascade_history.append({
                    "provider": name,
                    "status": "failed",
                    "error": err_msg,
                })
                last_error = e
                # Continue loop to next provider in cascade!

        raise RuntimeError(
            f"All providers in the cascading failover chain failed: {cascade_history}"
        ) from last_error

    def dispatch_sync(
        self,
        prompt: str,
        tier: ModelTier = ModelTier.NANO,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
        preferred_provider: Optional[str] = None,
    ) -> ProviderResponse:
        """Synchronous wrapper for dispatch(). Handles active event loops safely."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.dispatch(prompt, tier, system_prompt, files_context, preferred_provider),
                )
                return future.result()
        else:
            return asyncio.run(
                self.dispatch(prompt, tier, system_prompt, files_context, preferred_provider)
            )


# Global singleton router
cascading_router = CascadingProviderRouter()
