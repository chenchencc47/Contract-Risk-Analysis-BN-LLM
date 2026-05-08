"""Miscellaneous endpoints: favicon, health, demo."""

from __future__ import annotations

import os
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from contract_risk_analysis.bn.config_validator import validate_v2_config

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
    """Return a pre-computed demo review to showcase the system output."""

    return {
        "demo": True,
        "note": "This is a pre-computed demo to show what ContractLens output looks like. "
                "Set DEMO_MODE=false and configure API keys for live contract analysis.",
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
        },
        "free_review": {
            "segments_count": 15,
            "risk_segments": [
                {"risk_title": "预付款80%过高", "severity": "high",
                 "clause_type": "付款结构", "description": "预付款80%远超行业惯例(30%)，买方资金风险集中"},
                {"risk_title": "无责任上限条款", "severity": "high",
                 "clause_type": "责任上限", "description": "合同未约定卖方责任上限，存在双向风险"},
                {"risk_title": "违约金基数不当", "severity": "high",
                 "clause_type": "违约金", "description": "违约金以合同总价为基数，对买方极不利"},
                {"risk_title": "质保金仅5%", "severity": "medium",
                 "clause_type": "质保金", "description": "质保金比例过低，不足以覆盖质保期内质量风险"},
                {"risk_title": "交付地点模糊", "severity": "medium",
                 "clause_type": "交付", "description": "交付地点表述为'甲方指定地点'，存在履约争议风险"},
            ],
        },
        "consistency": {
            "counterfactuals": [
                {"node_label": "责任上限条款", "node_name": "liability_cap",
                 "current_state": "missing", "proposed_state": "present",
                 "base_high_risk": 0.204, "counterfactual_high_risk": 0.117,
                 "delta_high_risk": -0.087,
                 "dimension_deltas": [
                     {"dimension_key": "clause_balance_risk", "dimension_label": "条款失衡风险",
                      "base_high": 0.523, "counterfactual_high": 0.089, "delta": -0.434}
                 ],
                 "derivation_chain": "条款状态missing→present | CUAD统计该条款缺失时82%合同出现纠纷 → pgmpy VE推理 delta=-8.7%"},
                {"node_label": "付款结构", "node_name": "payment_structure",
                 "current_state": "unfavorable", "proposed_state": "favorable",
                 "base_high_risk": 0.204, "counterfactual_high_risk": 0.171,
                 "delta_high_risk": -0.033,
                 "dimension_deltas": [
                     {"dimension_key": "financial_exposure_risk", "dimension_label": "财务暴露风险",
                      "base_high": 0.783, "counterfactual_high": 0.452, "delta": -0.331}
                 ],
                 "derivation_chain": "条款状态unfavorable→favorable | 预付款比例降低至30% → pgmpy VE推理 delta=-3.3%"},
            ],
        },
        "quality_gate": {"counterfactual_count": 2, "note": "demo-mode"},
    }
