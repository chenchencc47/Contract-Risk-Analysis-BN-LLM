"""Post-hoc validation rules for contract text quality checks.

These rules are deterministic (regex-based), do not depend on LLM output,
and provide 100% stable coverage for common clause-quality issues that
BN existence-checking nodes cannot capture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    label: str
    severity: str  # high / medium / low
    message: str
    matched_text: str


VALIDATION_RULES: list[dict] = [
    {
        "id": "penalty_base_unreasonable",
        "label": "违约金基数可能不当",
        "pattern": r"违约金.*按.*合同[总金]|按合同[总金].*违约金",
        "severity": "medium",
        "message": "违约金可能以合同总价为基数，存在被法院调减风险（民法典第585条）",
    },
    {
        "id": "payment_guarantee_inversion",
        "label": "付款与担保时间倒挂",
        "pattern": r"支付.*尾.*款.*前.*乙方.*(?:提供|提交|开具|递交).*(?:质保金|保证金|保函)|支付.*后.*日内.*(?:质保金|保证金)",
        "severity": "high",
        "message": "可能存在先付全款再收担保的结构性倒挂，担保形同虚设",
    },
    {
        "id": "delivery_location_vague",
        "label": "交付地点模糊",
        "pattern": r"(?:收货|交付|交货)[^。]*(?:市辖区范围|甲方指定地点|乙方指定地点)(?!.*\d+号|\d+楼|\d+层)",
        "severity": "medium",
        "message": "交付地点不够精确，可能引发履约地点和运费争议",
    },
    {
        "id": "deemed_acceptance_risk",
        "label": "默示接受/视为交付风险",
        "pattern": r"视为[接验交][收付]|视为[合完]格|逾期[未不].*提出.*异议.*视为",
        "severity": "high",
        "message": "存在默示接受或视为交付条款，可能导致风险在未完成实质验收时转移",
    },
]


def _normalize_text(text: str) -> str:
    """Normalize text for rule matching: collapse whitespace between CJK characters."""
    import re
    # Remove spaces between CJK characters (common in OCR output)
    text = re.sub(r'(?<=[一-鿿㐀-䶿])\s+(?=[一-鿿㐀-䶿])', '', text)
    # Collapse multiple whitespace to single space
    text = re.sub(r'\s+', ' ', text)
    return text


def run_validation_rules(contract_text: str) -> list[RuleMatch]:
    """Scan contract text and return all rule matches."""
    if not contract_text:
        return []
    normalized = _normalize_text(contract_text)
    matches: list[RuleMatch] = []
    for rule in VALIDATION_RULES:
        pattern = re.compile(rule["pattern"])
        found = pattern.search(normalized)
        if found:
            matches.append(RuleMatch(
                rule_id=rule["id"],
                label=rule["label"],
                severity=rule["severity"],
                message=rule["message"],
                matched_text=found.group()[:100],
            ))
    return matches
