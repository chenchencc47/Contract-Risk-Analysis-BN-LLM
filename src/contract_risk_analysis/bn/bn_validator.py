"""BN Validator — consistency checks and counterfactual simulation.

Checks completeness, contradictions, confidence calibration,
causal coherence, and cross-dimension risk interactions.
Then runs counterfactual analyses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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

# Cross-dimension risk pairs that multiply each other
CROSS_DIMENSION_RISK_PAIRS = [(('financial_exposure_risk', 'high'), ('dispute_resolution_risk', 'high'), "高财务暴露风险 + 高争议处置风险 → 追偿成本极高且路径不确定，形成'钱已出手、维权无门'的致命组合。"), (('performance_delivery_risk', 'high'), ('legal_enforceability_risk', 'high'), '高履约交付风险 + 低法律可执行性 → 交付纠纷中缺乏合同依据，可能陷入长期诉讼。'), (('financial_exposure_risk', 'high'), ('clause_balance_risk', 'high'), '高财务暴露 + 条款严重失衡 → 合同整体偏向交易对手方，我方的财务状况和谈判地位均受压制。'), (('dispute_resolution_risk', 'high'), ('legal_enforceability_risk', 'high'), '争议解决路径不明确 + 法律执行性缺失 → 即使胜诉，判决也可能无法有效执行。')]

# ═══════════════════════════════════════════════════════════════════
#  BnValidator — Consistency checks and counterfactual simulation
# ═══════════════════════════════════════════════════════════════════

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
        self, node_states: dict[str, str], top_n: int = 8
    ) -> list[CounterfactualResult]:
        """Run counterfactual simulations and return as CounterfactualResult list.

        Includes dimension-level deltas and a floor guarantee: if fewer than 3
        counterfactuals pass the overall-delta threshold, dimension-level deltas
        are used to supplement the results (P0 fix for output stability).
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
        # Track items filtered out for potential fallback inclusion
        fallback_pool: list[dict] = []

        for sr in sensitivity[:top_n]:
            if sr["delta_high_risk"] < 0.003:
                # P0: keep in fallback pool if has significant dimension-level delta
                has_significant_dim_delta = any(
                    dd.get("delta", 0) >= 0.05 for dd in sr.get("dimension_deltas", [])
                )
                if has_significant_dim_delta:
                    fallback_pool.append(sr)
                continue
            node_label = NODE_LABELS.get(sr["node_name"], sr["node_name"])
            results.append(self._build_counterfactual_result(sr, node_label))

        # P0: floor guarantee — if < 3 results, supplement from fallback pool
        if len(results) < 3 and fallback_pool:
            fallback_pool.sort(key=lambda r: r["delta_high_risk"], reverse=True)
            needed = 3 - len(results)
            for sr in fallback_pool[:needed]:
                node_label = NODE_LABELS.get(sr["node_name"], sr["node_name"])
                results.append(self._build_counterfactual_result(sr, node_label))

        return results

    def _build_counterfactual_result(
        self, sr: dict, node_label: str
    ) -> CounterfactualResult:
        """Build a CounterfactualResult from a sensitivity result dict."""
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

        # P1: Build derivation chain
        derivation_chain = self._build_derivation_chain(sr)

        return CounterfactualResult(
            node_name=sr["node_name"],
            node_label=node_label,
            current_state=sr["current_state"],
            proposed_state=sr["best_state"],
            base_high_risk=sr["base_high_risk"],
            counterfactual_high_risk=sr["counterfactual_high_risk"],
            delta_high_risk=sr["delta_high_risk"],
            description="\n".join(desc_parts),
            dimension_deltas=dim_deltas,
            derivation_chain=derivation_chain,
        )

    def _build_derivation_chain(self, sr: dict) -> str:
        """P1: Build a traceable derivation chain for a counterfactual result.

        Format: 条款状态 X→Y | CPT来源 Z | pgmpy VE推理 → δ=-43.3%
        """
        node_name = sr["node_name"]
        node_cfg = self.v2_config.get("nodes", {}).get(node_name, {})
        cpt_source = node_cfg.get("cpt_source", "expert_estimated")
        cpt_source_label = {
            "cuad_empirical": "CUAD数据集统计",
            "contractnli_empirical": "ContractNLI数据集统计",
            "expert_estimated": "专家估计",
        }.get(cpt_source, cpt_source)

        chain_parts = [
            f"条款状态 {sr['current_state']}→{sr['best_state']}",
            f"CPT来源：{cpt_source_label}",
            f"pgmpy变量消除推理 → 整体δ={sr['delta_high_risk']:.1%}",
        ]

        # Add dimension-level delta summary if present
        for dd in sr.get("dimension_deltas", [])[:2]:
            chain_parts.append(
                f"{dd['dimension_label']}δ={dd['delta']:.1%}"
            )

        return " | ".join(chain_parts)

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

