import argparse
import json
from dataclasses import asdict
from pathlib import Path

from contract_risk_analysis.demo.app import render_report_payload
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult
from contract_risk_analysis.pipeline.build_evidence import build_evidence
from contract_risk_analysis.review.ai_review import review_contract_text, review_result_to_json


DEFAULT_INPUT_PATH = Path("sample_data/review_result_examples/nda_example.json")


def load_review_result(path: str | Path) -> ReviewResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    findings = [ReviewFinding(**item) for item in payload["findings"]]
    return ReviewResult(
        contract_id=payload["contract_id"],
        findings=findings,
        review_type=payload.get("review_type"),
        source_document=payload.get("source_document"),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path", nargs="?", default=None)
    parser.add_argument("--contract-text-path")
    parser.add_argument("--contract-id")
    parser.add_argument("--dump-review-json", action="store_true")
    parser.add_argument("--allowed-priority", action="append")
    parser.add_argument("--debug-output", action="store_true")
    # Node discovery commands (P6)
    parser.add_argument("--discover-nodes", action="store_true",
                        help="Show pending BN nodes discovered from contract reviews")
    parser.add_argument("--approve-node", type=str, default=None, metavar="CLAUSE_TYPE",
                        help="Approve a pending node and add to BN config")
    parser.add_argument("--reject-node", type=str, default=None, metavar="CLAUSE_TYPE",
                        help="Remove a pending node entry")
    parser.add_argument("--feedback-summary", action="store_true",
                        help="Show aggregated BN feedback accuracy per node")
    parser.add_argument("--score-golden-case", type=str, default=None, metavar="YAML",
                        help="Score a Markdown report against a golden case YAML")
    parser.add_argument("--score-golden-case-batch", type=str, default=None, metavar="YAML",
                        help="Score all Markdown reports in a directory against a golden case YAML")
    parser.add_argument("--report", type=str, default=None, metavar="MD",
                        help="Markdown report path for --score-golden-case")
    parser.add_argument("--reports-dir", type=str, default=None, metavar="DIR",
                        help="Markdown reports directory for --score-golden-case-batch")
    parser.add_argument("--list-golden-patterns", action="store_true",
                        help="List golden pattern metadata as JSON")
    parser.add_argument("--golden-patterns-dir", type=str, default="tests/fixtures/golden_patterns",
                        help="Directory containing golden pattern YAML files")
    return parser.parse_args(argv)


def _print_debug_payload(
    review_result: ReviewResult, allowed_priorities: set[str] | None = None
) -> None:
    evidence = build_evidence(review_result, allowed_priorities=allowed_priorities)
    print(
        json.dumps(
            {
                "contract_id": review_result.contract_id,
                "allowed_priorities": sorted(allowed_priorities)
                if allowed_priorities
                else None,
                "evidence_items": [asdict(item) for item in evidence.evidence_items],
                "node_observations": [
                    asdict(item) for item in evidence.node_observations
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # ── Golden case scoring: --score-golden-case-batch ──
    if args.score_golden_case_batch:
        if not args.reports_dir:
            raise SystemExit("--score-golden-case-batch requires --reports-dir")
        from contract_risk_analysis.evaluation.golden_score import (
            format_batch_golden_summary,
            score_reports_against_case_batch,
        )

        try:
            batch = score_reports_against_case_batch(
                args.score_golden_case_batch,
                args.reports_dir,
            )
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise SystemExit(str(exc)) from exc

        print(format_batch_golden_summary(batch))
        print()
        print(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2))
        return

    # ── Golden case scoring: --score-golden-case ──
    if args.score_golden_case:
        if not args.report:
            raise SystemExit("--score-golden-case requires --report")
        from contract_risk_analysis.evaluation.golden_score import score_report_against_case
        score = score_report_against_case(args.score_golden_case, args.report)
        print(json.dumps(score.to_dict(), ensure_ascii=False, indent=2))
        return

    # ── Golden patterns: --list-golden-patterns ──
    if args.list_golden_patterns:
        from contract_risk_analysis.evaluation.golden_score import (
            load_golden_patterns,
            summarize_patterns,
        )
        rows = summarize_patterns(load_golden_patterns(args.golden_patterns_dir))
        print(json.dumps({"patterns": rows}, ensure_ascii=False, indent=2))
        return

    # ── Node discovery: --discover-nodes ──
    if args.discover_nodes:
        from contract_risk_analysis.bn.node_discovery import discover_pending_nodes
        nodes = discover_pending_nodes()
        if not nodes:
            print("No pending nodes found. Run some contract reviews first.")
            return
        print(f"\n{'='*70}")
        print(f"  Pending BN Nodes ({len(nodes)} unique clause_types)")
        print(f"{'='*70}\n")
        for i, n in enumerate(nodes, 1):
            print(f"  [{i}] {n['clause_type']}")
            print(f"      Risk: {n.get('risk_title', 'N/A')}")
            print(f"      Seen: {n['occurrence_count']}x | Severity: {n.get('severity','?')}")
            print(f"      → Node name: {n['suggested_node_name']}")
            print(f"      → States:    {n['suggested_states']}")
            print(f"      → Dimension: {n['suggested_dimension']}")
            print(f"      → Approve:   python -m contract_risk_analysis.cli --approve-node \"{n['clause_type']}\"")
            print(f"      → Reject:    python -m contract_risk_analysis.cli --reject-node \"{n['clause_type']}\"")
            print()
        return

    # ── Node discovery: --approve-node ──
    if args.approve_node:
        from contract_risk_analysis.bn.node_discovery import approve_node
        success = approve_node(args.approve_node)
        if success:
            print("Run tests to verify BN model integrity.")
        return

    # ── Node discovery: --reject-node ──
    if args.reject_node:
        from contract_risk_analysis.bn.node_discovery import reject_node
        reject_node(args.reject_node)
        return

    # ── Feedback: --feedback-summary ──
    if args.feedback_summary:
        from contract_risk_analysis.bn.feedback import get_feedback_summary
        rows = get_feedback_summary()
        if not rows:
            print("No feedback records yet.")
            return
        print(f"\n{'='*60}")
        print(f"  BN Feedback Summary ({len(rows)} nodes with feedback)")
        print(f"{'='*60}\n")
        for r in rows:
            bar = "█" * int(r["accuracy"] * 10) + "░" * (10 - int(r["accuracy"] * 10))
            print(f"  {r['node_name']}")
            print(f"     Accuracy: {bar} {r['accuracy']:.0%} ({r['correct']}/{r['total']})")
            if r["incorrect"]:
                print(f"     ⚠ {r['incorrect']} incorrect — review suggested")
            print()
        return

    # ── Default: contract review ──
    allowed_priorities = set(args.allowed_priority or []) or None
    if args.contract_text_path:
        contract_text_path = Path(args.contract_text_path)
        review_result = review_contract_text(
            contract_text_path.read_text(encoding="utf-8"),
            contract_id=args.contract_id or contract_text_path.stem,
            source_document=contract_text_path.name,
        )
        if args.dump_review_json:
            print(review_result_to_json(review_result))
        if args.debug_output:
            _print_debug_payload(review_result, allowed_priorities=allowed_priorities)
            return
        print(render_report_payload(review_result, allowed_priorities=allowed_priorities))
        return

    input_path = args.input_path or str(DEFAULT_INPUT_PATH)
    review_result = load_review_result(input_path)
    if args.debug_output:
        _print_debug_payload(review_result, allowed_priorities=allowed_priorities)
        return
    print(render_report_payload(review_result, allowed_priorities=allowed_priorities))


if __name__ == "__main__":
    main()
