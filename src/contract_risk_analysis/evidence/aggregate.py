from contract_risk_analysis.domain.review_schema import EvidenceItem, NodeObservation
from contract_risk_analysis.evidence.conflict import detect_conflicts


def _resolve_observed_state(node_name: str, observed_state: str, states: set[str]) -> str:
    non_unknown_states = {state for state in states if state != "unknown"}
    if len(non_unknown_states) > 1:
        return "ambiguous"
    if observed_state == "unknown" and len(non_unknown_states) == 1:
        return next(iter(non_unknown_states))
    return observed_state


def aggregate_node_observations(
    node_states: dict[str, str],
    evidence_items: list[EvidenceItem],
) -> list[NodeObservation]:
    evidence_ids_by_node: dict[str, list[str]] = {}
    confidence_by_node: dict[str, float] = {}
    conflicts = detect_conflicts(evidence_items)
    states_by_node: dict[str, set[str]] = {}

    for item in evidence_items:
        evidence_ids_by_node.setdefault(item.node_name, []).append(item.evidence_id)
        confidence_by_node[item.node_name] = max(
            confidence_by_node.get(item.node_name, 0.0), item.confidence
        )
        states_by_node.setdefault(item.node_name, set()).add(item.mapped_state)

    observations: list[NodeObservation] = []
    for node_name, observed_state in node_states.items():
        resolved_state = _resolve_observed_state(
            node_name,
            observed_state,
            states_by_node.get(node_name, set()),
        )
        observations.append(
            NodeObservation(
                node_name=node_name,
                observed_state=resolved_state,
                observation_confidence=confidence_by_node.get(node_name, 0.0),
                supporting_evidence_ids=evidence_ids_by_node.get(node_name, []),
                conflict_flag=conflicts.get(node_name, False),
            )
        )
    return observations
