"""Report history endpoints — list, detail, diff."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/api/reports")
async def api_list_reports(request: Request):
    review_party = request.query_params.get("review_party")
    contract_type = request.query_params.get("contract_type")
    limit = min(int(request.query_params.get("limit", "50")), 200)
    from contract_risk_analysis.db.repository import list_reports
    try:
        reports = list_reports(review_party=review_party, contract_type=contract_type, limit=limit)
        for r in reports:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return JSONResponse({"reports": reports, "count": len(reports)})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


@router.get("/api/reports/{report_id}")
async def api_get_report(report_id: int):
    from contract_risk_analysis.db.repository import get_report
    try:
        report = get_report(report_id)
        if not report:
            return JSONResponse({"error": "报告不存在"}, status_code=404)
        return JSONResponse({
            "id": report.id, "contract_id": report.contract_id,
            "report_version": report.report_version, "review_party": report.review_party,
            "overall_risk_level": report.overall_risk_level, "overall_p_high": report.overall_p_high,
            "summary_text": report.summary_text, "report_content_md": report.report_content_md,
            "bn_counterfactual_count": report.bn_counterfactual_count,
            "created_at": report.created_at.isoformat(),
        })
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


@router.get("/api/reports/diff")
async def api_diff_reports(request: Request):
    id1 = request.query_params.get("id1")
    id2 = request.query_params.get("id2")
    if not id1 or not id2:
        return JSONResponse({"error": "需要 id1 和 id2 参数"}, status_code=400)
    from contract_risk_analysis.db.repository import get_report_diff
    try:
        return JSONResponse(get_report_diff(int(id1), int(id2)))
    except Exception as exc:
        return JSONResponse({"error": f"对比失败：{exc}"}, status_code=500)
