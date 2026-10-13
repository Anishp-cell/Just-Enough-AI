"""CLI interface for Just-Enough-AI using Typer and Rich."""

from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .models import ExecutionMode, ModelTier, RunMetadata
from .profiler import get_gpu_headroom, assess_kv_headroom, NEMOTRON_SPECS
from .bridge import query_codebase_memory
from .router import determine_route, PRICING_TABLE
from .agent import run_task, run_speculative_draft, execute_agent_loop, AgentLoopEvent
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


@app.command(name="kv-budget")
def kv_budget(
    tokens: int = typer.Option(4000, "--tokens", "-n", help="Active context tokens to evaluate"),
    tier: Optional[str] = typer.Option("nano", "--tier", "-t", help="Target model tier: nano, super, ultra"),
):
    """Calculate physical GPU KV-Cache memory footprint and dynamic headroom via NVML."""
    selected_tier = _parse_tier(tier) or ModelTier.NANO
    headroom = get_gpu_headroom()
    budget = assess_kv_headroom(active_tokens=tokens, tier=selected_tier, headroom=headroom)

    console.print(f"[bold cyan]Physical GPU KV-Cache Budgeting[/bold cyan] (Evaluating {tokens} active tokens)")
    table = Table(title=f"KV-Cache Physical Footprint across NVIDIA Nemotron Architectures")
    table.add_column("Tier", style="cyan")
    table.add_column("Transformer Architecture", style="dim")
    table.add_column("KV Memory / 1k Tokens", style="green")
    table.add_column(f"Footprint for {tokens} Tokens", style="yellow")
    table.add_column("Governor Action", style="bold")

    for t, spec in NEMOTRON_SPECS.items():
        mb_per_1k = (2.0 * spec.layers * spec.kv_heads * spec.head_dim * spec.precision_bytes * 1000) / (1024 * 1024)
        total_mb = (mb_per_1k / 1000) * tokens
        action = "[green]Pass[/green]"
        if headroom.gpu_available and total_mb > headroom.free_vram_mb:
            action = "[red]Offload to Cloud[/red]"
        elif total_mb > 500:
            action = "[yellow]Prune Context[/yellow]"

        table.add_row(
            t.value.upper(),
            f"{spec.layers}L / {spec.kv_heads}H (dim={spec.head_dim})",
            f"{mb_per_1k:.2f} MB",
            f"{total_mb:.1f} MB",
            action,
        )

    console.print(table)
    console.print(Panel(
        f"[bold]Active Tokens:[/bold] {budget.active_tokens}\n"
        f"[bold]Target Tier:[/bold] {budget.tier.value.upper()}\n"
        f"[bold]KV Memory Used:[/bold] {budget.kv_cache_used_mb:.2f} MB\n"
        f"[bold]Projected Next Step:[/bold] {budget.projected_next_step_mb:.2f} MB\n"
        f"[bold]Local VRAM Free:[/bold] {budget.vram_free_mb:.1f} MB\n"
        f"[bold]Action:[/bold] {budget.governor_action}\n\n"
        f"[dim]{budget.reasoning}[/dim]",
        title="KV-Cache Governor Assessment", border_style="cyan",
    ))


@app.command()
def speculative(
    task: str = typer.Argument(..., help="Coding task to execute speculatively"),
    fallback: Optional[str] = typer.Option("super", "--fallback", "-f", help="Fallback tier on miss: super or ultra"),
):
    """Execute Speculative Agentic Drafting: Fast Nano draft -> SteerLM Gate -> Warm-Start Escalation."""
    fallback_tier = _parse_tier(fallback) or ModelTier.SUPER
    console.print(f"[bold]Speculative Agent Dispatch:[/bold] {task}")
    console.print("[dim]Phase 1: Dispatching 300ms Nemotron Nano speculative draft...[/dim]")

    result = run_speculative_draft(task_description=task, preferred_fallback_tier=fallback_tier)

    status_color = "green" if result.status == "SPECULATION_HIT" else "yellow"
    console.print(f"\n[{status_color} bold]Result: {result.status}[/{status_color} bold] (Assigned: {result.final_tier.value.upper()})")

    # SteerLM scorecard
    table = Table(title="In-Harness Nemotron HelpSteer2 PR Scorecard")
    table.add_column("Attribute", style="dim")
    table.add_column("Score (0.0 - 1.0)", style="bold")
    table.add_column("Status", style="cyan")

    table.add_row("Correctness", f"{result.gate_report.attributes.correctness:.2f}", "[green]PASS[/green]" if result.gate_report.attributes.correctness >= 0.6 else "[red]FAIL[/red]")
    table.add_row("Regression Risk", f"{result.gate_report.attributes.regression_risk:.2f}", "[green]LOW[/green]" if result.gate_report.attributes.regression_risk <= 0.3 else "[yellow]MED[/yellow]")
    table.add_row("Security Score", f"{result.gate_report.attributes.security_score:.2f}", "[green]SECURE[/green]" if result.gate_report.attributes.security_score >= 0.7 else "[red]RISK[/red]")
    table.add_row("Conciseness", f"{result.gate_report.attributes.conciseness:.2f}", "[green]SURGICAL[/green]")
    table.add_row("Composite Gate Score", f"[bold]{result.gate_report.gate_score:.2f}[/bold]", f"[bold {'green' if result.gate_report.passed else 'red'}]{'PASSED' if result.gate_report.passed else 'REJECTED'}[/]")
    console.print(table)

    console.print(Panel(
        f"[bold]Status:[/bold] {result.status}\n"
        f"[bold]Warm-Started:[/bold] {'Yes (Failure Trace Guided)' if result.warm_started else 'No (Direct Hit)'}\n"
        f"[bold]Total Latency:[/bold] {result.total_latency_ms:.0f}ms (Draft: {result.draft_latency_ms:.0f}ms)\n"
        f"[bold]Total Cost:[/bold] ${result.total_cost_usd:.6f}\n"
        f"[bold green]Saved vs Ultra:[/bold green] ${result.savings_vs_ultra_usd:.6f}\n\n"
        f"[dim]{result.reasoning}[/dim]",
        title="Speculative Execution Telemetry", border_style=status_color,
    ))

    console.print("\n[bold]Generated Solution:[/bold]")
    console.print(result.code_solution)


@app.command()
def loop(
    task: str = typer.Argument(..., help="Coding task to execute via multi-step agent loop"),
):
    """Run full agentic loop with KV-governor, speculative drafting, and self-fix escalation."""
    console.print(f"[bold]Starting Agentic Tool Loop:[/bold] {task}\n")

    for event in execute_agent_loop(task_description=task):
        if isinstance(event, AgentLoopEvent):
            color = "cyan" if event.event_type == "KV_BUDGET" else "yellow" if event.event_type == "SPECULATION" else "green"
            console.print(f"[{color}][Step {event.step} - {event.event_type}][/{color}] {event.message}")
        elif isinstance(event, RunMetadata):
            console.print(Panel(
                f"[bold]Final Tier:[/bold] {event.tier.value.upper()}\n"
                f"[bold]Total Tokens:[/bold] {event.total_tokens}\n"
                f"[bold green]Actual Cost:[/bold green] ${event.actual_cost_usd:.6f}\n"
                f"[bold cyan]Saved vs Ultra:[/bold cyan] ${event.savings_vs_ultra_usd:.6f}\n"
                f"[bold]Elapsed Latency:[/bold] {event.latency_ms:.0f}ms",
                title="Agent Loop Completed", border_style="green",
            ))


if __name__ == "__main__":
    app()
