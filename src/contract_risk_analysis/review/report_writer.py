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

from contract_risk_analysis.domain.free_review_schema import (
    ConsistencyReport,
    CounterfactualResult,
    DossierRiskItem,
    FreeReviewOutput,
    NegotiationChip,
    ReportDossier,
    ValidationAnnotation,
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
        f"**渲染器备注机制（纠错上报）：**\n"
        f"如果你在撰写报告时发现 Dossier 中的某项结论（严重度、优先级、签署建议等）\n"
        f"与你的法律判断存在实质性冲突，你不得自行修改。但你必须：\n"
        f"1. 在报告中仍然按照 Dossier 的结论撰写（遵守渲染器纪律）\n"
        f"2. 在报告末尾增加「## 渲染器备注」章节\n"
        f"3. 在该章节中逐条列出：哪个风险项的哪个字段，Dossier结论是什么，\n"
        f"   你的法律判断是什么，为什么你认为可能存在错误，建议人工复核\n"
        f"这个机制是为了在保持报告稳定性的同时，不压制你的法律专业判断。\n"
        f"没有冲突时不需要写此章节。\n"
        f"\n"
        f"**有利条款处理规则：**\n"
        f"Dossier 中严重度为「positive」（✅有利）的条款是客户的既有优势，不是风险。\n"
        f"你必须：\n"
        f"- 在执行摘要和风险总览中明确标注这些是有利条款，建议保留\n"
        f"- 在谈判策略中将这些有利条款归类为「底线筹码」或「响应筹码」\n"
        f"- 绝对不要建议修改或削弱这些条款\n"
        f"- 绝对不要将有利条款列入签署条件（signing_forbidden/signing_acceptable）\n"
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


def _build_dossier(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None,
    review_party: str = "buyer",
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

        dossier_items.append(DossierRiskItem(
            issue_id=issue_id,
            risk_title=seg.risk_title,
            clause_type=seg.clause_type,
            canonical_type=seg.canonical_type,
            severity=seg.severity,
            priority_rank=priority,
            evidence_text=seg.evidence_text,
            confidence=seg.confidence,
            recommendation=seg.recommendation,
            legal_basis=seg.legal_basis,
            negotiation_chip=seg.negotiation_chip,
            counterparty_impact=seg.counterparty_impact,
            commercial_impact=seg.commercial_impact,
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
        manual_review_items=manual_review_items,
        internal_conflicts=internal_conflicts,
    )


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
    lines.append(f"- 内部一致性冲突：{len(dossier.internal_conflicts)} 处")
    lines.append("")

    # ── Favorable terms (v2.11: party-aware) ──
    if dossier.favorable_terms:
        lines.append("### 有利条款清单（立场感知裁决——这些是优势，必须保护）")
        lines.append("")
        lines.append("以下条款对当前审查立场**有利**，LLM₂必须在报告中明确标注为优势并建议保留。")
        lines.append("**严禁**将这些条款当作风险项建议修改。")
        lines.append("")
        lines.append("| 条款 | 类型 | 防御优先级 | 筹码类型 | 说明 |")
        lines.append("|------|------|-----------|---------|------|")
        for ft in dossier.favorable_terms:
            lines.append(
                f"| {ft.term_name} | {ft.clause_type} "
                f"| {ft.defense_priority} | {ft.chip_type or '—'} "
                f"| {ft.description[:80]} |"
            )
        lines.append("")

    # ── Overall assessment (frozen from LLM₁) ──
    lines.append("### 执行摘要（来源：LLM₁，已冻结）")
    lines.append(dossier.overall_assessment)
    lines.append("")

    # ── Risk items table (THE frozen truth) ──
    lines.append("### 风险项清单（来源：系统裁决层，已冻结——不得修改）")
    lines.append("")
    lines.append("| Issue ID | 风险项 | 条款类别 | 严重度 | 优先级 | BN覆盖 | 人工复核 |")
    lines.append("|----------|--------|---------|--------|--------|--------|---------|")
    for item in dossier.risk_items:
        severity_emoji = {
            "critical": "🔴致命", "high": "🟠高", "medium": "🟡中",
            "low": "🟢低", "positive": "✅有利",
        }.get(item.severity, item.severity)
        bn_label = "✓" if item.bn_coverage else "—"
        mr_label = "⚠️ 是" if item.manual_review else "否"
        lines.append(
            f"| {item.issue_id} | {item.risk_title} | {item.clause_type} "
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

    # ── BN counterfactuals (frozen numbers) ──
    if dossier.counterfactuals:
        lines.append("### BN反事实模拟数据（BN生成，数字已冻结——不得修改或编造）")
        lines.append("")
        for cf in dossier.counterfactuals:
            lines.append(f"#### {cf.node_label}")
            lines.append(f"- 当前状态：{cf.current_state} → 建议状态：{cf.proposed_state}")
            lines.append(f"- 整体高风险概率：{cf.base_high_risk:.1%} → {cf.counterfactual_high_risk:.1%}（Δ={cf.delta_high_risk:.1%}）")
            if cf.dimension_deltas:
                lines.append(f"- 维度级数据（主要数据源）：")
                for dd in cf.dimension_deltas:
                    lines.append(f"  - {dd.dimension_label}：{dd.base_high:.1%} → {dd.counterfactual_high:.1%}（降幅{dd.delta:.1%}）")
            if cf.derivation_chain:
                lines.append(f"- 推导链：{cf.derivation_chain}")
            lines.append(f"- BN说明：{cf.description}")
            lines.append("")
        lines.append("**要求：每个反事实项必须在第四章中出现，维度级数据为主，整体级为辅助。**")
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

    # ── Strengths ──
    if dossier.strengths:
        lines.append("### 合同亮点")
        for s in dossier.strengths:
            lines.append(f"- {s}")
        lines.append("")

    # ── Missing clauses ──
    if dossier.missing_clauses:
        lines.append("### 缺失条款")
        for mc in dossier.missing_clauses:
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

6. **人工复核标记必须传达。** Dossier 中标记为 manual_review 的风险项，报告中必须标注"建议人工复核"，并说明系统标记原因。不得自行下结论绕过人工复核。

7. **Dossier中没有的BN数字不得编造。** 明确标注"BN未对此维度进行反事实模拟"。

### 你的法律专业能力的使用范围

虽然你是受约束渲染器，但以下方面是你的核心价值所在：
- 法律分析的展开：引用《民法典》具体条文论证风险
- 修改建议的细化：在 Dossier 给定的修改方向下，给出具体修改条款文本和谈判话术
- 谈判策略的设计：第五章筹码防御分析完全由你撰写
- 报告的文风和可读性：确保报告像资深律师写的一样专业、流畅

### BN数据使用规则

- **维度级风险概率**（dimension_deltas）→ **第四章的主要数据源**。每个反事实项必须展示维度级delta。
- **整体风险概率**（base_high_risk → counterfactual_high_risk）→ **仅作辅助参考**。不要在报告中过度强调整体概率的绝对值。

示例格式（每个反事实项都采用此结构）：
```
### N. 改善XXX条款
- BN模拟效果：
  - [维度级，主要数据] XX风险的高概率从A%降至B%，降幅C%
  - [整体级，辅助参考] 合同整体高风险概率从D%降至E%
- 交叉校验判断：[你的分析——但不得推翻Dossier中的severity/priority]
```

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
   - "逾期未提异议视为接受"类的条款 → 对需要检测/试用的货物（煤炭、建材、设备等）
     可能意味着隐蔽缺陷无法追责。设定异议期时必须考虑标的物的检验特性。
   - 质量异议期的设定必须长于标的物合理检测所需时间（如煤炭需试烧→至少30天）。
2. **建议中的期限和数字是否与标的物属性匹配？**
   - 不要对需要破坏性检验或长周期试用的货物设定短于15个工作日的异议期。
   - 如果不确定，标注"异议期长度需根据{party_label}的检测能力确认"。
   - **责任上限数字基准**：合同行业中，责任上限的谈判起点通常是合同金额的100%。
     低于50%在商业谈判中几乎不可能被对方接受。
     **绝对禁止建议低于合同总价100%的责任上限**（如"30%"）。如果因公司合规要求必须加入责任上限，
     底线必须是合同总价的100%。低于100%意味着对方只需退还少量款项即可免除全部赔偿责任，
     对{party_label}是灾难性的。质保期对建材产品（如瓷砖）通常为12-24个月。
     不要提出明显脱离行业惯例的数字——这会损害报告的可信度和客户的谈判地位。
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

**质量标杆**：报告-2（DeepSeek 9.49/10）在本节预判了对手的"三板斧"——
①攻击付款结构、②换取解除权松绑、③要求均等权利——每一斧都有具体话术和精确数字。
你的对手攻击预判也应达到同等水准：精确到条款号、具体百分比、可验证的商业逻辑。

**5.3 策略设计（按筹码类型区别对待）**

**底线筹码 → 三层防御：**
1. 防守话术：论证该条款对{party_label}的合理性（为什么不应改）
2. 交换筹码：如对方极度坚持，用交换筹码或响应筹码来换，而非直接放弃底线
   - **必须指明**：用哪个具体筹码来换？换对方的哪个具体让步？数字是多少？
3. 底线划定：什么条件下才应退出谈判

**交换筹码 → 退让阶梯：**
1. 开局姿态：{party_label}的最理想目标（含具体数字，如"降至30%"）
2. 退让范围：从目标到可接受底线的阶梯（如：目标30%→可接受40%→底线50%）
   - **每一步退让都必须附带交换要求**（如："退至40%的条件是对方接受风险转移节点推迟至终验"）
3. 交换清单：每次退让要求对方对应让步的具体条款和数字

**响应筹码 → 等鱼上钩：**
1. 等待纪律：绝不主动提出修改此条款
2. 接招姿态：对方提出时，表示"这是重大让步，需要对方在对等重要的条款上配合"
3. 交换目标：明确列出用此筹码可换取哪些对方让步，按优先级排序
   - **示例**：「对方要求加入责任上限→我方可用此换取：①预付款降至20%+履约保函（无条件）；②风险转移节点推迟至终验（最低）；③明确验收标准（次低）」

**跨筹码联动规则（强制执行）：**
- 每次在一个筹码上退让，必须要求对方在另一个筹码上做出对应让步
- 不得出现"单向让步"（我方退让了但对方什么都没给）
- 筹码之间的交换比率必须在策略中明确：「用X换Y，数字从A调到B」

注意：
- 本章不是前面逐条款分析的重复——它是谈判桌前的作战计划
- 不得使用"建议律师准备谈判策略"、"可考虑适度让步"等空话
- 每一个数字、条款号和策略步骤必须有据可依
- **策略结论必须与第六章（签署建议）一致**：如果某条款在第五章被归类为"响应筹码/等鱼上钩"，则在第六章不得将其列为"必须修改的签署条件"

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

---

现在请开始撰写最终报告。直接输出 Markdown，不要有任何前言或后记。"""

    return prompt


def generate_combined_report(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None = None,
    review_party: str = "buyer",
    strategy_mode: bool = False,
    dossier: ReportDossier | None = None,
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

    api_key, base_url, model = _load_polish_settings()
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _build_combined_prompt(free_output, consistency, dossier, review_party)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _combined_system_prompt(review_party)},
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
