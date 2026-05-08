"""Upload endpoint."""

from __future__ import annotations

import tempfile
import os as _os
from pathlib import Path

from fastapi import APIRouter, UploadFile, File as FastAPIFile
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/api/upload")
async def api_upload(file: UploadFile = FastAPIFile(...)):
    """Upload a contract file (PDF/Word/TXT) and return extracted text."""
    if not file.filename:
        return JSONResponse({"error": "未选择文件"}, status_code=400)

    filename = file.filename
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".doc", ".txt", ".md"):
        return JSONResponse({"error": f"不支持的文件格式: {suffix}，支持 .pdf / .docx / .txt"}, status_code=400)

    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        from contract_risk_analysis.utils.file_extractor import extract_text
        text, error = extract_text(tmp_path, filename)
        _os.unlink(tmp_path)

        if error:
            return JSONResponse({"error": error}, status_code=422)
        if not text.strip():
            return JSONResponse({"error": "文件内容为空"}, status_code=422)

        return JSONResponse({
            "filename": filename,
            "text": text,
            "char_count": len(text),
        })
    except Exception as exc:
        return JSONResponse({"error": f"文件处理失败: {exc}"}, status_code=500)
