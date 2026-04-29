"""Downstream LLM report generator.

Takes BN-structured risk data and produces a natural-language
contract risk review report in Markdown format.

The core philosophy: the LLM is a report WRITER, not a form-filler.
It receives rich structured evidence from the BN and produces a
cohesive, professional legal review document.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from contract_risk_analysis.domain.free_review_schema import (
    ConsistencyReport,
    FreeReviewOutput,
)
from contract_risk_analysis.domain.review_schema import LegalIssueReport, RiskReport

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

DIMENSION_LABELS = {
    "legal_enforceability_risk": "法律可执行性风险",
    "financial_exposure_risk": "财务暴露风险",
    "performance_delivery_risk": "履约交付风险",
    "dispute_resolution_risk": "争议处置风险",
    "clause_balance_risk": "条款失衡风险",
}

RISK_LABELS = {"high": "高风险", "medium": "中风险", "low": "低风险"}

# Standard report sections the LLM must produce
REPORT_SECTIONS = [
    "## 一、执行摘要",
    "## 二、风险总览",
    "## 三、逐条款风险分析",
    "## 四、反事实分析：改善关键条款的预期效果",
    "## 五、签署建议",
    "## 六、整改行动计划",
    "## 七、附录：贝叶斯网络推理依据",
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

### 五、签署建议
2-3 段话。明确给出签署/不签署/有条件签署的判断。如果是有条件签署，列出必须补齐的具体条件及其优先级。如果是暂不建议签署，说明风险底线在哪里。

### 六、整改行动计划
按优先级从高到低排列的整改清单（至少 3 条），每条包含：
- 整改项名称
- 负责方建议（甲方/乙方/双方）
- 建议完成时限（签署前/签署后 N 日内）
- 预期效果（完成后预计降低的风险）

### 七、附录：贝叶斯网络推理依据
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
    signing_section = _extract_section(markdown, "## 五、签署建议")
    action_section = _extract_section(markdown, "## 六、整改行动计划")

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
        max_tokens=8192,  # Increased for full report
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


def _combined_system_prompt() -> str:
    return (
        "你是一位资深法务风控顾问，同时也是一位专业法律报告撰写人。"
        "你收到两份信息来源：AI初审的自由审查分析和贝叶斯网络的一致性校验结果。"
        "你的任务是综合两份信息，撰写出最终的、权威的合同风险审查报告。"
        "你拥有最终判断权——如果AI初审和BN校验存在分歧，你应根据合同文本"
        "和相关法律知识做出独立判断，并在报告中注明分歧。"
    )


def _fmt_llm_analysis(free_output: FreeReviewOutput) -> str:
    """Format LLM₁'s free review output as a structured prompt section."""
    lines: list[str] = [
        "### 合同基本信息",
        f"- 合同编号：{free_output.contract_id}",
    ]

    lines.append("\n### 执行摘要")
    lines.append(free_output.overall_assessment)

    if free_output.missing_clauses:
        lines.append("\n### 缺失条款")
        for mc in free_output.missing_clauses:
            lines.append(f"- {mc}")

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
            lines.append(f"- 修改建议：{seg.recommendation}")
        if seg.legal_basis:
            lines.append(f"- 法律依据：{seg.legal_basis}")

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
) -> str:
    """Build the combined prompt for LLM₂ report generation.

    Strategy:
    1. LLM₁'s free review is the PRIMARY source — rich risk analysis
    2. BN's consistency report is SUPPLEMENTARY — validation notes, not constraints
    3. LLM₂ has final authority — synthesize both, resolve conflicts, write the report
    """
    llm_section = _fmt_llm_analysis(free_output)

    if consistency:
        bn_section = _fmt_bn_validation(consistency)
    else:
        bn_section = "（贝叶斯网络验证未执行，报告完全基于AI审查判断。）"

    prompt = f"""你是一位资深法务风控顾问，负责出具合同风险审查报告的最终版本。

## 信息来源一：AI初审分析（主要依据）

以下内容由AI审查助手对合同进行自由审查后得出，覆盖了合同中识别到的所有风险维度：
{llm_section}

## 信息来源二：贝叶斯网络一致性验证（辅助参考）

贝叶斯网络对上述分析进行了结构一致性校验和反事实模拟，结果如下：
{bn_section}

---

## 报告撰写要求

请根据以上两份信息，撰写一份**完整、专业、可读**的合同风险审查报告。

### 审核与判断原则

1. **AI初审分析是主要依据**：其风险识别和语义判断应作为报告的核心内容。
2. **贝叶斯网络验证仅供参考**：BN执行的是结构一致性校验而非风险判断。若BN标注的
   "gap_detected"提示了AI初审未覆盖的风险维度，请考虑补充。
   若BN标注的"contradiction"提示了LLM与BN的分歧，请以AI初审判断为主，
   并在报告中注明分歧。
3. **乘数效应风险必须重视**：若BN标注了"cross_dimension_risk"，这是系统通过
   因果模型识别出的高风险组合，其风险远超单一维度之和，必须在报告中重点提示。
4. **你拥有最终判断权**：你是资深法务顾问，不是格式化工具。请根据合同文本和
   法律知识做出独立判断。如果BN的数据与你对合同的理解冲突，以你的判断为准。
5. **反事实数据必须来自BN**：第四章反事实分析中的概率数字必须严格来自
   BN校验数据中的"反事实模拟"部分。BN提供了几条就用几条，不要自行补充。
   如果BN没有提供某维度的模拟数据，请明确标注"BN未对此维度进行反事实模拟"，
   不得自行编造概率数字。
   **重要：BN现在提供两层数据**：
   - **整体风险概率**（base_high_risk → counterfactual_high_risk）：反映对合同总体风险的影响
   - **维度级风险概率**（dimension_deltas）：反映对具体维度（如财务暴露、履约交付）的影响
   维度级数据通常数值更大、更有区分度。例如：修改付款条款可能只降低整体风险5%，
   但能将「财务暴露风险」从95%降至45%。**请优先在报告中使用维度级数据**，
   因为它能更直观地展示改善效果。整体风险概率作为辅助参考。
6. **交叉校验反事实排序与风险评级**：BN反事实模拟的排序基于因果图权重，可能
   与你前文基于合同语义的风险评级不完全一致。在撰写第四章时，请执行以下步骤：
   - 先列出BN提供的所有反事实数据（按整体delta降序，同时展示维度级delta）
   - 然后对照前文的风险评级：如果BN整体delta认为降幅最大的条款，你前文评为较低风险，请
    主动标注差异，并给出你的独立判断——可以坚持前文评级（附带理由）、也可以
    采纳BN建议（说明为什么BN的视角有道理）、或两者兼顾
   - 注意：维度级delta往往与你的手动评级更一致。如果某条款的维度级delta很大
    但整体delta很小，说明该条款对该维度的影响是真实显著的，可以据此调整优先级
   - 最终给读者的建议优先顺序，必须是你综合判断后的结果，标签清楚哪些来自BN数据、
    哪些是你的法务判断
   示例表述："BN整体模拟显示终止条款修改降幅最大（13.5%），但维度级数据显示
   付款结构改善可将「财务暴露风险」从95%降至45%（降幅50%），与手动评级一致。
   考虑到本合同付款结构已构成致命风险，本报告认为付款条款的谈判优先级最高。
   BN的整体排序偏向终止条款是因为其因果权重模型，但维度级数据支持了付款优先的判断。"

### 输出格式

- 使用 Markdown 格式，包含标题、表格、列表、引用块
- 语言风格：专业法律中文 + 业务可读性
- 推荐以下章节结构（可按需调整）：
  ## 一、执行摘要
  ## 二、风险总览（包含BN乘数效应预警）
  ## 三、逐条款风险分析
  ## 四、反事实分析与优化建议（引用BN模拟数据）
  ## 五、签署建议
  ## 六、整改行动计划
  ## 七、附录：方法论说明

### 严禁行为

- 不得编造不存在的法律条文
- 不得在没有证据的情况下断言某条款"完善"或"合理"
- 不得在证据不足时做出确定的结论
- 不得编造或补充反事实分析中的概率数字
- 不得输出JSON——这是给人类阅读的报告

---

现在请开始撰写最终报告。直接输出 Markdown，不要有任何前言或后记。"""

    return prompt


def generate_combined_report(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None = None,
) -> PolishedReport:
    """Generate a combined report using LLM₂ as the authoritative writer.

    Unlike polish_report() which treats BN output as unchangeable facts,
    this function treats LLM₁'s analysis as primary evidence and BN
    validation as supplementary checks. LLM₂ has final authority to
    reconcile conflicts and produce the definitive report.

    Args:
        free_output: LLM₁'s free-form contract review (primary source).
        consistency: BN consistency validation report (supplementary).

    Returns:
        PolishedReport with generation_mode="combined".
    """
    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_combined_prompt(free_output, consistency)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _combined_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8192,
        temperature=0.5,
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
        generation_mode="combined",
        bn_derived_claims=result.bn_derived_claims,
        llm_judgment_claims=result.llm_judgment_claims,
    )
