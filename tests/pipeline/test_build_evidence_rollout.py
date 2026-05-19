from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult
from contract_risk_analysis.pipeline.build_evidence import build_evidence


def test_build_evidence_can_limit_output_to_p0_nodes() -> None:
    review_result = ReviewResult(
        contract_id="nda-rollout-001",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No express termination clause found.",
                confidence=0.93,
                finding_key="termination_clause_missing",
                finding_label="终止条款缺失",
            ),
            ReviewFinding(
                clause_type="acceptance",
                status="missing",
                evidence_text="No acceptance clause found.",
                confidence=0.82,
                finding_key="acceptance_terms_missing",
                finding_label="验收条款缺失",
            ),
        ],
    )

    evidence = build_evidence(review_result, allowed_priorities={"P0"})

    assert len(evidence.evidence_items) == 1
    assert all(item.node_priority == "P0" for item in evidence.evidence_items)
    assert len(evidence.node_observations) == 1
