"""Canonicalization layer — stabilizes the LLM₁ → BN handoff.

After LLM₁ produces free-form risk segments with arbitrary clause_type strings,
this module deterministically normalizes them to a fixed canonical vocabulary
derived from config/clause_type_mapping.yaml.

This eliminates clause_type drift as a source of BN mapping instability across
repeated runs of the same contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, RiskSegment


def _load_canonical_vocabulary() -> dict[str, str]:
    """Load clause_type → canonical_type lookup from clause_type_mapping.yaml.

    Builds a bidirectional map: every key in the YAML is a canonical type,
    and every alias (keyword) maps back to it.
    Also includes Chinese→English normalization from common patterns.
    """
    import yaml as _yaml
    config_path = Path(__file__).resolve().parents[3] / "config" / "clause_type_mapping.yaml"
    vocab: dict[str, str] = {}

    try:
        with open(config_path, encoding="utf-8") as fh:
            config = _yaml.safe_load(fh) or {}
    except Exception:
        return vocab

    for canonical_key, entry in config.items():
        if not isinstance(entry, dict):
            continue
        # The key itself IS the canonical type
        canonical = canonical_key.lower().strip()
        vocab[canonical] = canonical

        # Map common Chinese aliases
        chinese_map: dict[str, str] = {
            "付款": "payment", "支付": "payment", "预付款": "payment",
            "交付": "delivery", "交货": "delivery", "运输": "delivery",
            "验收": "acceptance", "质保": "warranty", "保修": "warranty",
            "责任上限": "liability_cap", "责任限制": "liability_cap",
            "违约金": "liquidated_damages", "罚则": "liquidated_damages",
            "终止": "termination", "解除": "termination",
            "争议": "dispute_resolution", "管辖": "dispute_resolution",
            "保密": "confidentiality",
            "知识产权": "ip_ownership", "知识产权归属": "ip_ownership",
            "不可抗力": "force_majeure",
            "适用法律": "governing_law",
            "保险": "insurance",
            "转让": "anti_assignment",
            "排他": "exclusivity",
        }
        for cn, en in chinese_map.items():
            # Forward: English canonical → add Chinese aliases
            if en == canonical:
                vocab[cn] = canonical
                vocab[cn.lower()] = canonical

    # Second pass: Chinese YAML keys → map to English canonical
    for cn, en in chinese_map.items():
        if cn in vocab and en in vocab and vocab[cn] == cn:
            vocab[cn] = en

    return vocab


# Module-level cache
_CANONICAL_VOCAB: dict[str, str] | None = None


def _get_vocab() -> dict[str, str]:
    global _CANONICAL_VOCAB
    if _CANONICAL_VOCAB is None:
        _CANONICAL_VOCAB = _load_canonical_vocabulary()
    return _CANONICAL_VOCAB


def canonicalize_clause_type(clause_type: str) -> str | None:
    """Deterministically normalize a free-form clause_type to a canonical type.

    Returns None if no canonical match is found — the caller should fall back
    to the original clause_type.

    Matching strategy (in order):
    1. Exact match against canonical vocabulary
    2. Normalized match (lowercase, strip)
    3. Substring match (if canonical key appears in clause_type or vice versa)
    """
    vocab = _get_vocab()
    ct = clause_type.strip()

    # Strategy 1: exact match
    if ct in vocab:
        return vocab[ct]

    # Strategy 2: normalized
    normalized = ct.lower().strip().replace("_", "").replace("-", "").replace(" ", "")
    for key, canonical in vocab.items():
        key_norm = key.lower().strip().replace("_", "").replace("-", "").replace(" ", "")
        if normalized == key_norm:
            return canonical

    # Strategy 3: substring
    for key, canonical in vocab.items():
        if key in ct or ct in key:
            return canonical

    return None


def canonicalize_free_review(free_output: FreeReviewOutput) -> FreeReviewOutput:
    """Apply canonicalization to all risk segments in a FreeReviewOutput.

    Mutates each RiskSegment in-place to set canonical_type.
    Returns the same FreeReviewOutput (with populated canonical_type fields).
    """
    for seg in free_output.risk_segments:
        seg.canonical_type = canonicalize_clause_type(seg.clause_type)

    return free_output
