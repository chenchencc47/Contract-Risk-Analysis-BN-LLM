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

from contract_risk_analysis.constants import DIMENSION_LABELS, RISK_LABELS

# ── P2: Strategy mode section (pre-built constant to avoid f-string backslash issue) ──
_STRATEGY_SECTION = """## 八、谈判筹码与策略建议（战略层）

基于以下框架，给出具体的战略建议：
1. **筹码识别**：审查所有"优势保留"条款，逐个评估其"边际价值"是否递减——多占的部分对我方保护有限，但对对方的压迫感巨大。将这样的条款标注为"可策略性调整的筹码"。
2. **不对称风险判定**：哪些风险是"不对称致命"的——一次触发即可毁灭客户（如无限责任让24万订单毁掉公司），必须清零。
3. **交换方案**：用1换2。给出具体建议："主动将X从A%降至B%，要求对方接受Y条款"。说明我方净收益是什么。

这不是道德说教，是最冷静的商业理性——极端失衡的合同在执行中必然引发对抗，用可控的让步换取核心安全才是真正的"赢"。
"""

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


def _combined_system_prompt(review_party: str = "buyer") -> str:
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"
    return (
        f"你是{party_label}的代理律师。"
        f"你的唯一使命是在合法前提下，最大化{party_label}的合同利益。"
        f"你不是中立的合同设计者，也不是学术评论员——你是客户的代言人。"
        f"\n\n"
        f"核心行为准则：\n"
        f"1. 对客户有利的条款 → 明确标注为优势，建议保留并强化\n"
        f"2. 对客户不利的条款 → 坚决要求修改，给出具体修改方案\n"
        f"3. 对手方的不利境地 → 不是你要解决的问题。不要为对手设计保护条款\n"
        f"4. 当你识别到某个条款'对双方都不公平'时 → 只从客户角度论述为什么不利，"
        f"不要提供'让双方都公平'的折中方案，除非该折中方案对客户有明显净收益\n"
        f"5. 你的修改建议必须首先通过安全性检验：这个建议是否可能被对手方利用"
        f"来损害{party_label}的利益？如果答案不确定，标注'建议人工复核'而非直接给出方案\n"
        f"\n"
        f"你收到两份信息来源：AI初审的自由审查分析和贝叶斯网络的一致性校验结果。"
        f"BN数据是用于交叉验证的辅助工具，不是需要'中立综合'的第二信息源。"
        f"当你的法律判断与BN数据存在分歧时，以你的法律判断为准并说明理由。"
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
            "**用法**：维度级delta作主要数据，整体delta作辅助参考。"
            "整体概率是Noisy-OR聚合压缩值，绝对值偏低属正常现象，仅看delta方向。"
            "每个反事实项都附有📐推导链（条款状态→CPT来源→推理引擎→delta），请在报告中保留。"
            "所有反事实项必须全部使用，BN与手动判断不一致时需解释原因。"
        )
        for cf in consistency.counterfactuals:
            lines.append(f"\n- **{cf.node_label}**：{cf.description}")
            if cf.derivation_chain:
                lines.append(f"  📐 推导链：{cf.derivation_chain}")
            if cf.dimension_deltas:
                lines.append(f"  关联维度变化：")
                for dd in cf.dimension_deltas:
                    lines.append(
                        f"    - {dd.dimension_label}：P(high) {dd.base_high:.1%} → {dd.counterfactual_high:.1%}（降幅 {dd.delta:.1%}）"
                    )

    # P6.1: Joint probability analysis
    if consistency.joint_risks:
        lines.append("\n### 跨维度联合概率分析")
        lines.append(
            "**用法**：在报告2.2节使用P(A∩B=high)=X%+乘数因子Yx格式替代纯定性描述。"
            "乘数因子>1.3=乘数效应（需同步处理），>1.5=高危（必须重点警告）。"
        )
        for jr in consistency.joint_risks:
            if jr.get("multiplier", 1.0) > 1.1:
                lines.append(
                    f"- ⚠️ {jr['dim_a_label']} × {jr['dim_b_label']}："
                    f"P(A)={jr['p_a_high']:.1%}, P(B)={jr['p_b_high']:.1%}, "
                    f"联合P(A∩B)={jr['p_joint_high']:.1%}, "
                    f"乘数因子 {jr['multiplier']}x"
                )

    return "\n".join(lines)


def _build_combined_prompt(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None,
    review_party: str = "buyer",
    strategy_mode: bool = False,
) -> str:
    """Build the combined prompt for LLM₂ report generation.

    Strategy:
    1. LLM₁'s free review is the PRIMARY source — rich risk analysis
    2. BN's consistency report is SUPPLEMENTARY — validation notes, not constraints
    3. LLM₂ has final authority — synthesize both, resolve conflicts, write the report

    If strategy_mode=True, adds a strategic negotiation framework
    (筹码识别→不对称风险→交换方案).
    """
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"
    llm_section = _fmt_llm_analysis(free_output)

    if consistency:
        bn_section = _fmt_bn_validation(consistency)
    else:
        bn_section = "（贝叶斯网络验证未执行，报告完全基于AI审查判断。）"

    # ── Seller-specific safety rules ──
    seller_safety = ""
    if review_party == "seller":
        seller_safety = """
### ⚠️ 卖方视角专项安全规则

1. **责任上限修改的铁律**：如果你建议增加责任上限条款，**必须同时做到两件事**：
   - ① 先排除间接损失（利润损失、商誉损失、工期延误、第三方索赔等）
   - ② 再设定赔偿上限（具体比例由你结合合同金额、行业惯例和标的物属性判断，援引《民法典》第584条可预见规则论证）
   **只设上限不排除间接损失 = 承认无限赔偿义务 = 给客户挖坑。这是一个致命的法律错误。**

2. **不要将客观风险标注为"有利"**：过短的异议期（如48小时外观验收）虽然表面加速争议关闭，
   但根据《民法典》第622条，过短检验期仅视为对外观瑕疵的异议期，不能对抗内在质量索赔。
   不要将此条款标注为"对卖方有利"——它只是中性的程序条款，不是保护伞。

3. **违约金修改的对等性陷阱**：如果建议降低乙方的违约金比例，注意这可能在谈判中触发甲方
   要求同样的降低。在建议中注明"仅争取降低本方违约金，不主动给对方同等优惠"。
"""

    prompt = f"""你是{party_label}的代理律师，出具合同风险审查报告。唯一使命：合法前提下最大化{party_label}利益。

## 信息来源一：AI初审分析（主要依据）

{llm_section}

## 信息来源二：贝叶斯网络校验（辅助参考）

{bn_section}
{seller_safety}
---

## 立场差异说明

{"**你是卖方代理律师。** 卖方在合同中通常处于优势地位（付款、管辖、风险转移条款偏向卖方），因此BN反事实模拟的改善项天然少于买方视角——这不代表分析深度不足，而是因为需要修改的条款本身就少。在报告中无需为此解释或道歉，专注分析实际存在的风险即可。" if review_party == "seller" else ""}

## 核心要求

1. **AI初审为主，BN为辅**。BN是结构校验工具，不是风险评分器。BN与你的判断冲突时，以你为准并说明理由。
2. **每个风险必须回答"对我方意味着什么"**——不只是描述条款，要讲清楚商业后果。
3. **企业红线判定**：对每个高风险项，从三个维度评估是否构成"企业红线"（不可妥协的底线条款）：
   - **可量化损失**：最坏情况下触发该条款，损失是否超过合同金额的倍数？是否威胁企业生存？
   - **不可逆性**：损失能否通过后续补救挽回？（赔钱可以赚回来 vs 知识产权永久丧失）
   - **触发概率**：是在正常履约中就有较大概率触发（如验收期过短），还是仅在极小概率事件下触发？
   同时满足"损失巨大 + 不可逆 + 高触发"的，标注为 **"🔴 企业红线，不可妥协"**。
4. **建议必须可操作**：具体措辞（diff格式优先）、法律依据（民法典条款）、安全性自检。
5. **BN提供的每条反事实数据都要用**。格式：维度级delta（主要）+ 整体delta（辅助）+ 📐推导链 + 交叉校验判断。不一致时解释原因。
6. **联合概率乘数因子>1.3的组合必须重点警告**。不只是展示数字——用一句话描述它意味着什么商业场景。
   例如不要说"乘数因子 1.53x"，要说"这意味着甲方可以轻易以轻微违约为由解除合同，同时利用无限责任条款追索远超合同金额的赔偿"。
7. **不得编造任何数字**。BN未提供的数据标注"BN未对此维度进行反事实模拟"。
8. **你是律师，不是格式工具**。法律分析深度优先于格式完美。

## 让步梯度规则（P1）

当你建议削弱或消除对方的某项合同权利时（如降低违约金比例、延长对方义务期限），
**必须给出两个版本**：
- **开盘立场**：我方最理想的目标（如违约金从 10%→0%）
- **可接受底线**：仍能保护我方核心利益、对方大概率能接受的最低标准（如违约金从 10%→5%）

标注格式："若对方坚决不接受开盘立场，可退让至 [可接受底线]，但 [底线条款编号] 不可再退。"
**禁止只给一个极端数字而不给退让空间。** 一个看起来"完美"的极端建议如果让对方完全无法接受，
反而会导致整份修改方案被拒绝，连核心保护条款一起落空。

## 输出结构

## 一、执行摘要（核心结论+风险表+BN交叉验证要点）
## 二、风险总览（维度矩阵+联合概率乘数效应预警）
## 三、逐条款风险分析（原文+风险分析+对我方影响+修改建议+法律依据+安全性检验）
## 四、反事实分析与优化建议（BN数据+推导链+交叉校验+优先级排序表）
## 五、签署建议（底线条款+力争条款+优势保留+退出策略）
## 六、整改行动计划
## 七、附录：方法论说明
{_STRATEGY_SECTION if strategy_mode else ""}

## 法律引用规范

- 引用民法典条文时，确认条文号与内容准确（参考 `config/civil_code_reference.md` 精选集）
- 法律有明文规定的（如第 622 条检验期限过短、第 585 条违约金调整）→ 直接引用
- 法律无明文规定的具体数字（如"异议期 N 天""违约金 X%"）→ 结合标的物属性、行业惯例、合同金额自行推理，并说明推理依据
- 不得编造不存在的法律条文

## 格式注意

- 表格单元格内**不要使用 `|` 字符**（会被解析为列分隔符导致表格破裂）。用 `/` 或 `、` 代替。

## 严禁

编造法律条文、编造BN数字、为对手设计保护条款、以"公平"为由削弱我方优势、输出JSON。

---
直接输出 Markdown 报告："""

    return prompt


def generate_combined_report(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None = None,
    review_party: str = "buyer",
    strategy_mode: bool = False,
) -> PolishedReport:
    """Generate a combined report using LLM₂ as the authoritative writer.

    Args:
        free_output: LLM₁'s free-form contract review (primary source).
        consistency: BN consistency validation report (supplementary).
        review_party: "buyer" or "seller" — anchors LLM₂'s stance.
        strategy_mode: If True, adds strategic negotiation framework
                       (筹码识别 → 不对称风险 → 交换方案).
    """
    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_combined_prompt(free_output, consistency, review_party, strategy_mode)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _combined_system_prompt(review_party)},
            {"role": "user", "content": prompt},
        ],
        max_tokens=24576,
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
