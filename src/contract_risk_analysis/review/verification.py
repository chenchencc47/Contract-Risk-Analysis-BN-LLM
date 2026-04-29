"""Selective double-confirmation for suspicious findings (P2.3).

Only triggered when evidence quality validation flags a finding as problematic.
Makes a single targeted LLM call per suspicious clause to cross-verify.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from contract_risk_analysis.evidence.validate import EvidenceQuality


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class VerificationResult:
    clause_type: str
    original_status: str
    verified_status: str
    verified_evidence: str
    is_consistent: bool
    conflict_reason: str


def _verification_prompt(
    contract_text: str,
    clause_type: str,
    original_status: str,
    original_evidence: str,
) -> str:
    clause_labels = {
        "termination": "终止/解除条款",
        "liability_cap": "责任上限/赔偿条款",
        "confidentiality": "保密条款",
        "governing_law": "适用法律/管辖条款",
        "dispute_resolution": "争议解决条款",
        "acceptance": "验收条款",
        "payment": "付款条款",
        "delivery": "交付条款",
    }
    label = clause_labels.get(clause_type, clause_type)

    return (
        f"你是合同条款验证助手。请从以下合同文本中，**直接引用**与{label}相关的原文。\n\n"
        "要求：\n"
        "1. 如果合同文本中确实存在该条款，请**原样引用**相关原文片段（至少15字）。\n"
        "2. 如果合同文本中**完全没有**涉及该条款，请直接回答 NOT_FOUND。\n"
        "3. 直接输出引用文本或 NOT_FOUND，不要输出任何JSON或解释。\n\n"
        f"之前审查认为该条款状态为「{original_status}」，提取的证据为：{original_evidence[:200]}\n\n"
        "合同文本如下：\n"
        f"{contract_text[:6000]}"
    )


def run_verification(
    contract_text: str,
    quality: EvidenceQuality,
) -> VerificationResult:
    """Run a targeted LLM verification for a single suspicious finding.

    Only call this when EvidenceQuality flags a finding as problematic.
    Makes exactly 1 LLM call.
    """
    load_dotenv(ENV_PATH)
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.moonshot.cn/v1")
    model = os.getenv("OPENAI_MODEL", "moonshot-v1-128k")

    if not api_key:
        raise ValueError("缺少 OPENAI_API_KEY")

    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _verification_prompt(
        contract_text=contract_text,
        clause_type=quality.clause_type,
        original_status=quality.status,
        original_evidence=quality.evidence_text,
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你只输出合同文本原文摘录或 NOT_FOUND，不输出其他内容。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=512,
            temperature=0.0,
        )
    except Exception:
        return VerificationResult(
            clause_type=quality.clause_type,
            original_status=quality.status,
            verified_status="unknown",
            verified_evidence="",
            is_consistent=False,
            conflict_reason=f"验证LLM调用失败，保留原状态",
        )

    content = (completion.choices[0].message.content or "").strip()

    if "NOT_FOUND" in content.upper():
        verified_status = "missing"
        verified_evidence = ""
        is_consistent = quality.status in ("missing", "unknown")
        conflict_reason = "" if is_consistent else f"验证发现条款缺失，但原判断为{quality.status}"
    elif len(content) >= 10:
        verified_status = "present"
        verified_evidence = content
        is_consistent = quality.status != "missing"
        conflict_reason = "" if is_consistent else f"验证发现条款存在（原文：{content[:100]}...），但原判断为missing"
    else:
        verified_status = "unknown"
        verified_evidence = content
        is_consistent = False
        conflict_reason = f"验证返回内容过短，无法确认"

    return VerificationResult(
        clause_type=quality.clause_type,
        original_status=quality.status,
        verified_status=verified_status,
        verified_evidence=verified_evidence,
        is_consistent=is_consistent,
        conflict_reason=conflict_reason,
    )


def should_verify(quality: EvidenceQuality) -> bool:
    """Decide whether a finding needs targeted re-verification.

    Only triggers when evidence has quality problems, to avoid unnecessary cost.
    """
    if quality.should_be_unknown:
        return True
    if quality.adjusted_confidence < quality.raw_confidence:
        return True
    return False
