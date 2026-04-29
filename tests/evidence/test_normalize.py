from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult
from contract_risk_analysis.evidence.normalize import normalize_review_result
import pytest


def test_normalize_review_result_builds_evidence_items() -> None:
    review_result = ReviewResult(
        contract_id="nda-ev-001",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No express termination clause found.",
                confidence=0.93,
                finding_key="termination_clause_missing",
                finding_label="终止条款缺失",
            )
        ],
    )

    evidence_items = normalize_review_result(review_result)

    assert len(evidence_items) == 1
    assert evidence_items[0].node_name == "termination_clause_completeness"
    assert evidence_items[0].node_layer == "legal_semantics"


def test_normalize_review_result_rejects_state_not_allowed_by_schema() -> None:
    review_result = ReviewResult(
        contract_id="nda-ev-006",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="weird_status",
                evidence_text="Termination clause text.",
                confidence=0.9,
            )
        ],
    )

    with pytest.raises(ValueError, match="not allowed"):
        normalize_review_result(review_result)


def test_normalize_review_result_can_filter_by_allowed_priorities() -> None:
    review_result = ReviewResult(
        contract_id="nda-ev-007",
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

    evidence_items = normalize_review_result(
        review_result, allowed_priorities={"P0"}
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].node_priority == "P0"
