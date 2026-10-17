"""Tests for Universal Provider Adapters and Cascading Failover Router (Tasks L-12 to L-16)."""

import pytest
import time
from typing import Dict, Optional

from just_enough_ai.models import ModelTier
from just_enough_ai.providers.base import ProviderAdapter, ProviderResponse, RateLimitStatus
from just_enough_ai.providers.registry import ProviderRegistry, provider_registry
from just_enough_ai.providers.nebius import NebiusDirectAdapter
from just_enough_ai.providers.ollama import OllamaLocalAdapter
from just_enough_ai.providers.antigravity import AntigravityCliAdapter
from just_enough_ai.providers.claude_code import ClaudeCodePtyAdapter
from just_enough_ai.providers.cascade import CascadingProviderRouter


class DummyMockAdapter(ProviderAdapter):
    """Test helper adapter with configurable behavior."""

    def __init__(
        self,
        name: str = "dummy",
        tier: ModelTier = ModelTier.NANO,
        should_fail: bool = False,
        is_rate_limited: bool = False,
        cost_usd: float = 0.0,
    ):
        self.name = name
        self.tier = tier
        self.should_fail = should_fail
        self.is_rate_limited = is_rate_limited
        self.cost_usd = cost_usd
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return f"mock/{self.name}"

    def get_estimated_tier(self) -> ModelTier:
        return self.tier

    def get_rate_limit_status(self) -> RateLimitStatus:
        if self.is_rate_limited:
            return RateLimitStatus(has_capacity=False, retry_after_seconds=30.0, error_message="Mock quota hit")
        return RateLimitStatus(has_capacity=True)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        files_context: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError(f"Simulated failure in {self.name}")

        return ProviderResponse(
            text=f"def solution_{self.name}(): pass",
            model_name=self.get_model_name(),
            cost_usd=self.cost_usd,
            latency_ms=15.0,
            is_free_tier=(self.cost_usd == 0.0),
            raw_metadata={"mock": True},
        )


# ── L-12: Base & Registry Tests ──────────────────────────────────────────────

def test_provider_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ProviderAdapter()  # Abstract class


def test_provider_registry_registration_and_priority():
    reg = ProviderRegistry()
    a1 = DummyMockAdapter("adapter_1")
    a2 = DummyMockAdapter("adapter_2")

    reg.register("p2", a2, priority=50)
    reg.register("p1", a1, priority=10)

    assert reg.get("p1") is a1
    assert reg.get("p2") is a2
    assert reg.list_providers() == ["p2", "p1"]

    available = reg.get_available_providers()
    # Should be sorted by priority ascending (p1=10 before p2=50)
    assert available[0][0] == "p1"
    assert available[1][0] == "p2"

    reg.unregister("p1")
    assert reg.get("p1") is None
    assert len(reg.list_providers()) == 1


def test_provider_registry_auto_discover():
    reg = ProviderRegistry()
    reg.auto_discover()

    providers = reg.list_providers()
    assert "ollama" in providers
    assert "antigravity" in providers
    assert "claude_code" in providers
    assert "nebius" in providers

    available = reg.get_available_providers()
    assert len(available) >= 1


# ── L-13: Nebius & Ollama Adapters ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_nebius_direct_adapter_mock_generation():
    adapter = NebiusDirectAdapter(tier=ModelTier.NANO)
    assert adapter.is_available() is True
    assert adapter.get_estimated_tier() == ModelTier.NANO
    assert adapter.get_rate_limit_status().has_capacity is True

    resp = await adapter.generate("Write a function to add two numbers")
    assert isinstance(resp, ProviderResponse)
    assert len(resp.text) > 0
    assert resp.is_free_tier is False
    assert resp.cost_usd >= 0.0
    assert "prompt_tokens" in resp.raw_metadata


def test_nebius_rate_limit_tracking():
    adapter = NebiusDirectAdapter(tier=ModelTier.SUPER)
    assert adapter.get_rate_limit_status().has_capacity is True

    # Simulate 429 trigger
    adapter._rate_limited_until = time.monotonic() + 10.0
    status = adapter.get_rate_limit_status()
    assert status.has_capacity is False
    assert status.retry_after_seconds is not None
    assert status.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_ollama_local_adapter_mock_generation():
    adapter = OllamaLocalAdapter(model_name="nemotron-mini:latest")
    assert adapter.is_available() is True
    assert adapter.get_estimated_tier() == ModelTier.NANO

    resp = await adapter.generate("Create an async HTTP fetcher")
    assert isinstance(resp, ProviderResponse)
    assert resp.cost_usd == 0.0  # Must be 100% free
    assert resp.is_free_tier is True
    assert "ollama" in resp.model_name


# ── L-14: Google Antigravity CLI Adapter ─────────────────────────────────────

@pytest.mark.asyncio
async def test_antigravity_cli_adapter_mock_generation():
    adapter = AntigravityCliAdapter()
    assert adapter.is_available() is True
    assert adapter.get_estimated_tier() == ModelTier.NANO
    assert adapter.get_rate_limit_status().has_capacity is True

    resp = await adapter.generate("Fix typo in docstring")
    assert isinstance(resp, ProviderResponse)
    assert resp.cost_usd == 0.0  # Free tier
    assert resp.is_free_tier is True
    assert "antigravity" in resp.model_name


def test_antigravity_code_extraction():
    adapter = AntigravityCliAdapter()
    raw = "Here is the code:\n```python\ndef test_fn():\n    return 42\n```\nDone!"
    extracted = adapter._extract_code_from_output(raw)
    assert extracted == "def test_fn():\n    return 42"


# ── L-15: Claude Code CLI Adapter ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_claude_code_adapter_mock_generation():
    adapter = ClaudeCodePtyAdapter()
    assert adapter.is_available() is True
    assert adapter.get_estimated_tier() == ModelTier.SUPER

    resp = await adapter.generate("Refactor database connection pool")
    assert isinstance(resp, ProviderResponse)
    assert resp.cost_usd == 0.0
    assert resp.is_free_tier is True
    assert "claude-code" in resp.model_name


def test_claude_code_code_extraction():
    adapter = ClaudeCodePtyAdapter()
    raw = "\x1b[32mScanning...\x1b[0m\n```python\nclass DB:\n    pass\n```\n\r[Done]"
    extracted = adapter._extract_code_from_output(raw)
    assert extracted == "class DB:\n    pass"


# ── L-16: Cascading Failover Router Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_cascading_router_success_first_attempt():
    reg = ProviderRegistry()
    p1 = DummyMockAdapter("local_ollama", tier=ModelTier.NANO)
    p2 = DummyMockAdapter("nebius_cloud", tier=ModelTier.NANO, cost_usd=0.0005)
    reg.register("ollama", p1, priority=10)
    reg.register("nebius", p2, priority=50)

    router = CascadingProviderRouter(registry=reg)
    resp = await router.dispatch(prompt="Sort a list", tier=ModelTier.NANO)

    assert resp.model_name == "mock/local_ollama"
    assert p1.call_count == 1
    assert p2.call_count == 0  # Second provider was not needed!
    assert resp.raw_metadata["active_provider"] == "ollama"
    assert len(resp.raw_metadata["cascade_history"]) == 1


@pytest.mark.asyncio
async def test_cascading_router_failover_on_rate_limit_or_error():
    reg = ProviderRegistry()
    # First provider fails (simulating 429 quota exhaustion or crash)
    p1 = DummyMockAdapter("antigravity_free", tier=ModelTier.NANO, should_fail=True)
    # Second provider succeeds (fallback to cloud)
    p2 = DummyMockAdapter("nebius_cloud", tier=ModelTier.NANO, cost_usd=0.0001)

    reg.register("antigravity", p1, priority=10)
    reg.register("nebius", p2, priority=50)

    router = CascadingProviderRouter(registry=reg)
    resp = await router.dispatch(prompt="Format datetime string", tier=ModelTier.NANO)

    assert p1.call_count == 1
    assert p2.call_count == 1
    assert resp.model_name == "mock/nebius_cloud"
    assert resp.raw_metadata["active_provider"] == "nebius"

    # Check cascading history
    history = resp.raw_metadata["cascade_history"]
    assert len(history) == 2
    assert history[0]["provider"] == "antigravity"
    assert history[0]["status"] == "failed"
    assert history[1]["provider"] == "nebius"
    assert history[1]["status"] == "success"


@pytest.mark.asyncio
async def test_cascading_router_skips_rate_limited_provider():
    reg = ProviderRegistry()
    p1 = DummyMockAdapter("ollama", tier=ModelTier.NANO, is_rate_limited=True)
    p2 = DummyMockAdapter("nebius", tier=ModelTier.NANO)
    reg.register("ollama", p1, priority=10)
    reg.register("nebius", p2, priority=50)

    router = CascadingProviderRouter(registry=reg)
    resp = await router.dispatch(prompt="Parse JSON", tier=ModelTier.NANO)

    assert p1.call_count == 0  # Skipped without calling generate()
    assert p2.call_count == 1
    assert resp.raw_metadata["active_provider"] == "nebius"


@pytest.mark.asyncio
async def test_cascading_router_all_fail_raises_runtime_error():
    reg = ProviderRegistry()
    p1 = DummyMockAdapter("p1", should_fail=True)
    p2 = DummyMockAdapter("p2", should_fail=True)
    reg.register("p1", p1, priority=10)
    reg.register("p2", p2, priority=20)

    router = CascadingProviderRouter(registry=reg)
    with pytest.raises(RuntimeError, match="All providers in the cascading failover chain failed"):
        await router.dispatch(prompt="Do impossible task")


def test_cascading_router_dispatch_sync():
    reg = ProviderRegistry()
    p1 = DummyMockAdapter("sync_adapter")
    reg.register("sync_adapter", p1)

    router = CascadingProviderRouter(registry=reg)
    resp = router.dispatch_sync("Sync prompt")
    assert resp.model_name == "mock/sync_adapter"
    assert p1.call_count == 1
