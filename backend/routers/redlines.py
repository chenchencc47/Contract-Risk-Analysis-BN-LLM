"""Company redlines CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/api/redlines")
async def api_list_redlines():
    from contract_risk_analysis.db.repository import list_all_redlines
    try:
        redlines = list_all_redlines()
        return JSONResponse({"redlines": redlines, "count": len(redlines)})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


@router.post("/api/redlines")
async def api_save_redline(request: Request):
    body = await request.json()
    for key in ("contract_type", "category", "rule_id", "label", "description"):
        if not body.get(key):
            return JSONResponse({"error": f"{key} 不能为空"}, status_code=400)
    from contract_risk_analysis.db.repository import upsert_redline
    try:
        rid = upsert_redline(
            contract_type=str(body["contract_type"]), category=str(body["category"]),
            rule_id=str(body["rule_id"]), label=str(body["label"]),
            description=str(body["description"]), severity=body.get("severity"),
            is_active=int(body.get("is_active", 1)),
        )
        return JSONResponse({"id": rid, "status": "ok"})
    except Exception as exc:
        return JSONResponse({"error": f"保存失败：{exc}"}, status_code=500)


@router.delete("/api/redlines/{redline_id}")
async def api_delete_redline(redline_id: int):
    from contract_risk_analysis.db.repository import delete_redline
    try:
        ok = delete_redline(redline_id)
        if not ok:
            return JSONResponse({"error": "规则不存在"}, status_code=404)
        return JSONResponse({"status": "ok"})
    except Exception as exc:
        return JSONResponse({"error": f"删除失败：{exc}"}, status_code=500)


@router.get("/api/redlines/types")
async def api_redline_types():
    from contract_risk_analysis.db.repository import get_redline_contract_types
    try:
        types = get_redline_contract_types()
        return JSONResponse({"types": types})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)
