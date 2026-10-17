"""Abstract Base Class and data structures for Universal Provider Adapters.

Task L-12: Defines polymorphic interface so any inference backend (REST API,
local Ollama daemon, or headless CLI IDEs like Antigravity and Claude Code)
can be plugged into the Just-Enough-AI harness seamlessly.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..models import ModelTier


@dataclass
class RateLimitStatus:
    """Represents real-time rate limit and quota health for a provider."""
    has_capacity: bool = True
    retry_after_seconds: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class ProviderResponse:
    """Normalized response returned by any ProviderAdapter."""
    text: str
    model_name: str
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    is_free_tier: bool = False
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(ABC):
    """Abstract interface that all inference providers must implement."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        """Asynchronously generate a completion from the underlying model or tool."""
        pass

    def generate_sync(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        """Synchronous wrapper for generate(). Handles existing event loops safely."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # In an active event loop thread: create a new thread or use nest_asyncio/future
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.generate(prompt, system_prompt, files_context),
                )
                return future.result()
        else:
            return asyncio.run(self.generate(prompt, system_prompt, files_context))

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider binary/endpoint is present and accessible."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the concrete model identifier or agent version."""
        pass

    @abstractmethod
    def get_estimated_tier(self) -> ModelTier:
        """Return the equivalent quality tier (nano, super, ultra)."""
        pass

    @abstractmethod
    def get_rate_limit_status(self) -> RateLimitStatus:
        """Return real-time capacity and rate limit status."""
        pass

    def shutdown(self) -> None:
        """Gracefully release any child processes or network connections."""
        pass
