"""Data models and schemas for Just-Enough-AI."""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class ModelTier(str, Enum):
    """NVIDIA Nemotron model tiers on Nebius Token Factory."""
    NANO = "nano"
    SUPER = "super"
    ULTRA = "ultra"


class ExecutionMode(str, Enum):
    """Whether routing uses local hardware headroom or cloud-only mode."""
    LOCAL = "local"          # GPU VRAM is factored into routing
    REMOTE_CLOUD = "remote"  # No local GPU; routing uses only memory confidence


class HardwareHeadroom(BaseModel):
    """Hardware profile measured at session start."""
    gpu_available: bool = False
    gpu_name: Optional[str] = None
    total_vram_mb: float = 0.0
    free_vram_mb: float = 0.0
    vram_headroom_pct: float = 0.0
    system_ram_free_mb: float = 0.0
    has_sufficient_headroom: bool = False


class MemoryContext(BaseModel):
    """Retrieved memory context from devmind codebase index."""
    query: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    context_chunks: List[str] = Field(default_factory=list)
    has_high_confidence: bool = False


class RoutingDecision(BaseModel):
    """Routing outcome determining which model tier to assign."""
    selected_tier: ModelTier
    model_id: str
    reasoning: str
    estimated_cost_per_1m_tokens: float
    hardware_headroom: HardwareHeadroom
    memory_context: MemoryContext
    execution_mode: ExecutionMode = ExecutionMode.LOCAL
    force_tier: Optional[ModelTier] = None


class RunMetadata(BaseModel):
    """Actual telemetry captured after a completed Nebius inference call."""
    model_id: str
    tier: ModelTier
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    actual_cost_usd: float = 0.0
    savings_vs_ultra_usd: float = 0.0
    latency_ms: float = 0.0
    execution_mode: ExecutionMode = ExecutionMode.LOCAL
