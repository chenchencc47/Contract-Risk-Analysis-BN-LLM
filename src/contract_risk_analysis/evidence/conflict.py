from contract_risk_analysis.domain.review_schema import EvidenceItem


def detect_conflicts(evidence_items: list[EvidenceItem]) -> dict[str, bool]:
    state_set_by_node: dict[str, set[str]] = {}
    for item in evidence_items:
        state_set_by_node.setdefault(item.node_name, set()).add(item.mapped_state)
    return {
        node_name: len(states) > 1 for node_name, states in state_set_by_node.items()
    }
