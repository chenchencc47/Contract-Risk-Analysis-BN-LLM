"""BN Node Discovery — auto-detect missing risk dimensions from contract reviews.

Pipeline (semi-automated):
  1. LLM₁ free review → identifies risks with clause_types not in BN
  2. record_gap() writes them to config/pending_nodes.json
  3. CLI: python -m contract_risk_analysis.cli discover-nodes
     → shows deduplicated gaps with suggested BN node configs
  4. Developer reviews and approves → writes to bayesian_network_v2.json

This creates a feedback loop: every contract review makes the BN richer.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PENDING_PATH = PROJECT_ROOT / "config" / "pending_nodes.json"
BN_CONFIG_PATH = PROJECT_ROOT / "config" / "bayesian_network_v2.json"

# ── Dimension keywords for auto-classification ──
DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "financial_exposure_risk": [
        "付款", "资金", "价格", "费用", "价款", "预付款", "结算",
        "计价", "损耗", "运费", "仓储", "库存", "质保金",
        "payment", "price", "cost", "fee", "prepay",
    ],
    "performance_delivery_risk": [
        "交货", "交付", "验收", "质量", "运输", "供货", "试烧",
        "检测", "检验", "发货", "履约", "批次",
        "delivery", "acceptance", "quality", "shipment",
    ],
    "dispute_resolution_risk": [
        "管辖", "争议", "仲裁", "诉讼", "计量", "法律适用",
        "dispute", "jurisdiction", "arbitration",
    ],
    "clause_balance_risk": [
        "违约责任", "解除权", "终止", "违约", "不对等", "失衡",
        "单方", "调整机制", "变更",
        "termination", "breach", "balance",
    ],
    "legal_enforceability_risk": [
        "不可抗力", "保密", "知识产权", "法律", "合规",
        "force", "confidential", "ip", "compliance",
    ],
}


def record_gap(
    clause_type: str,
    risk_title: str = "",
    severity: str = "medium",
    confidence: float = 0.0,
    contract_id: str = "",
) -> None:
    """Record an unmapped clause_type to the pending nodes file.

    Called during pipeline execution when BnMappingService cannot map
    a risk segment to any existing BN node.
    """
    pending = _load_pending()

    # Deduplicate: update existing entry if same clause_type
    entry = {
        "clause_type": clause_type,
        "risk_title": risk_title,
        "severity": severity,
        "confidence": confidence,
        "contract_id": contract_id,
        "last_seen": datetime.now().isoformat(),
        "occurrence_count": 1,
    }

    existing = pending.get(clause_type)
    if existing:
        existing["occurrence_count"] = existing.get("occurrence_count", 1) + 1
        existing["last_seen"] = entry["last_seen"]
        if risk_title and not existing.get("risk_title"):
            existing["risk_title"] = risk_title
    else:
        pending[clause_type] = entry

    _save_pending(pending)


def discover_pending_nodes() -> list[dict]:
    """Return deduplicated, sorted list of pending nodes for review.

    Each entry includes:
      - clause_type: the original LLM output
      - occurrence_count: how many times seen
      - suggested_node_name: snake_case BN node name
      - suggested_states: inferred from the clause_type semantics
      - suggested_dimension: which risk dimension it connects to
    """
    pending = _load_pending()
    if not pending:
        return []

    results: list[dict] = []
    for clause_type, entry in sorted(
        pending.items(), key=lambda x: -x[1].get("occurrence_count", 1)
    ):
        suggested_name = _clause_type_to_node_name(clause_type)
        results.append({
            **entry,
            "suggested_node_name": suggested_name,
            "suggested_states": _infer_states(clause_type, entry.get("risk_title", "")),
            "suggested_dimension": _infer_dimension(
                clause_type, entry.get("risk_title", "")
            ),
        })
    return results


def approve_node(clause_type: str) -> bool:
    """Approve a pending node and add it to the BN config.

    Generates a contract_fact node with expert_estimated CPT,
    adds an edge to the suggested dimension, and removes the
    entry from pending_nodes.json.

    Returns True on success.
    """
    pending = _load_pending()
    entry = pending.pop(clause_type, None)
    if not entry:
        print(f"'{clause_type}' not found in pending nodes")
        return False

    nodes = discover_pending_nodes()
    suggestion = next(
        (n for n in nodes if n["clause_type"] == clause_type), None
    )
    if not suggestion:
        return False

    node_name = suggestion["suggested_node_name"]
    states = suggestion["suggested_states"]
    dim = suggestion["suggested_dimension"]
    label = entry.get("risk_title", clause_type)

    # Build node config
    cpt_entries: dict[str, float] = {}
    n_states = len(states)
    for i, s in enumerate(states):
        cpt_entries[s] = round(1.0 / n_states, 4)

    node_config = {
        "label": label,
        "layer": "contract_fact",
        "states": states,
        "parents": [],
        "cpt": {"": cpt_entries},
        "cpt_source": "expert_estimated",
        "description": f"Auto-discovered from contract review: {label}",
    }

    # Add to BN config
    bn_config = json.loads(BN_CONFIG_PATH.read_text(encoding="utf-8"))
    if node_name in bn_config["nodes"]:
        print(f"Node '{node_name}' already exists in BN config, skipping")
        _save_pending(pending)
        return False

    bn_config["nodes"][node_name] = node_config
    bn_config["edges"].append([node_name, dim])

    # Update dimension node parents list
    if dim in bn_config["nodes"]:
        dim_parents = bn_config["nodes"][dim].get("parents", [])
        if node_name not in dim_parents:
            dim_parents.append(node_name)

    BN_CONFIG_PATH.write_text(
        json.dumps(bn_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _save_pending(pending)

    print(f"Approved: {node_name} ({label}) → {dim}")
    print(f"  States: {states}")
    print(f"  Removed from pending_nodes.json")
    return True


def reject_node(clause_type: str) -> bool:
    """Remove a pending node entry without adding to BN."""
    pending = _load_pending()
    if clause_type in pending:
        del pending[clause_type]
        _save_pending(pending)
        print(f"Rejected: {clause_type}")
        return True
    return False


# ── Internal helpers ──────────────────────────────────────────


def _load_pending() -> dict:
    if PENDING_PATH.exists():
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    return {}


def _save_pending(data: dict) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _clause_type_to_node_name(clause_type: str) -> str:
    """Convert a Chinese/English clause_type to a snake_case BN node name."""
    # Simple transliteration for common patterns
    mapping: dict[str, str] = {
        "付款": "payment", "交货": "delivery", "验收": "acceptance",
        "质量": "quality", "违约": "breach", "管辖": "jurisdiction",
        "保密": "confidentiality", "保险": "insurance", "终止": "termination",
        "解除": "rescission", "赔偿": "indemnity", "运输": "transport",
        "价格": "pricing", "检测": "inspection", "检验": "inspection",
        "仓储": "storage", "库存": "inventory", "批次": "batch",
        "结算": "settlement", "能源": "energy", "供货": "supply",
        "热值": "calorific", "试烧": "trial_burn", "计量": "measurement",
        "损耗": "loss", "途耗": "transit_loss", "单方": "unilateral",
        "调价": "price_adj", "原料": "raw_material", "不可抗力": "force_majeure",
    }
    name = clause_type
    for cn, en in mapping.items():
        name = name.replace(cn, en)
    # Convert to snake_case
    result = name.lower().strip()
    result = "".join(c if c.isalnum() else "_" for c in result)
    result = result.strip("_").replace("__", "_")
    # Prefix with 'cust_' for custom-discovered nodes
    if not result.startswith("cust_"):
        result = f"cust_{result}"
    return result[:64]  # limit length


def _infer_states(clause_type: str, risk_title: str = "") -> list[str]:
    """Infer appropriate states for a new BN node."""
    combined = f"{clause_type} {risk_title}".lower()
    # Binary presence nodes
    for kw in ["标准", "条款", "约定", "机制", "流程", "clause", "term",
               "缺失", "缺失条款", "无", "缺少", "未约定", "不完整"]:
        if kw in combined:
            return ["present", "vague", "missing"]
    # Balance nodes
    for kw in ["不对等", "失衡", "单方", "偏向", "unfair", "one-sided"]:
        if kw in combined:
            return ["balanced", "counterparty_favorable"]
    # Favorability nodes
    for kw in ["比例", "节点", "金额", "费用", "价格", "rate", "amount",
               "price", "cost", "fee", "承担", "转移"]:
        if kw in combined:
            return ["favorable", "neutral", "unfavorable"]
    # Default: binary presence
    return ["present", "missing"]


def _infer_dimension(clause_type: str, risk_title: str = "") -> str:
    """Infer which risk dimension a new node connects to."""
    combined = f"{clause_type} {risk_title}"
    scores: dict[str, int] = defaultdict(int)
    for dim, keywords in DIMENSION_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                scores[dim] += 1
    if scores:
        return max(scores, key=scores.get)
    return "clause_balance_risk"  # default fallback
