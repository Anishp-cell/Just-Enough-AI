"""Configuration settings for Just-Enough-AI."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Nebius Token Factory
    nebius_api_key: Optional[str] = Field(default=None, alias="NEBIUS_API_KEY")
    nebius_base_url: str = Field(default="https://api.studio.nebius.ai/v1", alias="NEBIUS_BASE_URL")

    # Model Tiers
    model_nano: str = Field(default="nvidia/nemotron-3-nano-omni", alias="MODEL_NANO")
    model_super: str = Field(default="nvidia/nemotron-3-super-120b-a12b", alias="MODEL_SUPER")
    model_ultra: str = Field(default="nvidia/Llama-3_1-Nemotron-Ultra-253B-v1", alias="MODEL_ULTRA")

    # Profiling & Headroom
    enable_gpu_profiling: bool = Field(default=True, alias="ENABLE_GPU_PROFILING")
    vram_threshold_mb: int = Field(default=6144, alias="VRAM_THRESHOLD_MB")

    # devmind Codebase Memory Bridge
    devmind_enabled: bool = Field(default=True, alias="DEVMIND_ENABLED")
    devmind_cli_path: str = Field(default="devmind", alias="DEVMIND_CLI_PATH")

    # Execution & Telemetry
    mock_mode: bool = Field(default=True, alias="MOCK_MODE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()
