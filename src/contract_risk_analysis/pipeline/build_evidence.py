from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput
from contract_risk_analysis.domain.review_schema import ReviewResult, RiskEvidence
from contract_risk_analysis.evidence.aggregate import aggregate_node_observations
from contract_risk_analysis.evidence.normalize import (
    load_mapping_config,
    normalize_review_result,
    resolve_mapping,
    severity_rank,
    supporting_label,
    trigger_label,
)


def build_evidence(
    review_result: ReviewResult,
    allowed_priorities: set[str] | None = None,
) -> RiskEvidence:
    config = load_mapping_config()
    node_states: dict[str, str] = {}
    triggered_findings: list[str] = []
    evidence_items = normalize_review_result(
        review_result, allowed_priorities=allowed_priorities
    )
    supporting_findings_by_node: dict[str, list[str]] = {}
    supporting_evidence_by_node: dict[str, list[str]] = {}

    resolved_items_by_key = {
        (
            item.node_name,
            item.source_text,
            item.raw_status,
            item.finding_key,
        ): item
        for item in evidence_items
    }

    for finding in review_result.findings:
        resolved = resolve_mapping(finding, config)
        if resolved is None:
            continue
        node_name, mapped_state = resolved
        evidence_item = resolved_items_by_key.get(
            (
                node_name,
                finding.evidence_text,
                finding.status,
                finding.finding_key,
            )
        )
        if evidence_item is None:
            continue

        current_state = node_states.get(node_name)
        if current_state is None or severity_rank(
            node_name, mapped_state, config
        ) > severity_rank(node_name, current_state, config):
            node_states[node_name] = mapped_state

        supporting_findings_by_node.setdefault(node_name, []).append(
            supporting_label(finding)
        )
        supporting_evidence_by_node.setdefault(node_name, []).append(
            finding.evidence_text
        )
        triggered_findings.append(f"{trigger_label(finding)}:{finding.status}")

    # P2.4: Remove 'unknown' states so BN uses prior instead of forced evidence
    filtered_states = {
        node: state for node, state in node_states.items()
        if state != "unknown"
    }

    node_observations = aggregate_node_observations(filtered_states, evidence_items)

    return RiskEvidence(
        contract_id=review_result.contract_id,
        node_states=filtered_states,
        triggered_findings=triggered_findings,
        evidence_items=evidence_items,
        node_observations=node_observations,
        supporting_findings_by_node=supporting_findings_by_node,
        supporting_evidence_by_node=supporting_evidence_by_node,
    )


def build_evidence_from_free_output(
    free_output: FreeReviewOutput,
    allowed_priorities: set[str] | None = None,
) -> RiskEvidence:
    """Build RiskEvidence from FreeReviewOutput for backward compatibility.

    Converts v2 free-review output to legacy v1 format via the adapter
    in ai_review.py, then runs the normal build_evidence pipeline.
    Used by the v2 API endpoint to produce legacy-compatible structured data.
    """
    from contract_risk_analysis.review.ai_review import free_review_to_legacy_result

    legacy_result = free_review_to_legacy_result(free_output)
    return build_evidence(legacy_result, allowed_priorities=allowed_priorities)
