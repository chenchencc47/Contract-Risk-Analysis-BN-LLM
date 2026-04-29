import json

from contract_risk_analysis.demo.app import render_report_payload
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult


def test_render_report_payload_returns_demo_ready_json() -> None:
    review_result = ReviewResult(
        contract_id="nda-001",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No termination clause found.",
                confidence=0.91,
                finding_key="termination_clause_missing",
                finding_label="终止条款缺失",
            )
        ],
    )

    payload = render_report_payload(review_result)

    data = json.loads(payload)
    assert data["contract_id"] == "nda-001"
    assert data["overall_risk"] == "medium"
    assert data["requires_manual_review"] is False
    assert data["signing_recommendation"] == "有条件签署"
    assert data["category_scores"]["overall_contract_risk"] == 0.17
    assert data["dimension_scores"]["legal_enforceability_risk"] == 0.4675
    assert data["dimension_summaries"]["legal_enforceability_risk"] == "合同存在一定法律执行不确定性，建议签署前补齐关键基础条款。"
    assert data["top_risks"][0]["title"] == "终止条款完整性"
    assert data["top_risks"][0]["reason"] == "终止条款缺失"
    assert data["top_risks"][0]["evidence"] == ["No termination clause found."]
    assert data["manual_review_items"] == []
