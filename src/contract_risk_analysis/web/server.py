from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.domain.review_schema import RiskEvidence
from contract_risk_analysis.pipeline.build_evidence import build_evidence
from contract_risk_analysis.review.ai_review import review_contract_text
from contract_risk_analysis.review.report_writer import polish_report

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

DIMENSION_LABELS = {
    "legal_enforceability_risk": "法律可执行性风险",
    "financial_exposure_risk": "财务暴露风险",
    "performance_delivery_risk": "履约交付风险",
    "dispute_resolution_risk": "争议处置风险",
    "clause_balance_risk": "条款失衡风险",
}

RISK_LABELS = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
}

SIGNING_LABELS = {
    "暂不建议直接签署": "暂不建议直接签署",
    "有条件签署": "有条件签署",
    "建议签署": "建议签署",
}

app = FastAPI(title="合同风险评估系统", docs_url=None, redoc_url=None)


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = TEMPLATES_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/review")
async def api_review(request: Request):
    body = await request.json()
    contract_text = body.get("contract_text", "").strip()
    contract_id = body.get("contract_id", "").strip()
    source_document = body.get("source_document")
    allowed_priorities = set(body.get("allowed_priorities") or []) or None
    include_debug = bool(body.get("include_debug"))

    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)
    if not contract_id:
        contract_id = "unnamed-contract"

    try:
        review_result = review_contract_text(
            contract_text,
            contract_id=contract_id,
            source_document=source_document,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"AI 审查失败：{exc}"}, status_code=502)

    evidence = build_evidence(review_result, allowed_priorities=allowed_priorities)
    report = assess_risk(evidence)
    report_dict = asdict(report)
    _localize_report(report_dict)

    try:
        polished = polish_report(report)
        report_dict["polished"] = {
            "executive_summary": polished.executive_summary,
            "dimension_insights": polished.dimension_insights,
            "signing_advice": polished.signing_advice,
            "action_plan": polished.action_plan,
            "cross_dimension_notes": polished.cross_dimension_notes,
            "issue_reports": [asdict(item) for item in polished.issue_reports],
            "legal_view": polished.legal_view,
            "business_view": polished.business_view,
            "executive_view": polished.executive_view,
        }
    except Exception:
        report_dict["polished"] = None

    response_payload = {
        "contract_id": review_result.contract_id,
        "node_observations": [asdict(item) for item in evidence.node_observations],
        "report": report_dict,
    }
    if include_debug:
        response_payload["debug"] = {
            "allowed_priorities": sorted(allowed_priorities)
            if allowed_priorities
            else None,
            "evidence_items": [asdict(item) for item in evidence.evidence_items],
            "node_observations": [asdict(item) for item in evidence.node_observations],
        }

    return JSONResponse(response_payload)


def _localize_report(report: dict) -> None:
    report["overall_risk_label"] = RISK_LABELS.get(
        report["overall_risk"], report["overall_risk"]
    )
    report["signing_recommendation_label"] = SIGNING_LABELS.get(
        report.get("signing_recommendation", ""),
        report.get("signing_recommendation", "有条件签署"),
    )
    report["requires_manual_review_label"] = (
        "建议复核" if report.get("requires_manual_review") else "暂不需要"
    )

    for dim_name, label in DIMENSION_LABELS.items():
        score = report.get("dimension_scores", {}).get(dim_name)
        if score is not None:
            if "dimension_risk_labels" not in report:
                report["dimension_risk_labels"] = {}
            report["dimension_risk_labels"][dim_name] = RISK_LABELS.get(
                _score_to_level(score), ""
            )

    for dim_name in report.get("dimension_summaries", {}):
        if dim_name in DIMENSION_LABELS:
            report["dimension_labels"] = report.get("dimension_labels", {})
            report["dimension_labels"][dim_name] = DIMENSION_LABELS[dim_name]

    for risk in report.get("top_risks", []):
        risk["risk_level_label"] = RISK_LABELS.get(
            risk.get("risk_level", ""), risk.get("risk_level", "")
        )
        risk["dimension_label"] = DIMENSION_LABELS.get(
            risk.get("dimension", ""), risk.get("dimension", "")
        )

    for dim_name, label in DIMENSION_LABELS.items():
        report["dimension_labels"] = report.get("dimension_labels", {})
        report["dimension_labels"][dim_name] = label


def _score_to_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"
