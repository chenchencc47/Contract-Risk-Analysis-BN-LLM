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

    demo_narrative_report = """# 合同风险审查报告

## 一、执行摘要

本报告对《瓷砖购销合同》进行 LLM + BN 融合审查。审查立场：**买方代理律师**。

本 Demo 展示 5 项代表性风险：预付款比例过高、责任上限缺失、违约金基数不当、质保金比例偏低、交付地点不明确。核心问题是 **80% 预付款与 5% 质保金的结构性失衡**：买方大量资金前置，但卖方履约保障、质量救济和交付约束不足。

BN 量化评估显示：整体合同风险概率 P(high)=20.4%；其中财务暴露风险维度 P(high)=78.3%，条款失衡维度 P(high)=52.3%，履约交付维度 P(high)=35.1%。反事实分析显示，补充责任上限条款可使整体高风险概率下降 8.7%，调整付款结构可下降 3.3%。

**签署建议**：暂不建议直接签署。建议先把预付款比例、责任上限、违约金计算基数和交付信息补充清楚，再进入签署流程。

## 二、合同基本信息

| 项目 | 内容 |
|---|---|
| 合同名称 | 瓷砖购销合同 |
| 合同类型 | 买卖合同 / 销售合同 |
| 审查视角 | 买方 |
| Demo 模式 | 预计算样例，不调用外部 API |
| 核心审查链路 | LLM₁ 自由审查 → BN 一致性校验 → LLM₂ 综合报告 |

本合同的商业结构是：买方向卖方采购瓷砖，卖方负责供货和运输，买方按约定节点付款。合同对价格、付款、交付、质保和违约责任均有约定，但关键条款之间的风险分配不均衡。

## 三、核心风险总览

| 优先级 | 风险项 | 当前状态 | 主要影响 | 建议动作 |
|---|---|---|---|---|
| P0 | 预付款 80% 过高 | 不利于买方 | 买方资金提前暴露，卖方履约压力不足 | 降至 30%，与交付里程碑挂钩 |
| P0 | 责任上限缺失 | 需策略性处理 | 对买方索赔有利，但谈判中可能引发卖方反弹 | 可保留为筹码，必要时设为合同总价 120% |
| P1 | 违约金以合同总价为基数 | 可执行性风险 | 发生部分违约时容易被认为过高 | 改为未履行部分对应金额 |
| P1 | 质保金仅 5% | 质量救济不足 | 质量问题发生后买方留存资金有限 | 提高至 10%，或要求银行保函 |
| P2 | 交付地点模糊 | 履约争议风险 | 运输、签收、风险转移节点不清 | 写明地址、联系人、签收标准 |

这些风险不是孤立存在的。高预付款、低质保金、交付地点模糊共同放大了买方的履约和资金风险；违约金基数不当则会影响后续救济的可执行性。

## 四、重点风险逐项分析

### 1. 付款结构失衡

合同约定买方在签订后短期内支付 80% 预付款。该安排让买方在货物交付、质量验收和售后保障尚未完成前承担大部分资金压力。

**风险影响**：如果卖方延迟交货、交付不合格或售后响应不足，买方已经支付大部分价款，谈判和追偿主动权下降。

**修订建议**：将付款拆成“预付款 30% + 到货验收后支付主体价款 + 质保期届满后释放质保金”。如卖方坚持高预付款，应提供等额履约保函或银行担保。

### 2. 责任上限条款缺失

合同未明确卖方责任上限。站在买方视角，这一条款并不必然是坏事，因为它保留了全额索赔空间；但在谈判中，卖方可能要求补充责任上限。

**风险影响**：如果没有策略性处理，责任上限可能在后续谈判中被卖方压低，反而削弱买方救济能力。

**修订建议**：买方可把“责任上限缺失”作为谈判筹码。若必须设置上限，建议不低于合同总价 120%，并排除故意违约、重大过失、知识产权侵权和保密违约等情形。

### 3. 违约金基数不当

合同约定违约方按合同总价 20% 支付违约金。若实际只发生部分迟延或部分质量问题，以合同总价作为统一基数可能与损失范围不匹配。

**风险影响**：在争议中，对方可能主张违约金过高并请求调整，导致买方预期救济打折。

**修订建议**：将违约金基数改为“未履行部分、迟延部分或不合格部分对应金额”，并保留“实际损失超过违约金的，守约方可继续请求赔偿”的表述。

### 4. 质保金比例偏低

合同仅保留 5% 质保金。对于瓷砖类货物，外观瑕疵、色差、破损、铺贴后质量问题可能在交付后一段时间才显现。

**风险影响**：质保金比例偏低会降低卖方后续维修、更换和赔偿的约束力。

**修订建议**：将质保金提高至 10%，或要求卖方提供银行保函；同时明确质保期、响应时限、维修/更换责任和逾期处理方式。

### 5. 交付地点和验收流程不够精确

合同使用“甲方指定地点”等概括表述，但没有写明精确地址、联系人、签收材料和验收时限。

**风险影响**：一旦发生迟延、破损或数量争议，双方可能围绕“是否完成交付”“风险何时转移”“谁负责运输损耗”发生分歧。

**修订建议**：写明交付地址、联系人、联系电话、签收单据、外观验收和内在质量异议期限，并约定运输损耗由卖方承担至买方完成签收。

## 五、BN 反事实分析

BN 反事实分析用于回答：如果修改某个条款，整体高风险概率会下降多少。

| 条款状态调整 | 当前 P(high) | 调整后 P(high) | Delta | 解释 |
|---|---:|---:|---:|---|
| 责任上限条款 missing → present | 20.4% | 11.7% | -8.7% | 对条款失衡维度影响最大 |
| 付款结构 unfavorable → favorable | 20.4% | 17.1% | -3.3% | 对财务暴露风险影响最直接 |

维度层面上，责任上限条款补充后，条款失衡风险从 52.3% 降至 8.9%；付款结构调整后，财务暴露风险从 78.3% 降至 45.2%。这说明优先修订顺序应是：先处理责任边界和付款结构，再处理违约金、质保和交付细节。

## 六、修订建议

1. 将预付款比例从 80% 调整为 30%，并将后续付款与到货、验收、质保期挂钩。
2. 增加责任上限条款；如需设限，建议不低于合同总价 120%，并排除故意违约、重大过失、保密违约等情形。
3. 将违约金基数从“合同总价”改为“未履行部分对应金额”。
4. 将质保金从 5% 提高至 10%，或要求卖方提供银行保函。
5. 明确交付地址、签收材料、验收标准、异议期限和运输损耗承担。
6. 补充不可抗力、知识产权、通知送达和保密条款，降低后续争议解释空间。

## 七、签署建议

当前版本不建议直接签署。若商业上必须推进，建议至少完成三项底线修订：预付款降至 30%、责任上限不低于合同总价 120%、违约金基数改为未履行部分对应金额。

如果卖方拒绝修改付款结构，买方应要求等额履约保函；如果卖方要求设置较低责任上限，买方应同步要求更高质保金、更严格验收标准和更明确的违约救济。

## 八、Demo 说明与局限

本 Demo 是预计算样例，用于展示 ContractLens 的报告结构、BN 反事实解释和修订建议格式。点击「体验 Demo」不会调用外部 LLM API，也不会连接 MySQL。

真实审查时，系统会基于用户上传或粘贴的合同文本运行完整链路，并根据合同内容生成新的风险段、BN evidence、反事实 delta 和综合报告。Demo 中的数值和结论仅对应这份瓷砖购销合同样例，不应直接套用于其他合同。
"""

    demo_revision_checklist = """# 合同修订清单

| 优先级 | 条款 | 当前问题 | 建议修订 |
|---|---|---|---|
| P0 | 付款结构 | 80% 预付款导致买方资金前置 | 预付款降至 30%，尾款与验收和质保期挂钩 |
| P0 | 责任上限 | 未明确责任边界，谈判策略不清 | 设置不低于合同总价 120% 的上限，并保留例外情形 |
| P1 | 违约金 | 以合同总价为基数，存在调整风险 | 改为未履行部分对应金额 |
| P1 | 质保金 | 5% 质保金不足以约束售后 | 提高至 10% 或提供银行保函 |
| P2 | 交付验收 | 地址、签收、异议期限不完整 | 写明交付地址、联系人、验收标准和异议期限 |

## 建议谈判顺序

1. 先谈付款结构，因为它直接决定买方资金暴露。
2. 再谈责任上限，把责任上限作为交换筹码。
3. 最后补齐违约金、质保和交付验收细节。
"""

    demo_bn_appendix = """# BN 推理附录

## 推理链路

LLM₁ 先识别合同风险段，系统将风险段映射为 BN evidence，再由 pgmpy 构建贝叶斯网络并执行变量消元推理。LLM₂ 只使用结构化 Dossier 中的事实、BN 后验概率和反事实 delta 生成报告。

## 关键 evidence

| BN 节点 | 当前状态 | 建议状态 | 说明 |
|---|---|---|---|
| payment_structure | unfavorable | favorable | 80% 预付款导致财务暴露风险升高 |
| liability_cap_strength | missing | present | 责任边界缺失影响条款失衡维度 |
| cuad_liquidated_damages | unfavorable | favorable | 违约金基数需要与实际违约范围匹配 |
| cuad_warranty_duration | unfavorable | favorable | 质保安排对售后救济有直接影响 |
| delivery_terms | ambiguous | clear | 交付地点和签收标准需要明确 |

## 反事实结果

- 责任上限条款 missing → present：整体 P(high) 从 20.4% 降至 11.7%，delta=-8.7%。
- 付款结构 unfavorable → favorable：整体 P(high) 从 20.4% 降至 17.1%，delta=-3.3%。

## 解释

BN 的价值不是替代律师判断，而是把“先改哪一条收益最大”量化出来。这个 Demo 中，优先修订责任边界和付款结构，比单独修改交付地址更能降低整体风险。
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
            "narrative_report": demo_narrative_report,
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
        "narrative_report": demo_narrative_report,
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
        "revision_checklist": demo_revision_checklist,
        "bn_appendix": demo_bn_appendix,
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
