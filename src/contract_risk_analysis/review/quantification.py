from __future__ import annotations

import re

from contract_risk_analysis.domain.free_review_schema import (
    FreeReviewOutput,
    QuantitativeAnchor,
    QuantitativeContext,
)

_AMOUNT_PATTERNS = [
    re.compile(r"合同总价(?:为|：|:)?\s*(?:人民币)?\s*(?:：|:)?\s*[¥￥_]*\s*([0-9]+(?:\.[0-9]+)?)\s*万元"),
    re.compile(r"合同总价(?:为|：|:)?\s*(?:人民币)?\s*(?:：|:)?\s*[¥￥_]*\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*元"),
    re.compile(r"(?:合同货物)?总价(?:为|：|:)?\s*(?:人民币)?\s*(?:：|:)?\s*[¥￥_]*\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*元"),
    re.compile(r"总金额(?:为|：|:)?\s*(?:人民币)?\s*(?:：|:)?\s*[¥￥_]*\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*元"),
]
_PERCENT_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)%")


def _normalize_contract_text(contract_text: str) -> str:
    return re.sub(r"\s+", " ", contract_text)



def _compact_contract_text(contract_text: str) -> str:
    return re.sub(r"[\s_]+", "", contract_text)



def _parse_contract_amount(contract_text: str) -> tuple[float | None, str]:
    for text in (_normalize_contract_text(contract_text), _compact_contract_text(contract_text)):
        for pattern in _AMOUNT_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            raw = match.group(1).replace(",", "")
            if "万元" in match.group(0):
                return float(raw) * 10_000, match.group(0)
            return float(raw), match.group(0)
    return None, ""


def _fmt_money(value: float) -> str:
    return f"人民币{value:,.0f}元"


def build_quantitative_context(contract_text: str, free_output: FreeReviewOutput) -> QuantitativeContext:
    contract_amount, source_text = _parse_contract_amount(contract_text)
    anchors: list[QuantitativeAnchor] = []
    warnings: list[str] = []
    hints: list[str] = []

    for seg in free_output.risk_segments:
        seg_type = seg.canonical_type or seg.clause_type
        if seg_type not in {"payment_structure", "payment"}:
            continue
        match = _PERCENT_PATTERN.search(f"{seg.evidence_text} {seg.risk_description}")
        if not match:
            match = _PERCENT_PATTERN.search(_compact_contract_text(f"{seg.evidence_text} {seg.risk_description}"))
        if not match:
            continue
        percentage = float(match.group(1))
        amount = round(contract_amount * percentage / 100, 2) if contract_amount is not None else None
        anchors.append(
            QuantitativeAnchor(
                label=seg.risk_title,
                percentage=percentage,
                amount=amount,
                source_text=seg.evidence_text,
                formula=(
                    f"{_fmt_money(contract_amount)} × {percentage:.0f}%"
                    if contract_amount is not None else ""
                ),
            )
        )

    if contract_amount is not None:
        hints.append(f"每降低10个百分点≈{_fmt_money(contract_amount * 0.10)}")
    elif anchors:
        warnings.append("缺少合同总价，禁止把百分比换算成金额")

    return QuantitativeContext(
        contract_amount=contract_amount,
        amount_source_text=source_text,
        quantification_allowed=contract_amount is not None,
        payment_anchors=anchors,
        exchange_rate_hints=hints,
        warnings=warnings,
    )
