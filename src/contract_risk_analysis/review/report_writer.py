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

# Standard report sections the LLM must produce
REPORT_SECTIONS = [
    "## 一、执行摘要",
    "## 二、风险总览",
    "## 三、逐条款风险分析",
    "## 四、反事实分析：改善关键条款的预期效果",
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


def _combined_system_prompt(review_party: str = "buyer") -> str:
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"
    return (
        f"你是{party_label}的代理律师/商业谈判顾问。"
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

    if free_output.overall_strategic_assessment:
        lines.append("\n### 战略评估")
        lines.append(free_output.overall_strategic_assessment)

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
        if seg.negotiation_chip:
            lines.append(f"- 筹码分析：{seg.negotiation_chip}")
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
    review_party: str = "buyer",
) -> str:
    """Build the combined prompt for LLM₂ report generation.

    Strategy:
    1. LLM₁'s free review is the PRIMARY source — rich risk analysis
    2. BN's consistency report is SUPPLEMENTARY — validation notes, not constraints
    3. LLM₂ has final authority — synthesize both, resolve conflicts, write the report
    """
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"
    llm_section = _fmt_llm_analysis(free_output)

    if consistency:
        bn_section = _fmt_bn_validation(consistency)
    else:
        bn_section = "（贝叶斯网络验证未执行，报告完全基于AI审查判断。）"

    prompt = f"""你是{party_label}的代理律师，负责出具合同风险审查报告的最终版本。

你的唯一使命是在合法前提下最大化{party_label}的利益。

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
   **LLM₁ 识别的所有风险项必须全部出现在报告中**。第二章（风险总览）的表格必须列出每一项；
   top 3-5 项在第三章逐条深度展开；其余项在表格中简要覆盖。不得遗漏或删除 LLM₁ 已识别的风险。
2. **贝叶斯网络验证仅供参考**：BN执行的是结构一致性校验而非风险判断。若BN标注的
   "gap_detected"提示了AI初审未覆盖的风险维度，请考虑补充。
   若BN标注的"contradiction"提示了LLM与BN的分歧，请以AI初审判断为主，
   并在报告中注明分歧。
3. **乘数效应风险必须重视**：若BN标注了"cross_dimension_risk"，这是系统通过
   因果模型识别出的高风险组合，其风险远超单一维度之和，必须在报告中重点提示。
4. **你拥有最终判断权**：你是资深法务顾问，不是格式化工具。请根据合同文本和
   法律知识做出独立判断。如果BN的数据与你对合同的理解冲突，以你的判断为准。
5. **反事实数据必须来自BN，且必须用完所有BN提供的数据**：第四章反事实分析中的
   概率数字必须严格来自BN校验数据中的"反事实模拟"部分。
   **BN提供了几条就必须全部使用，不得挑选、不得遗漏。**
   如果BN没有提供某维度的模拟数据，请明确标注"BN未对此维度进行反事实模拟"，
   不得自行编造概率数字。

   **BN提供两层数据，请按以下规则使用**：

   - **维度级风险概率**（dimension_deltas）→ **第四章的主要数据源**。
     维度级数据直观展示修改某条款对具体风险维度的影响（如：修改付款条款→财务暴露风险
     从35.8%降至18.4%，降幅17.3%）。这些数字区分度大、与手动风险评级高度一致，
     是报告中最有说服力的量化证据。**每个反事实项必须展示其维度级delta。**

   - **整体风险概率**（base_high_risk → counterfactual_high_risk）→ **仅作辅助参考**。
     整体概率是BN通过Noisy-OR聚合五个维度后的压缩值，数学上必然低于各维度的实际
     风险概率（例如维度级P(high)=35-78%时，整体通常只有20-35%）。
     **不要在报告中过度强调整体概率的绝对值，也不要将其与维度级概率并列对比**
     ——它们是不同层级的数据，直接对比会造成混淆。
     整体概率的用处仅在于展示"改善前后有变化"，delta的方向和相对大小有意义，
     绝对值意义不大。

   示例格式（每个反事实项都采用此结构）：
   ```
   ### N. 改善XXX条款
   - BN模拟效果：
     - [维度级，主要数据] XX风险的高概率从A%降至B%，降幅C%
     - [整体级，辅助参考] 合同整体高风险概率从D%降至E%
   - 交叉校验判断：[你的独立分析]
   ```

6. **交叉校验每个反事实项**：对BN提供的每一个反事实模拟结果：
   - 先展示BN数据（维度级在前，整体级在后）
   - 然后给出你独立的"交叉校验判断"：BN数据与前文手动评级是否一致？
     一致→说明相互印证、增强可信度。不一致→解释原因并给出你的最终判断
   - 所有反事实项分析完毕后，给出一张整合的"优先级排序表"，明确列出
     每个条款的谈判优先级（最高/高/中）、建议措施和依据（BN数据 + 法务判断）

### 输出格式

- 使用 Markdown 格式，包含标题、表格、列表、引用块
- 语言风格：专业法律中文 + 业务可读性
- 必须严格按以下章节结构输出，不得跳过任何一章：
  ## 一、执行摘要
  ## 二、风险总览（包含BN乘数效应预警。所有LLM₁识别的风险必须全部列出，
     至少以表格形式呈现；最致命的1-2项必须给出BN联合概率乘数效应的场景化解读）
  ## 三、逐条款风险分析（top 3-5风险深度展开，其余风险在第二章表格中简要覆盖即可）
  ## 四、反事实分析与优化建议（引用BN模拟数据）
  ## 五、筹码防御与谈判策略（必写，不可跳过，不可用"建议律师准备谈判策略"敷衍）
  ## 六、签署建议
  ## 七、整改行动计划
  ## 八、附录：方法论说明

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
   - "逾期未提异议视为接受"类的条款 → 对需要检测/试用的货物（煤炭、建材、设备等）
     可能意味着隐蔽缺陷无法追责。设定异议期时必须考虑标的物的检验特性。
   - 质量异议期的设定必须长于标的物合理检测所需时间（如煤炭需试烧→至少30天）。
2. **建议中的期限和数字是否与标的物属性匹配？**
   - 不要对需要破坏性检验或长周期试用的货物设定短于15个工作日的异议期。
   - 如果不确定，标注"异议期长度需根据{party_label}的检测能力确认"。
   - **责任上限数字基准**：合同行业中，责任上限的谈判起点通常是合同金额的100%。
     低于50%在商业谈判中几乎不可能被对方接受。质保期对建材产品（如瓷砖）通常为12-24个月。
     不要提出明显脱离行业惯例的数字——这会损害报告的可信度和客户的谈判地位。
3. **这个建议在谈判中是否会被对手方用来要价？**
   - 如果会，在签署建议中提醒{party_label}准备应对策略。
4. 任何安全性检验未通过的建议，必须标注"⚠️ 建议人工复核"。

### 核心筹码防御分析（强制执行，第五章必写）

本报告**必须**包含「## 五、筹码防御与谈判策略」章节。此章不是可选的——它的重要性与执行摘要和签署建议等同。
如果跳过或用泛泛空话敷衍，报告视为不合格。

此章必须包含三个子节，每一节都必须引用本合同的具体条款：

**5.1 筹码识别**

从合同的具体条款出发，识别{party_label}的 1-2 个**核心谈判筹码**。筹码是指：
- {party_label}拥有、但对方有强烈动机去修改的条款
- 一旦失去，{party_label}的交易地位将显著恶化

对每个筹码，必须回答：它在合同第几条？为什么是筹码？对方为什么想改它？
（例如：第五条付款结构——发货前到账90%，对方会认为钱货风险不对等。）

**5.2 对手主攻方向预判**

站在对方律师的角度，预测其最可能从哪个筹码下手、用什么法律或商业理由。
必须给出具体的攻击话术示例（对方律师会怎么说），而不是泛泛的"对方可能要求修改"。

（例如：甲方律师会说："贵司在未交付任何货物前已收取90%货款，这构成显失公平。
我方要求在验收合格后再支付发货款部分，即改为预付30%+验收后付60%+质保金10%。"）

**5.3 防御策略**

针对 5.2 的攻击，给出三层回应：

1. **防守话术**：如何论证该筹码的合理性？
   （例如：预付款+发货款是建材行业标准做法，瓷砖为定制化产品，乙方需提前备料排产，
   90%预收款是锁定产能的必要保障，并非不合理条款。）
2. **交换筹码**：如果必须让步，用什么次要条款交换？
   （例如：若对方坚持调整付款比例，可退让至预付30%+发货前付30%+货到后付30%+质保金10%，
   但要求对方同时让步——在责任上限条款上接受100%上限+排除间接损失。）
3. **底线划定**：什么条件下应该退出谈判？
   （例如：若对方要求改为"货到验收后付全款"，则付款结构优势完全丧失，建议退出。）

注意：
- 本章不是前面逐条款分析的重复——它是谈判桌前的作战计划
- 不得使用"建议律师准备谈判策略"、"可考虑适度让步"等空话
- 每一个防守话术和交换方案必须有具体的数字、条款号和可执行的措辞

### 严禁行为

- 不得编造不存在的法律条文
- 不得在没有证据的情况下断言某条款"完善"或"合理"
- 不得在证据不足时做出确定的结论
- 不得编造或补充反事实分析中的概率数字
- 不得输出JSON——这是给人类阅读的报告
- 不得以"公平"或"合同稳定性"为由主动削弱{party_label}的既有优势

---

现在请开始撰写最终报告。直接输出 Markdown，不要有任何前言或后记。"""

    return prompt


def generate_combined_report(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None = None,
    review_party: str = "buyer",
    strategy_mode: bool = False,
) -> PolishedReport:
    """Generate a combined report using LLM₂ as the authoritative writer.

    Unlike polish_report() which treats BN output as unchangeable facts,
    this function treats LLM₁'s analysis as primary evidence and BN
    validation as supplementary checks. LLM₂ has final authority to
    reconcile conflicts and produce the definitive report.

    Args:
        free_output: LLM₁'s free-form contract review (primary source).
        consistency: BN consistency validation report (supplementary).
        review_party: "buyer" or "seller" — anchors LLM₂'s stance.

    Returns:
        PolishedReport with generation_mode="combined".
    """
    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_combined_prompt(free_output, consistency, review_party)

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
