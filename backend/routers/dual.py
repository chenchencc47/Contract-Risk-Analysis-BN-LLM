"""Dual-perspective review endpoint."""

from __future__ import annotations

import time as _time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from contract_risk_analysis.bn.consistency_validator import build_consistency_report
from contract_risk_analysis.review.ai_review import free_review_contract_text, detect_bn_confidence
from contract_risk_analysis.review.report_writer import generate_combined_report

router = APIRouter()


@router.post("/api/v2/review/dual")
async def api_v2_dual_review(request: Request):
    body = await request.json()
    contract_text = str(body.get("contract_text", "")).strip()
    contract_id = str(body.get("contract_id", "")).strip() or "unnamed"
    source_document = body.get("source_document")
    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)

    results: dict[str, dict] = {}
    bn_confidence = detect_bn_confidence(contract_text)
    for party in ("buyer", "seller"):
        t0 = _time.time()
        try:
            free_output = free_review_contract_text(
                contract_text, contract_id, source_document, party)
            consistency = build_consistency_report(free_output, bn_confidence)
            polished = generate_combined_report(
                free_output, consistency, party, bn_confidence=bn_confidence,
            )
            results[party] = {
                "executive_summary": polished.executive_summary,
                "signing_advice": polished.signing_advice,
                "overall_assessment": free_output.overall_assessment,
                "risk_segments_count": len(free_output.risk_segments),
                "counterfactuals_count": len(consistency.counterfactuals) if consistency else 0,
                "strengths": free_output.strengths,
                "missing_clauses": free_output.missing_clauses,
                "duration_ms": int((_time.time() - t0) * 1000),
            }
        except Exception as exc:
            results[party] = {"error": str(exc)}

    comparison: dict = {}
    if "buyer" in results and "seller" in results:
        b, s = results["buyer"], results["seller"]
        b_st = set(b.get("strengths", [])); s_st = set(s.get("strengths", []))
        b_ms = set(b.get("missing_clauses", [])); s_ms = set(s.get("missing_clauses", []))
        comparison = {
            "shared_strengths": sorted(b_st & s_st),
            "buyer_unique_strengths": sorted(b_st - s_st),
            "seller_unique_strengths": sorted(s_st - b_st),
            "shared_missing": sorted(b_ms & s_ms),
            "buyer_unique_concerns": sorted(b_ms - s_ms),
            "seller_unique_concerns": sorted(s_ms - b_ms),
        }

    return JSONResponse({"contract_id": contract_id, "buyer": results.get("buyer", {}),
                         "seller": results.get("seller", {}), "comparison": comparison})
