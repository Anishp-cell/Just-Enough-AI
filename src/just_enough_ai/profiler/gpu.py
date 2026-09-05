"""NVIDIA GPU VRAM profiling via nvidia-ml-py."""

import logging
from ..models import HardwareHeadroom
from ..config import settings

logger = logging.getLogger(__name__)


def get_gpu_headroom() -> HardwareHeadroom:
    """Measure physical GPU VRAM headroom using NVML if an NVIDIA GPU is present.

    Gracefully falls back if NVML or NVIDIA hardware is unavailable.
    """
    if not settings.enable_gpu_profiling:
        return HardwareHeadroom(gpu_available=False, reasoning="GPU profiling disabled via settings")

    try:
        import pynvml
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()

        if device_count == 0:
            return HardwareHeadroom(gpu_available=False)

        # Profile the primary GPU (device 0)
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode("utf-8")

        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_mb = mem_info.total / (1024 * 1024)
        free_mb = mem_info.free / (1024 * 1024)
        headroom_pct = (free_mb / total_mb) * 100 if total_mb > 0 else 0.0

        has_headroom = free_mb >= settings.vram_threshold_mb

        pynvml.nvmlShutdown()

        return HardwareHeadroom(
            gpu_available=True,
            gpu_name=gpu_name,
            total_vram_mb=round(total_mb, 2),
            free_vram_mb=round(free_mb, 2),
            vram_headroom_pct=round(headroom_pct, 2),
            has_sufficient_headroom=has_headroom,
        )
    except Exception as e:
        logger.debug(f"NVML detection failed or NVIDIA GPU not present: {e}")
        return HardwareHeadroom(
            gpu_available=False,
            gpu_name=None,
            total_vram_mb=0.0,
            free_vram_mb=0.0,
            vram_headroom_pct=0.0,
            has_sufficient_headroom=False,
        )
