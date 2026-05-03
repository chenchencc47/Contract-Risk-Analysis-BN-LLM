"""BN Feedback Loop — human review verdicts flow back to CPT calibration.

Pipeline:
  1. Human reviewer reads a report, judges each BN-derived claim
  2. POST /api/feedback {report_id, node_name, verdict, note}
  3. Stored in bn_feedback table
  4. CLI: python -m contract_risk_analysis.cli --feedback-summary
     → aggregated stats per node (correct/incorrect rate)
  5. Future: aggregate stats → CPT calibration adjustments

This closes the loop from static CUAD statistics to dynamic,
project-specific experience accumulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from contract_risk_analysis.db.connection import get_connection


@dataclass
class FeedbackRecord:
    id: int
    report_id: int
    node_name: str
    verdict: str  # "correct" | "incorrect" | "partial"
    reviewer_note: str | None
    created_at: datetime


def save_feedback(
    *,
    report_id: int,
    node_name: str,
    verdict: str,
    reviewer_note: str | None = None,
) -> int:
    """Record human feedback on a BN claim.

    Args:
        report_id: The report this feedback refers to.
        node_name: The BN node name (e.g., "liability_cap_strength").
        verdict: "correct", "incorrect", or "partial".
        reviewer_note: Optional free-text explanation.
    """
    if verdict not in ("correct", "incorrect", "partial"):
        raise ValueError(f"Invalid verdict: {verdict}")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO bn_feedback (report_id, node_name, verdict, reviewer_note)
               VALUES (%s, %s, %s, %s)""",
            (report_id, node_name, verdict, reviewer_note),
        )
        return cur.lastrowid or 0


def get_feedback_summary() -> list[dict[str, Any]]:
    """Aggregate feedback per BN node with accuracy stats."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT node_name,
                      COUNT(*) as total,
                      SUM(CASE WHEN verdict='correct' THEN 1 ELSE 0 END) as correct,
                      SUM(CASE WHEN verdict='incorrect' THEN 1 ELSE 0 END) as incorrect,
                      SUM(CASE WHEN verdict='partial' THEN 1 ELSE 0 END) as partial
               FROM bn_feedback
               GROUP BY node_name
               ORDER BY total DESC"""
        )
        cols = ["node_name", "total", "correct", "incorrect", "partial"]
        results: list[dict] = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            total = d["total"]
            d["accuracy"] = round(d["correct"] / total, 2) if total > 0 else 0.0
            results.append(d)
        return results


def get_feedback_for_report(report_id: int) -> list[FeedbackRecord]:
    """Get all feedback entries for a specific report."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, report_id, node_name, verdict, reviewer_note, created_at "
            "FROM bn_feedback WHERE report_id = %s ORDER BY id",
            (report_id,),
        )
        return [_row_to_feedback(r) for r in cur.fetchall()]


def _row_to_feedback(row: tuple) -> FeedbackRecord:
    return FeedbackRecord(
        id=row[0], report_id=row[1], node_name=row[2],
        verdict=row[3], reviewer_note=row[4], created_at=row[5],
    )
