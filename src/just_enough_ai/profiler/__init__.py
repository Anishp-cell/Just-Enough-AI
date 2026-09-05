"""Hardware and GPU headroom profiling package."""

from .gpu import get_gpu_headroom
from .system import get_system_profile

__all__ = ["get_gpu_headroom", "get_system_profile"]
