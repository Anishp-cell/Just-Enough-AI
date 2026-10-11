"""System and host-level resource profiling."""

import platform

try:
    import psutil
except ImportError:
    psutil = None


def get_system_profile() -> dict:
    """Collect host CPU, RAM, and platform metrics."""
    if psutil is not None and hasattr(psutil, "virtual_memory"):
        try:
            vm = psutil.virtual_memory()
            free_ram_mb = round(vm.available / (1024 * 1024), 2)
            total_ram_mb = round(vm.total / (1024 * 1024), 2)
        except Exception:
            free_ram_mb = 0.0
            total_ram_mb = 0.0
    else:
        free_ram_mb = 0.0
        total_ram_mb = 0.0

    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "free_ram_mb": free_ram_mb,
        "total_ram_mb": total_ram_mb,
    }
