import json
from functools import lru_cache
from pathlib import Path

from contract_risk_analysis.domain.review_schema import EvidenceItem, ReviewResult
from contract_risk_analysis.evidence.validate import assess_evidence_quality, resolve_effective_state
from contract_risk_analysis.pipeline.node_schema import (
    get_node_metadata,
    is_allowed_priority,
    is_allowed_state,
)


DEFAULT_MAPPING_PATH = Path(__file__).resolve().parents[3] / "config" / "evidence_mapping.json"


@lru_cache(maxsize=1)
def load_mapping_config() -> dict:
    return json.loads(DEFAULT_MAPPING_PATH.read_text(encoding="utf-8"))


def severity_rank(node_name: str, state: str, config: dict) -> int:
    states = config.get("state_priority_by_node", {}).get(node_name, [])
    try:
        return states.index(state)
    except ValueError:
        return -1


def resolve_mapping(finding, config: dict) -> tuple[str, str] | None:
    if finding.finding_key is not None:
        finding_key_rule = config.get("finding_key_rules", {}).get(finding.finding_key)
        if finding_key_rule is not None:
            return finding_key_rule["node_name"], finding_key_rule["mapped_state"]

    clause_rule = config["clause_type_rules"].get(finding.clause_type)
    if clause_rule is not None:
        mapped_state = clause_rule["state_by_status"].get(finding.status)
        if mapped_state is not None:
            return clause_rule["node_name"], mapped_state

    if finding.risk_factor is not None:
        factor_rule = config["risk_factor_rules"].get(finding.risk_factor)
        if factor_rule is not None:
            mapped_state = factor_rule["state_by_status"].get(finding.status)
            if mapped_state is not None:
                return factor_rule["node_name"], mapped_state

    if finding.hypothesis is not None:
        hypothesis_rule = config["hypothesis_rules"].get(finding.hypothesis)
        if hypothesis_rule is not None:
            mapped_state = hypothesis_rule["state_by_status"].get(finding.status)
            if mapped_state is not None:
                return hypothesis_rule["node_name"], mapped_state

    return None


def build_evidence_id(review_result: ReviewResult, index: int, node_name: str) -> str:
    return f"{review_result.contract_id}:{node_name}:{index}"


def build_evidence_item(
    review_result: ReviewResult,
    finding,
    node_name: str,
    mapped_state: str,
    index: int,
    adjusted_confidence: float | None = None,
) -> EvidenceItem:
    if not is_allowed_state(node_name, mapped_state):
        raise ValueError(
            f"State '{mapped_state}' is not allowed for node '{node_name}'."
        )
    node_metadata = get_node_metadata(node_name) or {}
    return EvidenceItem(
        evidence_id=build_evidence_id(review_result, index, node_name),
        contract_id=review_result.contract_id,
        node_name=node_name,
        mapped_state=mapped_state,
        node_layer=node_metadata.get("node_layer"),
        node_priority=node_metadata.get("priority"),
        source_text=finding.evidence_text,
        clause_type=finding.clause_type,
        raw_status=finding.status,
        confidence=adjusted_confidence if adjusted_confidence is not None else finding.confidence,
        finding_label=finding.finding_label,
        finding_key=finding.finding_key,
    )


def trigger_label(finding) -> str:
    if finding.finding_key is not None:
        return finding.finding_key
    if finding.risk_factor is not None:
        return finding.risk_factor
    if finding.hypothesis is not None:
        return finding.hypothesis
    return finding.clause_type


def supporting_label(finding) -> str:
    return (
        finding.finding_label
        or finding.finding_key
        or finding.risk_factor
        or finding.hypothesis
        or finding.clause_type
    )


def normalize_review_result(
    review_result: ReviewResult,
    allowed_priorities: set[str] | None = None,
) -> list[EvidenceItem]:
    config = load_mapping_config()
    evidence_items: list[EvidenceItem] = []
    quality_results: list[dict] = []

    for index, finding in enumerate(review_result.findings, start=1):
        resolved = resolve_mapping(finding, config)
        if resolved is None:
            if finding.status not in {"missing", "present", "acceptable", "unfavorable", "contradiction", "entailment", "neutral", "ambiguous", "unknown"}:
                raise ValueError(
                    f"Status '{finding.status}' is not allowed by the mapping/schema layer."
                )
            continue
        node_name, mapped_state = resolved
        if not is_allowed_priority(node_name, allowed_priorities):
            continue

        # P2.1+P2.2: Quality assessment with confidence adjustment
        eq = assess_evidence_quality(
            finding_key=finding.finding_key,
            clause_type=finding.clause_type,
            status=mapped_state,
            evidence_text=finding.evidence_text,
            raw_confidence=finding.confidence,
        )

        # P2.4: Resolve effective state — use 'unknown' for low-confidence findings
        effective_state = resolve_effective_state(mapped_state, eq)

        evidence_items.append(
            build_evidence_item(
                review_result, finding, node_name, effective_state, index,
                adjusted_confidence=eq.adjusted_confidence,
            )
        )
        if not eq.is_quality_ok:
            quality_results.append({
                "clause_type": finding.clause_type,
                "finding_key": finding.finding_key,
                "original_status": mapped_state,
                "effective_state": effective_state,
                "raw_confidence": eq.raw_confidence,
                "adjusted_confidence": eq.adjusted_confidence,
                "flags": eq.flags,
            })

    return evidence_items
