"""Benchmark runner — CLI entry point for evaluation tasks.

Usage:
  python -m contract_risk_analysis.benchmark_runner contractnli [--max 200] [--split test] [--use-llm]
  python -m contract_risk_analysis.benchmark_runner cuad [--max 30] [--use-llm]
  python -m contract_risk_analysis.benchmark_runner calibrate
  python -m contract_risk_analysis.benchmark_runner baseline [--max 100]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from contract_risk_analysis.cli import load_review_result
from contract_risk_analysis.evaluation.cpt_calibrator import (
    calibrate_confidentiality_nodes,
    print_calibration_report,
)
from contract_risk_analysis.evaluation.runner import (
    print_benchmark_summary,
    run_baseline_comparison,
    run_contractnli_benchmark,
    run_cuad_benchmark,
    save_benchmark_results,
)
from contract_risk_analysis.pipeline.build_evidence import build_evidence
from contract_risk_analysis.bn.inference import assess_risk


OUTPUT_DIR = Path(__file__).resolve().parents[3] / "sample_data"


def _run_variant(input_path: str | Path, allowed_priorities: set[str] | None) -> dict:
    review_result = load_review_result(input_path)
    evidence = build_evidence(review_result, allowed_priorities=allowed_priorities)
    report = assess_risk(evidence)
    return {
        "allowed_priorities": sorted(allowed_priorities) if allowed_priorities else None,
        "report": asdict(report),
        "node_observations": [asdict(item) for item in evidence.node_observations],
    }


def cmd_legacy(argv: list[str]) -> None:
    """Original benchmark: run review JSON through pipeline variants."""
    input_path = argv[0]
    review_result = load_review_result(input_path)
    payload = {
        "contract_id": review_result.contract_id,
        "full": _run_variant(input_path, allowed_priorities=None),
        "p0": _run_variant(input_path, allowed_priorities={"P0"}),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_contractnli(args: argparse.Namespace) -> None:
    print(f"Running ContractNLI benchmark (max={args.max}, split={args.split}, llm={args.use_llm})...")
    result = run_contractnli_benchmark(
        max_samples=args.max,
        split=args.split,
        use_llm=args.use_llm,
        verbose=args.verbose,
    )
    print(print_benchmark_summary([result]))
    out_path = OUTPUT_DIR / f"benchmark_contractnli_{args.split}.json"
    save_benchmark_results([result], out_path)
    print(f"Saved to {out_path}")


def cmd_cuad(args: argparse.Namespace) -> None:
    print(f"Running CUAD benchmark (max={args.max}, llm={args.use_llm})...")
    result = run_cuad_benchmark(
        max_contracts=args.max,
        use_llm=args.use_llm,
        verbose=args.verbose,
    )
    print(print_benchmark_summary([result]))
    out_path = OUTPUT_DIR / "benchmark_cuad.json"
    save_benchmark_results([result], out_path)
    print(f"Saved to {out_path}")


def cmd_calibrate(_args: argparse.Namespace) -> None:
    print(print_calibration_report())
    calibrate_confidentiality_nodes()
    print("\nCPT values calibrated and saved to bayesian_network_v2.json.")


def cmd_baseline(args: argparse.Namespace) -> None:
    print(f"Running baseline comparison (max={args.max})...")
    results = run_baseline_comparison(max_samples=args.max)
    print(print_benchmark_summary(results))
    out_path = OUTPUT_DIR / "benchmark_baseline_comparison.json"
    save_benchmark_results(results, out_path)
    print(f"Saved to {out_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BN Contract Risk Analysis — Benchmark Runner")
    sub = parser.add_subparsers(dest="command")

    p_nli = sub.add_parser("contractnli", help="Evaluate on ContractNLI")
    p_nli.add_argument("--max", type=int, default=200)
    p_nli.add_argument("--split", default="test")
    p_nli.add_argument("--use-llm", action="store_true")
    p_nli.add_argument("--verbose", action="store_true")

    p_cuad = sub.add_parser("cuad", help="Evaluate on CUAD")
    p_cuad.add_argument("--max", type=int, default=30)
    p_cuad.add_argument("--use-llm", action="store_true")
    p_cuad.add_argument("--verbose", action="store_true")

    sub.add_parser("calibrate", help="Calibrate CPT from ContractNLI data")

    p_base = sub.add_parser("baseline", help="Run baseline comparison")
    p_base.add_argument("--max", type=int, default=100)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()

    # Legacy mode: first positional arg is a JSON path (no subcommand)
    if argv is None:
        import sys
        argv = sys.argv[1:]
    if argv and not argv[0].startswith("-") and argv[0] not in {
        "contractnli", "cuad", "calibrate", "baseline",
    }:
        cmd_legacy(argv)
        return

    args = parser.parse_args(argv)
    if args.command == "contractnli":
        cmd_contractnli(args)
    elif args.command == "cuad":
        cmd_cuad(args)
    elif args.command == "calibrate":
        cmd_calibrate(args)
    elif args.command == "baseline":
        cmd_baseline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
