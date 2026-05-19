from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult
from contract_risk_analysis.pipeline.build_evidence import build_evidence


def test_build_evidence_maps_findings_to_expected_node_states() -> None:
    review_result = ReviewResult(
        contract_id="nda-001",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No termination clause found.",
                confidence=0.91,
            ),
            ReviewFinding(
                clause_type="liability_cap",
                status="unfavorable",
                evidence_text="Unlimited liability applies.",
                confidence=0.88,
            ),
            ReviewFinding(
                clause_type="confidentiality",
                status="contradiction",
                evidence_text="The clause allows disclosure without notice.",
                confidence=0.79,
            ),
        ],
    )

    evidence = build_evidence(review_result)

    assert evidence.contract_id == "nda-001"
    assert evidence.node_states == {
        "termination_clause": "missing",
        "liability_cap": "unfavorable",
        "confidentiality_nli": "contradiction",
    }
    assert evidence.triggered_findings == [
        "termination:missing",
        "liability_cap:unfavorable",
        "confidentiality:contradiction",
    ]


def test_build_evidence_uses_risk_factor_and_hypothesis_mapping_rules() -> None:
    review_result = ReviewResult(
        contract_id="nda-002",
        findings=[
            ReviewFinding(
                clause_type="other",
                status="missing",
                evidence_text="No liability cap found.",
                confidence=0.9,
                risk_factor="liability_risk",
            ),
            ReviewFinding(
                clause_type="other",
                status="entailment",
                evidence_text="The agreement keeps confidentiality obligations.",
                confidence=0.82,
                hypothesis="Agreement contains a confidentiality restriction.",
            ),
            ReviewFinding(
                clause_type="governing_law",
                status="missing",
                evidence_text="No governing law clause found.",
                confidence=0.76,
            ),
            ReviewFinding(
                clause_type="dispute_resolution",
                status="missing",
                evidence_text="No dispute resolution clause found.",
                confidence=0.73,
            ),
        ],
    )

    evidence = build_evidence(review_result)

    assert evidence.node_states == {
        "liability_cap": "unfavorable",
        "confidentiality_nli": "entailment",
        "governing_law_clause": "missing",
        "dispute_resolution_clause": "missing",
    }
    assert evidence.triggered_findings == [
        "liability_risk:missing",
        "Agreement contains a confidentiality restriction.:entailment",
        "governing_law:missing",
        "dispute_resolution:missing",
    ]


def test_build_evidence_uses_finding_key_mapping_and_keeps_supporting_evidence() -> None:
    review_result = ReviewResult(
        contract_id="nda-003",
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
                clause_type="liability_cap",
                status="unfavorable",
                evidence_text="Supplier liability is uncapped.",
                confidence=0.88,
                finding_key="liability_cap_missing",
                finding_label="责任上限缺失",
            ),
        ],
    )

    evidence = build_evidence(review_result)

    assert evidence.node_states["termination_clause_completeness"] == "missing"
    assert evidence.node_states["liability_cap_strength"] == "missing"
    assert evidence.supporting_findings_by_node["termination_clause_completeness"] == ["终止条款缺失"]
    assert evidence.supporting_evidence_by_node["termination_clause_completeness"] == ["No express termination clause found."]


def test_build_evidence_keeps_more_severe_state_when_same_node_is_hit_twice() -> None:
    review_result = ReviewResult(
        contract_id="nda-004",
        findings=[
            ReviewFinding(
                clause_type="liability_cap",
                status="acceptable",
                evidence_text="Liability cap equals total fees.",
                confidence=0.61,
                finding_key="liability_cap_present",
                finding_label="责任上限已约定",
            ),
            ReviewFinding(
                clause_type="liability_cap",
                status="unfavorable",
                evidence_text="Indirect damages are fully recoverable.",
                confidence=0.84,
                finding_key="indirect_damage_exposure_high",
                finding_label="间接损失暴露过高",
            ),
        ],
    )

    evidence = build_evidence(review_result)

    assert evidence.node_states["liability_cap_strength"] == "severe"
    assert evidence.supporting_findings_by_node["liability_cap_strength"] == [
        "责任上限已约定",
        "间接损失暴露过高",
    ]


def test_build_evidence_exposes_evidence_items_and_node_observations() -> None:
    review_result = ReviewResult(
        contract_id="nda-005",
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

    evidence = build_evidence(review_result)

    assert len(evidence.evidence_items) == 1
    assert evidence.evidence_items[0].contract_id == "nda-005"
    assert evidence.evidence_items[0].node_name == "termination_clause_completeness"
    assert evidence.evidence_items[0].mapped_state == "missing"
    assert evidence.evidence_items[0].node_layer == "legal_semantics"
    assert evidence.evidence_items[0].node_priority == "P0"
    assert evidence.evidence_items[0].finding_label == "终止条款缺失"

    assert len(evidence.node_observations) == 1
    assert evidence.node_observations[0].node_name == "termination_clause_completeness"
    assert evidence.node_observations[0].observed_state == "missing"
    assert evidence.node_observations[0].supporting_evidence_ids == [
        evidence.evidence_items[0].evidence_id
    ]
