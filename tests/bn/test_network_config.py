import json
from pathlib import Path

from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.bn.network_schema import load_network_config
from contract_risk_analysis.domain.review_schema import RiskEvidence


def test_load_network_config_reads_external_json() -> None:
    config = load_network_config()

    assert config["nodes"]["termination_clause"]["states"] == ["missing", "present"]
    assert config["cpts"]["termination_risk"]["missing"] == 0.85
    assert config["cpts"]["overall_legal_risk"]["high|high|high"]["high"] == 0.95


def test_assess_risk_uses_externalized_network_config() -> None:
    evidence = RiskEvidence(
        contract_id="nda-005",
        node_states={
            "termination_clause": "missing",
            "liability_cap": "acceptable",
            "confidentiality_nli": "entailment",
        },
        triggered_findings=["termination:missing"],
    )

    report = assess_risk(evidence)

    assert report.overall_risk == "medium"
    assert report.category_scores["overall_legal_risk"] == 0.55
