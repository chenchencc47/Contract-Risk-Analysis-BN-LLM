from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.domain.review_schema import NodeObservation, RiskEvidence


def test_assess_risk_returns_category_scores_and_manual_review_flag() -> None:
    evidence = RiskEvidence(
        contract_id="nda-001",
        node_states={
            "termination_clause": "missing",
            "liability_cap": "unfavorable",
            "confidentiality_nli": "contradiction",
        },
        triggered_findings=[
            "termination:missing",
            "liability_cap:unfavorable",
            "confidentiality:contradiction",
        ],
    )

    report = assess_risk(evidence)

    assert report.contract_id == "nda-001"
    assert report.overall_risk == "high"
    assert report.requires_manual_review is True
    assert report.category_scores == {
        "termination_risk": 0.85,
        "liability_risk": 0.8,
        "confidentiality_risk": 0.8,
        "overall_legal_risk": 0.95,
    }
    assert report.summary_reasons == [
        "termination clause is missing",
        "liability cap is unfavorable",
        "confidentiality review produced contradiction",
    ]


def test_assess_risk_returns_multi_dimensional_report_fields() -> None:
    evidence = RiskEvidence(
        contract_id="nda-101",
        node_states={
            "termination_clause_completeness": "missing",
            "liability_cap_strength": "severe",
            "damages_exposure": "high",
            "governing_law_clarity": "missing",
            "dispute_resolution_clarity": "missing",
            "acceptance_process_clarity": "missing",
        },
        triggered_findings=[
            "termination_clause_missing:missing",
            "liability_cap_missing:missing",
            "indirect_damage_exposure_high:unfavorable",
            "governing_law_missing:missing",
            "dispute_resolution_missing:missing",
            "acceptance_terms_missing:missing",
        ],
        supporting_findings_by_node={
            "termination_clause_completeness": ["终止条款缺失"],
            "liability_cap_strength": ["责任上限缺失", "间接损失暴露过高"],
            "governing_law_clarity": ["适用法律缺失"],
        },
        supporting_evidence_by_node={
            "termination_clause_completeness": ["No express termination clause found."],
            "liability_cap_strength": ["Supplier liability is uncapped."],
            "governing_law_clarity": ["No governing law clause found."],
        },
    )

    report = assess_risk(evidence)

    assert report.signing_recommendation in {"建议签署", "有条件签署", "暂不建议直接签署"}
    assert report.dimension_scores["financial_exposure_risk"] >= 0.5
    assert report.dimension_scores["dispute_resolution_risk"] >= 0.5
    assert report.dimension_summaries["financial_exposure_risk"]
    assert report.top_risks
    assert report.top_risks[0].title
    assert report.top_risks[0].recommendation
    assert report.manual_review_items


def test_assess_risk_can_read_states_from_node_observations() -> None:
    evidence = RiskEvidence(
        contract_id="nda-102",
        node_states={},
        triggered_findings=["termination_clause_missing:missing"],
        node_observations=[
            NodeObservation(
                node_name="termination_clause_completeness",
                observed_state="missing",
                observation_confidence=0.93,
                supporting_evidence_ids=["ev-1"],
            )
        ],
        supporting_findings_by_node={
            "termination_clause_completeness": ["终止条款缺失"]
        },
        supporting_evidence_by_node={
            "termination_clause_completeness": ["No express termination clause found."]
        },
    )

    report = assess_risk(evidence)

    assert report.dimension_scores["legal_enforceability_risk"] > 0
    assert report.top_risks
    assert report.top_risks[0].reason == "终止条款缺失"


def test_assess_risk_builds_report_issue_inputs() -> None:
    evidence = RiskEvidence(
        contract_id="nda-103",
        node_states={
            "termination_clause_completeness": "missing",
            "governing_law_clarity": "missing",
        },
        triggered_findings=[
            "termination_clause_missing:missing",
            "governing_law_missing:missing",
        ],
        supporting_findings_by_node={
            "termination_clause_completeness": ["终止条款缺失"],
            "governing_law_clarity": ["适用法律缺失"],
        },
        supporting_evidence_by_node={
            "termination_clause_completeness": ["No express termination clause found."],
            "governing_law_clarity": ["No governing law clause found."],
        },
    )

    report = assess_risk(evidence)

    assert report.report_issue_inputs
    assert report.report_issue_inputs[0].issue_id
    assert report.report_issue_inputs[0].title
    assert report.report_issue_inputs[0].clause_excerpt
