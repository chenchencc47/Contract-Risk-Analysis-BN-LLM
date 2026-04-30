"""Centralized constants for BN contract risk analysis.

All dimension labels, node labels, risk labels, and dimension node keys
are defined here as the single source of truth. Other modules import only
what they need.

Previously these were duplicated across 7+ files, leading to maintenance
risk on any label change.
"""

from __future__ import annotations

# ── Risk dimension nodes (5 core dimensions + 1 overall) ──────────

DIMENSION_NODES: list[str] = [
    "legal_enforceability_risk",
    "financial_exposure_risk",
    "performance_delivery_risk",
    "dispute_resolution_risk",
    "clause_balance_risk",
]

DIMENSION_LABELS: dict[str, str] = {
    "legal_enforceability_risk": "法律可执行性风险",
    "financial_exposure_risk": "财务暴露风险",
    "performance_delivery_risk": "履约交付风险",
    "dispute_resolution_risk": "争议处置风险",
    "clause_balance_risk": "条款失衡风险",
}

RISK_LABELS: dict[str, str] = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
}

# ── Evidence node labels (BN nodes → Chinese display names) ───────

NODE_LABELS: dict[str, str] = {
    "termination_clause_completeness": "终止条款完整性",
    "termination_right_balance": "解除权平衡性",
    "liability_cap_strength": "责任上限强度",
    "damages_exposure": "损害赔偿暴露",
    "acceptance_process_clarity": "验收流程明确性",
    "governing_law_clarity": "适用法律明确性",
    "dispute_resolution_clarity": "争议解决明确性",
    "jurisdiction_fairness": "管辖安排公平性",
}
