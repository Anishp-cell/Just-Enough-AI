#!/usr/bin/env python
"""Reproducible benchmark and cost evaluation runner for Just-Enough-AI.

Usage:
    uv run python scripts/run_eval.py
    uv run python scripts/run_eval.py --mode remote --tasks data/benchmarks/tasks_v1.json
"""

import argparse
import sys
from pathlib import Path

# Fix Windows console cp1252 encoding issues
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from just_enough_ai.models import ExecutionMode
from just_enough_ai.eval.runner import run_benchmark_suite


def main():
    parser = argparse.ArgumentParser(description="Just-Enough-AI Evaluation Runner")
    parser.add_argument(
        "--tasks",
        default="data/benchmarks/tasks_v1.json",
        help="Path to tasks JSON file (default: data/benchmarks/tasks_v1.json)",
    )
    parser.add_argument(
        "--mode",
        choices=["local", "remote"],
        default="remote",
        help="Execution mode: local (VRAM-aware) or remote (cloud-only) (default: remote)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum tasks to evaluate (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/results",
        help="Output directory for reports (default: data/results)",
    )
    args = parser.parse_args()

    mode = ExecutionMode.REMOTE_CLOUD if args.mode == "remote" else ExecutionMode.LOCAL

    print(f"\n=======================================================")
    print(f"[JEAI] Just-Enough-AI: Running Evaluation Suite")
    print(f"=======================================================")
    print(f"Dataset:    {args.tasks}")
    print(f"Mode:       {mode.value.upper()}")
    print(f"Output Dir: {args.output_dir}\n")

    report = run_benchmark_suite(
        tasks_file=args.tasks,
        mode=mode,
        max_tasks=args.max_tasks,
        output_dir=args.output_dir,
    )

    print("\n=======================================================")
    print("🏆 Benchmark Suite Execution Completed Successfully!")
    print("=======================================================")
    print(f"Total Tasks Evaluated:  {report.total_tasks}")
    print(f"Routing Accuracy:       {report.routing_accuracy_pct}%")
    print(f"Total Tokens:           {report.total_tokens:,}")
    print(f"Total Cost (JEAI):      ${report.total_actual_cost_usd:.5f}")
    print(f"Baseline Ultra Cost:    ${report.total_baseline_ultra_cost_usd:.5f}")
    print(f"Baseline GPT-4o Cost:   ${report.total_baseline_gpt4o_cost_usd:.5f}")
    print(f"Savings vs Ultra:       {report.savings_pct_vs_ultra}% (${report.total_savings_vs_ultra_usd:.4f})")
    print(f"Savings vs GPT-4o:      {report.savings_pct_vs_gpt4o}% (${report.total_savings_vs_gpt4o_usd:.4f})")
    print(f"Savings vs Claude:      {report.savings_pct_vs_claude}% (${report.total_savings_vs_claude_usd:.4f})")
    print(f"Reports Written to:     {args.output_dir}/")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
