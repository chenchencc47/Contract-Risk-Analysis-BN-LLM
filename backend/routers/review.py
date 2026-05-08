"""Review endpoints — v1 and v2 contract risk analysis pipelines."""

from __future__ import annotations

import logging
import time as _time
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from contract_risk_analysis.bn.consistency_validator import build_consistency_report
from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.pipeline.build_evidence import (
    build_evidence,
    build_evidence_from_free_output,
)
from contract_risk_analysis.review.ai_review import (
    free_review_contract_text,
    review_contract_text,
)
from contract_risk_analysis.review.report_writer import (
    generate_combined_report,
    polish_report,
)
from contract_risk_analysis.constants import DIMENSION_LABELS, RISK_LABELS
from contract_risk_analysis.evidence.rules import run_validation_rules

logger = logging.getLogger(__name__)

router = APIRouter()


def _score_to_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


async def _run_v1_pipeline(body: dict[str, Any]) -> JSONResponse:
    """Original LLM→BN→LLM pipeline (constrained extraction)."""
    contract_text = str(body.get("contract_text", "")).strip()
    contract_id = str(body.get("contract_id", "")).strip() or "unnamed"
    include_debug = bool(body.get("include_debug"))

    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)

    # ── Layer 1: LLM extraction ──
    try:
        review_result = review_contract_text(
            contract_text, contract_id=contract_id, source_document=body.get("source_document"),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"AI 审查失败：{exc}"}, status_code=502)

    # ── Layer 2: Evidence mapping + BN inference ──
    evidence = build_evidence(review_result)
    report = assess_risk(evidence)
    report_dict = asdict(report)

    # Localize labels
    report_dict["overall_risk_label"] = RISK_LABELS.get(report.overall_risk, report.overall_risk)
    dim_scores: dict[str, float] = report_dict.get("dimension_scores", {})
    report_dict["dimension_labels"] = {
        k: DIMENSION_LABELS.get(k, k) for k in dim_scores
    }
    report_dict["dimension_risk_labels"] = {
        k: RISK_LABELS.get(_score_to_level(v), "") for k, v in dim_scores.items()
    }
    for r in report_dict.get("top_risks", []):
        r["risk_level_label"] = RISK_LABELS.get(r.get("risk_level", ""), "")

    # ── Layer 3: LLM polish (multi-role) ──
    polished = None
    try:
        polished = polish_report(report)
    except Exception:
        pass

    response: dict[str, Any] = {
        "generation_mode": "v1_legacy",
        "contract_id": review_result.contract_id,
        "findings_count": len(review_result.findings),
        "node_observations": [asdict(o) for o in evidence.node_observations],
        "evidence_summary": {
            "total_nodes": len(evidence.node_states),
            "triggered": len(evidence.triggered_findings),
            "states": evidence.node_states,
        },
        "report": report_dict,
    }

    if polished:
        response["polished"] = {
            "narrative_report": polished.narrative_report,
            "executive_summary": polished.executive_summary,
            "dimension_insights": polished.dimension_insights,
            "signing_advice": polished.signing_advice,
            "action_plan": polished.action_plan,
            "cross_dimension_notes": polished.cross_dimension_notes,
            "issue_reports": [asdict(i) for i in polished.issue_reports],
            "legal_view": polished.legal_view,
            "business_view": polished.business_view,
            "executive_view": polished.executive_view,
        }
    else:
        response["polished"] = None

    if include_debug:
        response["debug"] = {
            "findings": [asdict(f) for f in review_result.findings],
            "evidence_items": [asdict(e) for e in evidence.evidence_items],
        }

    return JSONResponse(response)


async def _run_v2_pipeline(body: dict[str, Any]) -> JSONResponse:
    """v2 pipeline: free LLM review → BN validator → combined report."""
    _v2_t0 = _time.time()
    contract_text = str(body.get("contract_text", "")).strip()
    contract_id = str(body.get("contract_id", "")).strip() or "unnamed"
    review_party = str(body.get("review_party", "buyer"))
    strategy_mode = bool(body.get("strategy_mode", False))
    include_debug = bool(body.get("include_debug"))

    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)

    # ── Layer 1: Free-form LLM review ──
    try:
        free_output = free_review_contract_text(
            contract_text, contract_id=contract_id,
            source_document=body.get("source_document"),
            review_party=review_party,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"AI 自由审查失败：{exc}"}, status_code=502)

    # ── Layer 2: BN consistency validation ──
    consistency = build_consistency_report(free_output)

    # ── P2: Post-hoc rule validation (deterministic, no LLM dependency) ──
    rule_matches = run_validation_rules(contract_text)

    # Also produce legacy report for backward-compatible structured data
    legacy_evidence = build_evidence_from_free_output(free_output)
    legacy_report = assess_risk(legacy_evidence)
    legacy_dict = asdict(legacy_report)
    legacy_dict["overall_risk_label"] = RISK_LABELS.get(
        legacy_report.overall_risk, legacy_report.overall_risk
    )
    dim_scores: dict[str, float] = legacy_dict.get("dimension_scores", {})
    legacy_dict["dimension_labels"] = {
        k: DIMENSION_LABELS.get(k, k) for k in dim_scores
    }
    legacy_dict["dimension_risk_labels"] = {
        k: RISK_LABELS.get(_score_to_level(v), "") for k, v in dim_scores.items()
    }

    # ── Quality gate (P2+P3) ──
    cf_count = len(consistency.counterfactuals) if consistency else 0
    if cf_count < 3:
        logger.warning("QUALITY_GATE: only %s counterfactuals (target ≥5)", cf_count)

    # P3: Check if top-ranked manual risks have BN counterfactual coverage
    top_risks = sorted(free_output.risk_segments, key=lambda s: {"critical":0,"high":1,"medium":2,"low":3,"positive":4}.get(s.severity, 5))[:3]
    cf_node_names = {cf.node_name for cf in (consistency.counterfactuals or [])}
    # Collect BN-mapped node names for top risks
    from contract_risk_analysis.bn.bn_mapping import BnMappingService
    mapper = BnMappingService()
    top_risk_nodes: set[str] = set()
    for seg in top_risks:
        node_name, _ = mapper._resolve_node_state(seg)
        if node_name:
            top_risk_nodes.add(node_name)
    covered_top = top_risk_nodes & cf_node_names
    if len(top_risk_nodes) > 0 and len(covered_top) < max(1, len(top_risk_nodes) * 2 // 3):
        logger.warning("QUALITY_GATE: top risks BN coverage %s/%s (target ≥66%%)", len(covered_top), len(top_risk_nodes))

    # ── Layer 3: Combined report generation ──
    import traceback as _tb
    polished = None
    try:
        polished = generate_combined_report(free_output, consistency, review_party, strategy_mode)
    except Exception as exc:
        logger.error("LLM₂ report generation failed: %s\n%s", exc, _tb.format_exc())

    # ── DB auto-save (P3) ──
    report_id: int | None = None
    try:
        from contract_risk_analysis.db.repository import (
            save_report, save_report_risks, save_report_counterfactuals, upsert_contract)
        cid = upsert_contract(contract_name=contract_id, contract_text=contract_text,
                              file_name=body.get("source_document"))
        overall_ph = None
        if consistency and consistency.bn_posteriors:
            ov = consistency.bn_posteriors.get("overall_contract_risk")
            if ov:
                overall_ph = round(ov.get("high", 0.0) * 100, 1)
        report_id = save_report(
            contract_id=cid, report_content_md=polished.narrative_report if polished else "",
            review_party=review_party, overall_p_high=overall_ph,
            summary_text=polished.executive_summary if polished else None,
            bn_counterfactual_count=cf_count,
            review_duration_ms=int((_time.time() - _v2_t0) * 1000))
        risk_records = [{"name": s.risk_title, "level": {"critical":"致命","high":"高","medium":"中","low":"低"}.get(s.severity,"中"),
                         "category": s.clause_type, "confidence": int(s.confidence*100)}
                        for s in free_output.risk_segments]
        save_report_risks(report_id, risk_records)
        if consistency and consistency.counterfactuals:
            cf_records = [{"node_label": cf.node_label, "base_high_risk": cf.base_high_risk,
                           "counterfactual_high_risk": cf.counterfactual_high_risk,
                           "delta_high_risk": cf.delta_high_risk,
                           "dimension_deltas": [{"base_high": dd.base_high, "counterfactual_high": dd.counterfactual_high,
                                                 "delta": dd.delta} for dd in cf.dimension_deltas]}
                          for cf in consistency.counterfactuals]
            save_report_counterfactuals(report_id, cf_records)
    except Exception as db_exc:
        logger.warning("DB_SAVE_FAILED: %s", db_exc)

    response: dict[str, Any] = {
        "generation_mode": "v2_combined",
        "contract_id": free_output.contract_id,
        "review_party": review_party,
        "free_review": {
            "segments_count": len(free_output.risk_segments),
            "missing_clauses": free_output.missing_clauses,
            "strengths": free_output.strengths,
            "overall_assessment": free_output.overall_assessment,
            "risk_segments": [asdict(s) for s in free_output.risk_segments],
        },
        "consistency": {
            "annotations": [asdict(a) for a in consistency.annotations],
            "counterfactuals": [asdict(c) for c in consistency.counterfactuals],
            "bn_summary": consistency.bn_summary,
            "rule_matches": [asdict(m) for m in rule_matches],
        },
        "report": legacy_dict,
    }

    if polished:
        response["polished"] = {
            "narrative_report": polished.narrative_report,
            "executive_summary": polished.executive_summary,
            "dimension_insights": polished.dimension_insights,
            "signing_advice": polished.signing_advice,
            "action_plan": polished.action_plan,
            "cross_dimension_notes": polished.cross_dimension_notes,
            "issue_reports": [asdict(i) for i in polished.issue_reports],
            "legal_view": polished.legal_view,
            "business_view": polished.business_view,
            "executive_view": polished.executive_view,
            "generation_mode": polished.generation_mode,
        }
        response["narrative_report"] = polished.narrative_report
        response["executive_summary"] = polished.executive_summary
        response["signing_advice"] = polished.signing_advice
        response["action_plan"] = polished.action_plan
        response["cross_dimension_notes"] = polished.cross_dimension_notes
    else:
        response["polished"] = None
        response["narrative_report"] = ""
        logger.error("LLM₂ report generation returned None — check DEEPSEEK_MODEL and API connectivity")

    if include_debug:
        response["debug"] = {
            "bn_posteriors": consistency.bn_posteriors,
            "node_states": legacy_evidence.node_states,
            "triggered_findings": legacy_evidence.triggered_findings,
        }

    return JSONResponse(response)


@router.post("/api/review")
async def review(request: Request) -> JSONResponse:
    """Contract risk review — v2 pipeline (free LLM → BN validator → combined report).

    The v2 pipeline treats the BN as a consistency validator, not the central
    risk engine. LLM₁ performs unconstrained review, BN checks for gaps and
    cross-dimension risks, and LLM₂ produces the authoritative report.

    Pass generation_mode="v1_legacy" to use the original constrained pipeline.
    """
    body: dict[str, Any] = await request.json()
    generation_mode = str(body.get("generation_mode", "v2_combined"))

    if generation_mode == "v1_legacy":
        return await _run_v1_pipeline(body)

    return await _run_v2_pipeline(body)


@router.post("/api/v2/review")
async def api_v2_review(request: Request) -> JSONResponse:
    """Direct v2 pipeline endpoint — mirrors /api/review with v2_combined mode."""
    body: dict[str, Any] = await request.json()
    return await _run_v2_pipeline(body)
