import json
from dataclasses import asdict

from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.domain.review_schema import ReviewResult
from contract_risk_analysis.pipeline.build_evidence import build_evidence


def render_report_payload(
    review_result: ReviewResult, allowed_priorities: set[str] | None = None
) -> str:
    evidence = build_evidence(review_result, allowed_priorities=allowed_priorities)
    report = assess_risk(evidence)
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)
