from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from contract_risk_analysis.domain.free_review_schema import (
    FreeReviewOutput,
    RiskSegment,
)
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"
BN_CONFIG_PATH = PROJECT_ROOT / "config" / "bayesian_network_v2.json"


def _build_bn_checklist() -> str:
    """Build a systematic risk-dimension checklist from the BN node inventory.

    Reads all contract_fact and legal_semantics layer nodes from the BN config,
    groups them by their associated dimension, and returns a Markdown-formatted
    checklist for LLM₁ to systematically cover every dimension.

    This is the single source of truth — when BN config adds/changes nodes,
    the checklist automatically follows without prompt maintenance.
    """
    with open(BN_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    # ── Collect non-aggregate evidence-layer nodes ──
    contract_fact_nodes: list[tuple[str, str]] = []
    legal_semantics_nodes: list[tuple[str, str]] = []

    for node_name, node_cfg in config["nodes"].items():
        layer = node_cfg.get("layer", "")
        label = node_cfg.get("label", node_name)
        if node_name.startswith("cuad_agg_"):
            continue  # skip aggregate nodes
        if layer == "contract_fact":
            contract_fact_nodes.append((node_name, label))
        elif layer == "legal_semantics":
            legal_semantics_nodes.append((node_name, label))

    # ── Build the checklist ──
    lines: list[str] = [
        "## 系统性审查清单（基于BN知识图谱节点）",
        "",
        "对以下每一个维度，你必须明确判断：",
        "- **已覆盖**：合同中有相关条款 → 摘录原文并分析",
        "- **缺失**：合同中完全缺失 → 标注 missing_clauses 并简要说明可能的后果",
        "- **不适用**：与本合同性质无关 → 标注 N/A 并简要说原因",
        "",
        "### 合同基础事实层（contract_fact）",
    ]
    for name, label in contract_fact_nodes:
        lines.append(f"- [ ] {label} (`{name}`)")

    lines.append("")
    lines.append("### 法律语义层（legal_semantics）")
    for name, label in legal_semantics_nodes:
        lines.append(f"- [ ] {label} (`{name}`)")

    return "\n".join(lines)


def _get_all_evidence_node_names() -> list[str]:
    """Return all BN evidence-layer node names for the suggested_bn_nodes hint."""
    with open(BN_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    names: list[str] = []
    for node_name, node_cfg in config["nodes"].items():
        layer = node_cfg.get("layer", "")
        if layer in ("contract_fact", "legal_semantics") and not node_name.startswith("cuad_agg_"):
            names.append(node_name)
    return names


@dataclass(frozen=True)
class AIReviewSettings:
    api_key: str
    base_url: str
    model: str


def load_ai_review_settings() -> AIReviewSettings:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("缺少 OPENAI_API_KEY，请先在项目根目录 .env 中配置。")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.moonshot.ai/v1")
    model = os.getenv("OPENAI_MODEL", "kimi-k2.6")
    return AIReviewSettings(api_key=api_key, base_url=base_url, model=model)


def _nullable_string() -> dict:
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _review_result_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "contract_id": {"type": "string"},
            "review_type": _nullable_string(),
            "source_document": _nullable_string(),
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "clause_type": {"type": "string"},
                        "status": {"type": "string"},
                        "evidence_text": {"type": "string"},
                        "confidence": {"type": "number"},
                        "hypothesis": _nullable_string(),
                        "risk_factor": _nullable_string(),
                        "finding_key": _nullable_string(),
                        "finding_label": _nullable_string(),
                        "counterparty_favorability": _nullable_string(),
                    },
                    "required": [
                        "clause_type",
                        "status",
                        "evidence_text",
                        "confidence",
                        "hypothesis",
                        "risk_factor",
                        "finding_key",
                        "finding_label",
                        "counterparty_favorability",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["contract_id", "review_type", "source_document", "findings"],
        "additionalProperties": False,
    }


def _review_prompt(
    contract_text: str, contract_id: str, source_document: str | None
) -> str:
    return (
        "你是合同审查助手。请从给定合同文本中抽取结构化审查结果，只输出严格 JSON。"
        " 顶层字段必须包含 contract_id、review_type、source_document、findings。"
        " findings 中每一项都必须包含 clause_type、status、evidence_text、confidence。"
        " 如能识别更细粒度风险原子，请额外输出 finding_key、finding_label、counterparty_favorability。"
        " finding_key 应优先使用这类规范键：termination_clause_missing、termination_right_unbalanced、liability_cap_missing、indirect_damage_exposure_high、acceptance_terms_missing、governing_law_missing、dispute_resolution_missing。"
        " finding_label 使用简短中文，例如‘终止条款缺失’、‘责任上限缺失’。"
        " 当前优先识别这些 clause_type：termination、liability_cap、confidentiality、governing_law、dispute_resolution、acceptance、payment、delivery。"
        " status 必须尽量使用系统现有可识别标签，例如 missing、present、unfavorable、acceptable、contradiction、entailment、neutral。"
        " 如果文本无法支持某项，不要臆造 findings；不要输出最终总体风险结论。"
        f" contract_id 固定填 {contract_id}。"
        f" source_document 固定填 {json.dumps(source_document, ensure_ascii=False)}。"
        "\n\n合同文本如下：\n"
        f"{contract_text}"
    )


def _parse_review_result_payload(payload: dict) -> ReviewResult:
    findings_payload = payload.get("findings")
    if not isinstance(findings_payload, list):
        raise ValueError("AI 审查结果必须包含 findings 数组。")
    findings = [ReviewFinding(**item) for item in findings_payload]
    return ReviewResult(
        contract_id=payload["contract_id"],
        findings=findings,
        review_type=payload.get("review_type"),
        source_document=payload.get("source_document"),
    )


def _completion_to_payload(completion) -> dict:
    if not getattr(completion, "choices", None):
        raise ValueError("AI 响应中没有可解析的候选结果。")
    choice = completion.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise ValueError(
            "AI 响应因 token 上限被截断，请缩短合同文本或增大 max_tokens。"
        )
    content = choice.message.content
    if not content:
        raise ValueError("AI 响应中没有可解析的 JSON 文本。")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI 响应 JSON 解析失败（可能被截断）：{exc}") from exc


def review_contract_text(
    contract_text: str, contract_id: str, source_document: str | None = None
) -> ReviewResult:
    if not contract_text.strip():
        raise ValueError("合同文本不能为空。")
    settings = load_ai_review_settings()
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    completion = client.chat.completions.create(
        model=settings.model,
        messages=[
            {"role": "system", "content": "你输出的内容必须严格符合给定 JSON Schema。"},
            {
                "role": "user",
                "content": _review_prompt(contract_text, contract_id, source_document),
            },
        ],
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    payload = _completion_to_payload(completion)
    payload["contract_id"] = contract_id
    payload["source_document"] = source_document
    return _parse_review_result_payload(payload)


def review_result_to_json(review_result: ReviewResult) -> str:
    return json.dumps(asdict(review_result), ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════
#  Free-form review (v2 pipeline) — LLM₁ reviews without BN constraints
# ═══════════════════════════════════════════════════════════════════


def _free_review_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "contract_id": {"type": "string"},
            "overall_assessment": {"type": "string"},
            "risk_segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "clause_type": {"type": "string"},
                        "risk_title": {"type": "string"},
                        "risk_description": {"type": "string"},
                        "evidence_text": {"type": "string"},
                        "confidence": {"type": "number"},
                        "severity": {"type": "string"},
                        "counterparty_impact": _nullable_string(),
                        "recommendation": _nullable_string(),
                        "suggested_bn_nodes": {
                            "anyOf": [
                                {"type": "array", "items": {"type": "string"}},
                                {"type": "null"},
                            ]
                        },
                        "legal_basis": _nullable_string(),
                    },
                    "required": [
                        "clause_type",
                        "risk_title",
                        "risk_description",
                        "evidence_text",
                        "confidence",
                        "severity",
                    ],
                    "additionalProperties": False,
                },
            },
            "missing_clauses": {"type": "array", "items": {"type": "string"}},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "review_type": _nullable_string(),
            "source_document": _nullable_string(),
        },
        "required": [
            "contract_id",
            "overall_assessment",
            "risk_segments",
            "missing_clauses",
            "strengths",
        ],
        "additionalProperties": False,
    }


def _free_review_prompt(
    contract_text: str, contract_id: str, source_document: str | None
) -> str:
    checklist = _build_bn_checklist()
    all_bn_node_names = _get_all_evidence_node_names()

    return (
        "你是一位资深法务风控顾问，需要对以下合同进行全面、深入的风险审查。"
        "请输出严格JSON格式的审查结果。\n\n"
        "## 审查要求\n"
        "1. **全面覆盖**：必须系统性检查下方审查清单中的每一项。"
        "对每一项都要给出明确判断（已覆盖/缺失/不适用），不得遗漏。\n"
        "2. **深入分析**：对每项风险，不仅指出问题，更要解释为什么构成风险、"
        "对哪一方不利、可能引发什么商业后果。\n"
        "3. **证据导向**：每个发现必须附上合同原文摘录作为证据。\n"
        "4. **区分缺失与不公**：条款完全不存在标注为 missing_clauses；"
        "条款存在但内容不公平的标注在 risk_segments 中。\n"
        "5. **正面评价**：如果合同中有对客户有利的条款，也请记录在 strengths 中。\n\n"
        "## 输出字段说明\n"
        "- overall_assessment: 2-4段执行摘要，概括合同整体风险态势\n"
        "- risk_segments: 识别到的所有风险项，每项包含:\n"
        "  - clause_type: 条款类别（英文，如 payment/delivery/termination/warranty 等）\n"
        "  - risk_title: 风险标题（简练中文，如「预付款比例过高」）\n"
        "  - risk_description: 详细风险分析，说明问题和可能的商业后果\n"
        "  - evidence_text: 合同原文摘录\n"
        "  - confidence: LLM自行评估的置信度 0-1\n"
        "  - severity: 严重程度 critical/high/medium/low/positive\n"
        "  - counterparty_impact: 对哪方有利 buyer_favorable/seller_favorable/neutral\n"
        "  - recommendation: 修改建议（如适用）\n"
        "  - suggested_bn_nodes: 一个可选的BN节点名称数组，用于后续贝叶斯网络校验\n"
        f"    （可用的节点名：{', '.join(sorted(all_bn_node_names))}）\n"
        "  - legal_basis: 相关法条引用（如民法典第622条）\n"
        "- missing_clauses: 合同中完全缺失的条款类型列表\n"
        "- strengths: 合同中的有利条款或亮点\n\n"
        f"{checklist}\n\n"
        "## 重要提醒\n"
        "- 不要输出总体风险结论（由后续环节处理）\n"
        "- 如果文本无法支持某项，不要臆造\n"
        "- 请站在甲方（买方）立场进行审查\n"
        "- 清单中标注为\"不适用\"的项在risk_segments中可以省略\n"
        f"- contract_id 固定填 {contract_id}\n"
        f"- source_document 固定填 {json.dumps(source_document, ensure_ascii=False)}\n"
        "\n合同文本如下：\n"
        f"{contract_text}"
    )


def _parse_free_review_payload(payload: dict) -> FreeReviewOutput:
    segments_payload = payload.get("risk_segments")
    if not isinstance(segments_payload, list):
        raise ValueError("free review 结果必须包含 risk_segments 数组。")
    segments = [RiskSegment(**item) for item in segments_payload]
    return FreeReviewOutput(
        contract_id=payload["contract_id"],
        overall_assessment=payload.get("overall_assessment", ""),
        risk_segments=segments,
        missing_clauses=payload.get("missing_clauses", []),
        strengths=payload.get("strengths", []),
        review_type=payload.get("review_type"),
        source_document=payload.get("source_document"),
    )


def free_review_contract_text(
    contract_text: str,
    contract_id: str,
    source_document: str | None = None,
) -> FreeReviewOutput:
    """Perform a free-form contract risk review without BN node constraints.

    Unlike review_contract_text(), this does not limit the LLM to a predefined
    set of finding_key values. The LLM acts as a senior legal counsel and
    identifies any risk it finds, in any category.

    Returns FreeReviewOutput which feeds into the BN consistency validator
    (v2 pipeline) rather than the legacy evidence-mapping pipeline.
    """
    if not contract_text.strip():
        raise ValueError("合同文本不能为空。")
    settings = load_ai_review_settings()
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    completion = client.chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "system",
                "content": "你是一位资深法务风控顾问，输出必须严格符合给定JSON Schema。",
            },
            {
                "role": "user",
                "content": _free_review_prompt(
                    contract_text, contract_id, source_document
                ),
            },
        ],
        max_tokens=8192,
        response_format={"type": "json_object"},
    )
    payload = _completion_to_payload(completion)
    payload["contract_id"] = contract_id
    payload["source_document"] = source_document
    return _parse_free_review_payload(payload)


def free_review_to_legacy_result(
    free_output: FreeReviewOutput,
) -> ReviewResult:
    """Convert FreeReviewOutput to legacy ReviewResult for backward compat.

    Best-effort mapping: uses suggested_bn_nodes and clause_type heuristics
    to infer finding_key values. RiskSegments that cannot be mapped are
    dropped from the findings list.

    This adapter allows the v1 benchmark and evaluation code to consume
    v2 free-review output without modification.
    """
    from contract_risk_analysis.evidence.normalize import load_mapping_config

    mapping_config = load_mapping_config()
    finding_key_rules = mapping_config.get("finding_key_rules", {})

    # Build reverse index: node_name -> list of finding_keys
    node_to_keys: dict[str, list[str]] = {}
    for key, rule in finding_key_rules.items():
        node_name = rule["node_name"]
        node_to_keys.setdefault(node_name, []).append(key)

    findings: list[ReviewFinding] = []
    for segment in free_output.risk_segments:
        finding_key = None

        # Priority 1: use suggested_bn_nodes to find matching finding_key
        if segment.suggested_bn_nodes:
            for node_name in segment.suggested_bn_nodes:
                if node_name in node_to_keys:
                    # Pick the first key; prefer "missing" variants for missing items
                    keys = node_to_keys[node_name]
                    found = False
                    for key in keys:
                        if "missing" in key and segment.severity == "critical":
                            finding_key = key
                            found = True
                            break
                    if not found:
                        for key in keys:
                            if "unbalanced" in key or "one_sided" in key:
                                if segment.severity in ("high", "critical"):
                                    finding_key = key
                                    found = True
                                    break
                    if not found:
                        finding_key = keys[0]
                    break

        # Priority 2: map severity to status
        severity_to_status = {
            "critical": "unfavorable",
            "high": "unfavorable",
            "medium": "unfavorable",
            "low": "acceptable",
            "positive": "present",
        }
        status = severity_to_status.get(segment.severity, "neutral")

        # Priority 3: try clause type with status mapping
        if finding_key is None:
            clause_rules = mapping_config.get("clause_type_rules", {})
            if segment.clause_type in clause_rules:
                mapped = clause_rules[segment.clause_type]["state_by_status"].get(
                    status
                )
                if mapped:
                    finding_key = f"{segment.clause_type}_{mapped}"

        findings.append(
            ReviewFinding(
                clause_type=segment.clause_type,
                status=status,
                evidence_text=segment.evidence_text,
                confidence=segment.confidence,
                hypothesis=None,
                risk_factor=None,
                finding_key=finding_key,
                finding_label=segment.risk_title,
                counterparty_favorability=segment.counterparty_impact,
            )
        )

    return ReviewResult(
        contract_id=free_output.contract_id,
        findings=findings,
        review_type=free_output.review_type,
        source_document=free_output.source_document,
    )


def free_review_to_json(free_output: FreeReviewOutput) -> str:
    return json.dumps(asdict(free_output), ensure_ascii=False, indent=2)
