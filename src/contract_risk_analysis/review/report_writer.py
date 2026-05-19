"""Downstream LLM report generator.

Takes BN-structured risk data and produces a natural-language
contract risk review report in Markdown format.

The core philosophy: the LLM is a report WRITER, not a form-filler.
It receives rich structured evidence from the BN and produces a
cohesive, professional legal review document.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import yaml

from contract_risk_analysis.domain.free_review_schema import (
    ConsistencyReport,
    CounterfactualResult,
    DossierRiskItem,
    FreeReviewOutput,
    NegotiationChip,
    QuantitativeContext,
    ReportDossier,
    ValidationAnnotation,
)
from contract_risk_analysis.domain.review_schema import LegalIssueReport, RiskReport

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

from contract_risk_analysis.constants import DIMENSION_LABELS, RISK_LABELS

# ═══════════════════════════════════════════════════════════════════
#  v2.13-C: BN counterfactual interpretation guardrails
# ═══════════════════════════════════════════════════════════════════

BN_INTERPRETATION_RULES: dict[str, dict] = {
    "liability_cap": {
        "report_usage": "defensive_chip_only",
        "buyer": (
            "买方视角下，当前无责任上限是优势。BN反事实数据仅说明该条款的价值，"
            "应作为「防守筹码说明」使用，**严禁**写成主动新增责任上限建议。"
        ),
        "seller": (
            "卖方视角下，无责任上限是致命风险。BN数据可作为主动要求增加责任上限的量化依据。"
        ),
    },
    "liability_cap_strength": {
        "report_usage": "defensive_chip_only",
        "buyer": (
            "买方视角下，责任上限强度改善的反事实数据仅说明该条款的价值，"
            "应作为「防守筹码说明」使用，**严禁**写成主动修改建议。"
        ),
        "seller": (
            "卖方视角下，责任上限强度不足是重大风险。BN数据可作为主动要求加强责任上限的量化依据。"
        ),
    },
    "damages_exposure": {
        "report_usage": "defensive_chip_only",
        "buyer": (
            "买方视角下，未排除间接损失对买方影响有限（买方主要义务为付款，"
            "逾期付款的间接损失极难被司法支持）。BN数据应作为「防守筹码说明」，"
            "**严禁**写成主动排除间接损失建议。"
        ),
        "seller": (
            "卖方视角下，未排除间接损失是重大风险（产品缺陷可能引发停产、商誉损失、"
            "第三方索赔等）。BN数据可作为主动要求排除间接损失的量化依据。"
        ),
    },
    "jurisdiction_fairness": {
        "report_usage": "defensive_chip_only",
        "buyer": (
            "买方视角下，甲方住所地管辖是核心优势（大幅降低诉讼成本和执行难度）。"
            "BN数据应作为「底线筹码说明」使用，**严禁**写成主动修改管辖地建议。"
        ),
        "seller": (
            "卖方视角下，对方住所地管辖不利。BN数据可作为要求改为己方所在地或"
            "中立仲裁机构的量化依据。"
        ),
    },
    "termination_right_balance": {
        "report_usage": "manual_review_note",
        "buyer": (
            "终止权利平衡性需结合具体商业背景判断。BN数据仅供参考，"
            "报告中必须标注「建议人工复核」，不得自行下结论。"
        ),
        "seller": (
            "终止权利平衡性需结合具体商业背景判断。BN数据仅供参考，"
            "报告中必须标注「建议人工复核」，不得自行下结论。"
        ),
    },
    "termination_clause_completeness": {
        "report_usage": "manual_review_note",
        "buyer": (
            "终止条款完备性的BN数据需结合合同具体情况判断。"
            "报告中必须标注「建议人工复核」。"
        ),
        "seller": (
            "终止条款完备性的BN数据需结合合同具体情况判断。"
            "报告中必须标注「建议人工复核」。"
        ),
    },
}


def _get_bn_report_usage(node_name: str, review_party: str) -> str:
    """Classify a BN counterfactual's report usage based on interpretation rules."""
    rule = BN_INTERPRETATION_RULES.get(node_name)
    if rule is None:
        return ""
    return rule.get("report_usage", "")


def _get_bn_interpretation_note(node_name: str, review_party: str) -> str:
    """Get the party-aware interpretation note for a BN counterfactual."""
    rule = BN_INTERPRETATION_RULES.get(node_name)
    if rule is None:
        return ""
    return rule.get(review_party, "")

# Standard report sections the LLM must produce
REPORT_SECTIONS = [
    "## 一、执行摘要",
    "## 二、风险总览",
    "## 三、逐条款风险分析",
    "## 四、关键条款改善效果预估",
    "## 五、筹码防御与谈判策略",
    "## 六、签署建议",
    "## 七、整改行动计划",
    "## 八、附录：贝叶斯网络推理依据",
]


@dataclass(frozen=True)
class PolishedReport:
    """Holds both the narrative report and structured excerpts for backward compat."""
    narrative_report: str = ""  # The MAIN output — a complete Markdown document

    # Excerpts extracted from the narrative for structured display (optional)
    executive_summary: str = ""
    signing_advice: str = ""
    action_plan: list[str] = field(default_factory=list)
    cross_dimension_notes: list[str] = field(default_factory=list)
    issue_reports: list[LegalIssueReport] = field(default_factory=list)
    dimension_insights: dict[str, str] = field(default_factory=dict)
    legal_view: str = ""
    business_view: str = ""
    executive_view: str = ""
    generation_mode: str = "legacy_bn_only"  # "legacy_bn_only" | "combined"

    # ── Source annotations (P1.2) ──
    bn_derived_claims: list[str] = field(default_factory=list)
    """Claims/probability numbers in the report that come from BN output."""
    llm_judgment_claims: list[str] = field(default_factory=list)
    """Claims in the report that are LLM₂'s independent legal judgments."""


# ═══════════════════════════════════════════════════════════════════
#  v2.15: Multi-format report output
# ═══════════════════════════════════════════════════════════════════


@dataclass
class MultiFormatReports:
    """v2.15: Multiple report formats generated from the same Dossier.

    Each format serves a different audience and purpose.
    All formats share the same frozen Dossier as their single source of truth.
    """
    dossier: ReportDossier

    # v2.15-A: 1-2 page executive summary for management
    executive_brief: str = ""

    # v2.15-B: Full legal review (the existing combined report)
    full_legal_review: str = ""

    # v2.15-C: Negotiation playbook for business teams
    negotiation_playbook: str = ""

    # v2.15-D: Contract revision checklist (deterministic, no LLM)
    revision_checklist: str = ""

    # v2.15-E: BN/Methodology appendix (deterministic, no LLM)
    bn_appendix: str = ""

    # v2.15-F: Redline clause comparison table (deterministic, no LLM)
    redline_appendix: str = ""


def _build_executive_brief_prompt(
    dossier: ReportDossier,
    free_output: FreeReviewOutput,
    review_party: str = "buyer",
) -> str:
    """v2.15-A: Build prompt for 1-2 page executive summary."""
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"

    critical_items = [it for it in dossier.risk_items if it.severity == "critical"]
    high_items = [it for it in dossier.risk_items if it.severity == "high"]

    return f"""你是{party_label}的法务顾问，需要为管理层撰写一份**1-2页的合同审查摘要**。

管理层不需要逐条款法律分析——他们需要快速判断：能不能签？卡在哪？必须改什么？

## 报告事实清单（Dossier摘要）

- 合同编号：{dossier.contract_id}
- 审查立场：{dossier.review_party}
- 致命风险数：{len(critical_items)}
- 高风险数：{len(high_items)}
- 有利条款数：{len(dossier.favorable_terms)}
- 需人工复核项：{len(dossier.manual_review_items)}

### 致命风险（一票否决级）
{chr(10).join(f"- {it.risk_title}：{it.recommendation or '必须在签署前修改'}（证据：{it.evidence_text[:100]}）" for it in critical_items) if critical_items else '- （无致命风险）'}

### 高风险项
{chr(10).join(f"- {it.risk_title}（P{it.priority_rank}，{it.legal_direction or 'unknown'}）" for it in high_items[:5]) if high_items else '- （无高风险项）'}

### 有利条款（必须守住）
{chr(10).join(f"- {ft.term_name}（{ft.chip_type or '防守'}）" for ft in dossier.favorable_terms[:5]) if dossier.favorable_terms else '- （无特殊有利条款）'}

### 签署底线
**禁止签署的条件：**
{chr(10).join(f"- {sf}" for sf in dossier.signing_forbidden) if dossier.signing_forbidden else '- （无）'}
**可签署的条件：**
{chr(10).join(f"- {sa}" for sa in dossier.signing_acceptable) if dossier.signing_acceptable else '- （无）'}

---
## 撰写要求

请撰写一份管理层摘要，使用 Markdown 格式，包含以下章节：

### 一、签署建议（一句话结论）
明确给出：建议签署 / 有条件签署 / 不建议签署。一句话说清为什么。

### 二、核心风险（最多3项）
每项用2-3句话说明：什么风险、为什么致命、必须怎么改。使用业务语言，不引用法律条文。

### 三、我方优势（最多3项）
我方在合同中的关键有利条款，谈判中必须守住。

### 四、谈判底线
简明列出不可退让的条件，以及可接受的修改范围。

### 五、决策建议
1-2段话，给管理层的最终建议。

**约束：**
- 总长度控制在1-2页等价（约500-800字）
- 使用业务语言，避免法律术语堆砌
- 不要展开法律分析——那是法务详版的工作
- 不要引用BN概率数字——这是给管理层的决策摘要
- 严格遵守 Dossier 中的签署底线，不得降低标准

直接输出 Markdown，不要前言或后记。"""


def _build_negotiation_playbook_prompt(
    dossier: ReportDossier,
    free_output: FreeReviewOutput,
    review_party: str = "buyer",
) -> str:
    """v2.15-C: Build prompt for negotiation playbook."""
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"
    counterparty = "乙方（卖方）" if review_party == "buyer" else "甲方（买方）"

    # Collect all chips
    chip_lines: list[str] = []
    for item in dossier.risk_items:
        ct = _chip_type(item.negotiation_chip)
        if ct:
            chip_lines.append(
                f"- [{ct}] {item.risk_title}（{item.legal_direction or 'unknown'}）"
                f"：{_inline_negotiation_chip(item.negotiation_chip)}"
            )
    for ft in dossier.favorable_terms:
        if ft.chip_type:
            chip_lines.append(
                f"- [{ft.chip_type}] {ft.term_name}（{ft.legal_direction or 'favorable'}）"
                f"：{ft.description[:120]}"
            )

    return f"""你是{party_label}的谈判顾问。你的任务是为业务团队撰写一份**可以直接带上谈判桌的作战手册**。

合同审查已完成，以下是系统生成的筹码清单和风险数据。

## 筹码清单

{chr(10).join(chip_lines) if chip_lines else '（无已识别筹码）'}

## 签署底线

**禁止签署的条件：**
{chr(10).join(f"- {sf}" for sf in dossier.signing_forbidden) if dossier.signing_forbidden else '- （无）'}

**谈判底线：**
{chr(10).join(f"- {bl}" for bl in dossier.negotiation_bottom_lines) if dossier.negotiation_bottom_lines else '- （无）'}

## 撰写要求

请撰写一份谈判作战手册，使用 Markdown 格式，包含以下章节：

### 一、筹码总览

用表格列出所有筹码：筹码名称 | 类型（底线/交换/响应）| 所属条款 | 筹码价值说明

### 二、对手主攻方向预判

站在{counterparty}律师的角度，预判对方在谈判桌上的核心攻击方向（3-5个）。
对每个攻击方向，必须给出：
- 对方律师具体会怎么说（给出话术示例）
- 该攻击的实质威胁有多大（高/中/低）
- 我方的应对策略

**质量要求**：不得使用"对方可能要求修改"等泛泛表述。必须具体到条款号和合同中已出现的百分比/节点；若无，则写明方向和条件。

### 三、底线筹码防御策略

对每个底线筹码：
1. 防守话术（如何论证该条款的合理性）
2. 如对方极度坚持 → 用哪个交换筹码或响应筹码来换
3. 底线：什么条件下才应考虑退出谈判

### 四、交换筹码退让阶梯

对每个交换筹码，给出三档阶梯：
- 开盘目标（最理想的方向和条件）
- 可接受中间价（方向和保护条件）
- 底线（不得退过的保护前提）
每档附带对方需做出的对应让步。
**数字纪律**：只能引用合同原文或 Dossier 定量锚点中已有的数字/百分比；如果没有，必须用方向+保护条件替代具体数字。

### 五、响应筹码交换方案

对每个响应筹码：
1. 等待纪律：绝不主动提出修改
2. 接招姿态：对方提出时的话术
3. 交换目标：明确列出可换取哪些对方让步，按优先级排序

### 六、谈判路线图

给出建议的谈判顺序和节奏：先谈什么、后谈什么、什么阶段亮出什么筹码。

**约束：**
- 这是给业务团队看的，不是给律师看的——使用商业语言
- 若本合同或 Dossier 已提供可追溯数字（百分比/金额/天数），应直接引用；若未提供，则必须写清方向、条件与交换前提，不得编造固定阈值
- 不得使用"建议律师准备谈判策略""可考虑适度让步"等空话
- 策略结论必须与签署底线一致

直接输出 Markdown，不要前言或后记。"""


def _build_revision_checklist(dossier: ReportDossier) -> str:
    """v2.15-D: Build deterministic contract revision checklist from dossier.

    No LLM needed — extracts recommendations directly from frozen risk items.
    """
    lines: list[str] = [
        f"# 合同修订清单",
        f"",
        f"> 合同编号：{dossier.contract_id}",
        f"> 审查立场：{dossier.review_party}",
        f"> 生成方式：系统确定性生成（非LLM）",
        f"",
        f"本清单列出审查中识别的所有需修改条款，按优先级排列。",
        f"**必须修改** = 签署前必须解决 | **建议修改** = 强烈建议 | **可谈判** = 可作交换筹码",
        f"",
    ]

    # Sort: critical → high → medium → low
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_items = sorted(
        dossier.risk_items,
        key=lambda it: (sev_order.get(it.severity, 99), it.priority_rank),
    )

    for item in sorted_items:
        if item.severity == "positive":
            continue

        if item.severity in ("critical",) and item.priority_rank == 1:
            must_label = "**⚠️ 必须修改（签署底线）**"
        elif item.severity in ("critical", "high") and item.priority_rank <= 2:
            must_label = "**建议修改**"
        else:
            must_label = "可谈判修改"

        lines.append(f"## {item.issue_id}：{item.risk_title}")
        lines.append(f"- 修改优先级：{must_label}")
        lines.append(f"- 条款类别：{item.canonical_type or item.clause_type}")
        lines.append(f"- 原文证据：「{item.evidence_text}」")
        if item.recommendation:
            lines.append(f"- 建议修改方向：{item.recommendation}")
        if item.legal_basis:
            lines.append(f"- 法律依据：{item.legal_basis}")
        if item.negotiation_role:
            role_labels = {
                "must_fix": "必须在签署前修改",
                "trade": "可作为交换筹码在谈判中让步",
                "protect": "应坚守的有利条款（不建议修改）",
                "respond": "等待对方提出后再交换",
                "monitor": "关注即可，不需主动修改",
            }
            lines.append(f"- 谈判角色：{role_labels.get(item.negotiation_role, item.negotiation_role)}")
        if item.manual_review:
            lines.append(f"- ⚠️ 建议人工复核：{item.internal_conflict or '系统标记需人工复核'}")
        lines.append("")

    if dossier.favorable_terms:
        lines.append("---")
        lines.append("")
        lines.append("## 有利条款（建议保留，不修改）")
        lines.append("")
        lines.append("以下条款对当前审查立场有利，**不建议主动提出修改**：")
        lines.append("")
        for ft in dossier.favorable_terms:
            lines.append(f"- **{ft.term_name}**（{ft.chip_type or '防守型'}）")
            if ft.description:
                lines.append(f"  - {ft.description[:150]}")
            lines.append("")

    return "\n".join(lines)


def _build_redline_appendix(dossier: ReportDossier) -> str:
    """Build a deterministic redline (条款对照表) appendix from Dossier risk items.

    No LLM needed. Generates a two-column Markdown table:
    left = original clause text, right = recommended modification.
    """
    lines: list[str] = [
        "# 条款修订对照表（Redline）",
        "",
        f"> 合同编号：{dossier.contract_id}",
        f"> 审查立场：{dossier.review_party}",
        f"> 生成方式：系统确定性生成（非LLM）",
        f"",
        f"本附录将报告中的修改建议与原条款逐条对照列出，",
        f"可直接用于生成合同修订版（如 Word 修订模式）。",
        f"",
        f"| 序号 | 风险项 | 原条款 | 修改建议 | 条款类别 | 优先级 |",
        f"|------|--------|--------|---------|---------|--------|",
    ]

    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_items = sorted(
        dossier.risk_items,
        key=lambda it: (sev_order.get(it.severity, 99), it.priority_rank),
    )

    idx = 0
    for item in sorted_items:
        if item.severity == "positive":
            continue
        idx += 1
        evidence = item.evidence_text[:200].replace("|", "\\|").replace("\n", " ")
        recommendation = (item.recommendation or "建议人工复核")[:200].replace("|", "\\|").replace("\n", " ")
        title_short = item.risk_title[:50].replace("|", "\\|")
        lines.append(
            f"| {idx} | {title_short} | {evidence} | {recommendation} | "
            f"{item.canonical_type or item.clause_type} | "
            f"{'🔴 P' + str(item.priority_rank) if item.priority_rank and item.priority_rank <= 2 else '🟡 P' + str(item.priority_rank) if item.priority_rank else '—'} |"
        )

    lines.append("")
    lines.append("*本对照表由系统自动生成，建议法务逐条复核后使用。*")
    return "\n".join(lines)


def _build_bn_appendix(dossier: ReportDossier) -> str:
    """v2.15-E: Build deterministic BN/methodology appendix from dossier.

    No LLM needed — all data comes from BN counterfactuals and annotations.
    """
    lines: list[str] = [
        f"# BN/方法论附录",
        f"",
        f"> 合同编号：{dossier.contract_id}",
        f"> 生成方式：系统确定性生成（非LLM）",
        f"",
        f"本附录记录本次审查中使用的贝叶斯网络推理数据和方法论，",
        f"供技术团队追溯数字来源和验证推理逻辑。",
        f"",
        f"## 一、方法论概述",
        f"",
        f"- **推理引擎**：pgmpy BayesianNetwork，使用变量消除法（Variable Elimination）进行精确概率推理",
        f"- **CPT参数来源**：CUAD数据集（510份合同）+ ContractNLI数据集统计校准",
        f"- **证据层节点**：从LLM₁抽取的合同事实映射为BN证据节点状态",
        f"- **反事实模拟**：逐一假设关键条款改善，重新运行推理，计算P(high)降幅",
        f"",
    ]

    # BN summary
    if dossier.bn_summary:
        lines.append("## 二、BN推理摘要")
        lines.append("")
        lines.append(dossier.bn_summary)
        lines.append("")

    # Counterfactuals
    if dossier.counterfactuals:
        lines.append("## 三、反事实模拟详情")
        lines.append("")
        cf_sorted = sorted(dossier.counterfactuals, key=lambda c: c.delta_high_risk, reverse=True)
        for cf in cf_sorted:
            lines.append(f"### {cf.node_label}")
            lines.append(f"- 当前状态：{cf.current_state}")
            lines.append(f"- 假设改善至：{cf.proposed_state}")
            lines.append(f"- 整体高风险概率变化：{cf.base_high_risk:.1%} → {cf.counterfactual_high_risk:.1%}（Δ {cf.delta_high_risk:+.1%}）")
            if cf.dimension_deltas:
                lines.append(f"- 维度级变化：")
                for dd in cf.dimension_deltas:
                    lines.append(f"  - {dd.dimension_label}：{dd.base_high:.1%} → {dd.counterfactual_high:.1%}（Δ {dd.delta:+.1%}）")
            if cf.description:
                lines.append(f"- 说明：{cf.description}")
            if cf.derivation_chain:
                lines.append(f"- 推导链：{cf.derivation_chain}")
            lines.append("")

    # Annotations
    if dossier.bn_annotations:
        lines.append("## 四、BN校验标注")
        lines.append("")
        by_type: dict[str, list] = {}
        for a in dossier.bn_annotations:
            by_type.setdefault(a.annotation_type, []).append(a)
        for atype, annotations in sorted(by_type.items()):
            type_labels = {
                "missing_dimension": "⚠️ 未覆盖的维度",
                "contradiction": "⚡ BN与LLM判断分歧",
                "confidence_mismatch": "📊 置信度异常",
                "causal_incoherence": "🔗 因果不一致",
                "cross_dimension_risk": "🔴 乘数效应风险",
                "gap_detected": "ℹ️ BN未覆盖的风险类型",
            }
            label = type_labels.get(atype, atype)
            lines.append(f"### {label}")
            for a in annotations:
                prefix = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(a.severity, "")
                lines.append(f"- {prefix} {a.message}")
            lines.append("")

    # Joint risks
    if dossier.joint_risks:
        lines.append("## 五、跨维度联合风险（乘数效应）")
        lines.append("")
        for jr in dossier.joint_risks:
            lines.append(f"- {jr}")
        lines.append("")

    # Limitations
    lines.append("## 六、方法论局限")
    lines.append("")
    lines.append("1. **反事实模拟仅覆盖单一维度改善**：每项反事实仅改变一个条款状态，未考虑多条款联动改善的协同效应。")
    lines.append("2. **CPT基于统计先验**：条件概率表（CPT）从公开数据集统计得出，可能无法完全反映本合同特定商业背景。")
    lines.append("3. **证据层映射依赖LLM₁**：合同事实→BN节点的映射由LLM₁完成，存在映射遗漏或错误的风险。")
    lines.append("4. **部分节点依赖先验概率**：合同文本中未涉及的风险维度，BN使用先验概率进行推理，准确性受限。")
    lines.append("")

    # Dossier-BN conflicts
    if dossier.internal_conflicts:
        lines.append("## 七、Dossier-BN冲突记录")
        lines.append("")
        lines.append("以下冲突已在系统层标记，建议人工复核：")
        lines.append("")
        for ic in dossier.internal_conflicts:
            lines.append(f"- {ic}")
        lines.append("")

    return "\n".join(lines)


def generate_executive_brief(
    dossier: ReportDossier,
    free_output: FreeReviewOutput,
    review_party: str = "buyer",
    bn_confidence: str = "high",
) -> str:
    """v2.15-A: Generate a 1-2 page executive summary for management."""
    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_executive_brief_prompt(dossier, free_output, review_party)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": _combined_system_prompt(review_party, bn_confidence, len(free_output.risk_segments), party_role_label)
                + "\n你现在的任务是撰写管理层摘要——简明、决策导向、使用商业语言。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.2,
    )

    content = completion.choices[0].message.content
    return _strip_think_tags(content) if content else ""


def generate_negotiation_playbook(
    dossier: ReportDossier,
    free_output: FreeReviewOutput,
    review_party: str = "buyer",
    bn_confidence: str = "high",
) -> str:
    """v2.15-C: Generate a negotiation playbook for business teams."""
    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_negotiation_playbook_prompt(dossier, free_output, review_party)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": _combined_system_prompt(review_party, bn_confidence, len(free_output.risk_segments), party_role_label)
                + "\n你现在的任务是撰写谈判作战手册——具体、量化、可直接上谈判桌。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=8192,
        temperature=0.3,
    )

    content = completion.choices[0].message.content
    return _strip_think_tags(content) if content else ""


def generate_multi_format_reports(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None = None,
    review_party: str = "buyer",
    dossier: ReportDossier | None = None,
    *,
    include_executive: bool = True,
    include_full_review: bool = True,
    include_playbook: bool = True,
    include_checklist: bool = True,
    include_appendix: bool = True,
    include_redline: bool = True,
    bn_confidence: str = "high",
) -> MultiFormatReports:
    """v2.15: Generate multiple report formats from the same Dossier.

    This is the unified entry point for multi-format report generation.
    Each format serves a different audience:
    - Executive brief → management decision-makers
    - Full legal review → legal team
    - Negotiation playbook → business/negotiation team
    - Revision checklist → contract drafting team
    - BN appendix → technical/audit team

    All formats share the same frozen Dossier as their single source of truth.
    """
    import logging
    logger = logging.getLogger(__name__)

    if dossier is None:
        dossier = _build_dossier(free_output, consistency, review_party)

    reports = MultiFormatReports(dossier=dossier)

    # v2.15-A: Executive brief (LLM, ~4K tokens)
    if include_executive:
        logger.info("Generating executive brief...")
        try:
            reports.executive_brief = generate_executive_brief(
                dossier, free_output, review_party, bn_confidence
            )
        except Exception as e:
            logger.error("Failed to generate executive brief: %s", e)
            reports.executive_brief = f"（生成失败：{e}）"

    # v2.15-B: Full legal review (the existing combined report)
    if include_full_review:
        logger.info("Generating full legal review...")
        try:
            full = generate_combined_report(free_output, consistency, review_party, dossier=dossier, bn_confidence=bn_confidence)
            reports.full_legal_review = full.narrative_report
        except Exception as e:
            logger.error("Failed to generate full legal review: %s", e)
            reports.full_legal_review = f"（生成失败：{e}）"

    # v2.15-C: Negotiation playbook (LLM, ~8K tokens)
    if include_playbook:
        logger.info("Generating negotiation playbook...")
        try:
            reports.negotiation_playbook = generate_negotiation_playbook(
                dossier, free_output, review_party, bn_confidence
            )
        except Exception as e:
            logger.error("Failed to generate negotiation playbook: %s", e)
            reports.negotiation_playbook = f"（生成失败：{e}）"

    # v2.15-D: Revision checklist (deterministic, no LLM)
    if include_checklist:
        reports.revision_checklist = _build_revision_checklist(dossier)

    # v2.15-E: BN appendix (deterministic, no LLM)
    if include_appendix:
        reports.bn_appendix = _build_bn_appendix(dossier)

    # v2.15-F: Redline clause comparison table (deterministic, no LLM)
    if include_redline:
        reports.redline_appendix = _build_redline_appendix(dossier)

    return reports


def _score_to_risk_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _build_polish_prompt(report: RiskReport) -> str:
    """Build a prompt that asks the LLM to WRITE a report, not fill a form.

    Provides all BN-structured data as context, then asks for a natural-language
    Markdown report with specific sections.
    """
    # ── Dimension assessment table ──
    dim_rows: list[str] = []
    for dim_key, score in report.dimension_scores.items():
        label = DIMENSION_LABELS.get(dim_key, dim_key)
        level = RISK_LABELS.get(_score_to_risk_level(score), str(score))
        summary = report.dimension_summaries.get(dim_key, "")
        dim_rows.append(
            f"| {label} | {score:.2f} | {level} | {summary} |"
        )

    # ── Top risk items ──
    risk_items: list[str] = []
    for i, risk in enumerate(report.top_risks, 1):
        dim_label = DIMENSION_LABELS.get(risk.dimension, risk.dimension)
        risk_items.append(
            f"**风险项 {i}：{risk.title}**\n"
            f"- 风险等级：{RISK_LABELS.get(risk.risk_level, risk.risk_level)}\n"
            f"- 所属维度：{dim_label}\n"
            f"- 问题原因：{risk.reason}\n"
            f"- 建议动作：{risk.recommendation}\n"
            + (f"- 证据摘录：「{risk.evidence[0]}」\n" if risk.evidence else "")
        )

    # ── Attribution chain ──
    attribution_lines: list[str] = []
    for risk in report.top_risks:
        dim_label = DIMENSION_LABELS.get(risk.dimension, risk.dimension)
        attribution_lines.append(
            f"- **{risk.title}**（状态异常）→ 驱动 **{dim_label}** 风险升高 → 原因：{risk.reason}"
        )

    # ── Issue inputs (for per-clause detail) ──
    issue_details: list[str] = []
    for iss in report.report_issue_inputs:
        issue_details.append(
            f"**{iss.issue_id} {iss.title}**\n"
            f"- 风险等级：{iss.risk_level}\n"
            f"- 法律专题：{iss.legal_topic or '未指定'}\n"
            f"- 问题简述：{iss.problem_analysis_brief}\n"
            f"- 原文摘录：{iss.clause_excerpt or '（无原文摘录）'}\n"
            f"- 建议修订方向：{iss.recommendation}\n"
        )

    # ── Summary reasons ──
    summary_text = "\n".join(f"- {r}" for r in report.summary_reasons)

    # ── Manual review items ──
    manual_text = "\n".join(f"- {item}" for item in report.manual_review_items) if report.manual_review_items else "无"

    prompt = f"""你是一位资深法务风控顾问，同时也是一位专业法律报告撰写人。

下面是一份由贝叶斯网络（Bayesian Network）推理系统对合同进行自动审查后产出的结构化风险评估数据。请你基于这些数据，**撰写一份完整的合同风险审查报告**。

## 报告要求

1. **输出格式：Markdown**。使用标题、表格、列表、引用块等元素组织内容。
2. **语言风格**：专业法律中文 + 业务可读性。既要引用法律条文和风险概率数据，又要让非法律背景的业务负责人能理解风险的含义。
3. **必须包含以下七个章节**（使用 ## 标题）：

### 一、执行摘要
2-3 段话。第一段概括合同整体风险态势和等级。第二段指出最主要的 1-2 个风险驱动因素及其因果关系。第三段给出签署建议的核心结论。

### 二、风险总览
用表格列出五个风险维度（法律可执行性、财务暴露、履约交付、争议处置、条款失衡）的评估分数、风险等级和简要说明。表后加一段话，指出跨维度的关联风险（如"终止条款缺失同时影响了法律可执行性和履约交付两个维度"）。

### 三、逐条款风险分析
针对每个高风险条款，逐一分析：
- **条款原文摘录**（如有）
- **风险识别**：说明该条款存在什么问题，为什么构成风险
- **因果链**：该条款通过贝叶斯网络的哪条路径推高了哪个维度的风险
- **法律依据**：引用相关的《民法典》或《民事诉讼法》条文
- **修改建议**：给出具体的修改措辞建议
- 如果证据不足，应明确说明"该条款在合同中未找到明确约定（BN 节点状态为 missing）"

### 四、反事实分析：改善关键条款的预期效果
用表格展示：改善哪些条款可以将高风险概率降低多少（例如："补充终止条款后，法律可执行性高风险概率预计从 78% 降至 45%"）。数据来自贝叶斯网络的敏感性分析。

### 五、筹码防御与谈判策略
1-2 段话。站在客户的代理律师立场，分析对方最可能攻击的条款、攻击理由、以及我方的防守话术和交换筹码。必须基于本合同的具体条款，不能泛泛而谈。

### 六、签署建议
2-3 段话。明确给出签署/不签署/有条件签署的判断。如果是有条件签署，列出必须补齐的具体条件及其优先级。如果是暂不建议签署，说明风险底线在哪里。

### 七、整改行动计划
按优先级从高到低排列的整改清单（至少 3 条），每条包含：
- 整改项名称
- 负责方建议（甲方/乙方/双方）
- 建议完成时限（签署前/签署后 N 日内）
- 预期效果（完成后预计降低的风险）

### 八、附录：贝叶斯网络推理依据
简要说明本报告的推理方法论：LLM 从合同文本抽取结构化事实 → 证据层映射为贝叶斯网络节点状态 → BN 进行概率推理 → 本报告基于后验概率分布生成。

4. **严禁行为**：
   - 不得修改或虚构任何风险分数（这些是 BN 模型的客观输出）
   - 不得编造不存在的法律条文
   - 不得在没有证据的情况下断言某条款"完善"或"合理"
   - 不得输出 JSON——这是给人类阅读的报告，不是给程序解析的数据

---

## 贝叶斯网络推理数据（作为报告的事实依据）

### 合同基本信息
- 合同编号：{report.contract_id}
- 总体风险等级：{RISK_LABELS.get(report.overall_risk, report.overall_risk)}
- 是否需人工复核：{'是' if report.requires_manual_review else '否'}
- 规则化签署建议：{report.signing_recommendation}

### 维度风险评估表
| 维度 | 分数（P(high)） | 风险等级 | 概述 |
|------|----------------|---------|------|
{chr(10).join(dim_rows)}

### 关键风险项
{chr(10).join(risk_items)}

### 风险归因链（证据 → 节点 → 维度 → 总体风险）
{chr(10).join(attribution_lines)}

### 详细问题输入
{chr(10).join(issue_details)}

### 风险原因摘要
{summary_text}

### 需人工复核项
{manual_text}

---

现在请开始撰写报告。直接输出 Markdown，不要有任何前言或后记。"""

    return prompt


def _strip_think_tags(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _extract_section(text: str, heading: str) -> str:
    """Extract a section from Markdown by heading."""
    pattern = rf"{re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_list_items(text: str) -> list[str]:
    """Extract bullet list items from markdown."""
    items = re.findall(r"^\s*[-*]\s+(.+)$", text, re.MULTILINE)
    return [item.strip() for item in items]


def _parse_narrative_to_polished(markdown: str) -> PolishedReport:
    """Extract structured fields from the narrative Markdown for backward compat.

    This is a best-effort extraction. The narrative report is the primary output;
    these fields are secondary excerpts for structured display.
    """
    # Extract executive summary (section 一)
    exec_section = _extract_section(markdown, "## 一、执行摘要")
    signing_section = _extract_section(markdown, "## 六、签署建议")
    action_section = _extract_section(markdown, "## 七、整改行动计划")

    # Extract action plan items
    action_plan = _extract_list_items(action_section)

    # Cross-dimension notes — extract from 风险总览 section
    overview = _extract_section(markdown, "## 二、风险总览")
    cross_notes: list[str] = []
    if "跨维度" in overview or "关联" in overview:
        # Try to extract the paragraph mentioning cross-dimension
        for line in overview.split("\n"):
            if any(kw in line for kw in ["跨维度", "关联风险", "相互", "叠加"]):
                clean = line.strip().lstrip("- ").strip()
                if len(clean) > 10:
                    cross_notes.append(clean)

    # Dimension insights — extract from the overview table
    dim_insights: dict[str, str] = {}
    for dim_key, label in DIMENSION_LABELS.items():
        # Search for dimension mentions in the report
        pattern = rf"{re.escape(label)}.*?(?=\n\n|\n##|\Z)"
        match = re.search(pattern, markdown, re.DOTALL)
        if match:
            dim_insights[dim_key] = match.group(0).strip()[:300]

    # ── Source annotation extraction (P1.2) ──
    bn_claims: list[str] = []
    llm_claims: list[str] = []
    # Extract BN-derived claims: lines mentioning BN data sources or probability numbers
    bn_patterns = [
        r"BN[^，。,\.\n]{0,40}(?:概率|模拟|数据|反事实|预测|显示|输出)",
        r"贝叶斯网络[^，。,\.\n]{0,60}(?:概率|模拟|数据|反事实|预测|识别)",
        r"P\s*\(\s*high\s*\)\s*[=＝]\s*[\d.]+%",
        r"(?:高风险概率|风险概率)[^，。,\.\n]{0,30}(?:从|降至|降幅)",
    ]
    for pat in bn_patterns:
        for match in re.finditer(pat, markdown):
            claim = match.group(0).strip()
            if len(claim) > 6 and claim not in bn_claims:
                bn_claims.append(claim)

    # Extract LLM judgment claims
    llm_patterns = [
        r"本报告[^，。,\.\n]{0,80}(?:认为|判定|评级|建议|判断|坚持)",
        r"(?:独立判断|专家判断|专家建议)[^，。,\.\n]{0,60}",
        r"(?:法务判断|人工判断|手动评级)[^，。,\.\n]{0,60}",
    ]
    for pat in llm_patterns:
        for match in re.finditer(pat, markdown):
            claim = match.group(0).strip()
            if len(claim) > 6 and claim not in llm_claims:
                llm_claims.append(claim)

    return PolishedReport(
        narrative_report=markdown,
        executive_summary=exec_section[:500] if exec_section else "",
        signing_advice=signing_section[:600] if signing_section else "",
        action_plan=action_plan[:8] if action_plan else [],
        cross_dimension_notes=cross_notes[:5] if cross_notes else [],
        issue_reports=[],  # Issue reports are now embedded in the narrative
        dimension_insights=dim_insights,
        legal_view=_extract_section(markdown, "## 三、逐条款风险分析"),
        business_view=exec_section or "",
        executive_view=exec_section[:300] if exec_section else "",
        bn_derived_claims=bn_claims,
        llm_judgment_claims=llm_claims,
    )


def _load_polish_settings() -> tuple[str, str, str]:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY，请在项目根目录 .env 中配置。")
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL)
    model = os.getenv("DEEPSEEK_MODEL", DEEPSEEK_MODEL)
    return api_key, base_url, model


def polish_report(report: RiskReport) -> PolishedReport:
    """Generate a natural-language contract risk review report via LLM.

    The LLM receives BN-structured data as context and writes a complete
    Markdown report. The report is the primary output; structured fields
    are extracted secondarily for backward compatibility.
    """
    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_polish_prompt(report)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一位资深法务风控顾问兼法律报告撰写人。"
                    "你收到贝叶斯网络的结构化推理数据，将其转化为专业、"
                    "可读的中文合同风险审查报告。你的输出必须是 Markdown 格式，"
                    "包含所有七个指定章节。你从不编造数据——所有风险数值来自 BN 模型，"
                    "你只是进行专业解读和扩展说明。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=16384,  # Increased for full report
        temperature=0.5,  # Slightly warmer for natural prose variety
    )

    if not getattr(completion, "choices", None):
        raise ValueError("API 响应格式异常")
    choice = completion.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise ValueError("报告生成被截断，请增大 max_tokens。")
    content = choice.message.content
    if not content:
        raise ValueError("LLM 返回了空响应")

    markdown = _strip_think_tags(content)

    # Extract structured fields from the narrative for backward compatibility
    return _parse_narrative_to_polished(markdown)


# ═══════════════════════════════════════════════════════════════════
#  Combined report generation (v2 pipeline) — LLM₂ as authoritative writer
# ═══════════════════════════════════════════════════════════════════


def _combined_system_prompt(review_party: str = "buyer", bn_confidence: str = "high", risk_count: int = 10, party_role_label: str | None = None) -> str:
    # Build party label — use detected role if available, otherwise fall back to generic
    if party_role_label:
        party_label = f"贵司（{party_role_label}）" if review_party == "buyer" else f"贵司（{party_role_label}）"
    else:
        party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"

    # BN confidence framing — adjusts how LLM₂ presents quantitative data
    _BN_FRAMING = {
        "high": (
            "以下量化数据基于真实合同数据集统计校准，可用于谈判中的数字论证。"
            "乘数效应分析和反事实概率数字均可作为筹码强弱参考。"
        ),
        "medium": (
            "以下量化数据为方向性参考，基于历史合同数据统计先验推算，"
            "可能未完全反映本合同特定领域的商业实践。"
            "请在报告中呈现数字的同时，注明'建议结合具体行业惯例判断'。"
        ),
        "low": (
            "本类型合同的量化模型仍在建设中，BN分析以定性方向为主。"
            "报告中不应出现具体的百分比数字表格，改为方向性描述（如'此修改可显著降低风险'）。"
            "明确告知读者：量化模型对本合同类型的校准尚不充分，以下分析以法律判断为准。"
        ),
    }
    bn_framing = _BN_FRAMING.get(bn_confidence, _BN_FRAMING["high"])

    # Lightweight mode: only for genuinely simple contracts (very few risks).
    # Originally designed for NDAs (2 risks) that don't need 8-chapter framework.
    # BN confidence is NOT a factor — low BN calibration doesn't make a contract simple.
    is_lightweight = risk_count <= 3
    _LIGHTWEIGHT_INSTRUCTION = (
        f"\n**报告复杂度适配（v2.16-E4）：**\n"
        f"本合同风险项较少（{risk_count}项）且BN量化模型校准有限，适用**精简报告模式**。\n"
        f"与标准8章结构不同，精简模式按以下规则撰写：\n"
        f"1. **保持完整**的章节：一（执行摘要）、三（逐条款风险分析）、六（签署建议）、七（整改行动计划）\n"
        f"2. **合并简化**的章节：\n"
        f"   - 二（风险总览）：仅保留风险项清单表格，跳过BN乘数效应详细展开（一段话简述即可）\n"
        f"   - 四（关键条款改善效果预估）：**完全省略**，不写BN数字。如需提及改善方向，在第三章修改建议中一句话带过\n"
        f"   - 五（筹码防御与谈判策略）：简化为一段核心筹码概述+关键谈判话术，不需要退让阶梯表格和三层防御详述\n"
        f"3. **总篇幅控制**：精简版报告总长度控制在标准报告的50%-60%，避免'{party_label}只有3个风险点却写了8000字谈判策略'的空洞感\n"
        f"4. 八（附录方法论）保持原样，不可省略\n"
    ) if is_lightweight else ""

    return (
        f"你是{party_label}的代理律师/商业谈判顾问，同时你是一个**受约束的报告渲染器**。"
        f"你的使命是在合法前提下，最大化{party_label}的合同利益，"
        f"并将系统提供的**结构化报告事实清单（Report Dossier）**翻译成专业、可读的中文法律报告。"
        f"\n\n"
        f"核心行为准则：\n"
        f"1. 对客户有利的条款 → 明确标注为优势，建议保留并强化\n"
        f"2. 对客户不利的条款 → 坚决要求修改，给出具体修改方案\n"
        f"3. 对手方的不利境地 → 不是你要解决的问题。不要为对手设计保护条款\n"
        f"4. 当你识别到某个条款'对双方都不公平'时 → 只从客户角度论述为什么不利，"
        f"不要提供'让双方都公平'的折中方案，除非该折中方案对客户有明显净收益\n"
        f"5. 你的修改建议必须首先通过安全性检验：这个建议是否可能被对手方利用"
        f"来损害{party_label}的利益？如果答案不确定，标注'建议人工复核'而非直接给出方案\n"
        f"6. 每一句修改建议请在攻击性结论外面包一层'为了合作顺利'的包装——"
        f"先承认对方的合理关切，再提出我方的修改要求。"
        f"报告的最终目标是促成一份对{party_label}有利且对方愿意签署的合同，而不是把对方骂走。\n"
        f"\n"
        f"**身份表述纪律（v2.16）：**\n"
        f"系统将你保护的当事人标注为{party_label}。但在原合同中，{party_label}可能对应甲方也可能对应乙方。"
        f"撰写报告时：① 报告抬头和立场声明使用{party_label}；② 正文中涉及原合同条款时，"
        f"以原合同的甲方/乙方为准，不要自行改写——例如原合同写'甲方有权解除'，你应写'甲方（即贵司）有权解除'"
        f"或'贵司作为乙方，有权要求甲方……'，具体取决于{party_label}在原合同中的实际身份；"
        f"③ 如果无法确定{party_label}在原合同中是甲方还是乙方，统一用'贵司'代替'甲方'。\n"
        f"\n"
        f"你的角色定位：\n"
        f"系统已经生成了结构化的 Report Dossier（报告事实清单），包含：\n"
        f"- 所有风险项的最终严重度、优先级、证据摘录\n"
        f"- BN 反事实概率数字\n"
        f"- 签署建议底线\n"
        f"- 人工复核标记\n"
        f"你的任务是把 Dossier 翻译成专业的中文法律报告。\n"
        f"报告的结构、风险项集合、严重度、优先级、BN数字和签署底线均来自 Dossier，\n"
        f"你负责提供：法律解释的展开、修改建议的细化、谈判话术的撰写、报告的文风和可读性。\n"
        f"\n"
        f"**绝对禁止的行为（违反即报告不合格）：**\n"
        f"- 新增 Dossier 中不存在的风险项\n"
        f"- 删除 Dossier 中的任何风险项\n"
        f"- 修改任何风险项的严重度（severity）\n"
        f"- 修改任何风险项的优先级（priority_rank）\n"
        f"- 修改或编造 BN 反事实概率数字\n"
        f"- 修改签署建议底线（signing_forbidden / signing_acceptable / negotiation_bottom_lines）\n"
        f"- 对标记为 manual_review 的风险项自行下结论而不标注'建议人工复核'\n"
        f"- 以'公平'或'合同稳定性'为由主动削弱{party_label}的既有优势\n"
        f"\n"
        f"**客户版输出边界（强制执行）：**\n"
        f"- 客户版主报告不得暴露内部编号、渲染器问责、系统冲突排查过程或“我作为渲染器”的自述。\n"
        f"- 如果系统存在 internal_conflicts 或 manual_review_items，你必须在对应条款处写“建议人工复核”，但不要展开内部机制。\n"
        f"- Dossier 中的 internal_conflicts、manual_review_items 和内部校验信息属于系统内部事实，只能作为你收敛客户版措辞的约束，不能直接展开成客户版主报告章节。\n"
        f"- 你的任务是输出可直接交付客户的正式报告正文，而不是输出系统自检记录。\n"
        f"\n"
        f"**BN数据层级规则（v2.13-C，强制执行）：**\n"
        f"法务裁决层（Dossier中的severity/priority/legal_direction/negotiation_role）是最终权威。\n"
        f"BN反事实数据必须服从法务裁决，不得推翻裁决层的结论。具体规则：\n"
        f"1. 标为「🟡 仅防守筹码说明」的BN数据：只能用于说明条款的筹码价值，**严禁**写成主动修改建议\n"
        f"   - 例如：买方视角下，责任上限/间接损失/管辖地的BN反事实数据不能诱导「买方应主动增加责任上限」\n"
        f"2. 标为「🔴 仅人工复核备注」的BN数据：必须在报告中标注「建议人工复核」，不得自行下结论\n"
        f"3. BN数据与Dossier裁决冲突时，以Dossier裁决为准，冲突写入「渲染器备注」\n"
        f"4. 如果你不确定某条BN数据的使用层级，宁可保守（标为防守筹码说明）也不要越权（写成主动修改建议）\n"
        f"\n"
        f"**BN数据可信度层级（v2.16，本报告适用）：**\n"
        f"{bn_framing}\n"
        f"\n"
        f"**有利条款处理规则：**\n"
        f"Dossier 中严重度为「positive」（✅有利）的条款是客户的既有优势，不是风险。\n"
        f"你必须：\n"
        f"- 在执行摘要和风险总览中明确标注这些是有利条款，建议保留\n"
        f"- 在谈判策略中将这些有利条款归类为「底线筹码」或「响应筹码」\n"
        f"- 绝对不要建议修改或削弱这些条款\n"
        f"- 绝对不要将有利条款列入签署条件（signing_forbidden/signing_acceptable）\n"
        f"{_LIGHTWEIGHT_INSTRUCTION}"
    )


def _chip_type(chip: NegotiationChip | None) -> str:
    return (chip.chip_type or "").strip() if chip else ""


def _format_negotiation_chip(chip: NegotiationChip | None, prefix: str) -> list[str]:
    if not chip:
        return []

    lines: list[str] = []
    chip_type = _chip_type(chip)
    if chip_type:
        lines.append(f"- {prefix}：{chip_type}")
    if chip.location:
        lines.append(f"- 筹码位置：{chip.location}")
    if chip.reason:
        lines.append(f"- 筹码理由：{chip.reason}")
    if chip.counterparty_attack:
        lines.append(f"- 对手攻击点：{chip.counterparty_attack}")
    if chip.strategy:
        lines.append(f"- 筹码策略：{chip.strategy}")
    return lines


def _inline_negotiation_chip(chip: NegotiationChip | None) -> str:
    if not chip:
        return ""

    parts: list[str] = []
    chip_type = _chip_type(chip)
    if chip_type:
        parts.append(chip_type)
    if chip.reason:
        parts.append(f"理由：{chip.reason}")
    if chip.strategy:
        parts.append(f"策略：{chip.strategy}")
    if chip.counterparty_attack:
        parts.append(f"对手攻击点：{chip.counterparty_attack}")
    if chip.location:
        parts.append(f"位置：{chip.location}")
    return "；".join(parts)


def _fmt_currency_amount(value: float | None) -> str:
    if value is None:
        return "—"
    return f"人民币{value:,.0f}元"


def _format_quantitative_context_section(quantitative_context: QuantitativeContext | None) -> list[str]:
    if quantitative_context is None:
        return []

    lines = [
        "### 定量锚点（系统确定性抽取——第三/四/五章涉及金额时必须遵守）",
        "",
    ]
    if quantitative_context.contract_amount is not None:
        source = f"（来源：{quantitative_context.amount_source_text}）" if quantitative_context.amount_source_text else ""
        lines.append(
            f"- 合同总价：{_fmt_currency_amount(quantitative_context.contract_amount)}{source}"
        )
    else:
        lines.append("- 合同总价：未识别")
    lines.append(f"- 金额换算许可：{'是' if quantitative_context.quantification_allowed else '否'}")
    lines.append("- 纪律：若合同总价缺失，第三/四/五章只能写百分比或天数，严禁自行换算金额。")

    if quantitative_context.payment_anchors:
        lines.append("")
        lines.append("| 锚点 | 百分比 | 对应金额 | 证据 | 换算公式 |")
        lines.append("|------|--------|----------|------|----------|")
        for anchor in quantitative_context.payment_anchors:
            pct = f"{anchor.percentage:.0f}%" if anchor.percentage is not None else "—"
            lines.append(
                f"| {anchor.label} | {pct} | {_fmt_currency_amount(anchor.amount)} | "
                f"{anchor.source_text or '—'} | {anchor.formula or '—'} |"
            )

    if quantitative_context.exchange_rate_hints:
        lines.append("")
        lines.append("**交换比率参考：**")
        for hint in quantitative_context.exchange_rate_hints:
            lines.append(f"- {hint}")

    if quantitative_context.warnings:
        lines.append("")
        lines.append("**定量警告：**")
        for warning in quantitative_context.warnings:
            lines.append(f"- {warning}")

    lines.append("")
    return lines


def _legal_direction_fields(
    *,
    severity: str,
    review_party: str,
    counterparty_impact: str | None,
    chip: NegotiationChip | None,
) -> tuple[str, str, str, str]:
    """Derive deterministic legal-direction fields for Dossier rendering."""
    chip_type = _chip_type(chip)
    if severity == "positive" or counterparty_impact == f"{review_party}_favorable":
        legal_direction = "favorable"
        affected_party = "review_party"
    elif counterparty_impact == f"{review_party}_unfavorable" or severity in {"critical", "high", "medium", "low"}:
        legal_direction = "unfavorable"
        affected_party = "review_party"
    elif counterparty_impact == "neutral":
        legal_direction = "neutral"
        affected_party = "both"
    else:
        legal_direction = "mixed"
        affected_party = "unknown"

    if legal_direction == "favorable":
        negotiation_role = "protect" if chip_type == "底线筹码" else "respond"
    elif chip_type == "交换筹码":
        negotiation_role = "trade"
    elif severity in {"critical", "high"}:
        negotiation_role = "must_fix"
    else:
        negotiation_role = "monitor"

    return affected_party, review_party, legal_direction, negotiation_role


def _counterfactual_takeaway(cf: CounterfactualResult, review_party: str = "buyer") -> str:
    """Generate a one-line negotiation takeaway from a counterfactual result.

    v2.13-C: Respects BN interpretation guardrails — defensive_chip_only
    counterfactuals are framed as chip value, not modification targets.
    """
    usage = _get_bn_report_usage(cf.node_name, review_party)
    best_dim = max(cf.dimension_deltas, key=lambda d: d.delta) if cf.dimension_deltas else None
    if not best_dim or best_dim.delta < 0.03:
        return "改善效果有限，不建议主动消耗谈判筹码"

    dim_label = best_dim.dimension_label
    delta_pct = best_dim.delta * 100

    if usage == "defensive_chip_only":
        return f"该数据仅说明高风险概率改善幅度约{delta_pct:.0f}个百分点——此为筹码强弱说明，**不是金钱估值，也不是主动修改建议**"
    if usage == "manual_review_note":
        return f"高风险概率改善幅度约{delta_pct:.0f}个百分点，但需结合商业背景判断——建议人工复核后再决定谈判策略"

    advice = {
        "法律可执行性风险": "补充几行条款文本即可实质性降低法律争议风险——投入产出比最高",
        "履约交付风险": "明确交付/验收节点可显著降低履约争议——优先在谈判早期解决",
        "条款失衡风险": "增加对等条款或明确双方权利义务可大幅改善合同平衡——低阻力高回报",
        "财务暴露风险": "降低资金敞口是谈判核心——但需对方做出实质让步，可作为交换筹码的核心目标",
        "争议处置风险": "优化争议解决条款可降低诉讼成本——但当前安排已较优，不宜作为谈判重心",
    }
    base = advice.get(dim_label, f"降低{dim_label}约{delta_pct:.0f}%，可作为辅助谈判目标")
    return base


def _classify_missing_clause_priority(clause_name: str) -> str:
    config_path = PROJECT_ROOT / "config" / "missing_clause_priority.yaml"
    if not config_path.exists():
        return "P1"
    with open(config_path, encoding="utf-8") as f:
        tiers = yaml.safe_load(f) or {}
    name_lower = clause_name.lower()
    for tier in ("P0", "P1"):
        keywords = tiers.get(tier, {}).get("keywords", [])
        if any(kw.lower() in name_lower for kw in keywords):
            return tier
    return "P2"


def _build_dossier(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None,
    review_party: str = "buyer",
    quantitative_context: QuantitativeContext | None = None,
) -> ReportDossier:
    """Build a structured, deterministic Report Dossier from LLM₁ + BN outputs.

    This function is the SYSTEM's truth source — no LLM involved.
    All severity, priority, evidence, and BN numbers are frozen here.
    """
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"

    # ── Map BN data for quick lookup ──
    cf_by_node: dict[str, list[CounterfactualResult]] = {}
    if consistency:
        for cf in consistency.counterfactuals:
            cf_by_node.setdefault(cf.node_name, []).append(cf)

    annotations_by_type: dict[str, list[ValidationAnnotation]] = {}
    if consistency:
        for a in consistency.annotations:
            annotations_by_type.setdefault(a.annotation_type, []).append(a)

    contradictions = annotations_by_type.get("contradiction", [])
    gap_detected = annotations_by_type.get("gap_detected", [])
    cross_dim = annotations_by_type.get("cross_dimension_risk", [])

    # ── C-1: Severity rule adjudication (post-BN, deterministic) ──
    bn_posteriors = consistency.bn_posteriors if consistency else {}
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "positive": 4}
    for seg in free_output.risk_segments:
        # Skip C-1 rules for items already marked "positive" by party-aware rules.
        # "positive" means the adjudication layer has determined this is a
        # favorable term, not a risk — BN probability thresholds should not
        # override that strategic judgment.
        if seg.severity == "positive":
            continue

        has_bn_coverage = bool(seg.suggested_bn_nodes)
        bn_high: float | None = None
        if seg.suggested_bn_nodes and bn_posteriors:
            for node in seg.suggested_bn_nodes:
                posterior = bn_posteriors.get(node, {})
                high_p = posterior.get("high", 0.0)
                if high_p > 0:
                    bn_high = max(bn_high or 0, high_p)

        # Rule 3: critical without BN coverage → downgrade
        if seg.severity == "critical" and not has_bn_coverage:
            seg.severity = "high"
        elif bn_high is not None:
            # Rule 1: BN says high risk, LLM₁ underrated → upgrade
            if bn_high > 0.6 and severity_order.get(seg.severity, 5) >= 2:
                seg.severity = "high"
            # Rule 2: BN says low risk, LLM₁ overrated → downgrade
            elif bn_high < 0.1 and seg.severity == "critical":
                seg.severity = "high"

    # ── Freeze risk items ──
    dossier_items: list[DossierRiskItem] = []
    seen_ids: set[str] = set()
    for seg in free_output.risk_segments:
        # Check BN coverage
        bn_node = None
        bn_coverage = False
        if seg.suggested_bn_nodes:
            for hint in seg.suggested_bn_nodes:
                if hint in cf_by_node:
                    bn_node = hint
                    bn_coverage = True
                    break

        # Check for BN contradiction
        manual_review = False
        internal_conflict = None
        for ca in contradictions:
            if ca.llm_clause_type and ca.llm_clause_type in (seg.clause_type, seg.risk_title):
                manual_review = True
                internal_conflict = f"BN矛盾标注: {ca.message}"
                break

        # Gap detected — missing BN dimension
        for ga in gap_detected:
            if ga.llm_clause_type and ga.llm_clause_type in (seg.clause_type, seg.risk_title):
                if not manual_review:
                    internal_conflict = f"BN缺口标注: {ga.message}"
                break

        # Priority fallback: if LLM₁ didn't set priority_rank, derive from severity
        priority = seg.priority_rank
        if priority is None:
            priority = {"critical": 1, "high": 2, "medium": 3, "low": 4, "positive": 5}.get(
                seg.severity, 3
            )

        # Stable issue_id: content-derived hash, same across runs
        ctype = seg.canonical_type or seg.clause_type
        seed = f"{ctype}|{seg.evidence_text[:80]}"
        id_hash = hashlib.sha256(seed.encode()).hexdigest()[:8]
        issue_id = f"ISSUE-{ctype[:12]}-{id_hash}"
        # Collision guard: if same hash from different segments, append index
        if issue_id in seen_ids:
            issue_id = f"{issue_id}-{len(seen_ids)}"
        seen_ids.add(issue_id)

        affected_party, review_stance, legal_direction, negotiation_role = _legal_direction_fields(
            severity=seg.severity,
            review_party=review_party,
            counterparty_impact=seg.counterparty_impact,
            chip=seg.negotiation_chip,
        )
        dossier_items.append(DossierRiskItem(
            issue_id=issue_id,
            risk_title=seg.risk_title,
            clause_type=seg.clause_type,
            canonical_type=seg.canonical_type,
            severity=seg.severity,
            priority_rank=priority,
            evidence_text=seg.evidence_text,
            confidence=seg.confidence,
            recommendation=_rewrite_unsourced_payment_thresholds(seg.recommendation, quantitative_context),
            legal_basis=seg.legal_basis,
            negotiation_chip=seg.negotiation_chip,
            counterparty_impact=seg.counterparty_impact,
            commercial_impact=seg.commercial_impact,
            affected_party=affected_party,
            review_stance=review_stance,
            legal_direction=legal_direction,
            negotiation_role=negotiation_role,
            bn_node=bn_node,
            bn_coverage=bn_coverage,
            manual_review=manual_review,
            internal_conflict=internal_conflict,
        ))

    # ── Derive signing guardrails from frozen risk items ──
    signing_forbidden: list[str] = []
    signing_acceptable: list[str] = []
    negotiation_bottom_lines: list[str] = []
    for item in dossier_items:
        if item.severity == "critical" and item.priority_rank == 1:
            signing_forbidden.append(
                f"{item.risk_title}：{item.recommendation or '必须在签署前修改'}"
            )
            negotiation_bottom_lines.append(
                f"{item.risk_title}（{item.evidence_text[:80]}...）"
            )
        elif item.severity in ("critical", "high") and item.priority_rank <= 2:
            signing_acceptable.append(
                f"{item.risk_title}：{item.recommendation or '建议修改'}"
            )

    # ── Collect manual review items ──
    manual_review_items = [item.issue_id for item in dossier_items if item.manual_review]

    # ── Detect internal consistency issues ──
    internal_conflicts: list[str] = []
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "positive": 4}
    for item in dossier_items:
        if item.internal_conflict:
            internal_conflicts.append(f"{item.issue_id} {item.risk_title}: {item.internal_conflict}")

    # ── P0-3: Chip vs signing guardrail consistency ──
    _defensive_chip_types = {"响应筹码", "底线筹码"}
    for item in dossier_items:
        chip_type = _chip_type(item.negotiation_chip)
        is_defensive = chip_type in _defensive_chip_types
        if not is_defensive:
            continue
        in_forbidden = any(item.risk_title in sf for sf in signing_forbidden)
        in_acceptable = any(item.risk_title in sa for sa in signing_acceptable)
        if in_forbidden or in_acceptable:
            conflict_msg = (
                f"内部矛盾：筹码分类为「{chip_type}」（应保留/利用的有利条款），"
                f"但被列入签署条件（要求修改）。这二者互相矛盾。"
                f"请人工核查该条款的正确处理方式。"
            )
            internal_conflicts.append(f"{item.issue_id} {item.risk_title}: {conflict_msg}")
            if item.issue_id not in manual_review_items:
                manual_review_items.append(item.issue_id)
            if not item.manual_review:
                item.manual_review = True
                item.internal_conflict = conflict_msg

    # ── P1-1: Extract favorable terms (severity == "positive" → NOT risks) ──
    from contract_risk_analysis.domain.free_review_schema import FavorableTerm
    favorable_terms: list[FavorableTerm] = []
    actual_risks: list[DossierRiskItem] = []
    for item in dossier_items:
        if item.severity == "positive":
            favorable_terms.append(FavorableTerm(
                term_name=item.risk_title,
                clause_type=item.canonical_type or item.clause_type,
                description=item.recommendation or "",
                defense_priority="坚守",
                evidence_text=item.evidence_text,
                chip_type=_chip_type(item.negotiation_chip),
                affected_party=item.affected_party,
                review_stance=item.review_stance,
                legal_direction=item.legal_direction,
                negotiation_role=item.negotiation_role,
            ))
        else:
            actual_risks.append(item)

    # ── Build dossier ──
    return ReportDossier(
        contract_id=free_output.contract_id,
        review_party=review_party,
        risk_items=actual_risks,
        favorable_terms=favorable_terms,
        counterfactuals=list(consistency.counterfactuals) if consistency else [],
        bn_annotations=list(consistency.annotations) if consistency else [],
        joint_risks=list(consistency.joint_risks) if consistency else [],
        bn_summary=consistency.bn_summary if consistency else "",
        overall_assessment=free_output.overall_assessment,
        strengths=list(free_output.strengths),
        missing_clauses=list(free_output.missing_clauses),
        signing_forbidden=signing_forbidden,
        signing_acceptable=signing_acceptable,
        negotiation_bottom_lines=negotiation_bottom_lines,
        quantitative_context=quantitative_context,
        manual_review_items=manual_review_items,
        internal_conflicts=internal_conflicts,
    )


_NUMERIC_PHRASE_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?(?:\s*[-~至]\s*\d[\d,]*(?:\.\d+)?)?(?:%|个百分点|万元|亿元|元|万)?"
)
_AMOUNT_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?(?:\s*[-~至]\s*\d[\d,]*(?:\.\d+)?)?(?:万元|亿元|元|万)")
_SOURCE_AWARE_NUMERIC_KEYWORDS = (
    "诉讼成本",
    "资金成本",
    "回收率",
    "成功率",
    "预计损失",
    "预计节省",
    "高风险概率",
    "风险概率",
    "降幅",
    "每降低",
)


def _normalize_numeric_phrase(text: str) -> str:
    return re.sub(r"[\s,，]", "", text)


def _extract_numeric_phrases(text: str) -> set[str]:
    phrases: set[str] = set()
    for match in _NUMERIC_PHRASE_RE.finditer(text):
        phrase = match.group(0).strip()
        if not phrase or not re.search(r"\d", phrase):
            continue
        if phrase in {"1", "2", "3", "4", "5"}:
            continue
        phrases.add(_normalize_numeric_phrase(phrase))
    return phrases


def _allowed_numeric_phrases(dossier: ReportDossier) -> set[str]:
    allowed: set[str] = set()

    def _ingest(text: str | None) -> None:
        if not text:
            return
        allowed.update(_extract_numeric_phrases(text))

    for item in dossier.risk_items:
        _ingest(item.evidence_text)
        _ingest(item.legal_basis)
    for ft in dossier.favorable_terms:
        _ingest(ft.evidence_text)

    quantitative_context = dossier.quantitative_context
    if quantitative_context is None:
        return allowed

    _ingest(quantitative_context.amount_source_text)
    for hint in quantitative_context.exchange_rate_hints:
        _ingest(hint)
    for warning in quantitative_context.warnings:
        _ingest(warning)
    if quantitative_context.contract_amount is not None:
        allowed.add(_normalize_numeric_phrase(_fmt_currency_amount(quantitative_context.contract_amount)))
    for anchor in quantitative_context.payment_anchors:
        _ingest(anchor.source_text)
        _ingest(anchor.formula)
        if anchor.percentage is not None:
            allowed.add(_normalize_numeric_phrase(f"{anchor.percentage:.0f}%"))
        if anchor.amount is not None:
            allowed.add(_normalize_numeric_phrase(_fmt_currency_amount(anchor.amount)))
        if anchor.days is not None:
            allowed.add(_normalize_numeric_phrase(str(anchor.days)))

    return allowed


def _rewrite_unsourced_payment_thresholds(
    text: str | None,
    quantitative_context: QuantitativeContext | None,
) -> str | None:
    if not text:
        return text

    rewritten = text
    replacements = [
        (r"不超过\s*30%", "与当前交易风险相匹配的更低比例"),
        (r"30%以下", "与当前交易风险相匹配的更低比例"),
        (r"降至\s*20%以下", "显著降低至与当前交易风险相匹配的更低水平"),
        (r"降至\s*20%", "显著降低至与当前交易风险相匹配的更低水平"),
        (r"提高至\s*10%-15%", "提高至与当前资金敞口相匹配的更充分担保水平"),
        (r"提高至\s*10%以上", "提高至与当前资金敞口相匹配的更充分担保水平"),
        (r"提高至\s*10%", "提高至与当前资金敞口相匹配的更充分担保水平"),
        (r"不低于合同总价的10%", "达到足以覆盖当前资金敞口的担保强度"),
        (r"不低于10%", "达到足以覆盖当前资金敞口的担保强度"),
    ]
    for pattern, replacement in replacements:
        rewritten = re.sub(pattern, replacement, rewritten)

    return rewritten


def _run_pre_render_consistency_checks(dossier: ReportDossier) -> list[str]:
    """v2.13-D: Run deterministic pre-render consistency checks on the dossier.

    Returns a list of violation messages. Empty list = no violations found.
    These checks catch contradictions BEFORE the LLM prompt is built, so
    the LLM can be warned about specific issues to avoid.
    """
    violations: list[str] = []

    visible_texts = [
        dossier.overall_assessment,
        *dossier.strengths,
        *dossier.missing_clauses,
        *dossier.signing_forbidden,
        *dossier.signing_acceptable,
        *dossier.negotiation_bottom_lines,
    ]
    visible_texts.extend(item.risk_title for item in dossier.risk_items)
    visible_texts.extend(item.evidence_text for item in dossier.risk_items)
    visible_texts.extend(item.recommendation or "" for item in dossier.risk_items)
    visible_texts.extend(item.legal_basis or "" for item in dossier.risk_items)
    visible_texts.extend(item.commercial_impact or "" for item in dossier.risk_items)
    visible_texts.extend(ft.term_name for ft in dossier.favorable_terms)
    visible_texts.extend(ft.description for ft in dossier.favorable_terms)
    visible_texts.extend(ft.evidence_text for ft in dossier.favorable_terms)
    if dossier.quantitative_context:
        visible_texts.append(dossier.quantitative_context.amount_source_text)
        visible_texts.extend(anchor.source_text for anchor in dossier.quantitative_context.payment_anchors)
        visible_texts.extend(anchor.formula for anchor in dossier.quantitative_context.payment_anchors)
        visible_texts.extend(dossier.quantitative_context.exchange_rate_hints)
        visible_texts.extend(dossier.quantitative_context.warnings)
    visible_texts = [text if isinstance(text, str) else str(text) for text in visible_texts]

    allowed_numeric_phrases = _allowed_numeric_phrases(dossier)

    # ── Check 1: Buyer advantage must not be rendered as buyer risk ──
    for ft in dossier.favorable_terms:
        for item in dossier.risk_items:
            if ft.term_name and ft.term_name in item.risk_title:
                violations.append(
                    f"买方优势误入风险项：有利条款「{ft.term_name}」同时出现在"
                    f"风险项「{item.risk_title}」中（severity={item.severity}）。"
                    f"该条款应在有利条款清单中，不得在风险项中作为风险论述。"
                )
            if ft.clause_type and ft.clause_type == item.canonical_type:
                violations.append(
                    f"条款类型冲突：{ft.clause_type} 既被归类为有利条款"
                    f"（{ft.term_name}），又在风险项中出现（{item.risk_title}）。"
                    f"请确认该条款的正确定性。"
                )

    # ── Check 2: Response chips must not be unconditional modification targets ──
    _response_chip_types = {"响应筹码"}
    for item in dossier.risk_items:
        chip_type = _chip_type(item.negotiation_chip)
        if chip_type not in _response_chip_types:
            continue
        in_forbidden = any(item.risk_title in sf for sf in dossier.signing_forbidden)
        if in_forbidden:
            violations.append(
                f"响应筹码误列为签署禁止条件：{item.risk_title} 筹码类型为"
                f"「响应筹码」（应等待对方提出），但被列入 signing_forbidden"
                f"（签署前必须修改）。响应筹码不应主动要求修改——"
                f"只在对方提出时作为交换条件。"
            )

    # ── Check 3: BN defensive-chip counterfactuals vs signing conditions ──
    for cf in dossier.counterfactuals:
        usage = _get_bn_report_usage(cf.node_name, dossier.review_party)
        if usage != "defensive_chip_only":
            continue
        for sf in dossier.signing_forbidden:
            if cf.node_label and cf.node_label in sf:
                violations.append(
                    f"BN护栏冲突：{cf.node_label} 的BN数据使用层级为"
                    f"「defensive_chip_only」（仅防守筹码说明），但该条款出现在"
                    f"signing_forbidden中：{sf}。BN护栏禁止将此条款写成主动修改目标，"
                    f"但签署条件要求修改——二者矛盾。"
                )

    # ── Check 4: Cross-chapter consistency (chip type → signing alignment) ──
    _defensive_chip_types = {"底线筹码", "响应筹码"}
    for item in dossier.risk_items:
        chip_type = _chip_type(item.negotiation_chip)
        if chip_type not in _defensive_chip_types:
            continue
        in_forbidden = any(item.risk_title in sf for sf in dossier.signing_forbidden)
        in_acceptable = any(item.risk_title in sa for sa in dossier.signing_acceptable)
        if in_forbidden or in_acceptable:
            violations.append(
                f"筹码-签署矛盾：{item.risk_title} 筹码分类为"
                f"「{chip_type}」（防守型，应保留/利用），"
                f"但被列为签署条件要求修改。防守型筹码不应主动放弃——"
                f"请确认：是否应将其从签署条件中移除，或将其筹码类型改为交换筹码？"
            )

    # ── Check 5: Favorable terms internal consistency ──
    for ft in dossier.favorable_terms:
        if ft.negotiation_role and ft.negotiation_role == "must_fix":
            violations.append(
                f"有利条款角色错误：{ft.term_name} 被标记为有利条款但"
                f"negotiation_role='must_fix'。有利条款不应要求必须修改。"
            )

    # ── Check 6: Customer-facing text must not leak internal IDs ──
    for text in visible_texts:
        if not text:
            continue
        match = re.search(r"ISSUE-[A-Za-z0-9_-]+", text)
        if match:
            violations.append(
                f"客户版清洁度问题：用户可见文本中出现内部编号「{match.group(0)}」。"
                f"正式报告不得暴露 ISSUE-xxxx 内部标识。"
            )

    # ── Check 7: Customer-facing text must not contain placeholders ──
    placeholder_tokens = ["【X】", "TODO", "TBD"]
    for text in visible_texts:
        if not text:
            continue
        for token in placeholder_tokens:
            if token in text:
                violations.append(
                    f"占位符问题：用户可见文本中仍包含占位符「{token}」。"
                    f"正式报告返回前必须去除所有未决占位符。"
                )

    # ── Check 8: External evaluation traces must not appear in customer-facing text ──
    external_eval_markers = ["DeepSeek", "网页评价", "AI网页端检测报告"]
    for text in visible_texts:
        if not text:
            continue
        if any(marker in text for marker in external_eval_markers):
            violations.append(
                f"客户版清洁度问题：用户可见文本「{text}」包含外部评价痕迹。"
                f"正式客户版必须基于本次独立审查结论输出，不得直接引用外部评价来源。"
            )

    # ── Check 9: Source-aware numeric claims ──
    quantification_allowed = bool(
        dossier.quantitative_context and dossier.quantitative_context.quantification_allowed
    )
    for text in visible_texts:
        if not text:
            continue
        normalized_phrases = _extract_numeric_phrases(text)
        if not normalized_phrases:
            continue

        unsupported = sorted(p for p in normalized_phrases if p not in allowed_numeric_phrases)
        if not unsupported:
            continue

        has_amount_phrase = any(_normalize_numeric_phrase(m.group(0)) in unsupported for m in _AMOUNT_TOKEN_RE.finditer(text))
        has_source_aware_keyword = any(keyword in text for keyword in _SOURCE_AWARE_NUMERIC_KEYWORDS)

        if has_amount_phrase and not quantification_allowed:
            violations.append(
                f"无来源数字问题：用户可见文本中出现金额化表述，但当前合同总价未识别，"
                f"不得自行金额换算。问题文本：「{text}」。"
                f"未获支持的数字：{', '.join(unsupported)}。"
            )
            continue

        if has_source_aware_keyword:
            violations.append(
                f"无来源数字问题：用户可见文本中出现无法追溯到合同原文或Dossier定量锚点的数字。"
                f"问题文本：「{text}」。未获支持的数字：{', '.join(unsupported)}。"
            )

    return violations


def _fmt_dossier_section(dossier: ReportDossier) -> str:
    """Format the Report Dossier as the authoritative data section for LLM₂.

    This replaces the old '信息来源一/二' split. The dossier IS the truth source.
    LLM₂ receives it as frozen facts and must render faithfully.
    """
    lines: list[str] = [
        "## 报告事实清单（Report Dossier）—— 系统最终结论",
        "",
        "以下内容由系统确定性生成，是本次审查的最终事实基线。",
        "你作为LLM₂渲染器，必须严格基于以下数据撰写报告，不得新增、删除或修改任何事实。",
        "",
    ]

    # ── Basic info ──
    lines.append(f"- 合同编号：{dossier.contract_id}")
    lines.append(f"- 审查立场：{dossier.review_party}")
    lines.append(f"- 风险项总数：{len(dossier.risk_items)}")
    lines.append(f"- 有利条款数：{len(dossier.favorable_terms)}")
    lines.append(f"- BN反事实项数：{len(dossier.counterfactuals)}")
    lines.append(f"- 需人工复核项数：{len(dossier.manual_review_items)}")
    lines.append(f"- 内部一致性冲突：{len(dossier.internal_conflicts)} 处（内部字段，客户版不得直接展开）")
    lines.append("")

    # ── Favorable terms (v2.11: party-aware) ──
    if dossier.favorable_terms:
        lines.append("### 有利条款清单（立场感知裁决——这些是优势，必须保护）")
        lines.append("")
        lines.append("以下条款对当前审查立场**有利**，LLM₂必须在报告中明确标注为优势并建议保留。")
        lines.append("**严禁**将这些条款当作风险项建议修改。")
        lines.append("")
        lines.append("| 条款 | 类型 | 法律方向 | 谈判角色 | 防御优先级 | 筹码类型 | 说明 |")
        lines.append("|------|------|---------|---------|-----------|---------|------|")
        for ft in dossier.favorable_terms:
            lines.append(
                f"| {ft.term_name} | {ft.clause_type} "
                f"| {ft.legal_direction or 'favorable'} | {ft.negotiation_role or 'protect'} "
                f"| {ft.defense_priority} | {ft.chip_type or '—'} "
                f"| {ft.description[:80]} |"
            )
        lines.append("")

    # ── Overall assessment (frozen from LLM₁) ──
    lines.append("### 执行摘要（来源：LLM₁，已冻结）")
    lines.append(dossier.overall_assessment)
    lines.append("")

    lines.extend(_format_quantitative_context_section(getattr(dossier, "quantitative_context", None)))

    # ── Risk items table (THE frozen truth) ──
    lines.append("### 风险项清单（来源：系统裁决层，已冻结——不得修改）")
    lines.append("")
    lines.append("| Issue ID | 风险项 | 条款类别 | 法律方向 | 谈判角色 | 严重度 | 优先级 | BN覆盖 | 人工复核 |")
    lines.append("|----------|--------|---------|---------|---------|--------|--------|--------|---------|")
    for item in dossier.risk_items:
        severity_emoji = {
            "critical": "🔴致命", "high": "🟠高", "medium": "🟡中",
            "low": "🟢低", "positive": "✅有利",
        }.get(item.severity, item.severity)
        bn_label = "✓" if item.bn_coverage else "—"
        mr_label = "⚠️ 是" if item.manual_review else "否"
        lines.append(
            f"| {item.issue_id} | {item.risk_title} | {item.clause_type} "
            f"| {item.legal_direction or '—'} | {item.negotiation_role or '—'} "
            f"| {severity_emoji} | P{item.priority_rank} | {bn_label} | {mr_label} |"
        )
    lines.append("")

    # ── Detailed risk items ──
    lines.append("### 风险项详情（已冻结）")
    lines.append("")
    for item in dossier.risk_items:
        lines.append(f"#### {item.issue_id}：{item.risk_title}")
        lines.append(f"- 严重度：{item.severity}（已冻结，不得修改）")
        lines.append(f"- 优先级：P{item.priority_rank}（已冻结，不得修改）")
        lines.append(f"- 审查立场：{item.review_stance or dossier.review_party}（已冻结，不得修改）")
        lines.append(f"- 法律方向：{item.legal_direction or 'unknown'}（已冻结，不得自行反向推断）")
        lines.append(f"- 谈判角色：{item.negotiation_role or 'monitor'}（已冻结，渲染时必须遵守）")
        lines.append(f"- 证据：「{item.evidence_text}」")
        if item.recommendation:
            lines.append(f"- 修改方向：{item.recommendation}")
        if item.legal_basis:
            lines.append(f"- 法律依据：{item.legal_basis}")
        lines.extend(_format_negotiation_chip(item.negotiation_chip, "筹码类型"))
        if item.commercial_impact:
            lines.append(f"- 商业影响：{item.commercial_impact}")
        if item.manual_review:
            lines.append(f"- ⚠️ **人工复核标记**：{item.internal_conflict or '系统标注需人工复核'}")
            lines.append(f"  → 报告中必须标注'建议人工复核'，不得自行下结论")
        lines.append("")

    # ── BN counterfactuals (v2.12: merged + annotated, v2.13-C: report_usage guardrails) ──
    if dossier.counterfactuals:
        lines.append("### BN反事实模拟数据（BN生成，数字已冻结——不得修改或编造）")
        lines.append("")
        lines.append("**BN数据使用层级（v2.13-C护栏）：**")
        lines.append("- 🔵 可作为主动修改建议：BN数据支持将此条款作为谈判修改目标")
        lines.append("- 🟡 仅作为防守筹码说明：BN数据说明条款价值，**严禁**写成主动修改建议")
        lines.append("- 🔴 仅作为人工复核备注：BN数据仅供参考，报告中必须标注「建议人工复核」")
        lines.append("")
        # Merge overlapping items: group by primary dimension, keep best delta per group
        cf_sorted = sorted(dossier.counterfactuals, key=lambda c: c.delta_high_risk, reverse=True)
        primary_lines: list[str] = []
        minor_items: list[str] = []
        guarded_nodes: list[str] = []
        for cf in cf_sorted:
            # Find best dimension delta
            best_dim = max(cf.dimension_deltas, key=lambda d: d.delta) if cf.dimension_deltas else None
            best_delta = best_dim.delta if best_dim else cf.delta_high_risk
            # Minor node (<5% on best dimension) -> group into summary
            if best_delta < 0.05:
                label = best_dim.dimension_label if best_dim else cf.node_label
                minor_items.append(f"{cf.node_label}（{label} -{best_delta:.1%}）")
                continue
            # Build negotiation takeaway with party awareness
            takeaway = _counterfactual_takeaway(cf, dossier.review_party)
            usage = _get_bn_report_usage(cf.node_name, dossier.review_party)
            # Annotate report_usage
            if usage == "defensive_chip_only":
                usage_label = "🟡 仅防守筹码说明"
                guarded_nodes.append(f"{cf.node_label}：{_get_bn_interpretation_note(cf.node_name, dossier.review_party)}")
            elif usage == "manual_review_note":
                usage_label = "🔴 仅人工复核备注"
                guarded_nodes.append(f"{cf.node_label}：{_get_bn_interpretation_note(cf.node_name, dossier.review_party)}")
            elif usage == "exclude_from_main":
                usage_label = "🔴 不进入主报告"
            else:
                usage_label = "🔵 可作修改建议"
            dim_text = ""
            if best_dim:
                dim_text = f" | {best_dim.dimension_label} -{best_delta:.1%}"
            primary_lines.append(
                f"| {cf.node_label} | {cf.current_state} → {cf.proposed_state}"
                f"{dim_text}"
                f" | {usage_label} | {takeaway} |"
            )
        if primary_lines:
            lines.append("| 改善措施 | 状态变化 | 主要降幅维度 | 数据使用层级 | 该数字对谈判的意义 |")
            lines.append("|---------|---------|------------|------------|-----------------|")
            lines.extend(primary_lines)
            lines.append("")
        if minor_items:
            lines.append(f"**其他次要改善项（降幅<5%）：** {'；'.join(minor_items)}。")
            lines.append("这些条款改善效果有限，不建议为此消耗谈判筹码。")
            lines.append("")
        if guarded_nodes:
            lines.append("**⚠️ BN护栏特别提醒（LLM₂必须遵守）：**")
            for note in guarded_nodes:
                lines.append(f"- {note}")
            lines.append("")
        lines.append("**要求：每个反事实项必须在第四章中出现，优先使用维度级数据，并附一句'这个数字对谈判意味着什么'的解读。**")
        lines.append("")

    # ── BN annotations ──
    if dossier.bn_annotations:
        lines.append("### BN校验标注")
        for a in dossier.bn_annotations:
            lines.append(f"- [{a.annotation_type}] {a.severity}: {a.message}")
        lines.append("")

    # ── Joint risks ──
    if dossier.joint_risks:
        lines.append("### 跨维度联合风险（乘数效应）")
        for jr in dossier.joint_risks:
            lines.append(f"- {jr}")
        lines.append("")

    # ── Signing guardrails (FROZEN) ──
    lines.append("### 签署建议底线（系统裁决——不得修改）")
    lines.append("")
    lines.append("**禁止签署的条件（一票否决）：**")
    for cond in dossier.signing_forbidden:
        lines.append(f"- {cond}")
    if not dossier.signing_forbidden:
        lines.append("- （无）")
    lines.append("")
    lines.append("**可签署的条件（必须全部满足）：**")
    for cond in dossier.signing_acceptable:
        lines.append(f"- {cond}")
    if not dossier.signing_acceptable:
        lines.append("- （无）")
    lines.append("")
    lines.append("**谈判底线：**")
    for bl in dossier.negotiation_bottom_lines:
        lines.append(f"- {bl}")
    if not dossier.negotiation_bottom_lines:
        lines.append("- （无）")
    lines.append("")

    # ── Chip linkage matrix (v2.12) ──
    all_chips: list[tuple[str, str]] = []
    for item in dossier.risk_items:
        ct = _chip_type(item.negotiation_chip)
        if ct:
            all_chips.append((item.risk_title, ct))
    for ft in dossier.favorable_terms:
        if ft.chip_type:
            all_chips.append((ft.term_name, ft.chip_type))
    if all_chips:
        lines.append("### 筹码联动交换矩阵（系统模板——LLM₂必须在第五章逐行填写）")
        lines.append("")
        lines.append("以下矩阵用于第五章筹码防御分析。LLM₂必须在第五章中逐行展开此矩阵，")
        lines.append("如本合同或定量锚点已提供可追溯数字/节点，则应引用；如未提供，则写清方向、条件和交换前提，不得为了凑完整自行补固定比例、固定金额或固定天数。")
        lines.append("禁止单向退让——每次退让必须要求对方在另一条款上做出对等让步。")
        lines.append("**填写规则：**")
        lines.append("- '量化交换比率'必须包含本合同内可追溯的具体数字或节点变化，不得套用其他合同的固定比例/天数模板")
        lines.append("- '退让阶梯'必须三档：开盘目标→可接受的中间价→最终底线，每档附带对方需做出的对应让步")
        lines.append("- 禁止使用'可考虑''建议律师准备'等空话；若缺少可追溯数字，可具体到条款号、方向、条件和交换前提，但不得编造固定阈值")
        lines.append("- 底线筹码的退让阶梯可以只写'不进入交换菜单'，但必须写清楚什么条件下才考虑交换（对方给极高对价）")
        lines.append("")
        lines.append("| 我方筹码 | 筹码类型 | 交换对象（对方哪条） | 量化交换比率 | 退让阶梯（开盘目标→可接受→底线） | 底线条件 |")
        lines.append("|---------|---------|-------------------|-------------|-------------------------------|---------|")
        for name, ct in all_chips:
            lines.append(f"| {name} | {ct} | （由LLM₂填写） | （由LLM₂填写，如'某比例/期限/节点的让步，交换另一保护条件的补强'） | 目标：→可接受：→底线： | （由LLM₂填写） |")
        lines.append("")
        lines.append("**填写规则：**")
        lines.append("- '量化交换比率'必须包含本合同内可追溯的具体数字或节点变化，不得套用其他合同的固定比例/天数模板")
        lines.append("- '退让阶梯'必须三档：开盘目标→可接受的中间价→最终底线，每档附带对方需做出的对应让步")
        lines.append("- 禁止使用'可考虑''建议律师准备'等空话——每个交换项必须具体到条款号和数字")
        lines.append("- 底线筹码的退让阶梯可以只写'不进入交换菜单'，但必须写清楚什么条件下才考虑交换（对方给极高对价）")
        lines.append("")

    # ── Strengths ──
    if dossier.strengths:
        lines.append("### 合同亮点")
        for s in dossier.strengths:
            lines.append(f"- {s}")
        lines.append("")

    # ── Missing clauses ──
    if dossier.missing_clauses:
        lines.append("### 缺失条款（按优先级分层）")
        lines.append("")
        tiered: dict[str, list[str]] = {}
        for mc in dossier.missing_clauses:
            tier = _classify_missing_clause_priority(mc)
            tiered.setdefault(tier, []).append(mc)
        tier_labels = {"P0": "签署底线——必须补充", "P1": "强烈建议——积极争取", "P2": "可谈判——视对方接受度"}
        for tier in ("P0", "P1", "P2"):
            clauses = tiered.get(tier, [])
            if not clauses:
                continue
            lines.append(f"**{tier}（{tier_labels.get(tier, '')}）：**")
            for mc in clauses:
                lines.append(f"- {mc}")
            lines.append("")

    # ── Quality flags ──
    if dossier.internal_conflicts:
        lines.append("### ⚠️ 内部一致性警告")
        lines.append("以下风险项在系统校验中被标记，报告中不得掩盖或自行解决：")
        for ic in dossier.internal_conflicts:
            lines.append(f"- {ic}")
        lines.append("")

    return "\n".join(lines)


def _fmt_llm_analysis(free_output: FreeReviewOutput) -> str:
    """Format LLM₁'s free review output as a structured prompt section."""
    lines: list[str] = [
        "### 合同基本信息",
        f"- 合同编号：{free_output.contract_id}",
    ]

    lines.append("\n### 执行摘要")
    lines.append(_rewrite_unsourced_payment_thresholds(free_output.overall_assessment, None))

    if free_output.overall_strategic_assessment:
        lines.append("\n### 战略评估")
        lines.append(_rewrite_unsourced_payment_thresholds(free_output.overall_strategic_assessment, None))

    if free_output.missing_clauses:
        lines.append("\n### 缺失条款（按优先级分层）")
        tiered_llm: dict[str, list[str]] = {}
        for mc in free_output.missing_clauses:
            tier_llm = _classify_missing_clause_priority(mc)
            tiered_llm.setdefault(tier_llm, []).append(mc)
        tier_labels_llm = {"P0": "签署底线——必须补充", "P1": "强烈建议——积极争取", "P2": "可谈判——视对方接受度"}
        for tier_llm in ("P0", "P1", "P2"):
            clauses_llm = tiered_llm.get(tier_llm, [])
            if not clauses_llm:
                continue
            lines.append(f"**{tier_llm}（{tier_labels_llm.get(tier_llm, '')}）：**")
            for mc_llm in clauses_llm:
                lines.append(f"- {mc_llm}")

    lines.append(f"\n### 识别到的风险项（共 {len(free_output.risk_segments)} 项）")
    for i, seg in enumerate(free_output.risk_segments, 1):
        severity_emoji = {
            "critical": "🔴 致命",
            "high": "🟠 高风险",
            "medium": "🟡 中风险",
            "low": "🟢 低风险",
            "positive": "✅ 有利",
        }.get(seg.severity, seg.severity)

        lines.append(f"\n**风险项 {i}：{seg.risk_title}** [{severity_emoji}]")
        lines.append(f"- 条款类别：{seg.clause_type}")
        lines.append(f"- 置信度：{seg.confidence:.0%}")
        lines.append(f"- 分析：{seg.risk_description}")
        lines.append(f"- 证据：「{seg.evidence_text}」")
        if seg.counterparty_impact:
            impact_label = {
                "buyer_favorable": "对买方有利",
                "seller_favorable": "对卖方有利",
                "neutral": "中性",
            }.get(seg.counterparty_impact, seg.counterparty_impact)
            lines.append(f"- 倾向性：{impact_label}")
        if seg.recommendation:
            lines.append(
                f"- 修改建议：{_rewrite_unsourced_payment_thresholds(seg.recommendation, None)}"
            )
        if seg.legal_basis:
            lines.append(f"- 法律依据：{seg.legal_basis}")
        inline_chip = _inline_negotiation_chip(seg.negotiation_chip)
        if inline_chip:
            lines.append(f"- 筹码分析：{inline_chip}")
        if seg.counterparty_attack_vector:
            lines.append(f"- 对手预判：{seg.counterparty_attack_vector}")
        if seg.priority_rank is not None:
            priority_labels = {1: "签约底线", 2: "核心目标", 3: "可交易", 4: "低优先级", 5: "仅供参考"}
            label = priority_labels.get(seg.priority_rank, str(seg.priority_rank))
            lines.append(f"- 谈判优先级：{seg.priority_rank}级（{label}）")
        if seg.commercial_impact:
            lines.append(f"- 商业影响：{seg.commercial_impact}")

    if free_output.strengths:
        lines.append("\n### 合同亮点（有利条款）")
        for s in free_output.strengths:
            lines.append(f"- {s}")

    return "\n".join(lines)


def _fmt_bn_validation(consistency: ConsistencyReport) -> str:
    """Format the BN consistency report as a structured prompt section."""
    lines: list[str] = []

    lines.append("### BN校验摘要")
    lines.append(consistency.bn_summary)

    # Validation annotations by type
    by_type: dict[str, list] = {}
    for a in consistency.annotations:
        by_type.setdefault(a.annotation_type, []).append(a)

    for atype, annotations in sorted(by_type.items()):
        type_labels = {
            "missing_dimension": "⚠️ 未覆盖的维度",
            "contradiction": "⚡ BN与LLM判断分歧",
            "confidence_mismatch": "📊 置信度异常",
            "causal_incoherence": "🔗 因果不一致",
            "cross_dimension_risk": "🔴 乘数效应风险",
            "gap_detected": "ℹ️ BN未覆盖的风险类型",
        }
        label = type_labels.get(atype, atype)

        lines.append(f"\n### {label}")
        for a in annotations:
            prefix = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(
                a.severity, ""
            )
            lines.append(f"- {prefix} {a.message}")

    if consistency.counterfactuals:
        lines.append("\n### 反事实模拟（BN预测的改善效果）")
        lines.append(
            "以下数据分为两层：（1）整体风险概率变化和（2）关联维度的风险概率变化。"
            "维度级数据展示了修改某条款对具体风险维度的影响，数值更有区分度，"
            "请在报告第四章中使用。"
        )
        for cf in consistency.counterfactuals:
            lines.append(f"\n- **{cf.node_label}**：{cf.description}")
            if cf.dimension_deltas:
                lines.append(f"  关联维度变化：")
                for dd in cf.dimension_deltas:
                    lines.append(
                        f"    - {dd.dimension_label}：P(high) {dd.base_high:.1%} → {dd.counterfactual_high:.1%}（降幅 {dd.delta:.1%}）"
                    )

    return "\n".join(lines)


def _build_combined_prompt(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None,
    dossier: ReportDossier,
    review_party: str = "buyer",
) -> str:
    """Build the combined prompt for LLM₂ report generation (Phase A: constrained renderer).

    Report Dossier is the AUTHORITATIVE truth source — LLM₂ must render faithfully.
    """
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"

    # Dossier section — THE authoritative truth source
    dossier_section = _fmt_dossier_section(dossier)
    llm_section = _fmt_llm_analysis(free_output)

    if consistency:
        bn_section = _fmt_bn_validation(consistency)
    else:
        bn_section = "（贝叶斯网络验证未执行。）"

    prompt = f"""你是{party_label}的代理律师，负责将系统生成的报告事实清单（Report Dossier）翻译成专业的中文合同风险审查报告。

你的唯一使命是在合法前提下最大化{party_label}的利益。

## 信息来源一：报告事实清单（Report Dossier）—— 系统最终结论，必须严格遵循

{dossier_section}

## 信息来源二：AI初审法律分析（用于展开论述和撰写话术）

以下内容提供法律分析上下文和论述素材，帮你理解每个风险项背后的法律逻辑：
{llm_section}

## 信息来源三：贝叶斯网络校验摘要（仅供参考）

{bn_section}

---

## 报告撰写要求

请根据以上三份信息，撰写一份**完整、专业、可读**的合同风险审查报告。

### 核心规则：你的角色是受约束渲染器

1. **Report Dossier 是最终事实基线。** Dossier 中的风险项集合、严重度、优先级、BN数字和签署底线已经由系统裁决层锁定。你的任务是把这些事实翻译成专业的中文法律报告，而不是重新裁决。

2. **所有风险项必须全部出现。** Dossier 中有多少条 ISSUE-xxx，报告中就必须全部覆盖。第二章（风险总览）表格列出每一项；top 3-5 项在第三章逐条深度展开；其余项在表格中简要覆盖。不得遗漏、不得删除、不得新增。

3. **严重度和优先级不得修改。** Dossier 中标注的 severity 和 priority_rank 是最终结论。你的法律分析可以解释 WHY，但不能推翻、降级或升级。

4. **BN数字必须原样使用。** 第四章反事实分析中的概率数字必须严格来自 Dossier 的 BN反事实模拟数据。不得编造、不得省略、不得修改。每个反事实项必须展示维度级delta。

5. **签署底线不得修改。** Dossier 中的 signing_forbidden / signing_acceptable / negotiation_bottom_lines 已在系统层锁定。第六章签署建议必须严格反映这些底线，可以展开论述和细化话术，但不能降低底线标准、不能增加豁免条件。
**签署底线数字纪律（强制执行）：** 第六章"禁止签署的条件""可签署的条件""谈判底线"中如果出现百分比、金额或天数目标值，这些目标值只能来自 Dossier 签署底线原文或合同原文。**严禁**在签署建议中自行补写 Dossier 中未出现的具体数字（如"30%""10%""20%"等）。如果需要给出量化标准而 Dossier 未提供，必须写成方向+条件的形式（如"预付款比例必须显著降低至覆盖资金敞口的水平，具体底线建议结合贵司现金流状况人工确定"）。签署底线的精确百分比只允许在 Dossier 已提供该数字时直接引用。

6. **人工复核标记必须传达。** Dossier 中标记为 manual_review 的风险项，报告中必须标注"建议人工复核"，并说明系统标记原因。不得自行下结论绕过人工复核。

7. **Dossier中没有的BN数字不得编造。** 明确标注"BN未对此维度进行反事实模拟"。
8. **第三/四/五章的金额数字必须服从Dossier中的定量锚点。** 只有定量锚点里已给出的合同总价、对应金额、换算公式和交换比率提示可以直接引用；系统未给出的金额不得自行补算。
9. **如果Dossier写明“金额换算许可：否”，第三/四/五章只允许写百分比/天数，不得补写任何金额、成本节省或“每调整10%=X元”。** 需要量化时，明确写“合同总价未识别，暂不进行金额换算”。
10. **去硬编码与模板隔离**：禁止把某一份合同中的固定比例、固定金额、固定期限、固定城市或固定行业惯例写成通用答案；所有具体数字、期限、金额、地点、节点都只能按本合同实际数字/节点填写。
11. **禁止样本答案回灌**：不得照搬其他报告中的现成退让阶梯、三板斧标签或固定攻击标题；所有标题、话术、让步路径都必须服务于当前合同的真实争议点。
12. **客户版清洁约束**：客户版报告不得暴露内部编号、渲染器问责或系统自检过程；客户版不得出现 ISSUE-、渲染器备注、内部一致性警告、TODO、TBD 或任何内部占位符。如果某条风险被标记为 manual_review 或存在 internal_conflicts，只写“建议人工复核”，不要展开内部机制。

### 你的法律专业能力的使用范围

虽然你是受约束渲染器，但以下方面是你的核心价值所在：
- 法律分析的展开：引用《民法典》具体条文论证风险
- 修改建议的细化：在 Dossier 给定的修改方向下，给出具体修改条款文本和谈判话术
- 谈判策略的设计：第五章筹码防御分析完全由你撰写
- 报告的文风和可读性：确保报告像资深律师写的一样专业、流畅

### BN数据使用规则（v2.13-C：层级护栏，强制执行）

**BN数据不得推翻法务裁决层。** Dossier中的severity/priority/legal_direction/negotiation_role
是系统裁决层的最终结论。BN反事实数据必须服从法务裁决，只能作为量化辅助。

Dossier的BN反事实模拟数据表格中，每条数据已标注「数据使用层级」：

- **🟡 仅防守筹码说明**：此BN数据只说明条款的筹码强弱。**严禁**在报告中写成主动修改建议。
  例如：买方视角下，责任上限/间接损失/管辖地的BN反事实数据，必须解释为
  「该条款带来的高风险概率改善幅度约X个百分点——这是筹码强弱说明，不是金钱估值，也不是修改目标」。
  **绝不可写成**「买方应主动增加责任上限」或「建议修改管辖地」。
- **🔴 仅人工复核备注**：此BN数据仅供参考。报告中必须标注「建议人工复核」，不得自行下结论。
- **🔵 可作修改建议**：此BN数据可以作为主动修改建议的量化依据。

**护栏自检清单（撰写第四章每条反事实时逐条过）：**
1. 该反事实的「数据使用层级」是什么？
2. 如果是🟡防守筹码说明 → 我的措辞是在说明筹码价值，还是在建议修改？如果是后者，重写。
3. 如果是🔴人工复核 → 我是否标注了「建议人工复核」？我是否自行下了结论？
4. 我是否在BN数据与Dossier裁决冲突时，服从了Dossier的结论？

- **维度级风险概率**（dimension_deltas）→ **第四章的主要数据源**。每个反事实项必须展示维度级delta。
- **整体风险概率**（base_high_risk → counterfactual_high_risk）→ **仅作辅助参考**。不要在报告中过度强调整体概率的绝对值。
- **所有BN百分比都表示高风险概率改善幅度或比较结果**，仅用于排序、优先级和筹码强弱判断；**不得**把这些百分比表述成直接金钱估值、收益金额或可兑现对价。

### 第四章用语规范（强制执行）

第四章面向客户管理层，必须使用商业语言，**严禁**出现以下学术/系统术语：

| 禁用术语 | 替换为 |
|---------|--------|
| P(high) | 高风险概率 |
| 反事实分析 / 反事实模拟 | 条款改善效果预估 |
| 维度级数据 | 具体风险维度的改善效果 |
| 整体级数据（辅助参考） | 合同整体参考效果 |
| BN模拟效果 | 风险改善量化评估 |
| 交叉校验判断 | 法律分析判断 |
| delta / 降幅 | 改善幅度 |
| 维度级delta | 各风险维度的改善幅度 |
| BN反事实数据 | 风险量化数据 |

第四章正文中**不得出现**"BN""贝叶斯""反事实""P(high)""delta""维度级""整体级"等标记。方法论说明统一放在第八章附录。

示例格式（每个改善预估项都采用此结构）：
```
### N. 改善XXX条款
- 风险改善量化评估：
  - [具体风险维度，主要数据] XX风险的高风险概率从A%降至B%，改善幅度C%
  - [合同整体，辅助参考] 合同整体高风险概率从D%降至E%
- 法律分析判断：[你的分析——但不得推翻Dossier中的severity/priority]
```

**第四章去重纪律**：如果多条改善预估项的核心法律判断结论完全相同（如均为"防守筹码，严禁主动修改"），必须将它们合并为一个汇总段落，格式："以下 N 项数据均指向同一结论：[结论]。具体数据如下：| 条款 | 高风险概率改善幅度 |"。**禁止**为同一结论重复展开独立段落（这会造成信息冗余，降低阅读效率）。

### 输出格式

- 使用 Markdown 格式，包含标题、表格、列表、引用块
- 语言风格：专业法律中文 + 业务可读性
- 必须严格按以下章节结构输出，不得跳过任何一章：
  ## 一、执行摘要
  ## 二、风险总览（包含BN乘数效应预警。所有LLM₁识别的风险必须全部列出，
     至少以表格形式呈现；最致命的1-2项必须给出BN联合概率乘数效应的场景化解读）
  ## 三、逐条款风险分析（top 3-5风险深度展开，其余风险在第二章表格中简要覆盖即可；若同时存在高额预付款/担保不足与质保金提交滞后，必须写成“主问题+补充子问题”的层次结构，避免重复平铺）
  ## 四、关键条款改善效果预估（基于风险量化数据）
  ## 五、筹码防御与谈判策略（必写，不可跳过，不可用"建议律师准备谈判策略"敷衍）
  ## 六、签署建议
  ## 七、整改行动计划
  ## 八、附录：方法论说明

  请按以下模板撰写，不得编造数字或数据规模：

  | 项目 | 说明 |
  |------|------|
  | 合同文本 | {{甲方/乙方}}提供的合同电子版 |
  | AI审查引擎 | LLM 自由审查 + 贝叶斯网络（BN）一致性校验 |
  | 贝叶斯网络 | CPT 参数由 CUAD 数据集（510份合同）和 ContractNLI 数据集统计校准，通过 pgmpy 变量消除法进行概率推理 |
  | 局限性 | ① BN 反事实模拟仅覆盖单一维度改善，未考虑多条款联动效应；② BN 基于统计先验，可能无法完全反映本合同特定商业背景；③ 部分条款需结合具体技术细节，建议法务和业务部门共同确认 |

### 立场规则

- 你是{party_label}的代理律师。你的每一句话、每一个建议、每一个风险判断都必须
  回答同一个问题：这对{party_label}意味着什么？
- 不要为对手方设计保护条款。如果你发现某个条款对双方都不利，只论述它对{party_label}
  的不利之处。不要主动建议"为对方设定责任上限"或"给对方增加解除权"。
- 如果你识别到某个条款对{party_label}有利（如对方违约责任上限缺失、我方拥有单方
  解除权等），明确标注为优势并建议保留。不要在谈判建议中主动让渡这些优势。

### 安全性规则（强制执行）

在给出任何修改建议前，你必须逐条检验：
1. **建议是否会实质性损害{party_label}的权利？**
   - "逾期未提异议视为接受"类的条款 → 对需要检测、试运行、第三方检测或存在隐蔽缺陷风险的标的物，可能意味着后续缺陷无法追责。设定异议期时必须考虑标的物的合理检测周期。
   - 如涉及试运行、破坏性检验或安装调试，最终确认节点不得早于完成相应验证所必需的合理周期。
2. **建议中的期限和数字是否与标的物属性匹配？**
   - 异议期、质保期、履约期限、责任上限等关键数字必须与本合同的标的物属性、履约模式和交易背景相匹配。
   - 如果不确定，标注"相关期限/比例需根据{party_label}的检测能力、履约安排和行业惯例人工复核"。
   - **责任上限数字纪律**：责任上限、赔偿排除、质保期限、异议期等数字必须优先来自合同原文、Dossier、明确行业惯例或可解释的商业背景。
     若缺少充分依据，不得凭单一案例经验直接给出固定比例、固定天数或固定金额；应明确写出“需结合标的物属性、履约模式和交易惯例人工复核”。
     不要提出明显脱离合同背景或缺乏依据的数字——这会损害报告的可信度和客户的谈判地位。
3. **这个建议在谈判中是否会被对手方用来要价？**
   - 如果会，在签署建议中提醒{party_label}准备应对策略。
4. 任何安全性检验未通过的建议，必须标注"⚠️ 建议人工复核"。

### 核心筹码防御分析（强制执行，第五章必写）

本报告**必须**包含「## 五、筹码防御与谈判策略」章节。此章不是可选的——它的重要性与执行摘要和签署建议等同。
如果跳过或用泛泛空话敷衍，报告视为不合格。

谈判筹码分为三种类型，各有不同的策略逻辑。此章按以下框架组织，每一节必须引用本合同的具体条款：

**5.1 筹码识别**

从合同具体条款出发，按三种类型识别{party_label}的谈判筹码（有几类写几类，不强制每类都有）：

- **底线筹码**：对{party_label}有利、对方强烈想改的条款。失去后{party_label}的系统性优势将永久受损。
- **交换筹码**：对{party_label}不利、但对方极度想保留的条款。{party_label}"同意做有控制的让步"本身就是交换条件。
- **响应筹码**：对{party_label}有利或中性、但对方有生存级恐惧的条款。对方必然主动要求修改——"同意修改"是最强交换牌。

对每个筹码，必须回答：它在合同第几条？属于哪种类型？为什么是筹码？对方的动机是什么？
**对每个筹码，必须预判对方律师的具体攻击话术**（例如：「贵司将管辖条款设为甲方所在地，这不符合公平原则。我们建议改为被告所在地……」）。不得使用"对方可能要求修改"等泛泛表述。

**5.2 对手主攻方向预判**

站在对方律师的角度，预判其针对每个筹码的攻击方向。必须给出具体的攻击话术示例（对方律师会怎么说），不得使用"对方可能要求修改"等泛泛表述。
每个攻击方向的小标题必须直接概括其后正文真正攻击的对象和诉求；标题与话术对象必须一一对应，禁止出现“标题写A、正文却在攻击B”的模板拼接错位。
禁止复用其他报告里的固定攻击标签（如现成的“第二斧/第三斧/解除权松绑”等）来套当前合同；如果正文主要攻击管辖、责任上限、验收或付款结构，标题必须如实反映该对象。

**质量要求**：对手攻击预判必须精确到条款号、具体比例/节点（若合同中存在）以及可验证的商业逻辑。
每一段攻击话术必须至少引用当前合同的一个具体条款号和一个本合同独有的百分比或金额（如”贵司要求80%预付款””第九条第2款的1,228万元””5%的质保金”等），以此证明该话术是针对本合同生成而非套用模板。
不得照搬其他报告的”三板斧”标签、固定数字或既有标题模板；每一轮攻击都必须从当前合同的真实争议点出发生成。

**5.3 策略设计（按筹码类型区别对待）**

**底线筹码 → 三层防御：**
1. 防守话术：论证该条款对{party_label}的合理性（为什么不应改）
2. 交换筹码：如对方极度坚持，用交换筹码或响应筹码来换，而非直接放弃底线
   - **必须指明**：用哪个具体筹码来换？换对方的哪个具体让步？如合同或 Dossier 已提供数字/节点则直接引用；否则写明方向、条件与交换前提，不得自行补固定阈值。
3. 底线划定：什么条件下才应退出谈判

**交换筹码 → 退让阶梯：**
1. 开局姿态：{party_label}的最理想目标（如更低比例、更晚风险转移、更强担保或更明确标准）
2. 退让范围：从目标到可接受底线的阶梯
   - **每一步退让都必须附带交换要求**（如：退让某个比例、期限或节点的条件，是对方接受另一项保护）。
   - **退让数字纪律（强制执行）**：三档阶梯中的**目标值**必须写成”从当前合同的 X% 降至与当前交易风险相匹配的更低水平（附保护条件）”的形式，而非”降至 Y%”。X 来自合同原文作为锚点，目标写成方向+条件而非另一个独立百分比。例如：”从 80% 降至对方提供等额履约保函覆盖的更低水平””从当前的滞后提交节点提前至买方资金敞口被担保之后”。**禁止**在退让阶梯中出现”降至 20%””降至 40%””降至 30%”等未被合同或 Dossier 直接支撑的独立目标百分比。如果没有可追溯来源，退让阶梯必须写成方向+保护条件的形式，不得在此处自行补数字。
   - 如果第六章对某付款/风险条款设置了签署底线，则本节出现比该底线更宽的退让阶梯时，必须同步写明使该退让成立的保护前提；不得把更宽的退让空间写成无条件底线。
3. 交换清单：每次退让要求对方对应让步的具体条款和可量化的交换条件

**响应筹码 → 等鱼上钩：**
1. 等待纪律：绝不主动提出修改此条款
2. 接招姿态：对方提出时，表示"这是重大让步，需要对方在对等重要的条款上配合"
3. 交换目标：明确列出用此筹码可换取哪些对方让步，按优先级排序
   - **示例**：若对方要求修改某项对己方有利的责任或程序安排，我方只能在对方同步降低核心付款风险、补强担保措施、后移风险节点或细化验收标准等前提下，考虑有限让步。

**跨筹码联动规则（强制执行）：**
- 每次在一个筹码上退让，必须要求对方在另一个筹码上做出对应让步
- 不得出现"单向让步"（我方退让了但对方什么都没给）
- 筹码之间的交换比率必须在策略中明确：若已有可追溯数字/节点，则写清「用X换Y，数字或节点如何调整」；若无，则写清「用X换Y，需要满足哪些保护条件」

注意：
- 本章不是前面逐条款分析的重复——它是谈判桌前的作战计划
- 不得使用"建议律师准备谈判策略"、"可考虑适度让步"等空话
- 每一个数字、条款号和策略步骤必须有据可依
- **第五章数字自检（完成本章后逐项过）：** 本章中出现的每一个百分比/金额/天数，是否已在 Dossier 风险项清单、定量锚点或合同证据文本中出现过？如果未出现过，将其替换为方向+保护条件的表述（如"与当前资金敞口相匹配的更低比例"），不得在此处自行补数字
- **策略结论必须与第六章（签署建议）一致**：如果某条款在第五章被归类为"响应筹码/等鱼上钩"，则在第六章不得将其列为"必须修改的签署条件"

### 第五章与第六章一致性自检（必须在生成报告后逐条验证）

- 第五章中归类为"底线筹码"的条款，如果在第六章签署条件中出现，必须在策略中明确标注"仅在对方给出极高对价时考虑交换"，否则构成矛盾
- 第五章中归类为"响应筹码"的条款，不得在第六章列为"签署前必须修改的条件"
- 如果第六章对某付款/风险条款设置了“缺少某项保护条件时不得超过X%/不得接受某节点”之类条件，第五章出现更宽退让时必须同步写出对应保护前提；若缺失该前提，视为与第六章矛盾
- 如果发现上述矛盾，在报告末尾「渲染器备注」中上报，不得在正文中掩盖

### 严禁行为

- 新增、删除或修改 Dossier 中的风险项
- 修改 Dossier 中任何风险项的严重度或优先级
- 修改或编造 BN 反事实概率数字
- 降低 Dossier 中的签署底线
- 对 manual_review 标记的风险项自行下结论而不标注"建议人工复核"
- 编造不存在的法律条文
- 在没有证据的情况下断言某条款"完善"或"合理"
- 输出JSON——这是给人类阅读的报告
- 以"公平"或"合同稳定性"为由主动削弱{party_label}的既有优势
- 在客户版主报告中暴露内部编号、渲染器问责或系统自检过程

---

现在请开始撰写最终报告。直接输出 Markdown，不要有任何前言或后记。"""

    return prompt


def generate_combined_report(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None = None,
    review_party: str = "buyer",
    strategy_mode: bool = False,
    dossier: ReportDossier | None = None,
    bn_confidence: str = "high",
    party_role_label: str | None = None,
) -> PolishedReport:
    """Generate a combined report using LLM₂ as a CONSTRAINED RENDERER (Phase A).

    Phase A: LLM₂ is demoted from "final judge" to "constrained renderer".
    The Report Dossier is the authoritative truth source — LLM₂ must render
    it faithfully into professional Chinese legal prose.

    Args:
        free_output: LLM₁'s free-form contract review (legal context).
        consistency: BN consistency validation report.
        review_party: "buyer" or "seller".
        strategy_mode: Enable strategic analysis chapter.
        dossier: Pre-built Report Dossier. If None, built automatically.

    Returns:
        PolishedReport with generation_mode="combined_phase_a".
    """
    import logging
    logger = logging.getLogger(__name__)

    # ── Build dossier if not provided ──
    if dossier is None:
        dossier = _build_dossier(free_output, consistency, review_party)

    # ── Log internal consistency issues ──
    if dossier.internal_conflicts:
        logger.warning(
            "DOSSIER_INTERNAL_CONFLICT: %s conflict(s) detected: %s",
            len(dossier.internal_conflicts),
            "; ".join(dossier.internal_conflicts[:5]),
        )
    if dossier.manual_review_items:
        logger.info(
            "DOSSIER_MANUAL_REVIEW: %s item(s) flagged: %s",
            len(dossier.manual_review_items),
            ", ".join(dossier.manual_review_items),
        )

    # ── v2.13-D: Pre-render consistency checks ──
    pre_render_violations = _run_pre_render_consistency_checks(dossier)
    if pre_render_violations:
        logger.warning(
            "PRE_RENDER_CONSISTENCY: %s violation(s) detected: %s",
            len(pre_render_violations),
            "; ".join(pre_render_violations[:5]),
        )
        for v in pre_render_violations:
            if v not in dossier.internal_conflicts:
                dossier.internal_conflicts.append(f"[渲染前校验] {v}")

    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_combined_prompt(free_output, consistency, dossier, review_party)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _combined_system_prompt(review_party, bn_confidence, len(free_output.risk_segments), party_role_label)},
            {"role": "user", "content": prompt},
        ],
        max_tokens=24576,
        temperature=0.1,  # Phase A: near-zero for stability
    )

    if not getattr(completion, "choices", None):
        raise ValueError("API 响应格式异常")
    choice = completion.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise ValueError("报告生成被截断，请增大 max_tokens。")
    content = choice.message.content
    if not content:
        raise ValueError("LLM 返回了空响应")

    markdown = _strip_think_tags(content)

    # Extract structured fields from the narrative, same parsing as v1
    result = _parse_narrative_to_polished(markdown)
    return PolishedReport(
        narrative_report=result.narrative_report,
        executive_summary=result.executive_summary,
        signing_advice=result.signing_advice,
        action_plan=result.action_plan,
        cross_dimension_notes=result.cross_dimension_notes,
        issue_reports=result.issue_reports,
        dimension_insights=result.dimension_insights,
        legal_view=result.legal_view,
        business_view=result.business_view,
        executive_view=result.executive_view,
        generation_mode="combined_phase_a",
        bn_derived_claims=result.bn_derived_claims,
        llm_judgment_claims=result.llm_judgment_claims,
    )
