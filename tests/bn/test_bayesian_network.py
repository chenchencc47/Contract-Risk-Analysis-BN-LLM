from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.domain.review_schema import RiskEvidence


def test_assess_risk_uses_bayesian_network_probabilities() -> None:
    evidence = RiskEvidence(
        contract_id="nda-004",
        node_states={
            "termination_clause": "missing",
            "liability_cap": "acceptable",
            "confidentiality_nli": "entailment",
        },
        triggered_findings=["termination:missing"],
    )

    report = assess_risk(evidence)

    assert report.contract_id == "nda-004"
    assert report.overall_risk == "medium"
    assert report.requires_manual_review is False
    assert report.category_scores == {
        "termination_risk": 0.85,
        "liability_risk": 0.1,
        "confidentiality_risk": 0.15,
        "overall_legal_risk": 0.55,
    }
    assert report.summary_reasons == ["termination clause is missing"]


def test_assess_risk_includes_governing_law_and_dispute_resolution_in_final_decision() -> None:
    evidence = RiskEvidence(
        contract_id="nda-202",
        node_states={
            "termination_clause_completeness": "present",
            "liability_cap_strength": "moderate",
            "governing_law_clarity": "missing",
            "dispute_resolution_clarity": "missing",
            "jurisdiction_fairness": "counterparty_favorable",
        },
        triggered_findings=[
            "governing_law_missing:missing",
            "dispute_resolution_missing:missing",
            "jurisdiction_one_sided:unfavorable",
        ],
        supporting_findings_by_node={
            "governing_law_clarity": ["适用法律缺失"],
            "dispute_resolution_clarity": ["争议解决缺失"],
            "jurisdiction_fairness": ["管辖地单方有利"],
        },
        supporting_evidence_by_node={
            "governing_law_clarity": ["No governing law clause found."],
            "dispute_resolution_clarity": ["No dispute resolution clause found."],
            "jurisdiction_fairness": ["All disputes shall be resolved in supplier local court."],
        },
    )

    report = assess_risk(evidence)

    assert report.dimension_scores["dispute_resolution_risk"] >= 0.5
    assert report.overall_risk in {"medium", "high"}
    assert any("争议" in item for item in report.manual_review_items)
    assert any(risk.dimension == "dispute_resolution_risk" for risk in report.top_risks)
