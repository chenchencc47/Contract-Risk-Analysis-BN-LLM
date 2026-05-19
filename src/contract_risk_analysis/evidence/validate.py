"""Evidence quality validation and confidence adjustment.

P2.1 + P2.2 + P2.4: Checks each LLM-produced finding for quality,
downgrades confidence on weak evidence, and flags ambiguous cases.
"""

from __future__ import annotations

from dataclasses import dataclass

import re


# Minimum length for evidence_text to be considered credible
MIN_EVIDENCE_LENGTH = 10

# Confidence threshold below which we set state to "unknown"
UNKNOWN_CONFIDENCE_THRESHOLD = 0.55

# Multiplier applied to confidence when evidence quality check fails
QUALITY_PENALTY_FACTOR = 0.50

# Multiplier applied when evidence_text is empty but status is "present"
EMPTY_EVIDENCE_PENALTY = 0.35


RELEVANCE_KEYWORDS: dict[str, list[str]] = {
    "termination": ["终止", "解除", "终止合同", "退", "违约", "解约",
                     "terminat", "cancel", "rescind", "breach"],
    "liability_cap": ["责任", "赔偿", "损失", "免责", "上限", "限制", "违约金",
                      "liabilit", "damage", "indemnif", "cap"],
    "confidentiality": ["保密", "机密", "秘密", "披露", "confidential",
                        "disclos", "secret", "proprietary", "nda"],
    "governing_law": ["法律", "管辖", "适用法", "法院", "governing law",
                      "applicable law", "jurisdiction", "arbitrat"],
    "dispute_resolution": ["争议", "仲裁", "诉讼", "纠纷", "协商",
                           "dispute", "arbitrat", "litigat", "court", "法院"],
    "acceptance": ["验收", "合格", "确认", "交付标准", "接受",
                   "acceptance", "approval", "inspection"],
    "payment": ["付款", "支付", "价款", "金额", "费用", "payment", "price", "fee", "invoice"],
    "delivery": ["交付", "交货", "发货", "delivery", "shipment", "transport"],
}


@dataclass(frozen=True)
class EvidenceQuality:
    """Quality assessment for a single finding's evidence."""

    finding_key: str | None
    clause_type: str
    status: str
    evidence_text: str
    raw_confidence: float

    is_quality_ok: bool
    adjusted_confidence: float
    flags: list[str]

    @property
    def should_be_unknown(self) -> bool:
        """Whether this finding is too uncertain and should be 'unknown'."""
        return self.adjusted_confidence < UNKNOWN_CONFIDENCE_THRESHOLD


def _check_length(evidence_text: str) -> tuple[bool, str]:
    """Check evidence_text meets minimum length."""
    if not evidence_text or not evidence_text.strip():
        return False, "证据文本为空"
    if len(evidence_text.strip()) < MIN_EVIDENCE_LENGTH:
        return False, f"证据文本过短（{len(evidence_text.strip())}字符 < {MIN_EVIDENCE_LENGTH}）"
    return True, ""


def _check_semantic_relevance(evidence_text: str, clause_type: str) -> tuple[bool, str]:
    """Check evidence_text contains keywords relevant to clause_type."""
    if not evidence_text or not evidence_text.strip():
        return False, "无法检查语义相关性（证据为空）"
    keywords = RELEVANCE_KEYWORDS.get(clause_type, [])
    if not keywords:
        return True, ""
    text_lower = evidence_text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True, ""
    return False, f"证据文本与条款类型「{clause_type}」关键词不匹配"


def _check_status_consistency(status: str, evidence_text: str) -> tuple[bool, str]:
    """Check status is consistent with evidence presence."""
    if status == "present" and (not evidence_text or not evidence_text.strip()):
        return False, "状态为present但证据文本为空"
    if status == "missing" and evidence_text and len(evidence_text.strip()) >= MIN_EVIDENCE_LENGTH:
        text = evidence_text.strip().lower()
        # Allow "no X found", "does not contain", "未发现" etc. for missing status
        if not any(phrase in text for phrase in (
            "no ", "not ", "未发现", "未找到", "没有", "不存在", "缺失",
            "does not", "doesn't", "cannot find", "not found",
        )):
            return False, "状态为missing但存在较长证据文本（可能误判）"
    return True, ""


def _check_generic_text(evidence_text: str) -> tuple[bool, str]:
    """Detect generic/non-specific evidence that looks like LLM fabrication."""
    if not evidence_text or not evidence_text.strip():
        return True, ""
    text = evidence_text.strip()
    # Patterns suggesting LLM invented rather than excerpted
    generic_patterns = [
        r"^(该|本|此|上述|前述).*(条款|规定|约定|合同).*(存在|明确|约定|包含|涉及|规定)",
        r"^(根据|依据).*(条款|规定|法律|法)",
        r"^合同.*(存在|包含|涉及|约定|规定).*(条款|内容)",
        r"^(未发现|未找到|没有).*(条款|规定|内容)",
    ]
    for pattern in generic_patterns:
        if re.search(pattern, text):
            return False, f"证据疑似LLM生成而非原文摘录：{text[:50]}..."
    return True, ""


def assess_evidence_quality(
    finding_key: str | None,
    clause_type: str,
    status: str,
    evidence_text: str,
    raw_confidence: float,
) -> EvidenceQuality:
    """Evaluate the quality of a single finding's evidence.

    Returns EvidenceQuality with adjusted confidence and quality flags.
    """
    flags: list[str] = []
    adjusted = raw_confidence

    # 1. Length check — only for non-missing status
    if status != "missing":
        length_ok, length_flag = _check_length(evidence_text)
        if not length_ok:
            flags.append(length_flag)

    # 2. Status consistency
    status_ok, status_flag = _check_status_consistency(status, evidence_text)
    if not status_ok:
        flags.append(status_flag)
        adjusted *= EMPTY_EVIDENCE_PENALTY

    # 3. Semantic relevance (only if we have text and status != missing)
    if evidence_text and evidence_text.strip() and status != "missing":
        rel_ok, rel_flag = _check_semantic_relevance(evidence_text, clause_type)
        if not rel_ok:
            flags.append(rel_flag)
            adjusted *= QUALITY_PENALTY_FACTOR

        # 4. Generic text detection — skip for missing/unfavorable/unacceptable status
        if status not in ("missing", "unfavorable"):
            generic_ok, generic_flag = _check_generic_text(evidence_text)
            if not generic_ok:
                flags.append(generic_flag)
                adjusted *= QUALITY_PENALTY_FACTOR

    is_ok = len(flags) == 0
    adjusted = round(min(adjusted, 1.0), 4)

    return EvidenceQuality(
        finding_key=finding_key,
        clause_type=clause_type,
        status=status,
        evidence_text=evidence_text,
        raw_confidence=raw_confidence,
        is_quality_ok=is_ok,
        adjusted_confidence=adjusted,
        flags=flags,
    )


def resolve_effective_state(status: str, quality: EvidenceQuality) -> str:
    """Determine the effective node state considering evidence quality.

    When confidence is too low, return 'unknown' instead of forcing a hard state.
    """
    if quality.should_be_unknown:
        return "unknown"
    return status
