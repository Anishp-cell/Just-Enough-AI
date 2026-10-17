"""Universal Provider Adapters and Cascading Failover Engine."""

from .base import ProviderAdapter, ProviderResponse, RateLimitStatus
from .registry import ProviderRegistry, provider_registry
from .nebius import NebiusDirectAdapter
from .ollama import OllamaLocalAdapter
from .antigravity import AntigravityCliAdapter
from .claude_code import ClaudeCodePtyAdapter
from .cascade import CascadingProviderRouter, cascading_router

__all__ = [
    "ProviderAdapter",
    "ProviderResponse",
    "RateLimitStatus",
    "ProviderRegistry",
    "provider_registry",
    "NebiusDirectAdapter",
    "OllamaLocalAdapter",
    "AntigravityCliAdapter",
    "ClaudeCodePtyAdapter",
    "CascadingProviderRouter",
    "cascading_router",
]
