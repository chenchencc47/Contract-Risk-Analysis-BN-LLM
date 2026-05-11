from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from contract_risk_analysis.domain.free_review_schema import (
    FreeReviewOutput,
    NegotiationChip,
    RiskSegment,
)
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"
BN_CONFIG_PATH = PROJECT_ROOT / "config" / "bayesian_network_v2.json"
CONTRACT_TYPE_ROUTING_PATH = PROJECT_ROOT / "config" / "contract_type_routing.yaml"
COMPANY_REDLINES_PATH = PROJECT_ROOT / "config" / "company_redlines.yaml"


@dataclass(frozen=True)
class ContractTypeRoutingResult:
    primary_type: str | None
    matched_types: list[str]
    selected_nodes: list[str]
    confidence: float


def load_contract_type_routing_config() -> dict:
    with open(CONTRACT_TYPE_ROUTING_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_company_redlines(matched_types: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Load company redline rules filtered by matched contract types.

    Returns (hard_rules, reasoning_hints) — both lists of dicts with keys:
    id, label, description, severity.
    """
    if not COMPANY_REDLINES_PATH.exists():
        return [], []
    with open(COMPANY_REDLINES_PATH, encoding="utf-8") as f:
        all_sections: dict = yaml.safe_load(f) or {}

    hard_rules: list[dict] = []
    reasoning_hints: list[dict] = []

    def _collect(section: dict) -> None:
        hard_rules.extend(section.get("hard_rules", []))
        reasoning_hints.extend(section.get("reasoning_hints", []))

    if matched_types:
        for contract_type in matched_types:
            section = all_sections.get(contract_type)
            if isinstance(section, dict):
                _collect(section)

    general = all_sections.get("通用")
    if isinstance(general, dict):
        _collect(general)

    return hard_rules, reasoning_hints


def _format_redlines_section(hard_rules: list[dict], reasoning_hints: list[dict]) -> str:
    if not hard_rules and not reasoning_hints:
        return ""
    lines: list[str] = []

    if hard_rules:
        lines.extend([
            "## 公司红线（不可妥协的底线原则）",
            "",
            "以下规则来自公司风险政策，审查时必须逐条对照，违反即为不可接受：",
        ])
        for r in hard_rules:
            level = r.get("severity", r.get("level", ""))
            label = r.get("label", r.get("id", ""))
            desc = r.get("description", "")
            lines.append(f"- [{level}] {label}：{desc}")
        lines.append("")

    if reasoning_hints:
        lines.extend([
            "## 推理指引（结合行业惯例与标的属性判断，不套用固定数字）",
            "",
        ])
        for h in reasoning_hints:
            label = h.get("label", h.get("id", ""))
            desc = h.get("description", "")
            lines.append(f"- {label}：{desc}")
        lines.append("")

    return "\n".join(lines)


def detect_contract_type_routing(contract_text: str) -> ContractTypeRoutingResult:
    config = load_contract_type_routing_config()
    universal_core = config.get("universal_core", {}).get("nodes", [])
    contract_types = config.get("contract_types", {})
    text_triggers = config.get("text_triggers", {})
    low_confidence_threshold = float(
        config.get("fallback", {}).get("low_confidence_threshold", 0.0)
    )
    text = contract_text.lower()

    scored_types: list[tuple[str, float]] = []
    best_type: str | None = None
    best_score = 0.0
    for contract_type, type_cfg in contract_types.items():
        keywords = type_cfg.get("keywords", [])
        if not keywords:
            continue
        match_count = sum(1 for keyword in keywords if str(keyword).lower() in text)
        score = match_count / len(keywords)
        if score > 0:
            scored_types.append((contract_type, score))
        if score > best_score:
            best_type = contract_type
            best_score = score

    matched_types = [
        contract_type for contract_type, score in scored_types if score >= low_confidence_threshold
    ]

    selected_nodes = list(dict.fromkeys(universal_core))
    for contract_type in matched_types:
        selected_nodes.extend(
            node for node in contract_types.get(contract_type, {}).get("nodes", [])
            if node not in selected_nodes
        )

    for trigger_cfg in text_triggers.values():
        trigger_words = trigger_cfg.get("any_of", [])
        if any(str(word).lower() in text for word in trigger_words):
            selected_nodes.extend(
                node for node in trigger_cfg.get("nodes", [])
                if node not in selected_nodes
            )

    return ContractTypeRoutingResult(
        primary_type=best_type,
        matched_types=matched_types,
        selected_nodes=selected_nodes,
        confidence=best_score,
    )


def _build_bn_checklist(contract_text: str | None = None) -> str:
    """Build a systematic risk-dimension checklist from the BN node inventory.

    Reads all contract_fact and legal_semantics layer nodes from the BN config,
    groups them by their associated dimension, and returns a Markdown-formatted
    checklist for LLM₁ to systematically cover every dimension.

    This is the single source of truth — when BN config adds/changes nodes,
    the checklist automatically follows without prompt maintenance.
    """
    with open(BN_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    bn_node_names = set(config["nodes"])
    selected_names: set[str] | None = None
    if contract_text:
        routing_config = load_contract_type_routing_config()
        low_confidence_threshold = float(
            routing_config.get("fallback", {}).get("low_confidence_threshold", 0.0)
        )
        routing_result = detect_contract_type_routing(contract_text)
        unknown_nodes = sorted(
            node for node in routing_result.selected_nodes if node not in bn_node_names
        )
        if unknown_nodes:
            raise ValueError(
                "合同类型路由配置包含未定义的 BN 节点: "
                + ", ".join(unknown_nodes)
            )
        if (
            routing_result.matched_types
            and routing_result.selected_nodes
        ):
            selected_names = set(routing_result.selected_nodes)

    # ── Collect non-aggregate evidence-layer nodes ──
    contract_fact_nodes: list[tuple[str, str]] = []
    legal_semantics_nodes: list[tuple[str, str]] = []

    for node_name, node_cfg in config["nodes"].items():
        layer = node_cfg.get("layer", "")
        label = node_cfg.get("label", node_name)
        if node_name.startswith("cuad_agg_"):
            continue  # skip aggregate nodes
        if selected_names is not None and node_name not in selected_names:
            continue
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
    lines.append("### 法律语义层（legal_semantics)")
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
                        "negotiation_chip": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "chip_type": _nullable_string(),
                                        "location": _nullable_string(),
                                        "reason": _nullable_string(),
                                        "counterparty_attack": _nullable_string(),
                                        "strategy": _nullable_string(),
                                    },
                                    "required": [
                                        "chip_type",
                                        "location",
                                        "reason",
                                        "counterparty_attack",
                                        "strategy",
                                    ],
                                    "additionalProperties": False,
                                },
                                {"type": "null"},
                            ]
                        },
                        "counterparty_attack_vector": _nullable_string(),
                        "priority_rank": {"anyOf": [{"type": "integer", "minimum": 1, "maximum": 5}, {"type": "null"}]},
                        "commercial_impact": _nullable_string(),
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
            "overall_strategic_assessment": _nullable_string(),
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

def _build_chip_instruction(review_party: str, party_label: str) -> str:
    """Build perspective-aware chip identification instructions for LLM₁."""
    if review_party == "buyer":
        examples = (
            "例：管辖在己方住所地——对方必然攻击'管辖不公'，但这是程序优势底线。\n"
            "② **交换筹码** — 对己方不利但对方极度想保留的条款。策略原则：主动出牌——"
            "用'愿意在此条款上做有控制的让步'换取对方在底线条款上的妥协。"
            "例：过高的预付款比例——买方想降至30%，卖方想保80%，"
            "买方'同意只降到50%而非30%'即可交换卖方的其他让步。\n"
            "③ **响应筹码** — 对己方有利或中性，但对方有生存级恐惧、必然主动要求修改的条款。"
            "策略原则：绝不主动提出修改；等对方提出时，将'同意修改'作为交换条件。"
            "例：合同中未排除间接损失——卖方恐惧无限赔偿敞口，"
            "买方可用'同意加入间接损失排除'换取卖方在付款结构上的让步。\n"
        )
    else:
        examples = (
            "例：付款节点在发货前（先款后货）——买方可能要求改为验收后付款，"
            "但这是卖方现金流安全的核心保障。\n"
            "② **交换筹码** — 对己方不利但对方极度想保留的条款。策略原则：主动出牌——"
            "用'愿意在此条款上做有控制的让步'换取对方在底线条款上的妥协。"
            "例：过低的预付款比例——卖方想提高至50%，买方想压到10%，"
            "卖方'同意只提到30%而非50%'即可交换买方在其他条款上的让步。\n"
            "③ **响应筹码** — 对己方有利或中性，但对方有生存级恐惧、必然主动要求修改的条款。"
            "策略原则：绝不主动提出修改；等对方提出时，将'同意修改'作为交换条件。"
            "例：买方拥有过于宽泛的单方解除权——买方不希望失去合同灵活性，"
            "卖方可用'同意加入合理限制'换取买方在付款结构上的让步。\n"
        )
    return (
        f"7. **筹码识别**：按以下三类框架，识别合同中对{party_label}的谈判筹码。"
        "有则识别，无则不填——并非每类都在每份合同中存在。"
        "对每个筹码，填入 negotiation_chip 对象，字段固定为 chip_type、location、reason、"
        f"counterparty_attack、strategy（均可为字符串或 null，不得输出额外字段）。\n"
        f"① **底线筹码** — 对{party_label}有利且对方强烈想改的条款。一旦失去，"
        f"{party_label}的系统性优势将永久受损。策略原则：寸步不让，不列入交换菜单。"
        + examples
    )


def _free_review_prompt(
    contract_text: str, contract_id: str, source_document: str | None,
    review_party: str = "buyer",
) -> str:
    checklist = _build_bn_checklist(contract_text=contract_text)
    all_bn_node_names = _get_all_evidence_node_names()
    party_label = "甲方（买方）" if review_party == "buyer" else "乙方（卖方）"
    counterparty_label = "乙方（卖方）" if review_party == "buyer" else "甲方（买方）"

    routing = detect_contract_type_routing(contract_text)
    hard_rules, reasoning_hints = load_company_redlines(routing.matched_types)
    redlines_section = _format_redlines_section(hard_rules, reasoning_hints)
    chip_instruction = _build_chip_instruction(review_party, party_label)

    return (
        f"你是{party_label}的代理律师/商业谈判顾问，需要对以下合同进行全面、深入"
        "的风险审查和博弈分析。请输出严格JSON格式的审查结果。\n\n"
        "## 审查要求\n"
        f"1. **立场**：审查必须始终站在{party_label}立场。"
        f"对{party_label}有利的条款要去识别并标注为 strengths；"
        f"对{party_label}不利或可能损害{party_label}利益的条款才是风险项。\n"
        "2. **全面覆盖**：必须系统性检查下方审查清单中的每一项。"
        "对每一项都要给出明确判断（已覆盖/缺失/不适用），不得遗漏。\n"
        "3. **深入分析**：对每项风险，不仅指出问题，更要解释为什么构成风险、"
        f"对{party_label}可能引发什么商业后果（包括现金流、运营效率、合作关系等商业层面影响）。\n"
        "4. **证据导向**：每个发现必须附上合同原文摘录作为证据。\n"
        "5. **区分缺失与不公**：条款完全不存在标注为 missing_clauses；"
        "条款存在但内容不公平的标注在 risk_segments 中。\n"
        f"6. **正面评价**：如果合同中有对{party_label}有利的条款，也请记录在 strengths 中。\n"
        f"{chip_instruction}"
        "8. **对手预判**：对每个高风险项，预测对方律师可能从哪些角度发起攻击："
        "法律角度（如'显失公平'、'违反强制性规定'）、商业角度（如'行业惯例并非如此'、"
        "'影响合作意愿'）、策略角度（如'用次要条款换取对我方不利的修改'）。"
        "结果填入 counterparty_attack_vector 字段。\n"
        "9. **优先级排序**：对每个风险项按谈判紧迫性和严重性给出 1-5 级优先级"
        "（填入 priority_rank 字段）："
        "1=签约底线（必须修改，否则不建议签署）；2=核心谈判目标（尽最大努力争取）；"
        "3=可交易项（可让步换取更高优先级目标）；"
        "4=低优先级（接受或仅做提示）；5=仅供参考（不影响谈判立场）。\n"
        "10. **商业影响评估**：对每个风险项，在 commercial_impact 字段中评估其商业层面影响，"
        f"包括对{party_label}的现金流压力、运营效率、合作关系、市场竞争力等。\n\n"
        "## 条款质量审查要点（请逐条对照审查，不得遗漏）\n"
        "1. **付款与担保的时间逻辑**：审查付款节点与担保措施的时间顺序——"
        "是否存在[先付全款再收担保]的结构性倒挂？质保金/履约保证金应在付款前提交，"
        "否则担保形同虚设。\n"
        "2. **违约金计算基数是否合理**：违约金以什么为基数计算？"
        "以[合同总价]为基数可能显失公平（民法典第585条）。"
        "逾期交货违约金宜以[迟交部分价值]为基数，逾期付款违约金以[未付款金额]为基数。\n"
        "3. **交付地点是否精确到具体地址**：仅写[某市辖区范围内]或[甲方指定地点]"
        "属于合同漏洞，应标记为风险。\n"
        "4. **是否存在[视为交付/验收]语言陷阱**：注意区分[外观验收]和[风险转移]——"
        "外观签字不等于货物风险转移。存在[签字即视为交付]、"
        "[逾期未提出异议视为合格]等表述时必须标注风险。\n\n"
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
        "  - negotiation_chip: （可选）对象，包含 chip_type、location、reason、counterparty_attack、strategy，所有字段均可为字符串或 null\n"
        "  - counterparty_attack_vector: （可选）对手攻击预判\n"
        "  - priority_rank: （可选）谈判优先级 1-5\n"
        "  - commercial_impact: （可选）商业影响分析（现金流、运营等）\n"
        "- missing_clauses: 合同中完全缺失的条款类型列表\n"
        "- strengths: 合同中的有利条款或亮点\n"
        "- overall_strategic_assessment: （可选）整体战略评估，包括核心筹码概括、力量对比和建议谈判姿态\n\n"
        f"{checklist}\n\n"
        f"{redlines_section}\n"
        "## 重要提醒\n"
        "- 不要输出总体风险结论（由后续环节处理）\n"
        "- 如果文本无法支持某项，不要臆造\n"
        f"- 审查立场：{party_label}。你不为中立方或{counterparty_label}的利益考虑\n"
        "- 清单中标注为\"不适用\"的项在risk_segments中可以省略\n"
        f"- contract_id 固定填 {contract_id}\n"
        f"- source_document 固定填 {json.dumps(source_document, ensure_ascii=False)}\n"
        "\n合同文本如下：\n"
        f"{contract_text}"
    )


def _parse_negotiation_chip(value: object) -> NegotiationChip | None:
    if value is None:
        return None
    if isinstance(value, dict):
        required_keys = {
            "chip_type",
            "location",
            "reason",
            "counterparty_attack",
            "strategy",
        }
        actual_keys = set(value)
        if actual_keys != required_keys:
            missing_keys = sorted(required_keys - actual_keys)
            extra_keys = sorted(actual_keys - required_keys)
            details: list[str] = []
            if missing_keys:
                details.append(f"缺少字段: {', '.join(missing_keys)}")
            if extra_keys:
                details.append(f"存在额外字段: {', '.join(extra_keys)}")
            raise ValueError(f"negotiation_chip 对象字段不合法（{'；'.join(details)}）。")
        for key in required_keys:
            field_value = value[key]
            if field_value is not None and not isinstance(field_value, str):
                raise ValueError(f"negotiation_chip.{key} 必须是字符串或 null。")
        return NegotiationChip(
            chip_type=value["chip_type"],
            location=value["location"],
            reason=value["reason"],
            counterparty_attack=value["counterparty_attack"],
            strategy=value["strategy"],
        )
    if isinstance(value, str):
        chip_type = value if value in {"底线筹码", "交换筹码", "响应筹码"} else None
        return NegotiationChip(
            chip_type=chip_type,
            reason=value,
        )
    raise ValueError("negotiation_chip 必须是对象、字符串或 null。")



def _parse_free_review_payload(payload: dict) -> FreeReviewOutput:
    segments_payload = payload.get("risk_segments")
    if not isinstance(segments_payload, list):
        raise ValueError("free review 结果必须包含 risk_segments 数组。")
    segments: list[RiskSegment] = []
    for item in segments_payload:
        normalized = dict(item)
        normalized["negotiation_chip"] = _parse_negotiation_chip(item.get("negotiation_chip"))
        segments.append(RiskSegment(**normalized))
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
    review_party: str = "buyer",
) -> FreeReviewOutput:
    """Perform a free-form contract risk review without BN node constraints.

    Unlike review_contract_text(), this does not limit the LLM to a predefined
    set of finding_key values. The LLM acts as a senior legal counsel and
    identifies any risk it finds, in any category.

    Args:
        review_party: "buyer" or "seller" — anchors LLM₁'s review stance.

    Returns FreeReviewOutput which feeds into the BN consistency validator
    (v2 pipeline) rather than the legacy evidence-mapping pipeline.
    """
    if not contract_text.strip():
        raise ValueError("合同文本不能为空。")
    settings = load_ai_review_settings()
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    for attempt in range(2):
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
                        contract_text, contract_id, source_document, review_party
                    ),
                },
            ],
            max_tokens=16384,
            response_format={"type": "json_object"},
        )
        try:
            payload = _completion_to_payload(completion)
            payload["contract_id"] = contract_id
            payload["source_document"] = source_document
            return _parse_free_review_payload(payload)
        except ValueError as exc:
            if "JSON 解析失败" not in str(exc) or attempt == 1:
                raise

    raise AssertionError("unreachable")


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
