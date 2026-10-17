"""Provider dynamic registry and discovery manager.

Task L-12: Manages registration, initialization, priority ordering, and auto-discovery
of available adapters across the environment.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..models import ModelTier
from .base import ProviderAdapter

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Central registry for all registered ProviderAdapter instances."""

    def __init__(self):
        self._providers: Dict[str, ProviderAdapter] = {}
        self._priorities: Dict[str, int] = {}

    def register(self, name: str, adapter: ProviderAdapter, priority: int = 100) -> None:
        """Register an adapter under a unique name with an execution priority (lower = higher priority)."""
        self._providers[name] = adapter
        self._priorities[name] = priority
        logger.debug(f"[REGISTRY] Registered provider '{name}' (priority={priority})")

    def unregister(self, name: str) -> Optional[ProviderAdapter]:
        """Remove a provider from the registry."""
        self._priorities.pop(name, None)
        return self._providers.pop(name, None)

    def get(self, name: str) -> Optional[ProviderAdapter]:
        """Fetch a registered provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> List[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def get_available_providers(self) -> List[Tuple[str, ProviderAdapter]]:
        """Return all currently available providers sorted by priority."""
        available = []
        for name, adapter in self._providers.items():
            try:
                if adapter.is_available():
                    available.append((name, adapter))
            except Exception as e:
                logger.warning(f"[REGISTRY] Provider '{name}' availability check failed: {e}")

        # Sort by priority ascending
        available.sort(key=lambda item: self._priorities.get(item[0], 100))
        return available

    def get_by_tier(self, tier: ModelTier) -> List[Tuple[str, ProviderAdapter]]:
        """Find available providers capable of serving the given quality tier."""
        tier_matches = []
        for name, adapter in self.get_available_providers():
            if adapter.get_estimated_tier() == tier:
                tier_matches.append((name, adapter))
        return tier_matches

    def load_user_config(self, config_path: Optional[Path] = None) -> Optional[Dict]:
        """Load user provider priority config from ~/.jeai/providers.json."""
        if config_path is None:
            config_path = Path.home() / ".jeai" / "providers.json"

        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                logger.info(f"[REGISTRY] Loaded user provider config from {config_path}")
                return data
            except Exception as e:
                logger.warning(f"[REGISTRY] Failed to read {config_path}: {e}")
        return None

    def auto_discover(self, config_path: Optional[Path] = None) -> None:
        """Dynamically discover and register all available local and remote providers."""
        # Import concrete adapters lazily to prevent circular imports
        from .nebius import NebiusDirectAdapter
        from .ollama import OllamaLocalAdapter
        from .antigravity import AntigravityCliAdapter
        from .claude_code import ClaudeCodePtyAdapter

        # Default waterfall priorities:
        # Tier 0 (Local Free): Ollama (priority=10)
        # Tier 1 (IDE Free): Antigravity (priority=20), Claude Code (priority=30)
        # Tier 2 (Cloud Fallback): Nebius (priority=50)
        if "ollama" not in self._providers:
            self.register("ollama", OllamaLocalAdapter(), priority=10)

        if "antigravity" not in self._providers:
            self.register("antigravity", AntigravityCliAdapter(), priority=20)

        if "claude_code" not in self._providers:
            self.register("claude_code", ClaudeCodePtyAdapter(), priority=30)

        if "nebius" not in self._providers:
            self.register("nebius", NebiusDirectAdapter(), priority=50)

        # Apply user config overrides if available
        user_cfg = self.load_user_config(config_path)
        if user_cfg and "priority" in user_cfg:
            for idx, name in enumerate(user_cfg["priority"]):
                if name in self._priorities:
                    self._priorities[name] = idx * 10

    def reset(self) -> None:
        """Reset all registered providers (primarily for unit test isolation)."""
        self._providers.clear()
        self._priorities.clear()


# Global singleton registry instance
provider_registry = ProviderRegistry()
