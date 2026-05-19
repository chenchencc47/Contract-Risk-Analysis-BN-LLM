"""Miscellaneous endpoints: favicon, health, demo, party-role detection."""

from __future__ import annotations

import os
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from contract_risk_analysis.bn.config_validator import validate_v2_config
from contract_risk_analysis.review.ai_review import detect_party_roles

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@router.get("/api/health")
async def health() -> dict:
    vreport = validate_v2_config()
    return {
        "status": "ok",
        "pgmpy_available": True,
        "config_valid": vreport.is_valid,
        "config_errors": len(vreport.errors),
        "demo_mode": os.getenv("DEMO_MODE", "").lower() == "true",
    }


@router.get("/api/demo")
async def api_demo() -> dict:
    """Return a pre-computed demo review that matches the ReviewResponse shape
    so the frontend RiskReport component renders it identically to a live review.
    """

    return {
        "demo": True,
        "contract_id": "demo-买卖合同-001",
        "review_party": "buyer",
        "generation_mode": "v2_combined",
        "polished": {
            "executive_summary": (
                "本合同为瓷砖购销合同，经LLM自由审查+BN一致性校验，共识别15项风险，"
                "其中高风险3项（付款结构失衡、责任上限缺失、违约金基数不当），"
                "中风险7项，低风险5项。BN反事实分析显示：责任上限条款缺失对整体风险"
                "影响最大（delta=-8.7%，条款失衡维度delta=-43.3%）。"
                "核心问题是80%预付款与5%质保金的结构性失衡——买方大量资金前置，"
                "但卖方履约保障不足。建议在签署前完成付款节奏调整和责任上限补充。"
            ),
            "narrative_report": (
                "# 合同风险审查报告\n\n"
                "## 一、执行摘要\n\n"
                "本报告对《瓷砖购销合同》进行LLM+BN融合审查。审查立场：**买方代理律师**。\n\n"
                "核心发现：合同中存在**80%预付款与5%质保金的结构性失衡**——"
                "买方大量资金前置，但卖方履约保障（交货质量、质保期、违约救济）严重不足。"
                "此外，合同**未设定责任上限**，在出现系统性质量问题时，买方虽能全额索赔，"
                "但卖方也可能因无限责任而消极应对——这是一个'双刃剑'条款。\n\n"
                "**BN量化评估**：整体合同风险概率P(high)=20.4%，其中财务暴露风险维度"
                "P(high)=78.3%（高），条款失衡维度P(high)=52.3%（中高），"
                "履约交付维度P(high)=35.1%（中）。\n\n"
                "**建议**：降低预付款比例至30%、设定责任上限（合同总价120%）、"
                "明确违约金计算基数为'未履行部分对应金额'而非'合同总价'。"
            ),
            "signing_advice": "暂不建议直接签署——需完成付款结构调整和责任上限补充",
            "action_plan": [
                "将预付款比例从80%降至30%，与交付里程碑挂钩",
                "设定卖方责任上限为合同总价的120%",
                "违约金计算基数改为'未履行部分对应金额'",
            ],
            "cross_dimension_notes": [
                "财务暴露风险与条款失衡风险联动：高预付款+低质保金+无责任上限形成系统性风险",
            ],
            "issue_reports": [],
            "legal_view": "",
            "business_view": "",
            "executive_view": "",
            "dimension_insights": {},
        },
        # Top-level aliases that RiskReport checks
        "narrative_report": (
            "# 合同风险审查报告\n\n"
            "## 一、执行摘要\n\n"
            "本报告对《瓷砖购销合同》进行LLM+BN融合审查。审查立场：**买方代理律师**。\n\n"
            "核心发现：合同中存在**80%预付款与5%质保金的结构性失衡**——"
            "买方大量资金前置，但卖方履约保障（交货质量、质保期、违约救济）严重不足。"
            "此外，合同**未设定责任上限**，在出现系统性质量问题时，买方虽能全额索赔，"
            "但卖方也可能因无限责任而消极应对——这是一个'双刃剑'条款。\n\n"
            "**BN量化评估**：整体合同风险概率P(high)=20.4%，其中财务暴露风险维度"
            "P(high)=78.3%（高），条款失衡维度P(high)=52.3%（中高），"
            "履约交付维度P(high)=35.1%（中）。\n\n"
            "**建议**：降低预付款比例至30%、设定责任上限（合同总价120%）、"
            "明确违约金计算基数为'未履行部分对应金额'而非'合同总价'。"
        ),
        "executive_summary": (
            "本合同为瓷砖购销合同，经LLM自由审查+BN一致性校验，共识别15项风险，"
            "其中高风险3项（付款结构失衡、责任上限缺失、违约金基数不当）。"
            "建议在签署前完成付款节奏调整和责任上限补充。"
        ),
        "signing_advice": "暂不建议直接签署",
        "action_plan": [
            "将预付款比例从80%降至30%",
            "设定卖方责任上限为合同总价的120%",
        ],
        "cross_dimension_notes": [],
        "free_review": {
            "segments_count": 5,
            "missing_clauses": ["缺少知识产权条款", "缺少不可抗力条款"],
            "strengths": ["争议管辖在甲方所在地", "验收区分外观与内在质量"],
            "overall_assessment": "合同整体对甲方有利，但付款结构存在重大风险",
            "risk_segments": [
                {"clause_type": "payment", "risk_title": "预付款80%过高",
                 "risk_description": "预付款80%远超行业惯例(30%)，买方资金风险集中",
                 "evidence_text": "甲方于签订后10日内支付80%预付款", "confidence": 0.92,
                 "severity": "critical", "counterparty_impact": None,
                 "recommendation": "将预付款降至30%并要求等额履约保函",
                 "suggested_bn_nodes": ["payment_structure"], "legal_basis": "民法典第6条公平原则"},
                {"clause_type": "liability_cap", "risk_title": "无责任上限条款",
                 "risk_description": "合同未约定卖方责任上限，卖方承担无限责任——对买方是有利筹码",
                 "evidence_text": "合同未约定责任上限", "confidence": 0.95,
                 "severity": "positive", "counterparty_impact": "very_favorable_to_client",
                 "recommendation": "保持现状作为防守筹码，仅在对方做出极端让步时作为交换",
                 "suggested_bn_nodes": ["liability_cap_strength"], "legal_basis": None},
                {"clause_type": "liquidated_damages", "risk_title": "违约金基数不当",
                 "risk_description": "违约金以合同总价为基数，被法院调减风险高",
                 "evidence_text": "违约方按合同总价20%支付违约金", "confidence": 0.88,
                 "severity": "high", "counterparty_impact": None,
                 "recommendation": "改为以未履行部分价值为基数",
                 "suggested_bn_nodes": ["cuad_liquidated_damages"], "legal_basis": "民法典第585条"},
                {"clause_type": "warranty", "risk_title": "质保金仅5%",
                 "risk_description": "质保金5%比例过低，且为支票形式——存在空头风险",
                 "evidence_text": "剩余5%作为质量保证金于交付后12个月支付", "confidence": 0.85,
                 "severity": "medium", "counterparty_impact": None,
                 "recommendation": "将质保金提高至10%，改为银行保函形式",
                 "suggested_bn_nodes": ["cuad_warranty_duration"], "legal_basis": None},
                {"clause_type": "delivery", "risk_title": "交付地点模糊",
                 "risk_description": "交付地点仅写'甲方指定地点'，无精确地址",
                 "evidence_text": "乙方负责运输至甲方指定仓库", "confidence": 0.78,
                 "severity": "medium", "counterparty_impact": None,
                 "recommendation": "写明精确到门牌号的地址及联系人",
                 "suggested_bn_nodes": ["delivery_terms"], "legal_basis": None},
            ],
        },
        "consistency": {
            "annotations": [],
            "counterfactuals": [
                {"node_name": "liability_cap_strength", "node_label": "责任上限条款强度",
                 "current_state": "missing", "proposed_state": "present",
                 "base_high_risk": 0.204, "counterfactual_high_risk": 0.117,
                 "delta_high_risk": -0.087, "description": "",
                 "dimension_deltas": [
                     {"dimension_key": "clause_balance_risk", "dimension_label": "条款失衡风险",
                      "base_high": 0.523, "counterfactual_high": 0.089, "delta": -0.434}
                 ],
                 "derivation_chain": "条款状态missing→present | CUAD统计缺失=82%纠纷率 | pgmpy VE delta=-8.7%"},
                {"node_name": "payment_structure", "node_label": "付款结构合理性",
                 "current_state": "unfavorable", "proposed_state": "favorable",
                 "base_high_risk": 0.204, "counterfactual_high_risk": 0.171,
                 "delta_high_risk": -0.033, "description": "",
                 "dimension_deltas": [
                     {"dimension_key": "financial_exposure_risk", "dimension_label": "财务暴露风险",
                      "base_high": 0.783, "counterfactual_high": 0.452, "delta": -0.331}
                 ],
                 "derivation_chain": "条款状态unfavorable→favorable | 预付款降至30% | pgmpy VE delta=-3.3%"},
            ],
            "counterfactuals_count": 2,
            "bn_summary": "BN交叉验证发现2项反事实改善空间（Demo 数据，非真实审查结果）",
        },
        "debug": {
            "routing": {
                "primary_type": "销售合同",
                "confidence": 0.82,
                "selected_nodes": ["payment_structure", "risk_transfer_point", "warranty_scope"],
            },
        },
        "runtime_metadata": {
            "generated_at": "2026-01-01T00:00:00Z",
            "backend_started_at": "2026-01-01T00:00:00Z",
            "generation_mode": "v2_combined",
            "golden_scoring_enabled": False,
        },
        "report": {
            "contract_id": "demo-买卖合同-001",
            "overall_risk": "medium",
            "overall_risk_label": "中风险",
            "requires_manual_review": False,
            "signing_recommendation": "有条件签署",
            "category_scores": {"overall_contract_risk": 0.35},
            "dimension_scores": {
                "financial_exposure_risk": 0.78,
                "clause_balance_risk": 0.52,
                "performance_delivery_risk": 0.35,
                "dispute_resolution_risk": 0.22,
                "legal_enforceability_risk": 0.18,
            },
            "dimension_labels": {
                "legal_enforceability_risk": "法律可执行性风险",
                "financial_exposure_risk": "财务暴露风险",
                "performance_delivery_risk": "履约交付风险",
                "dispute_resolution_risk": "争议处置风险",
                "clause_balance_risk": "条款失衡风险",
            },
            "dimension_risk_labels": {
                "legal_enforceability_risk": "低风险",
                "financial_exposure_risk": "高风险",
                "performance_delivery_risk": "中风险",
                "dispute_resolution_risk": "低风险",
                "clause_balance_risk": "中风险",
            },
            "dimension_summaries": {},
            "top_risks": [],
            "summary_reasons": [
                "责任上限条款缺失 → present可降 8.7% 高风险概率",
                "付款结构 unfavorable→favorable 可降 3.3% 高风险概率",
            ],
            "manual_review_items": [],
        },
    }


@router.post("/api/detect-party-roles")
async def api_detect_party_roles(request: Request) -> JSONResponse:
    """Detect 甲方/乙方 roles from contract text.

    POST body: {"contract_text": "..."}
    Returns: {"jia_role": "出租方", "yi_role": "承租方", "jia_name": "XX公司", "yi_name": null}
    """
    body = await request.json()
    contract_text = str(body.get("contract_text", "")).strip()
    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)

    roles = detect_party_roles(contract_text)
    return JSONResponse(roles)
