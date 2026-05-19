"""Export endpoints — PDF and Markdown."""

from __future__ import annotations

import tempfile

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()


@router.post("/api/export/pdf")
async def api_export_pdf(request: Request):
    body = await request.json()
    md_text = str(body.get("markdown", "")).strip()
    filename = str(body.get("filename", "contract-review-report"))
    if not md_text:
        return JSONResponse({"error": "markdown 内容不能为空"}, status_code=400)
    from contract_risk_analysis.export.pdf_exporter import export_pdf
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        output_path = export_pdf(md_text, tmp.name)
        return FileResponse(str(output_path), media_type="application/pdf",
                            filename=f"{filename}.pdf")


@router.post("/api/export/md")
async def api_export_md(request: Request):
    body = await request.json()
    md_text = str(body.get("markdown", "")).strip()
    filename = str(body.get("filename", "contract-review-report"))
    if not md_text:
        return JSONResponse({"error": "markdown 内容不能为空"}, status_code=400)
    from contract_risk_analysis.export.pdf_exporter import export_md
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False) as tmp:
        output_path = export_md(md_text, tmp.name)
        return FileResponse(str(output_path), media_type="text/markdown; charset=utf-8",
                            filename=f"{filename}.md")
