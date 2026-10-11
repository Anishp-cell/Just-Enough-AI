"""CLI interface for Just-Enough-AI using Typer and Rich."""

from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .models import ExecutionMode, ModelTier, RunMetadata
from .profiler import get_gpu_headroom
from .bridge import query_codebase_memory
from .router import determine_route, PRICING_TABLE
from .agent import run_task
from .config import settings
from . import __version__, __app_name__

app = typer.Typer(
    name="jeai",
    help="Just-Enough-AI: Memory-aware, hardware-headroom cost-tiered agentic coding harness.",
    add_completion=False,
)
console = Console()


def _parse_tier(tier_str: Optional[str]) -> Optional[ModelTier]:
    if not tier_str:
        return None
    try:
        return ModelTier(tier_str.lower().strip())
    except ValueError:
        valid = ", ".join([t.value for t in ModelTier])
        console.print(f"[red]Error:[/red] Invalid tier '{tier_str}'. Valid tiers: {valid}")
        raise typer.Exit(code=1)


def _parse_mode(mode_str: str) -> ExecutionMode:
    mode_lower = mode_str.lower().strip()
    if mode_lower in ("remote", "cloud", "remote_cloud"):
        return ExecutionMode.REMOTE_CLOUD
    elif mode_lower == "local":
        return ExecutionMode.LOCAL
    else:
        console.print(f"[red]Error:[/red] Invalid mode '{mode_str}'. Valid modes: 'local', 'remote'")
        raise typer.Exit(code=1)


@app.command()
def version():
    """Show current version."""
    console.print(f"[bold green]{__app_name__}[/bold green] v{__version__}")


@app.command()
def profile():
    """Inspect local hardware and NVIDIA GPU VRAM headroom."""
    console.print("[bold cyan]Scanning hardware and GPU headroom...[/bold cyan]")
    headroom = get_gpu_headroom()

    table = Table(title="Hardware Headroom Profile")
    table.add_column("Property", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("NVIDIA GPU Detected", "Yes" if headroom.gpu_available else "No")
    if headroom.gpu_available:
        table.add_row("GPU Model", headroom.gpu_name or "Unknown")
        table.add_row("Total VRAM", f"{headroom.total_vram_mb:.1f} MB")
        table.add_row("Free VRAM", f"{headroom.free_vram_mb:.1f} MB")
        table.add_row("VRAM Headroom", f"{headroom.vram_headroom_pct:.1f}%")
    table.add_row(
        "Sufficient Headroom (>= 6GB)",
        "[green]Yes (Eligible for Nano)[/green]" if headroom.has_sufficient_headroom else "[yellow]No (Routes to Super/Ultra)[/yellow]",
    )
    console.print(table)


@app.command()
def pricing():
    """Display Nebius Token Factory pricing tiers for NVIDIA Nemotron models."""
    table = Table(title="Nebius Token Factory Pricing Tiers (NVIDIA Nemotron)")
    table.add_column("Tier", style="cyan")
    table.add_column("Model ID", style="bold")
    table.add_column("Input / 1M", style="green")
    table.add_column("Output / 1M", style="green")
    table.add_column("Blended / 1M", style="yellow")

    for tier, info in PRICING_TABLE.items():
        table.add_row(
            tier.value.upper(),
            info["model_id"],
            f"${info['input_per_1m']:.2f}",
            f"${info['output_per_1m']:.2f}",
            f"${info['blended_per_1m']:.3f}",
        )
    console.print(table)


@app.command()
def route(
    task: str = typer.Argument(..., help="Coding task or prompt to evaluate"),
    mode: str = typer.Option("local", "--mode", "-m", help="Execution mode: 'local' or 'remote'"),
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="Force specific tier: nano, super, ultra"),
):
    """Determine the optimal Nemotron model tier without executing inference."""
    exec_mode = _parse_mode(mode)
    forced_tier = _parse_tier(tier)

    console.print(f"[bold]Evaluating task:[/bold] {task}")
    console.print(f"[dim]Mode: {exec_mode.value.upper()}[/dim]\n")

    headroom = get_gpu_headroom()
    memory = query_codebase_memory(task)
    decision = determine_route(task, headroom, memory, mode=exec_mode, force_tier=forced_tier)

    panel_content = (
        f"[bold cyan]Selected Tier:[/bold cyan] {decision.selected_tier.value.upper()}\n"
        f"[bold cyan]Model ID:[/bold cyan] {decision.model_id}\n"
        f"[bold cyan]Execution Mode:[/bold cyan] {decision.execution_mode.value.upper()}\n"
        f"[bold cyan]Estimated Cost:[/bold cyan] ${decision.estimated_cost_per_1m_tokens:.3f} / 1M tokens\n"
        f"[bold cyan]Memory Grounding Score:[/bold cyan] {memory.confidence_score:.2f}\n"
        f"[bold cyan]GPU Headroom:[/bold cyan] {headroom.free_vram_mb:.1f} MB free\n\n"
        f"[dim]{decision.reasoning}[/dim]"
    )
    console.print(Panel(panel_content, title="Routing Decision", border_style="green"))


@app.command()
def run(
    task: str = typer.Argument(..., help="Coding task to route and execute"),
    mode: str = typer.Option("local", "--mode", "-m", help="Execution mode: 'local' or 'remote'"),
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="Force specific tier: nano, super, ultra"),
):
    """Route and execute a coding task on Nebius Token Factory."""
    exec_mode = _parse_mode(mode)
    forced_tier = _parse_tier(tier)

    headroom = get_gpu_headroom()
    memory = query_codebase_memory(task)
    decision = determine_route(task, headroom, memory, mode=exec_mode, force_tier=forced_tier)

    mode_str = "[yellow]MOCK MODE[/yellow]" if settings.mock_mode or not settings.nebius_api_key else "[green]LIVE NEBIUS[/green]"
    console.print(f"Executing via {mode_str} [{exec_mode.value.upper()}] using [bold]{decision.model_id}[/bold] ({decision.selected_tier.value.upper()})\n")

    for chunk in run_task(task, decision):
        if isinstance(chunk, RunMetadata):
            console.print()
            console.print(Panel(
                f"[bold]Model:[/bold] {chunk.model_id}\n"
                f"[bold]Mode:[/bold] {chunk.execution_mode.value.upper()}\n"
                f"[bold]Tokens:[/bold] {chunk.prompt_tokens} prompt + {chunk.completion_tokens} completion ({chunk.total_tokens} total)\n"
                f"[bold green]Actual Cost:[/bold green] ${chunk.actual_cost_usd:.5f}\n"
                f"[bold cyan]Saved vs Ultra:[/bold cyan] ${chunk.savings_vs_ultra_usd:.5f}\n"
                f"[bold]Latency:[/bold] {chunk.latency_ms:.0f}ms",
                title="Run Summary & Cost Telemetry", border_style="green",
            ))
        else:
            console.print(chunk, end="")
    console.print()


if __name__ == "__main__":
    app()
