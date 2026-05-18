"""BN Mapping Service — maps LLM₁ risk segments to BN node states. — the BN's new role in the v2 pipeline.

Instead of acting as the central risk scoring engine, the BN now serves as
a consistency validator and counterfactual simulator. It checks LLM₁'s
free-form analysis for completeness, contradictions, and cross-dimension
risk interactions, then runs counterfactual simulations.

Architecture:
    FreeReviewOutput → BnMappingService → node_states + gap annotations
                                        → BnValidator → validation annotations
                                                      → counterfactuals
                                                      → build_consistency_report

This module handles clause-type-to-BN-node mapping and heuristic state inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contract_risk_analysis.bn.network_schema import load_network_config
from contract_risk_analysis.bn.pgmpy_adapter import (
    DIMENSION_NODES,
    build_model,
    load_v2_config,
    run_inference,
    run_sensitivity_analysis,
)
from contract_risk_analysis.constants import DIMENSION_LABELS, NODE_LABELS
from contract_risk_analysis.domain.free_review_schema import (
    ConsistencyReport,
    CounterfactualResult,
    DimensionDelta,
    FreeReviewOutput,
    RiskSegment,
    ValidationAnnotation,
)
from contract_risk_analysis.evidence.normalize import load_mapping_config

def _load_clause_type_hints() -> dict[str, list[str]]:
    """Load clause-type-to-BN-node hints from YAML config (config/clause_type_mapping.yaml).

    Community contributors can edit the YAML file to add new clause type mappings
    without touching Python code. Falls back to empty dict if config is unavailable.
    """
    import yaml as _yaml
    config_path = Path(__file__).resolve().parents[3] / "config" / "clause_type_mapping.yaml"
    try:
        with open(config_path, encoding="utf-8") as fh:
            raw = _yaml.safe_load(fh) or {}
    except Exception:
        return {}
    return {key: entry.get("nodes", []) for key, entry in raw.items()}


# Clause type → plausible BN node name hints (for heuristic matching)
# Source: config/clause_type_mapping.yaml — community-extensible, no code change needed.
CLAUSE_TYPE_HINTS: dict[str, list[str]] = _load_clause_type_hints()

# Severity to state mapping for heuristic node state inference
SEVERITY_TO_STATE_HINT: dict[str, str] = {
    "critical": "unfavorable",
    "high": "unfavorable",
    "medium": "moderate",
    "low": "acceptable",
    "positive": "acceptable",
}

# Cross-dimension risk pairs that multiply each other.
# NOTE: These are universal fallback descriptions. The actual dimension PAIRS
# queried for BN joint probability analysis are configured in
# config/contract_type_parameters.yaml → bn_dimension_pairs.
# The descriptions here serve as LLM context hints and are NOT the source
# of truth for which pairs get computed.
CROSS_DIMENSION_RISK_PAIRS: list[tuple[tuple[str, str], tuple[str, str], str]] = [
    (
        ("financial_exposure_risk", "high"),
        ("dispute_resolution_risk", "high"),
        "高财务暴露风险 + 高争议处置风险 → 追偿成本极高且路径不确定，"
        "形成'钱已出手、维权无门'的致命组合。",
    ),
    (
        ("performance_delivery_risk", "high"),
        ("legal_enforceability_risk", "high"),
        "高履约交付风险 + 低法律可执行性 → 交付纠纷中缺乏合同依据，"
        "可能陷入长期诉讼。",
    ),
    (
        ("financial_exposure_risk", "high"),
        ("clause_balance_risk", "high"),
        "高财务暴露 + 条款严重失衡 → 合同整体偏向交易对手方，"
        "我方的财务状况和谈判地位均受压制。",
    ),
    (
        ("dispute_resolution_risk", "high"),
        ("legal_enforceability_risk", "high"),
        "争议解决路径不明确 + 法律执行性缺失 → 即使胜诉，"
        "判决也可能无法有效执行。",
    ),
]


# ═══════════════════════════════════════════════════════════════════
#  BnMappingService — Maps FreeReviewOutput to BN node states
# ═══════════════════════════════════════════════════════════════════


@dataclass
class BnMappingService:
    """Best-effort mapping from LLM risk segments to BN node states.

    Unlike the v1 evidence mapping pipeline which DROPS unmappable findings,
    this service:
    1. Maps what it can (using evidence_mapping.json + heuristics)
    2. Records unmappable items as gap_detected ValidationAnnotations
    3. Handles multiple findings mapping to the same node
    """

    mapping_config: dict | None = None
    v2_config: dict | None = None

    def __post_init__(self):
        global CLAUSE_TYPE_HINTS
        CLAUSE_TYPE_HINTS = _load_clause_type_hints()
        if self.mapping_config is None:
            self.mapping_config = load_mapping_config()
        if self.v2_config is None:
            from contract_risk_analysis.bn.pgmpy_adapter import load_v2_config
            self.v2_config = load_v2_config()

    def map_risk_segments(
        self, segments: list[RiskSegment]
    ) -> tuple[dict[str, str], list[ValidationAnnotation]]:
        """Map segments to BN node states.

        Returns (node_states: dict[node_name → state],
                 gap_annotations: unmappable segments as ValidationAnnotations).

        P0: When a legal_semantics node receives evidence, its parent
        contract_fact nodes also get inferred evidence so counterfactual
        sensitivity analysis can trace the full causal chain.
        """
        node_states: dict[str, str] = {}
        gap_annotations: list[ValidationAnnotation] = []

        for segment in segments:
            node_name, mapped_state = self._resolve_node_state(segment)

            if node_name is None:
                gap_annotations.append(
                    ValidationAnnotation(
                        annotation_type="gap_detected",
                        severity="info",
                        message=(
                            f"LLM识别到的风险类型「{segment.clause_type}」"
                            f"（{segment.risk_title}）无对应的贝叶斯网络节点。"
                            f"该风险的评估完全基于AI判断，未经BN校验。"
                        ),
                        llm_clause_type=segment.clause_type,
                        bn_node=None,
                        detail={
                            "risk_title": segment.risk_title,
                            "severity": segment.severity,
                            "confidence": segment.confidence,
                        },
                    )
                )
                # P6: Auto-record unmapped clause_types for node discovery
                try:
                    from contract_risk_analysis.bn.node_discovery import record_gap
                    record_gap(
                        clause_type=segment.clause_type,
                        risk_title=segment.risk_title,
                        severity=segment.severity,
                        confidence=segment.confidence,
                    )
                except Exception:
                    pass  # non-critical, don't block the pipeline
                continue

            # Take the highest-severity state per node
            current = node_states.get(node_name)
            if current is None or self._state_is_worse(mapped_state, current):
                node_states[node_name] = mapped_state

            # P0: Propagate evidence to parent contract_fact nodes
            # This ensures counterfactual sensitivity analysis has the full
            # causal chain (e.g., liability_cap → liability_cap_strength)
            self._propagate_to_parents(node_name, mapped_state, node_states)

        return node_states, gap_annotations

    def _propagate_to_parents(
        self, node_name: str, state: str, node_states: dict[str, str]
    ) -> None:
        """Infer and set evidence on parent contract_fact nodes.

        When a legal_semantics node has evidence, its parent contract_fact
        nodes should also reflect the same underlying contract reality.
        For example, if liability_cap_strength=severe, then liability_cap
        should be set to missing (the contract lacks a liability cap).
        """
        node_cfg = self.v2_config.get("nodes", {}).get(node_name, {})
        parents = node_cfg.get("parents", [])
        for parent_name in parents:
            parent_cfg = self.v2_config.get("nodes", {}).get(parent_name, {})
            parent_layer = parent_cfg.get("layer", "")
            if parent_layer != "contract_fact":
                continue
            # Don't overwrite existing evidence
            if parent_name in node_states:
                continue
            # Infer parent state from child state
            parent_states = parent_cfg.get("states", [])
            inferred = self._infer_parent_state(state, parent_states)
            if inferred:
                node_states[parent_name] = inferred

    @staticmethod
    def _infer_parent_state(
        child_state: str, parent_states: list[str]
    ) -> str | None:
        """Infer a contract_fact parent state from its legal_semantics child.

        Mapping logic:
          child "severe"/"missing"/"unfavorable" → parent "missing"
          child "acceptable"/"present"/"balanced" → parent "present"
          child "moderate"/"neutral" → parent "present" (conservative)
        """
        bad_child = {"severe", "missing", "unfavorable", "counterparty_favorable", "high"}
        good_child = {"acceptable", "present", "balanced", "favorable", "entailment", "broad", "low"}
        if child_state in bad_child:
            for s in ("missing", "unfavorable", "absent"):
                if s in parent_states:
                    return s
            return parent_states[0] if parent_states else None
        if child_state in good_child:
            for s in ("present", "favorable", "balanced"):
                if s in parent_states:
                    return s
            return parent_states[-1] if parent_states else None
        return None

    def _resolve_node_state(
        self, segment: RiskSegment
    ) -> tuple[str | None, str | None]:
        """Determine which BN node and state a risk segment maps to.

        Three-tier matching:
        1. Explicit suggested_bn_nodes from LLM
        2. finding_key_rules — reverse lookup from clause_type + severity
        3. Heuristic: clause_type hints + severity → state
        """
        # Tier 1: suggested_bn_nodes
        if segment.suggested_bn_nodes:
            for node_name in segment.suggested_bn_nodes:
                mapped = self._match_node_state(node_name, segment)
                if mapped:
                    return self._validate_state(node_name, mapped, segment)

        # Tier 2: use finding_key_rules via reverse lookup
        finding_key = self._infer_finding_key_from_segment(segment)
        if finding_key:
            rule = self.mapping_config.get("finding_key_rules", {}).get(finding_key)
            if rule:
                return self._validate_state(rule["node_name"], rule["mapped_state"], segment)

        # Tier 3: heuristic by clause_type
        node_name, mapped_state = self._heuristic_match(segment)
        return self._validate_state(node_name, mapped_state, segment)

    def _validate_state(
        self, node_name: str | None, mapped_state: str | None, segment: RiskSegment
    ) -> tuple[str | None, str | None]:
        """Ensure the mapped state is valid for the target BN node."""
        if node_name is None or mapped_state is None:
            return node_name, mapped_state
        try:
            allowed = set(self.v2_config["nodes"].get(node_name, {}).get("states", []))
        except Exception:
            return node_name, mapped_state
        if not allowed or mapped_state in allowed:
            return node_name, mapped_state
        # State is invalid — use _match_node_state as fallback (it validates)
        corrected = self._match_node_state(node_name, segment)
        return (node_name, corrected) if corrected else (node_name, None)

    def _match_node_state(
        self, node_name: str, segment: RiskSegment
    ) -> str | None:
        """Map a known node_name to a state based on the segment's severity.

        Uses the BN node's actual allowed states to ensure validity.
        Falls back to the closest semantically valid state.
        """
        sev = segment.severity
        # Get allowed states from BN config
        node_states = set()
        try:
            node_states = set(self.v2_config["nodes"].get(node_name, {}).get("states", []))
        except Exception:
            pass
        if not node_states:
            return None

        # Priority order from worst to best state
        if sev in ("critical", "high"):
            for s in ("severe", "missing", "unfavorable", "counterparty_favorable",
                      "high", "narrow"):
                if s in node_states:
                    return s
            return next(iter(node_states))

        if sev == "medium":
            for s in ("moderate", "unfavorable", "neutral", "missing"):
                if s in node_states:
                    return s
            return next(iter(node_states))

        if sev in ("low", "positive"):
            for s in ("acceptable", "balanced", "present", "favorable",
                      "entailment", "broad", "low"):
                if s in node_states:
                    return s
            return next(iter(node_states))

        return next(iter(node_states))

    def _infer_finding_key_from_segment(
        self, segment: RiskSegment
    ) -> str | None:
        """Try to infer a finding_key from clause_type + severity."""
        finding_key_rules = self.mapping_config.get("finding_key_rules", {})
        hints = CLAUSE_TYPE_HINTS.get(segment.clause_type, [])

        for hint_node in hints:
            for key, rule in finding_key_rules.items():
                if rule["node_name"] == hint_node:
                    # Match severity to key semantics
                    if segment.severity in ("high", "critical"):
                        if "missing" in key or "unbalanced" in key or "one_sided" in key or "high" in key:
                            return key
                    elif segment.severity == "medium":
                        if "moderate" in key or "present" in key:
                            return key
                    elif segment.severity in ("low", "positive"):
                        if "balanced" in key or "acceptable" in key or "present" in key:
                            return key
        return None

    def _heuristic_match(
        self, segment: RiskSegment
    ) -> tuple[str | None, str | None]:
        """Fallback: match by clause_type hints + severity.

        Priority order:
        1. canonical_type (deterministic, set by canonicalization layer)
        2. Exact match on clause_type (English or Chinese)
        3. Normalized match (lowercase, stripped)
        4. Substring match against known keys
        """
        # Strategy 0: canonical_type first (Phase A P2 — stable handoff)
        ct = getattr(segment, "canonical_type", None) or segment.clause_type

        # Strategy 1: exact match
        hints = CLAUSE_TYPE_HINTS.get(ct)
        if hints is None:
            # Strategy 2: normalized (lowercase, stripped)
            normalized = ct.lower().strip()
            hints = CLAUSE_TYPE_HINTS.get(normalized)

        if hints is None:
            # Strategy 3: fall back to original clause_type if canonical didn't match
            if ct != segment.clause_type:
                hints = CLAUSE_TYPE_HINTS.get(segment.clause_type)
                if hints is None:
                    hints = CLAUSE_TYPE_HINTS.get(segment.clause_type.lower().strip())

        if hints is None:
            # Strategy 4: substring match — check if any known key is in the lookup key
            for key in CLAUSE_TYPE_HINTS:
                if key in ct or ct in key:
                    hints = CLAUSE_TYPE_HINTS[key]
                    break

        if not hints:
            return None, None

        node_name = hints[0]
        state = SEVERITY_TO_STATE_HINT.get(segment.severity, "unfavorable")
        return node_name, state

    def _node_supports_state(self, node_name: str, state: str) -> bool:
        """Check if a BN node has a given state."""
        # Load from v2 config
        try:
            v2_config = load_v2_config()
            node_states = v2_config["nodes"].get(node_name, {}).get("states", [])
            return state in node_states
        except Exception:
            return True  # Be permissive if config can't be loaded

    def _state_is_worse(self, new_state: str, current_state: str) -> bool:
        """Return True if new_state represents a worse condition."""
        severity_order = [
            "severe", "missing", "unfavorable", "counterparty_favorable",
            "high", "medium", "moderate", "contradiction",
            "neutral", "acceptable", "balanced", "low",
            "present", "entailment",
        ]
        try:
            return severity_order.index(new_state) < severity_order.index(current_state)
        except ValueError:
            return False

