from contract_risk_analysis.domain.review_schema import EvidenceItem
from contract_risk_analysis.evidence.aggregate import aggregate_node_observations
from contract_risk_analysis.evidence.conflict import detect_conflicts


def test_detect_conflicts_marks_multi_state_node() -> None:
    evidence_items = [
        EvidenceItem(
            evidence_id="ev-1",
            contract_id="nda-ev-002",
            node_name="liability_cap_strength",
            mapped_state="moderate",
            node_layer="legal_semantics",
            node_priority="P0",
            source_text="Liability cap equals total fees.",
            clause_type="liability_cap",
            raw_status="acceptable",
            confidence=0.61,
        ),
        EvidenceItem(
            evidence_id="ev-2",
            contract_id="nda-ev-002",
            node_name="liability_cap_strength",
            mapped_state="severe",
            node_layer="legal_semantics",
            node_priority="P0",
            source_text="Indirect damages are fully recoverable.",
            clause_type="liability_cap",
            raw_status="unfavorable",
            confidence=0.84,
        ),
    ]

    conflicts = detect_conflicts(evidence_items)

    assert conflicts["liability_cap_strength"] is True


def test_aggregate_node_observations_keeps_supporting_evidence_ids() -> None:
    evidence_items = [
        EvidenceItem(
            evidence_id="ev-1",
            contract_id="nda-ev-003",
            node_name="termination_clause_completeness",
            mapped_state="missing",
            node_layer="legal_semantics",
            node_priority="P0",
            source_text="No express termination clause found.",
            clause_type="termination",
            raw_status="missing",
            confidence=0.93,
            finding_label="终止条款缺失",
        )
    ]

    observations = aggregate_node_observations(
        node_states={"termination_clause_completeness": "missing"},
        evidence_items=evidence_items,
    )

    assert len(observations) == 1
    assert observations[0].node_name == "termination_clause_completeness"
    assert observations[0].supporting_evidence_ids == ["ev-1"]


def test_aggregate_node_observations_resolves_conflict_to_ambiguous() -> None:
    evidence_items = [
        EvidenceItem(
            evidence_id="ev-1",
            contract_id="nda-ev-004",
            node_name="termination_clause_existence",
            mapped_state="present",
            node_layer="contract_fact",
            node_priority="P0",
            source_text="Either party may terminate with notice.",
            clause_type="termination",
            raw_status="present",
            confidence=0.9,
        ),
        EvidenceItem(
            evidence_id="ev-2",
            contract_id="nda-ev-004",
            node_name="termination_clause_existence",
            mapped_state="missing",
            node_layer="contract_fact",
            node_priority="P0",
            source_text="No termination clause found.",
            clause_type="termination",
            raw_status="missing",
            confidence=0.91,
        ),
    ]

    observations = aggregate_node_observations(
        node_states={"termination_clause_existence": "missing"},
        evidence_items=evidence_items,
    )

    assert observations[0].conflict_flag is True
    assert observations[0].observed_state == "ambiguous"


def test_aggregate_node_observations_does_not_let_unknown_override_stronger_state() -> None:
    evidence_items = [
        EvidenceItem(
            evidence_id="ev-1",
            contract_id="nda-ev-005",
            node_name="termination_clause_existence",
            mapped_state="unknown",
            node_layer="contract_fact",
            node_priority="P0",
            source_text="Document fragment is incomplete.",
            clause_type="termination",
            raw_status="unknown",
            confidence=0.4,
        ),
        EvidenceItem(
            evidence_id="ev-2",
            contract_id="nda-ev-005",
            node_name="termination_clause_existence",
            mapped_state="present",
            node_layer="contract_fact",
            node_priority="P0",
            source_text="Either party may terminate with notice.",
            clause_type="termination",
            raw_status="present",
            confidence=0.9,
        ),
    ]

    observations = aggregate_node_observations(
        node_states={"termination_clause_existence": "present"},
        evidence_items=evidence_items,
    )

    assert observations[0].observed_state == "present"
