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
