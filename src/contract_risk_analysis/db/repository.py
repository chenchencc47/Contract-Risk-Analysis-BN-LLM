"""CRUD repository for contracts and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from contract_risk_analysis.db.connection import get_connection


@dataclass
class ContractRecord:
    id: int
    contract_name: str
    contract_type: str
    contract_text: str
    file_name: str | None
    party_a: str | None
    party_b: str | None
    contract_amount: float | None
    created_at: datetime


@dataclass
class ReportRecord:
    id: int
    contract_id: int
    report_version: int
    review_party: str
    overall_risk_level: str | None
    overall_p_high: float | None
    summary_text: str | None
    report_content_md: str
    bn_counterfactual_count: int
    review_duration_ms: int | None
    created_at: datetime


# ── Contract CRUD ────────────────────────────────────────────


def upsert_contract(
    *,
    contract_name: str,
    contract_type: str = "销售合同",
    contract_text: str = "",
    file_name: str | None = None,
    party_a: str | None = None,
    party_b: str | None = None,
    contract_amount: float | None = None,
) -> int:
    """Insert or update a contract, return its id."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO contracts
               (contract_name, contract_type, contract_text, file_name,
                party_a, party_b, contract_amount)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 contract_text = VALUES(contract_text),
                 updated_at = CURRENT_TIMESTAMP""",
            (contract_name, contract_type, contract_text, file_name,
             party_a, party_b, contract_amount),
        )
        if cur.lastrowid:
            return cur.lastrowid
        cur.execute(
            "SELECT id FROM contracts WHERE contract_name = %s LIMIT 1",
            (contract_name,),
        )
        row = cur.fetchone()
        return row[0] if row else 0


def get_contract(contract_id: int) -> ContractRecord | None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM contracts WHERE id = %s", (contract_id,))
        row = cur.fetchone()
        return _row_to_contract(row) if row else None


def list_contracts(
    contract_type: str | None = None,
    limit: int = 50,
) -> list[ContractRecord]:
    with get_connection() as conn:
        cur = conn.cursor()
        if contract_type:
            cur.execute(
                "SELECT * FROM contracts WHERE contract_type = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (contract_type, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM contracts ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        return [_row_to_contract(r) for r in cur.fetchall()]


# ── Report CRUD ──────────────────────────────────────────────


def save_report(
    *,
    contract_id: int,
    report_content_md: str,
    review_party: str = "buyer",
    overall_risk_level: str | None = None,
    overall_p_high: float | None = None,
    summary_text: str | None = None,
    bn_counterfactual_count: int = 0,
    review_duration_ms: int | None = None,
) -> int:
    """Save a new report, return its id."""
    # Auto-increment version for this contract+party pair
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(report_version), 0) FROM reports "
            "WHERE contract_id = %s AND review_party = %s",
            (contract_id, review_party),
        )
        version = cur.fetchone()[0] + 1
        cur.execute(
            """INSERT INTO reports
               (contract_id, report_version, review_party, overall_risk_level,
                overall_p_high, summary_text, report_content_md,
                bn_counterfactual_count, review_duration_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (contract_id, version, review_party, overall_risk_level,
             overall_p_high, summary_text, report_content_md,
             bn_counterfactual_count, review_duration_ms),
        )
        return cur.lastrowid or 0


def save_report_risks(
    report_id: int,
    risks: list[dict[str, Any]],
) -> None:
    """Bulk-save risk items for a report."""
    if not risks:
        return
    with get_connection() as conn:
        cur = conn.cursor()
        for i, risk in enumerate(risks):
            cur.execute(
                """INSERT INTO report_risks
                   (report_id, risk_name, risk_level, clause_category,
                    ai_confidence, bn_verified, suggestion_text, sort_order)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (report_id, risk.get("name", ""),
                 risk.get("level", "中"),
                 risk.get("category"),
                 risk.get("confidence"),
                 1 if risk.get("bn_verified") else 0,
                 risk.get("suggestion"),
                 i),
            )


def save_report_counterfactuals(
    report_id: int,
    cfs: list[dict[str, Any]],
) -> None:
    """Bulk-save counterfactual data for a report."""
    if not cfs:
        return
    with get_connection() as conn:
        cur = conn.cursor()
        for cf in cfs:
            dim_deltas = cf.get("dimension_deltas", [])
            dd0 = dim_deltas[0] if dim_deltas else {}
            cur.execute(
                """INSERT INTO report_counterfactuals
                   (report_id, dimension_name, dimension_level_p_high,
                    dimension_improved, dimension_delta, overall_p_high,
                    overall_improved, overall_delta, ai_rating, consensus)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (report_id, cf.get("node_label", ""),
                 dd0.get("base_high"),
                 dd0.get("counterfactual_high"),
                 dd0.get("delta"),
                 cf.get("base_high_risk"),
                 cf.get("counterfactual_high_risk"),
                 cf.get("delta_high_risk"),
                 None, None),
            )


def get_report(report_id: int) -> ReportRecord | None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM reports WHERE id = %s", (report_id,))
        row = cur.fetchone()
        return _row_to_report(row) if row else None


def list_reports(
    review_party: str | None = None,
    contract_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List reports with joined contract info."""
    with get_connection() as conn:
        cur = conn.cursor()
        where = []
        params: list[Any] = []
        if review_party:
            where.append("r.review_party = %s")
            params.append(review_party)
        if contract_type:
            where.append("c.contract_type = %s")
            params.append(contract_type)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        cur.execute(
            f"""SELECT r.id, r.contract_id, r.report_version, r.review_party,
                       r.overall_risk_level, r.overall_p_high,
                       r.bn_counterfactual_count, r.created_at,
                       c.contract_name, c.contract_type
                FROM reports r
                JOIN contracts c ON r.contract_id = c.id
                {clause}
                ORDER BY r.created_at DESC LIMIT %s""",
            (*params, limit),
        )
        cols = ["id", "contract_id", "report_version", "review_party",
                "overall_risk_level", "overall_p_high",
                "bn_counterfactual_count", "created_at",
                "contract_name", "contract_type"]
        results: list[dict[str, Any]] = []
        for row in cur.fetchall():
            d = dict(zip(cols, row, strict=False))
            for k, v in d.items():
                if hasattr(v, "__float__") and not isinstance(v, (int, float)):
                    d[k] = float(v)
            results.append(d)
        return results


def get_report_diff(
    report_id_1: int, report_id_2: int
) -> dict[str, Any]:
    """Return a diff summary of two reports."""
    r1 = get_report(report_id_1)
    r2 = get_report(report_id_2)
    if not r1 or not r2:
        return {"error": "Report not found"}

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT risk_name, risk_level FROM report_risks WHERE report_id = %s ORDER BY sort_order",
            (report_id_1,),
        )
        risks1 = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute(
            "SELECT risk_name, risk_level FROM report_risks WHERE report_id = %s ORDER BY sort_order",
            (report_id_2,),
        )
        risks2 = {row[0]: row[1] for row in cur.fetchall()}

    all_risks = set(risks1) | set(risks2)
    changed: list[dict] = []
    added: list[str] = []
    removed: list[str] = []
    for risk in all_risks:
        lv1 = risks1.get(risk)
        lv2 = risks2.get(risk)
        if lv1 and lv2 and lv1 != lv2:
            changed.append({"name": risk, "from": lv1, "to": lv2})
        elif lv1 and not lv2:
            removed.append(risk)
        elif lv2 and not lv1:
            added.append(risk)

    return {
        "report_1": {"id": r1.id, "created_at": r1.created_at.isoformat(),
                     "counterfactuals": r1.bn_counterfactual_count,
                     "risk_level": r1.overall_risk_level},
        "report_2": {"id": r2.id, "created_at": r2.created_at.isoformat(),
                     "counterfactuals": r2.bn_counterfactual_count,
                     "risk_level": r2.overall_risk_level},
        "risk_changes": changed,
        "risks_added": added,
        "risks_removed": removed,
    }


# ── Helpers ───────────────────────────────────────────────────


def _d(v):
    """Convert Decimal to float, pass through everything else."""
    if hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
        return float(v)
    return v


def _row_to_contract(row: tuple) -> ContractRecord:
    return ContractRecord(
        id=_d(row[0]), contract_name=_d(row[1]), contract_type=_d(row[2]),
        contract_text=_d(row[3]), file_name=_d(row[4]),
        party_a=_d(row[5]), party_b=_d(row[6]),
        contract_amount=_d(row[7]), created_at=_d(row[8]),
    )


def _row_to_report(row: tuple) -> ReportRecord:
    return ReportRecord(
        id=_d(row[0]), contract_id=_d(row[1]), report_version=_d(row[2]),
        review_party=_d(row[3]), overall_risk_level=_d(row[4]),
        overall_p_high=_d(row[5]), summary_text=_d(row[6]),
        report_content_md=_d(row[7]), bn_counterfactual_count=_d(row[8]),
        review_duration_ms=_d(row[9]), created_at=_d(row[10]),
    )


# ── Company Redlines CRUD ──────────────────────────────────────


def load_active_redlines(
    contract_types: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load active hard_rules and reasoning_hints filtered by contract types.

    Returns (hard_rules, reasoning_hints). Always includes '通用' type rules.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        types = list(contract_types or [])
        if "通用" not in types:
            types.append("通用")
        placeholders = ",".join(["%s"] * len(types))
        cur.execute(
            f"""SELECT contract_type, category, rule_id, label, description, severity
                FROM company_redlines
                WHERE contract_type IN ({placeholders}) AND is_active = 1
                ORDER BY contract_type, category, id""",
            types,
        )
        hard_rules: list[dict[str, Any]] = []
        reasoning_hints: list[dict[str, Any]] = []
        for row in cur.fetchall():
            item = {
                "contract_type": row[0], "rule_id": row[2],
                "label": row[3], "description": row[4], "severity": row[5],
            }
            if row[1] == "hard_rules":
                hard_rules.append(item)
            else:
                reasoning_hints.append(item)
        return hard_rules, reasoning_hints


def list_all_redlines() -> list[dict[str, Any]]:
    """List all redlines (active and inactive) for management UI."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, contract_type, category, rule_id, label, description,
                      severity, is_active, created_at
               FROM company_redlines ORDER BY contract_type, category, id"""
        )
        cols = ["id", "contract_type", "category", "rule_id", "label",
                "description", "severity", "is_active", "created_at"]
        results: list[dict[str, Any]] = []
        for row in cur.fetchall():
            d = dict(zip(cols, row, strict=False))
            for k, v in d.items():
                if hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
                    d[k] = float(v)
                elif hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            results.append(d)
        return results


def upsert_redline(
    *, contract_type: str, category: str, rule_id: str,
    label: str, description: str, severity: str | None = None, is_active: int = 1,
) -> int:
    """Insert or update a redline rule. Returns the row id."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO company_redlines
               (contract_type, category, rule_id, label, description, severity, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 category = VALUES(category), label = VALUES(label),
                 description = VALUES(description), severity = VALUES(severity),
                 is_active = VALUES(is_active), updated_at = CURRENT_TIMESTAMP""",
            (contract_type, category, rule_id, label, description, severity, is_active),
        )
        if cur.lastrowid:
            return cur.lastrowid
        cur.execute(
            "SELECT id FROM company_redlines WHERE contract_type=%s AND rule_id=%s",
            (contract_type, rule_id),
        )
        row = cur.fetchone()
        return row[0] if row else 0


def delete_redline(redline_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM company_redlines WHERE id=%s", (redline_id,))
        return cur.rowcount > 0


def get_redline_contract_types() -> list[str]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT contract_type FROM company_redlines "
            "WHERE is_active=1 ORDER BY contract_type"
        )
        return [row[0] for row in cur.fetchall()]
