"""BN Consistency Validator — the BN's new role in the v2 pipeline.

Instead of acting as the central risk scoring engine, the BN now serves as
a consistency validator and counterfactual simulator. It checks LLM₁'s
free-form analysis for completeness, contradictions, and cross-dimension
risk interactions, then runs counterfactual simulations.

Architecture:
    FreeReviewOutput → BnMappingService → node_states + gap annotations
                                        → BnValidator → validation annotations
                                                      → counterfactuals
                                                      → build_consistency_report
"""

from __future__ import annotations

from dataclasses import dataclass, field

from contract_risk_analysis.bn.network_schema import load_network_config
from contract_risk_analysis.bn.pgmpy_adapter import (
    DIMENSION_LABELS,
    DIMENSION_NODES,
    build_model,
    load_v2_config,
    run_inference,
    run_sensitivity_analysis,
)
from contract_risk_analysis.domain.free_review_schema import (
    ConsistencyReport,
    CounterfactualResult,
    DimensionDelta,
    FreeReviewOutput,
    RiskSegment,
    ValidationAnnotation,
)
from contract_risk_analysis.evidence.normalize import load_mapping_config

# ── Node metadata (shared with inference.py) ─────────────────────

NODE_LABELS: dict[str, str] = {
    "termination_clause_completeness": "终止条款完整性",
    "termination_right_balance": "解除权平衡性",
    "liability_cap_strength": "责任上限强度",
    "damages_exposure": "损害赔偿暴露",
    "acceptance_process_clarity": "验收流程明确性",
    "governing_law_clarity": "适用法律明确性",
    "dispute_resolution_clarity": "争议解决明确性",
    "jurisdiction_fairness": "管辖安排公平性",
}

DIMENSION_LABELS: dict[str, str] = {
    "legal_enforceability_risk": "法律可执行性风险",
    "financial_exposure_risk": "财务暴露风险",
    "performance_delivery_risk": "履约交付风险",
    "dispute_resolution_risk": "争议处置风险",
    "clause_balance_risk": "条款失衡风险",
}

# Clause type → plausible BN node name hints (for heuristic matching)
# Expanded with CUAD-derived nodes and sales-contract-specific nodes
CLAUSE_TYPE_HINTS: dict[str, list[str]] = {
    # Original nodes
    "termination": ["termination_clause_completeness", "termination_right_balance"],
    "liability_cap": ["liability_cap_strength", "damages_exposure"],
    "confidentiality": [],
    "governing_law": ["governing_law_clarity", "cuad_governing_law"],
    "dispute_resolution": ["dispute_resolution_clarity", "jurisdiction_fairness"],
    "acceptance": ["acceptance_process_clarity"],
    # CUAD-derived contract_fact nodes
    "termination_for_convenience": ["cuad_termination_for_convenience"],
    "notice_period": ["cuad_notice_period_to_terminate"],
    "third_party_beneficiary": ["cuad_third_party_beneficiary"],
    "audit_rights": ["cuad_audit_rights"],
    "uncapped_liability": ["cuad_uncapped_liability"],
    "cap_on_liability": ["cuad_cap_on_liability"],
    "liquidated_damages": ["cuad_liquidated_damages"],
    "insurance": ["cuad_insurance"],
    "warranty": ["cuad_warranty_duration"],
    "warranty_duration": ["cuad_warranty_duration"],
    "revenue_sharing": ["cuad_revenue_profit_sharing"],
    "minimum_commitment": ["cuad_minimum_commitment"],
    "volume_restriction": ["cuad_volume_restriction"],
    "post_termination": ["cuad_post_termination_services"],
    "source_code_escrow": ["cuad_source_code_escrow"],
    "covenant_not_to_sue": ["cuad_covenant_not_to_sue"],
    "no_solicit": ["cuad_no_solicit_of_customers", "cuad_no_solicit_of_employees"],
    "non_disparagement": ["cuad_non_disparagement"],
    "anti_assignment": ["cuad_anti_assignment"],
    "change_of_control": ["cuad_change_of_control"],
    "non_compete": ["cuad_non_compete"],
    "exclusivity": ["cuad_exclusivity"],
    "most_favored_nation": ["cuad_most_favored_nation"],
    "ip_ownership": ["cuad_ip_ownership_assignment", "cuad_joint_ip_ownership"],
    "license": ["cuad_license_grant", "cuad_non_transferable_license"],
    "rofr": ["cuad_rofr_rofo_rofn"],
    "price_restrictions": ["cuad_price_restrictions"],
    # Sales-contract-specific nodes (expert-defined, not CUAD)
    "payment": ["payment_structure"],
    "delivery": ["delivery_terms"],
    "risk_transfer": ["risk_transfer_point"],
    "dispute_venue": ["dispute_venue_fairness"],
    "force_majeure": ["force_majeure_completeness"],
    "indemnification": [],
    "warranty_scope": ["warranty_scope"],
    # Generic fallbacks
    "default": [],
    "quality": ["cuad_warranty_duration", "warranty_scope"],
    # Chinese aliases (LLM may output Chinese clause_types despite English prompt)
    "付款": ["payment_structure"],
    "付款方式": ["payment_structure"],
    "付款条款": ["payment_structure"],
    "验收": ["acceptance_process_clarity"],
    "验收条款": ["acceptance_process_clarity"],
    "验收流程": ["acceptance_process_clarity"],
    "交货": ["delivery_terms"],
    "交付": ["delivery_terms"],
    "运输": ["delivery_terms", "risk_transfer_point"],
    "风险转移": ["risk_transfer_point"],
    "管辖": ["dispute_resolution_clarity", "jurisdiction_fairness", "dispute_venue_fairness"],
    "争议": ["dispute_resolution_clarity", "dispute_venue_fairness"],
    "争议解决": ["dispute_resolution_clarity", "jurisdiction_fairness", "dispute_venue_fairness"],
    "终止": ["termination_clause_completeness"],
    "解除": ["termination_right_balance"],
    "解除权": ["termination_right_balance"],
    "违约": ["cuad_liquidated_damages", "liability_cap_strength"],
    "违约金": ["cuad_liquidated_damages"],
    "违约责任": ["cuad_liquidated_damages", "liability_cap_strength"],
    "质量": ["cuad_warranty_duration", "warranty_scope"],
    "质保": ["cuad_warranty_duration", "warranty_scope"],
    "不可抗力": ["force_majeure_completeness"],
    "责任上限": ["liability_cap_strength"],
    "责任限制": ["liability_cap_strength"],
    "赔偿": ["liability_cap_strength", "damages_exposure"],
    "适用法律": ["governing_law_clarity", "cuad_governing_law"],
    "法律适用": ["governing_law_clarity"],
    "保密": [],
    "知识产权": ["cuad_ip_ownership_assignment", "cuad_joint_ip_ownership"],
    "保险": ["cuad_insurance"],
    "色差": ["cuad_warranty_duration", "warranty_scope"],
    "颜色": ["cuad_warranty_duration"],
    "通知": [],
    "送达": [],
}

# Severity to state mapping for heuristic node state inference
SEVERITY_TO_STATE_HINT: dict[str, str] = {
    "critical": "unfavorable",
    "high": "unfavorable",
    "medium": "moderate",
    "low": "acceptable",
    "positive": "acceptable",
}

# Cross-dimension risk pairs that multiply each other
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
        """
        node_states: dict[str, str] = {}
        gap_annotations: list[ValidationAnnotation] = []

        for segment in segments:
            node_name, mapped_state = self._resolve_node_state(segment)

            if node_name is None:
                # This risk type has no corresponding BN node — record as gap
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
                continue

            # Take the highest-severity state per node
            current = node_states.get(node_name)
            if current is None or self._state_is_worse(mapped_state, current):
                node_states[node_name] = mapped_state

        return node_states, gap_annotations

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

        Tries multiple lookup strategies:
        1. Exact match on clause_type (English or Chinese)
        2. Normalized match (lowercase, stripped)
        3. Substring match against known keys
        """
        ct = segment.clause_type

        # Strategy 1: exact match
        hints = CLAUSE_TYPE_HINTS.get(ct)
        if hints is None:
            # Strategy 2: normalized (lowercase, stripped)
            normalized = ct.lower().strip()
            hints = CLAUSE_TYPE_HINTS.get(normalized)

        if hints is None:
            # Strategy 3: substring match — check if any known key is in the clause_type
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


# ═══════════════════════════════════════════════════════════════════
#  BnValidator — Consistency checks and counterfactual simulation
# ═══════════════════════════════════════════════════════════════════


@dataclass
class BnValidator:
    """Runs BN as a validator, not a risk scorer.

    Checks: missing dimensions, contradictions, cross-dimension risks,
    and runs counterfactual simulations.
    """

    v2_config: dict | None = None

    def __post_init__(self):
        if self.v2_config is None:
            self.v2_config = load_v2_config()

    def validate(
        self,
        free_output: FreeReviewOutput,
        node_states: dict[str, str],
    ) -> list[ValidationAnnotation]:
        """Run all consistency checks and return annotations."""
        annotations: list[ValidationAnnotation] = []

        annotations.extend(self._check_missing_dimensions(free_output, node_states))
        annotations.extend(self._check_contradictions(free_output, node_states))
        annotations.extend(self._check_cross_dimension_risks(node_states))
        annotations.extend(self._check_confidence_calibration(free_output))

        return annotations

    def _check_confidence_calibration(
        self, free_output: FreeReviewOutput
    ) -> list[ValidationAnnotation]:
        """Flag LLM findings with implausible confidence levels.

        Uses ContractNLI-derived difficulty weights as a baseline:
        - Highly confident (conf > 0.9) on complex legal questions → flag
        - Very low confidence (conf < 0.3) on simple presence checks → flag
        """
        annotations: list[ValidationAnnotation] = []
        try:
            from contract_risk_analysis.evaluation.cpt_calibrator import (
                compute_confidence_calibration_params,
            )
            calib = compute_confidence_calibration_params()
            difficulty_weights = calib.get("per_label_difficulty", {})
        except Exception:
            return annotations

        # Simple clause types (presence checks) should have high confidence
        simple_types = {"termination", "liability_cap", "governing_law", "insurance",
                       "audit_rights", "non_compete", "exclusivity", "anti_assignment"}
        # Complex clause types (semantic interpretation) naturally have lower confidence
        complex_types = {"confidentiality", "indemnification", "ip_ownership",
                        "most_favored_nation", "revenue_sharing"}

        for seg in free_output.risk_segments:
            ct = seg.clause_type
            if ct in simple_types and seg.confidence < 0.5:
                annotations.append(ValidationAnnotation(
                    annotation_type="confidence_mismatch",
                    severity="info",
                    bn_node=None,
                    llm_clause_type=ct,
                    message=(
                        f"LLM对「{seg.risk_title}」的置信度偏低（{seg.confidence:.0%}），"
                        f"但此类条款（{ct}）属于基础存在性检查，通常应有较高置信度。"
                        f"建议人工复核该发现是否为误报。"
                    ),
                    detail={"confidence": seg.confidence, "expected_min": 0.5},
                ))
            if ct in complex_types and seg.confidence > 0.95:
                annotations.append(ValidationAnnotation(
                    annotation_type="confidence_mismatch",
                    severity="info",
                    bn_node=None,
                    llm_clause_type=ct,
                    message=(
                        f"LLM对「{seg.risk_title}」的置信度异常偏高（{seg.confidence:.0%}），"
                        f"但此类条款（{ct}）涉及复杂法律语义判断。"
                        f"建议人工复核确认。"
                    ),
                    detail={"confidence": seg.confidence, "expected_max": 0.9},
                ))

        return annotations

    def _check_missing_dimensions(
        self, free_output: FreeReviewOutput, node_states: dict[str, str]
    ) -> list[ValidationAnnotation]:
        """Check if the BN graph expects dimensions the LLM didn't cover."""
        annotations: list[ValidationAnnotation] = []

        # BN evidence nodes that the LLM hasn't covered at all
        evidence_layer_nodes = {
            name for name, cfg in self.v2_config["nodes"].items()
            if cfg.get("layer") in ("contract_fact", "legal_semantics")
        }
        covered_nodes = set(node_states.keys())
        uncovered = evidence_layer_nodes - covered_nodes

        for node in uncovered:
            node_label = NODE_LABELS.get(node, node)
            annotations.append(
                ValidationAnnotation(
                    annotation_type="missing_dimension",
                    severity="warning",
                    bn_node=node,
                    llm_clause_type=None,
                    message=(
                        f"贝叶斯网络包含节点「{node_label}」，"
                        f"但LLM审查未覆盖此维度。BN将使用先验概率进行推理，"
                        f"建议人工补充对该维度的审查。"
                    ),
                    detail={"node_layer": self.v2_config["nodes"][node].get("layer")},
                )
            )

        return annotations

    def _check_contradictions(
        self, free_output: FreeReviewOutput, node_states: dict[str, str]
    ) -> list[ValidationAnnotation]:
        """Detect when BN posteriors conflict with LLM severity assessment."""
        annotations: list[ValidationAnnotation] = []

        if not node_states:
            return annotations

        # Run BN inference with current evidence
        try:
            inference_result = run_inference(
                evidence=node_states, config=self.v2_config
            )
        except Exception:
            return annotations

        # Build severity lookup from LLM segments
        llm_severity_map: dict[str, str] = {
            seg.clause_type: seg.severity for seg in free_output.risk_segments
        }

        # Map clause types to BN dimensions
        clause_to_dim_map: dict[str, str] = {
            "termination": "legal_enforceability_risk",
            "liability_cap": "financial_exposure_risk",
            "payment": "financial_exposure_risk",
            "delivery": "performance_delivery_risk",
            "acceptance": "performance_delivery_risk",
            "dispute_resolution": "dispute_resolution_risk",
            "governing_law": "legal_enforceability_risk",
        }

        # Convert LLM severity to approximate risk level
        severity_to_risk: dict[str, str] = {
            "critical": "high",
            "high": "high",
            "medium": "medium",
            "low": "low",
            "positive": "low",
        }

        for clause_type, dim_name in clause_to_dim_map.items():
            llm_sev = llm_severity_map.get(clause_type)
            if llm_sev is None:
                continue
            llm_risk = severity_to_risk.get(llm_sev, "medium")

            bn_dist = inference_result.dimension_distributions.get(dim_name, {})
            if not bn_dist:
                continue
            bn_best = max(bn_dist, key=bn_dist.get)

            # Flag contradictions: BN says low but LLM says high/critical
            if bn_best == "low" and llm_risk == "high":
                annotations.append(
                    ValidationAnnotation(
                        annotation_type="contradiction",
                        severity="warning",
                        bn_node=dim_name,
                        llm_clause_type=clause_type,
                        message=(
                            f"贝叶斯网络推断「{DIMENSION_LABELS.get(dim_name, dim_name)}」"
                            f"为低风险（P(low)={bn_dist.get('low', 0):.0%}），"
                            f"但LLM审查评级为「{llm_sev}」。"
                            f"BN的先验概率可能低估了此类风险的实际严重程度，"
                            f"建议以LLM判断为准并人工复核。"
                        ),
                        detail={
                            "bn_posterior": bn_dist,
                            "llm_severity": llm_sev,
                        },
                    )
                )

            # BN says high/medium but LLM didn't flag it as a risk
            if bn_best in ("high", "medium") and llm_sev in ("low", "positive"):
                annotations.append(
                    ValidationAnnotation(
                        annotation_type="contradiction",
                        severity="info",
                        bn_node=dim_name,
                        llm_clause_type=clause_type,
                        message=(
                            f"贝叶斯网络推断「{DIMENSION_LABELS.get(dim_name, dim_name)}」"
                            f"存在较高风险（P({bn_best})={bn_dist.get(bn_best, 0):.0%}），"
                            f"但LLM审查评级为「{llm_sev}」。"
                            f"BN基于历史合同的先验概率提示此处可能被低估，建议复核。"
                        ),
                        detail={
                            "bn_posterior": bn_dist,
                            "llm_severity": llm_sev,
                        },
                    )
                )

        return annotations

    def _check_cross_dimension_risks(
        self, node_states: dict[str, str]
    ) -> list[ValidationAnnotation]:
        """Detect multiplicative risk combinations that the Noisy-OR model misses.

        Certain combinations of unfavorable states across dimensions create
        outsized compound risk that simple weighted sums don't capture.
        """
        annotations: list[ValidationAnnotation] = []

        if not node_states:
            return annotations

        # Run inference to get dimension posteriors
        try:
            inference_result = run_inference(
                evidence=node_states, config=self.v2_config
            )
        except Exception:
            return annotations

        dim_dists = inference_result.dimension_distributions

        for (dim_a, state_a), (dim_b, state_b), message in CROSS_DIMENSION_RISK_PAIRS:
            dist_a = dim_dists.get(dim_a, {})
            dist_b = dim_dists.get(dim_b, {})
            high_a = dist_a.get(state_a, 0)
            high_b = dist_b.get(state_b, 0)

            # Both dimensions show probability > 0.35 for the bad state
            if high_a >= 0.35 and high_b >= 0.35:
                dim_label_a = DIMENSION_LABELS.get(dim_a, dim_a)
                dim_label_b = DIMENSION_LABELS.get(dim_b, dim_b)
                annotations.append(
                    ValidationAnnotation(
                        annotation_type="cross_dimension_risk",
                        severity="warning",
                        bn_node=f"{dim_a}+{dim_b}",
                        llm_clause_type=None,
                        message=(
                            f"⚠️ 乘数效应预警：{dim_label_a}（P({state_a})={high_a:.0%}）"
                            f" + {dim_label_b}（P({state_b})={high_b:.0%}）"
                            f" → {message}"
                        ),
                        detail={
                            "dim_a": dim_a,
                            "dim_b": dim_b,
                            "prob_a": high_a,
                            "prob_b": high_b,
                            "message": message,
                        },
                    )
                )

        return annotations

    def run_counterfactual_analysis(
        self, node_states: dict[str, str], top_n: int = 5
    ) -> list[CounterfactualResult]:
        """Run counterfactual simulations and return as CounterfactualResult list.

        Now includes dimension-level deltas: for each evidence node flip,
        we also compute the probability change on its associated dimension(s).
        """
        try:
            model = build_model(self.v2_config)
            sensitivity = run_sensitivity_analysis(
                model=model,
                evidence=node_states,
                config=self.v2_config,
                dimension_targets=DIMENSION_NODES,
            )
        except Exception:
            return []

        results: list[CounterfactualResult] = []
        for sr in sensitivity[:top_n]:
            if sr["delta_high_risk"] < 0.01:
                continue
            node_label = NODE_LABELS.get(sr["node_name"], sr["node_name"])

            # Build dimension-level deltas
            dim_deltas: list[DimensionDelta] = [
                DimensionDelta(
                    dimension_key=dd["dimension_key"],
                    dimension_label=dd["dimension_label"],
                    base_high=dd["base_high"],
                    counterfactual_high=dd["counterfactual_high"],
                    delta=dd["delta"],
                )
                for dd in sr.get("dimension_deltas", [])
            ]

            # Enrich description with dimension-level info
            desc_parts = [
                f"若将「{node_label}」从当前状态改善为目标状态，"
                f"合同整体高风险概率预计从 {sr['base_high_risk']:.1%} "
                f"降至 {sr['counterfactual_high_risk']:.1%}，"
                f"降幅 {sr['delta_high_risk']:.1%}。"
            ]
            for dd in dim_deltas:
                desc_parts.append(
                    f"→ {dd.dimension_label}：P(high)从 {dd.base_high:.1%} 降至 {dd.counterfactual_high:.1%}，降幅 {dd.delta:.1%}。"
                )

            results.append(
                CounterfactualResult(
                    node_name=sr["node_name"],
                    node_label=node_label,
                    current_state=sr["current_state"],
                    proposed_state=sr["best_state"],
                    base_high_risk=sr["base_high_risk"],
                    counterfactual_high_risk=sr["counterfactual_high_risk"],
                    delta_high_risk=sr["delta_high_risk"],
                    description="\n".join(desc_parts),
                    dimension_deltas=dim_deltas,
                )
            )

        return results

    def generate_bn_summary(
        self,
        node_states: dict[str, str],
        annotations: list[ValidationAnnotation],
        counterfactuals: list[CounterfactualResult],
    ) -> str:
        """Generate a concise BN perspective summary in Chinese."""
        parts: list[str] = []

        # Count annotation types
        type_counts: dict[str, int] = {}
        for a in annotations:
            type_counts[a.annotation_type] = type_counts.get(a.annotation_type, 0) + 1

        mapped_count = len(node_states)
        gap_count = type_counts.get("gap_detected", 0)
        contradiction_count = type_counts.get("contradiction", 0)
        cross_count = type_counts.get("cross_dimension_risk", 0)
        missing_count = type_counts.get("missing_dimension", 0)

        parts.append(
            f"贝叶斯网络对LLM审查结果进行了一致性校验。"
            f"LLM共识别{len(node_states) + gap_count}个风险维度，"
            f"其中{mapped_count}个维度可与BN知识图谱匹配，"
        )
        if gap_count > 0:
            parts.append(
                f"{gap_count}个维度（如付款结构等）不在BN覆盖范围内，"
                f"其评估完全依赖LLM判断。"
            )
        else:
            parts.append("全部维度均在BN覆盖范围内。")

        if contradiction_count > 0:
            parts.append(
                f"发现{contradiction_count}处BN与LLM的矛盾，"
                f"BN的先验概率基于历史合同数据，可能与当前合同的特殊情况"
                f"存在偏差，建议以LLM判断为主。"
            )
        else:
            parts.append("BN与LLM在风险判断上总体一致。")

        if cross_count > 0:
            parts.append(
                f"⚠️ BN识别出{cross_count}组乘数效应风险组合。"
                f"这些组合的风险远大于各维度风险的简单加总，"
                f"请重点关注。"
            )

        if missing_count > 0:
            parts.append(
                f"BN提示{missing_count}个维度的审查可能不够充分，"
                f"建议人工补充。"
            )

        if counterfactuals:
            parts.append(
                f"BN执行了{len(counterfactuals)}项反事实模拟。"
                f"排名第一的改善措施为"
                f"「{counterfactuals[0].node_label}」，"
                f"预计可降低高风险概率{counterfactuals[0].delta_high_risk:.1%}。"
            )

        return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
#  Top-level orchestrator
# ═══════════════════════════════════════════════════════════════════


def build_consistency_report(
    free_output: FreeReviewOutput,
) -> ConsistencyReport:
    """Orchestrate BN validation and return a ConsistencyReport.

    This is the main entry point for the v2 pipeline's BN layer.
    It maps LLM findings to BN nodes, runs all consistency checks,
    performs counterfactual simulation, and produces a structured report.
    """
    # Step 1: Map LLM findings to BN nodes
    mapping_service = BnMappingService()
    node_states, mapping_annotations = mapping_service.map_risk_segments(
        free_output.risk_segments
    )

    # Step 2: Run BN validation checks
    validator = BnValidator()
    validation_annotations = validator.validate(free_output, node_states)

    # Step 3: Counterfactual simulation
    counterfactuals = validator.run_counterfactual_analysis(node_states)

    # Step 4: Generate BN summary
    all_annotations = mapping_annotations + validation_annotations
    bn_summary = validator.generate_bn_summary(
        node_states, all_annotations, counterfactuals
    )

    # Step 5: Run full BN inference for posterior reference
    try:
        inference_result = run_inference(evidence=node_states)
        bn_posteriors = {
            name: posterior.state_distribution
            for name, posterior in inference_result.posteriors.items()
        }
    except Exception:
        bn_posteriors = {}

    return ConsistencyReport(
        contract_id=free_output.contract_id,
        annotations=all_annotations,
        counterfactuals=counterfactuals,
        bn_posteriors=bn_posteriors,
        bn_summary=bn_summary,
    )
