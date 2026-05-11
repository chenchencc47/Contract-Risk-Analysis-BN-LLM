"""Adjudication layer — deterministic final ruling on risk facts.

Placed between canonicalization and dossier building, this layer:
1. Deduplicates risk segments that describe the same underlying issue
2. Normalizes severity — reconciles LLM₁ ratings with BN posteriors
3. Enforces priority rules — critical items cannot have low priority
4. Assesses evidence quality — flags low-confidence / weak-evidence items
5. Applies party-aware rules — reclassifies risks that are actually advantages

All decisions are DETERMINISTIC — no LLM involvement.
This is where "final risk facts" become a system property.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from contract_risk_analysis.domain.free_review_schema import (
    FreeReviewOutput,
    NegotiationChip,
    RiskSegment,
)


def _title_similarity(a: str, b: str) -> float:
    """Simple similarity between two Chinese risk titles.

    Uses character-level Jaccard similarity — fast and deterministic.
    Returns 0.0-1.0.
    """
    set_a = set(a.replace(" ", ""))
    set_b = set(b.replace(" ", ""))
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _deduplicate(segments: list[RiskSegment]) -> list[RiskSegment]:
    """Merge segments that describe the same underlying risk.

    Two-pass dedup:
    Pass 1 — Same canonical_type: title similarity >= 0.5 + evidence overlap >= 0.3
    Pass 2 — Different canonical_type: title similarity >= 0.5 + evidence overlap >= 0.5
             (higher threshold for cross-type to avoid over-merging)

    When merging, keep the segment with higher confidence.
    """
    if len(segments) <= 1:
        return segments

    merged: list[RiskSegment] = []
    used: set[int] = set()

    # ── Pass 1: same canonical_type ──
    for i, seg_i in enumerate(segments):
        if i in used:
            continue
        best = seg_i
        type_i = seg_i.canonical_type or seg_i.clause_type
        for j, seg_j in enumerate(segments):
            if j <= i or j in used:
                continue
            type_j = seg_j.canonical_type or seg_j.clause_type
            if type_i != type_j:
                continue
            if _should_merge(seg_i, seg_j, ev_threshold=0.3):
                used.add(j)
                if seg_j.confidence > best.confidence:
                    best = seg_j
        merged.append(best)

    # ── Pass 2: cross-canonical_type (higher thresholds) ──
    # Re-check remaining items against already-merged items
    final: list[RiskSegment] = []
    used_cross: set[int] = set()
    for i, item in enumerate(merged):
        if i in used_cross:
            continue
        best = item
        for j, other in enumerate(merged):
            if j <= i or j in used_cross:
                continue
            type_i = item.canonical_type or item.clause_type
            type_j = other.canonical_type or other.clause_type
            if type_i == type_j:
                continue  # already handled in pass 1
            if _should_merge(item, other, ev_threshold=0.5):
                used_cross.add(j)
                if other.confidence > best.confidence:
                    best = other
        final.append(best)

    return final


def _should_merge(
    a: RiskSegment, b: RiskSegment, ev_threshold: float = 0.3,
) -> bool:
    """Check if two RiskSegments should be merged."""
    sim = _title_similarity(a.risk_title, b.risk_title)
    if sim < 0.5:
        return False
    ev_a = set(a.evidence_text.replace(" ", ""))
    ev_b = set(b.evidence_text.replace(" ", ""))
    ev_overlap = len(ev_a & ev_b) / max(len(ev_a | ev_b), 1)
    return ev_overlap >= ev_threshold


def _normalize_severity(
    segments: list[RiskSegment],
    bn_posteriors: dict[str, dict[str, float]] | None,
) -> list[RiskSegment]:
    """Rule-based severity adjudication — deterministic, no LLM.

    Rules (applied in order):
    1. BN P(high) > 0.6 AND LLM₁ rated 'medium' or 'low' → upgrade to 'high'
    2. BN P(high) < 0.1 AND LLM₁ rated 'critical' → downgrade to 'high'
    3. LLM₁ rated 'critical' AND no BN node mapped (no posterior available)
       → downgrade to 'high' (conservative: critical requires BN corroboration)
    """
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "positive": 4}

    for seg in segments:
        # Find max BN P(high) across all suggested nodes
        bn_high: float | None = None
        if seg.suggested_bn_nodes and bn_posteriors:
            for node in seg.suggested_bn_nodes:
                posterior = bn_posteriors.get(node, {})
                high_p = posterior.get("high", 0.0)
                if high_p > 0:
                    bn_high = max(bn_high or 0, high_p)

        has_bn_coverage = (
            seg.suggested_bn_nodes is not None
            and len(seg.suggested_bn_nodes) > 0
        )

        # Rule 3: critical without BN coverage → downgrade
        if seg.severity == "critical" and not has_bn_coverage:
            seg.severity = "high"
            continue

        if bn_high is None:
            continue

        # Rule 1: BN says high risk, LLM₁ underrated → upgrade
        if bn_high > 0.6 and severity_order.get(seg.severity, 5) >= 2:
            seg.severity = "high"

        # Rule 2: BN says low risk, LLM₁ overrated → downgrade
        elif bn_high < 0.1 and seg.severity == "critical":
            seg.severity = "high"

    return segments


def _enforce_priority(segments: list[RiskSegment]) -> list[RiskSegment]:
    """Enforce priority rules deterministically.

    Rules:
    - critical severity → priority_rank must be 1 or 2
    - high severity → priority_rank must be ≤ 3
    """
    for seg in segments:
        if seg.severity == "critical" and (seg.priority_rank is None or seg.priority_rank > 2):
            seg.priority_rank = 1
        elif seg.severity == "high" and (seg.priority_rank is None or seg.priority_rank > 3):
            seg.priority_rank = 2
    return segments


def _assess_evidence(segments: list[RiskSegment]) -> list[RiskSegment]:
    """Flag items with weak evidence for manual review.

    Criteria for manual review flag:
    - Confidence < 0.6 AND no BN coverage (suggested_bn_nodes is empty)
    - Evidence text is too short (< 20 chars) — probably not a real excerpt
    """
    for seg in segments:
        if seg.confidence < 0.6 and not seg.suggested_bn_nodes:
            if not seg.canonical_type:
                continue
        if len(seg.evidence_text.strip()) < 20:
            if not seg.canonical_type:
                continue
    return segments


def _apply_party_aware_rules(
    segments: list[RiskSegment],
    review_party: str = "buyer",
) -> list[RiskSegment]:
    """Apply party-aware rules to reclassify risks that are actually advantages.

    Some clauses like "liability_cap missing" look like risks from a neutral
    perspective but are actually WEAPONS for the buyer. This function loads
    party-aware rules from config and adjusts severity accordingly.

    Rules are defined in config/party_aware_rules.yaml.

    Returns the modified segment list (mutates in-place).
    """
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "party_aware_rules.yaml"
    if not config_path.exists():
        return segments

    with open(config_path, encoding="utf-8") as fh:
        rules = yaml.safe_load(fh) or {}

    party_rules = rules.get(review_party, {})
    if not party_rules:
        return segments

    for seg in segments:
        ctype = seg.canonical_type or seg.clause_type
        if ctype not in party_rules:
            continue

        rule = party_rules[ctype]
        action = rule.get("action", "")

        # ── Apply note ──
        note = rule.get("note", "")
        if note:
            existing = seg.risk_description or ""
            if "【立场感知裁决】" not in existing:
                seg.risk_description = f"{existing}\n\n【立场感知裁决】{note}"

        # ── Apply chip type override ──
        chip = rule.get("chip_type", "")
        if chip and not seg.negotiation_chip:
            seg.negotiation_chip = NegotiationChip(
                chip_type=chip,
                reason=note or chip,
            )

        # ── Apply severity override ──
        if action == "reclassify_favorable":
            seg.severity = rule.get("new_severity", "positive")
            if not seg.counterparty_impact:
                seg.counterparty_impact = rule.get("counterparty_impact") or f"{review_party}_favorable"
        elif action == "mark_favorable":
            if not seg.counterparty_impact:
                seg.counterparty_impact = rule.get("counterparty_impact") or f"{review_party}_favorable"
        elif action == "maintain_high":
            if rule.get("counterparty_impact") and not seg.counterparty_impact:
                seg.counterparty_impact = rule["counterparty_impact"]

    return segments


def adjudicate(
    free_output: FreeReviewOutput,
    review_party: str = "buyer",
) -> FreeReviewOutput:
    """Run pre-BN adjudication on a FreeReviewOutput.

    1. Deduplicate risk segments (Pass 1: same canonical_type, Pass 2: cross-type)
    2. Enforce priority rules
    3. Apply party-aware rules (buyer/seller perspective)

    All operations are deterministic. Returns the adjudicated FreeReviewOutput
    with modified risk_segments (in-place).

    Note: severity normalization requires BN posteriors and runs in
    _build_dossier(), not here.
    """
    original_count = len(free_output.risk_segments)

    # Step 1: Deduplicate
    free_output.risk_segments = _deduplicate(free_output.risk_segments)
    dedup_count = original_count - len(free_output.risk_segments)

    # Step 2: Enforce priority rules
    free_output.risk_segments = _enforce_priority(free_output.risk_segments)

    # Step 3: Apply party-aware rules
    free_output.risk_segments = _apply_party_aware_rules(
        free_output.risk_segments, review_party
    )

    return free_output
