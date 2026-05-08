"""BN feedback endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/api/feedback")
async def api_save_feedback(request: Request):
    body = await request.json()
    report_id = body.get("report_id")
    node_name = str(body.get("node_name", "")).strip()
    verdict = str(body.get("verdict", "")).strip()
    reviewer_note = body.get("reviewer_note")
    if not report_id or not node_name or not verdict:
        return JSONResponse({"error": "report_id, node_name, verdict 必填"}, status_code=400)
    from contract_risk_analysis.bn.feedback import save_feedback
    try:
        fid = save_feedback(report_id=int(report_id), node_name=node_name,
                            verdict=verdict, reviewer_note=reviewer_note)
        return JSONResponse({"id": fid, "status": "ok"})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"保存失败：{exc}"}, status_code=500)


@router.get("/api/feedback/summary")
async def api_feedback_summary():
    from contract_risk_analysis.bn.feedback import get_feedback_summary
    try:
        rows = get_feedback_summary()
        return JSONResponse({"nodes": rows, "count": len(rows)})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)
