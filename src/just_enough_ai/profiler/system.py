"""System and host-level resource profiling."""

import psutil
import platform


def get_system_profile() -> dict:
    """Collect host CPU, RAM, and platform metrics."""
    vm = psutil.virtual_memory() if hasattr(psutil, "virtual_memory") else None
    free_ram_mb = (vm.available / (1024 * 1024)) if vm else 0.0

    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "free_ram_mb": round(free_ram_mb, 2),
        "total_ram_mb": round(vm.total / (1024 * 1024), 2) if vm else 0.0,
    }
