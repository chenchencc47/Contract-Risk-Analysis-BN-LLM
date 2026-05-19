from contract_risk_analysis.bn.network_schema import load_network_config
from contract_risk_analysis.domain.review_schema import (
    ReportIssueInput,
    RiskEvidence,
    RiskItem,
    RiskReport,
)

_HAS_PGMPY = False
try:
    from contract_risk_analysis.bn.pgmpy_adapter import (
        build_model,
        load_v2_config,
        run_inference,
        run_sensitivity_analysis,
    )
    _HAS_PGMPY = True
except ImportError:
    pass


STATE_BY_PROBABILITY = {
    True: "high",
    False: "low",
}

from contract_risk_analysis.constants import DIMENSION_LABELS, NODE_LABELS

NODE_RECOMMENDATIONS = {
    "termination_clause_completeness": "补充终止条件、通知周期和解除后责任。",
    "termination_right_balance": "校正单方解除权，确保双方触发条件与救济机制对等。",
    "liability_cap_strength": "明确责任上限、间接损失范围和免责边界。",
    "damages_exposure": "压缩违约金或扩大赔偿例外的适用范围，控制损失暴露。",
    "acceptance_process_clarity": "明确验收标准、验收周期和异议提出机制。",
    "governing_law_clarity": "补充适用法律条款，降低争议解释不确定性。",
    "dispute_resolution_clarity": "补充仲裁或诉讼条款，明确处理路径与地点。",
    "jurisdiction_fairness": "重新谈判管辖地与争议解决地点，避免单方有利安排。",
}

NODE_CLAUSE_TYPES = {
    "termination_clause_completeness": "termination",
    "termination_right_balance": "termination",
    "liability_cap_strength": "liability_cap",
    "damages_exposure": "liability_cap",
    "acceptance_process_clarity": "acceptance",
    "governing_law_clarity": "governing_law",
    "dispute_resolution_clarity": "dispute_resolution",
    "jurisdiction_fairness": "dispute_resolution",
}

NODE_LEGAL_TOPICS = {
    "termination_clause_completeness": "终止条款",
    "termination_right_balance": "解除权平衡",
    "liability_cap_strength": "责任限制",
    "damages_exposure": "损害赔偿",
    "acceptance_process_clarity": "验收机制",
    "governing_law_clarity": "适用法律",
    "dispute_resolution_clarity": "争议解决",
    "jurisdiction_fairness": "协议管辖",
}

HIGH_PRIORITY_RISK_SCORE_FLOOR = 0.17


def _effective_node_states(evidence: RiskEvidence) -> dict[str, str]:
    if evidence.node_states:
        return evidence.node_states
    return {
        observation.node_name: observation.observed_state
        for observation in evidence.node_observations
    }


def _probability_to_risk_state(probability: float) -> str:
    return STATE_BY_PROBABILITY[probability >= 0.5]


def _overall_risk_label(probabilities: dict[str, float]) -> str:
    if probabilities["high"] >= max(probabilities["medium"], probabilities["low"]):
        return "high"
    if probabilities["medium"] >= probabilities["low"]:
        return "medium"
    return "low"


def _legacy_assess_risk(evidence: RiskEvidence, config: dict) -> RiskReport:
    node_states = _effective_node_states(evidence)
    cpts = config["cpts"]

    termination_probability = cpts["termination_risk"][node_states.get("termination_clause", "present")]
    liability_probability = cpts["liability_risk"][node_states.get("liability_cap", "acceptable")]
    confidentiality_probability = cpts["confidentiality_risk"][node_states.get("confidentiality_nli", "neutral")]

    overall_distribution = cpts["overall_legal_risk"][
        "|".join(
            [
                _probability_to_risk_state(termination_probability),
                _probability_to_risk_state(liability_probability),
                _probability_to_risk_state(confidentiality_probability),
            ]
        )
    ]

    summary_reasons: list[str] = []
    if node_states.get("termination_clause") == "missing":
        summary_reasons.append("termination clause is missing")
    if node_states.get("liability_cap") == "unfavorable":
        summary_reasons.append("liability cap is unfavorable")
    if node_states.get("confidentiality_nli") == "contradiction":
        summary_reasons.append("confidentiality review produced contradiction")
    if node_states.get("governing_law_clause") == "missing":
        summary_reasons.append("governing law clause is missing")
    if node_states.get("dispute_resolution_clause") == "missing":
        summary_reasons.append("dispute resolution clause is missing")

    overall_risk = _overall_risk_label(overall_distribution)
    category_scores = {
        "termination_risk": termination_probability,
        "liability_risk": liability_probability,
        "confidentiality_risk": confidentiality_probability,
        "overall_legal_risk": overall_distribution[overall_risk],
    }
    requires_manual_review = overall_risk == "high"

    return RiskReport(
        contract_id=evidence.contract_id,
        overall_risk=overall_risk,
        category_scores=category_scores,
        requires_manual_review=requires_manual_review,
        summary_reasons=summary_reasons,
    )


def _state_probability(node_name: str, state: str, config: dict) -> float:
    for rule in config.get("dimension_risk_rules", {}).values():
        inputs = rule.get("inputs", {})
        if node_name in inputs:
            return float(inputs[node_name].get(state, 0.5))
    return 0.5


def _score_to_risk_level(score: float, thresholds: dict[str, float] | None = None) -> str:
    effective_thresholds = thresholds or {"high": 0.7, "medium": 0.4}
    if score >= effective_thresholds["high"]:
        return "high"
    if score >= effective_thresholds["medium"]:
        return "medium"
    return "low"


def _build_dimension_score(dimension_name: str, evidence: RiskEvidence, config: dict) -> float:
    node_states = _effective_node_states(evidence)
    rule = config["dimension_risk_rules"][dimension_name]
    score = 0.0
    for node_name, weight in rule["weights"].items():
        state = node_states.get(node_name)
        if state is None:
            continue
        score += _state_probability(node_name, state, config) * float(weight)
    return round(score, 4)


def _build_dimension_summaries(dimension_scores: dict[str, float], config: dict) -> dict[str, str]:
    summaries: dict[str, str] = {}
    for dimension_name, score in dimension_scores.items():
        risk_level = _score_to_risk_level(score)
        summaries[dimension_name] = config["dimension_risk_rules"][dimension_name]["summary_templates"][risk_level]
    return summaries


def _build_top_risks(evidence: RiskEvidence, config: dict) -> list[RiskItem]:
    node_states = _effective_node_states(evidence)
    items: list[tuple[float, RiskItem]] = []
    for node_name, state in node_states.items():
        if node_name not in NODE_LABELS:
            continue
        score = _state_probability(node_name, state, config)
        if score < 0.55:
            continue
        dimension_name = next(
            (
                candidate_name
                for candidate_name, rule in config["dimension_risk_rules"].items()
                if node_name in rule.get("inputs", {})
            ),
            "legal_enforceability_risk",
        )
        items.append(
            (
                score,
                RiskItem(
                    title=NODE_LABELS[node_name],
                    dimension=dimension_name,
                    risk_level=_score_to_risk_level(score),
                    reason=(evidence.supporting_findings_by_node.get(node_name) or [f"{NODE_LABELS[node_name]}存在风险信号"])[0],
                    evidence=evidence.supporting_evidence_by_node.get(node_name, []),
                    recommendation=NODE_RECOMMENDATIONS[node_name],
                    node_name=node_name,
                    clause_type=NODE_CLAUSE_TYPES.get(node_name),
                ),
            )
        )
    items.sort(key=lambda item: item[0], reverse=True)
    return [item for _score, item in items[:5]]


def _build_report_issue_inputs(
    top_risks: list[RiskItem], requires_manual_review: bool
) -> list[ReportIssueInput]:
    report_issue_inputs: list[ReportIssueInput] = []
    for index, risk in enumerate(top_risks, start=1):
        clause_excerpt = risk.evidence[0] if risk.evidence else ""
        report_issue_inputs.append(
            ReportIssueInput(
                issue_id=f"issue_{index:03d}",
                title=risk.title,
                risk_level=risk.risk_level,
                dimension=risk.dimension,
                clause_type=risk.clause_type,
                node_name=risk.node_name,
                problem_analysis_brief=risk.reason,
                clause_excerpt=clause_excerpt,
                evidence=risk.evidence,
                legal_topic=NODE_LEGAL_TOPICS.get(risk.node_name or ""),
                recommendation=risk.recommendation,
                revision_hint=risk.recommendation,
                manual_review_required=requires_manual_review,
            )
        )
    return report_issue_inputs


def _build_manual_review_items(top_risks: list[RiskItem], overall_risk: str) -> list[str]:
    high_risks = [risk for risk in top_risks if risk.risk_level == "high"]
    if overall_risk != "high" and len(high_risks) < 2:
        return []

    manual_items: list[str] = []
    for risk in high_risks:
        manual_items.append(f"请人工复核：{risk.title}——{risk.recommendation}")
    return manual_items


def _build_signing_recommendation(overall_risk: str) -> str:
    if overall_risk == "high":
        return "暂不建议直接签署"
    if overall_risk == "medium":
        return "有条件签署"
    return "建议签署"


def _assess_rich_risk(evidence: RiskEvidence, config: dict) -> RiskReport:
    dimension_scores = {
        dimension_name: _build_dimension_score(dimension_name, evidence, config)
        for dimension_name in config["dimension_risk_rules"]
    }
    overall_weighted_score = 0.0
    for dimension_name, weight in config["overall_contract_risk"]["weights"].items():
        overall_weighted_score += dimension_scores.get(dimension_name, 0.0) * float(weight)
    overall_weighted_score = round(overall_weighted_score, 4)

    top_risks = _build_top_risks(evidence, config)
    if any(risk.risk_level == "high" for risk in top_risks):
        overall_weighted_score = max(overall_weighted_score, HIGH_PRIORITY_RISK_SCORE_FLOOR)

    overall_risk = _score_to_risk_level(overall_weighted_score, config["overall_contract_risk"].get("thresholds"))
    if overall_risk == "low" and any(risk.risk_level == "high" for risk in top_risks):
        overall_risk = "medium"

    summary_reasons = [risk.reason for risk in top_risks[:3]] or ["当前未识别到高优先级风险原因。"]
    manual_review_items = _build_manual_review_items(top_risks, overall_risk)
    requires_manual_review = overall_risk == "high" or bool(manual_review_items)
    report_issue_inputs = _build_report_issue_inputs(top_risks, requires_manual_review)

    category_scores = {
        "overall_contract_risk": overall_weighted_score,
        **dimension_scores,
    }

    return RiskReport(
        contract_id=evidence.contract_id,
        overall_risk=overall_risk,
        category_scores=category_scores,
        requires_manual_review=requires_manual_review,
        summary_reasons=summary_reasons,
        signing_recommendation=_build_signing_recommendation(overall_risk),
        dimension_scores=dimension_scores,
        dimension_summaries=_build_dimension_summaries(dimension_scores, config),
        top_risks=top_risks,
        report_issue_inputs=report_issue_inputs,
        manual_review_items=manual_review_items,
    )


def _assess_risk_pgmpy(evidence: RiskEvidence) -> RiskReport:
    """Risk assessment using true Bayesian Network inference via pgmpy."""
    v2_config = load_v2_config()
    model = build_model(v2_config)
    node_states = _effective_node_states(evidence)

    # Run BN inference with observed evidence
    result = run_inference(model=model, evidence=node_states, config=v2_config)

    # Build dimension scores from posterior P(high) for each dimension
    dimension_scores: dict[str, float] = {}
    dimension_risk_labels = ["legal_enforceability_risk", "financial_exposure_risk",
                             "performance_delivery_risk", "dispute_resolution_risk",
                             "clause_balance_risk"]
    for dim in dimension_risk_labels:
        dist = result.dimension_distributions.get(dim, {})
        dimension_scores[dim] = round(dist.get("high", 0.0), 4)

    overall_high_prob = result.overall_risk_distribution.get("high", 0.0)
    thresholds = v2_config.get("thresholds", {"high": 0.7, "medium": 0.35})

    # Use overall high probability for risk level
    if overall_high_prob >= thresholds["high"]:
        overall_risk = "high"
    elif overall_high_prob >= thresholds["medium"]:
        overall_risk = "medium"
    else:
        overall_risk = "low"

    # Build top risks from sensitivity analysis
    sensitivity_results = run_sensitivity_analysis(
        model=model, evidence=node_states, config=v2_config
    )
    top_risks: list[RiskItem] = []
    for sr in sensitivity_results[:5]:
        node_name = sr["node_name"]
        severity = "high" if sr["delta_high_risk"] >= 0.15 else (
            "medium" if sr["delta_high_risk"] >= 0.05 else "low"
        )
        dimension = next(
            (dim for dim in dimension_risk_labels
             if node_name in v2_config["nodes"]
             and any(
                 [node_name, dim] in v2_config["edges"]
                 or [node_name] == v2_config["nodes"].get(dim, {}).get("parents", [])
             )),
            "legal_enforceability_risk",
        )
        node_label = NODE_LABELS.get(node_name, node_name)
        top_risks.append(RiskItem(
            title=node_label,
            dimension=dimension,
            risk_level=severity,
            reason=(
                f"将「{node_label}」从「{sr['current_state']}」改善为「{sr['best_state']}」"
                f"可使高风险概率降低 {sr['delta_high_risk']:.1%}（从 {sr['base_high_risk']:.1%} 降至 {sr['counterfactual_high_risk']:.1%}）"
            ),
            evidence=evidence.supporting_evidence_by_node.get(node_name, []),
            recommendation=NODE_RECOMMENDATIONS.get(node_name, "建议人工审查该条款。"),
            node_name=node_name,
            clause_type=NODE_CLAUSE_TYPES.get(node_name),
        ))

    # Build summary reasons from top 3 sensitivity results
    summary_reasons: list[str] = []
    for sr in sensitivity_results[:3]:
        node_label = NODE_LABELS.get(sr["node_name"], sr["node_name"])
        summary_reasons.append(
            f"{node_label}（{sr['current_state']}→{sr['best_state']}可降 {sr['delta_high_risk']:.1%} 高风险概率）"
        )
    if not summary_reasons:
        summary_reasons = ["当前未识别到高优先级风险驱动因素。"]

    requires_manual_review = overall_risk == "high" or any(
        dim_scores >= 0.7 for dim_scores in dimension_scores.values()
    )
    manual_review_items = _build_manual_review_items(top_risks, overall_risk)

    # Build dimension summaries
    dim_labels = v2_config.get("dimension_labels", DIMENSION_LABELS)
    dim_summaries: dict[str, str] = {}
    for dim in dimension_risk_labels:
        score = dimension_scores.get(dim, 0.0)
        level = _score_to_risk_level(score)
        label = dim_labels.get(dim, dim)
        templates = {
            "high": f"{label}较高，存在可改善的关键因素。",
            "medium": f"{label}处于中等水平，建议关注相关条款。",
            "low": f"{label}整体可控。",
        }
        dim_summaries[dim] = templates.get(level, templates["low"])

    report_issue_inputs = _build_report_issue_inputs(top_risks, requires_manual_review)

    return RiskReport(
        contract_id=evidence.contract_id,
        overall_risk=overall_risk,
        category_scores={"overall_contract_risk": overall_high_prob, **dimension_scores},
        requires_manual_review=requires_manual_review,
        summary_reasons=summary_reasons,
        signing_recommendation=_build_signing_recommendation(overall_risk),
        dimension_scores=dimension_scores,
        dimension_summaries=dim_summaries,
        top_risks=top_risks,
        report_issue_inputs=report_issue_inputs,
        manual_review_items=manual_review_items,
    )


def assess_risk(evidence: RiskEvidence, network_config: dict | None = None) -> RiskReport:
    config = load_network_config() if network_config is None else network_config
    node_states = _effective_node_states(evidence)

    if _HAS_PGMPY and network_config is None:
        try:
            return _assess_risk_pgmpy(evidence)
        except Exception:
            pass

    if "dimension_risk_rules" in config and any(node in node_states for node in NODE_LABELS):
        return _assess_rich_risk(evidence, config)
    return _legacy_assess_risk(evidence, config)


def run_inference_from_states(
    node_states: dict[str, str],
    contract_id: str = "unnamed",
) -> RiskReport:
    """Quick BN inference from raw node_states dict (no RiskEvidence wrapper).

    Utility for the v2 pipeline and the consistency validator when they
    already have a node_states dict and want a legacy RiskReport for
    backward-compatible structured output.
    """
    from contract_risk_analysis.domain.review_schema import RiskEvidence

    evidence = RiskEvidence(
        contract_id=contract_id,
        node_states=node_states,
        triggered_findings=[],
    )
    return assess_risk(evidence)
