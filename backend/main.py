"""BN Contract Risk Analysis — FastAPI Backend.

Clean REST API wrapping the contract risk analysis pipeline.
Start: uvicorn backend.main:app --port 9527 --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.misc import router as misc_router
from backend.routers.upload import router as upload_router
from backend.routers.sandbox import router as sandbox_router
from backend.routers.review import router as review_router
from backend.routers.dual import router as dual_router
from backend.routers.export import router as export_router
from backend.routers.history import router as history_router
from backend.routers.redlines import router as redlines_router
from backend.routers.feedback import router as feedback_router

app = FastAPI(title="合同风险审查系统", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(misc_router)
app.include_router(upload_router)
app.include_router(sandbox_router)
app.include_router(review_router)
app.include_router(dual_router)
app.include_router(export_router)
app.include_router(history_router)
app.include_router(redlines_router)
app.include_router(feedback_router)
