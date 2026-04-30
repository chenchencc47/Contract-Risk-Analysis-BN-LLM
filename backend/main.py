"""BN Contract Risk Analysis — FastAPI Backend.

Clean REST API wrapping the contract risk analysis pipeline.
Start: uvicorn backend.main:app --port 9527 --reload
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Ensure src/ is on path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

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
from contract_risk_analysis.bn.config_validator import validate_v2_config
from contract_risk_analysis.constants import DIMENSION_LABELS, RISK_LABELS

app = FastAPI(title="合同风险审查系统", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _score_to_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
async def health() -> dict:
    vreport = validate_v2_config()
    return {
        "status": "ok",
        "pgmpy_available": True,
        "config_valid": vreport.is_valid,
        "config_errors": len(vreport.errors),
    }


@app.post("/api/review")
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
    contract_text = str(body.get("contract_text", "")).strip()
    contract_id = str(body.get("contract_id", "")).strip() or "unnamed"
    review_party = str(body.get("review_party", "buyer"))
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

    # ── Layer 3: Combined report generation ──
    polished = None
    try:
        polished = generate_combined_report(free_output, consistency, review_party)
    except Exception:
        pass

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
    else:
        response["polished"] = None

    if include_debug:
        response["debug"] = {
            "bn_posteriors": consistency.bn_posteriors,
            "node_states": legacy_evidence.node_states,
            "triggered_findings": legacy_evidence.triggered_findings,
        }

    return JSONResponse(response)


# Remove the old monolithic review endpoint body (replaced by _run_v1_pipeline)
# _run_v1_pipeline contains the same logic as the original /api/review
