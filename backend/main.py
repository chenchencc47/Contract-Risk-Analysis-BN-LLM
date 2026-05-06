"""BN Contract Risk Analysis — FastAPI Backend.

Clean REST API wrapping the contract risk analysis pipeline.
Start: uvicorn backend.main:app --port 9527 --reload
"""

from __future__ import annotations

import logging
import sys
import tempfile
import time as _time
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Ensure src/ is on path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi import FastAPI, Request, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

logger = logging.getLogger(__name__)

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
from contract_risk_analysis.evidence.rules import run_validation_rules

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


@app.post("/api/upload")
async def api_upload(file: UploadFile = FastAPIFile(...)):
    """Upload a contract file (PDF/Word/TXT) and return extracted text."""
    import tempfile, os as _os

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


@app.get("/api/health")
async def health() -> dict:
    vreport = validate_v2_config()
    return {
        "status": "ok",
        "pgmpy_available": True,
        "config_valid": vreport.is_valid,
        "config_errors": len(vreport.errors),
    }


# ── BN Interactive Sandbox API ──


@app.get("/api/bn/nodes")
async def api_bn_nodes():
    from contract_risk_analysis.bn.pgmpy_adapter import load_v2_config, _build_node_to_dimension_map
    from contract_risk_analysis.constants import DIMENSION_LABELS as DL
    config = load_v2_config()
    nodes: list[dict] = []
    node_map = _build_node_to_dimension_map(config)
    for node_name, node_cfg in config["nodes"].items():
        layer = node_cfg.get("layer", "")
        if layer not in ("contract_fact", "legal_semantics"):
            continue
        if node_name.startswith("cuad_agg_"):
            continue
        dims = node_map.get(node_name, [])
        nodes.append({
            "node_name": node_name,
            "label": node_cfg.get("label", node_name),
            "layer": layer,
            "states": node_cfg.get("states", []),
            "affects_dimensions": dims,
            "affects_dimension_labels": [DL.get(d, d) for d in dims],
        })
    return JSONResponse({"nodes": nodes, "dimension_labels": DL})


@app.post("/api/bn/simulate")
async def api_bn_simulate(request: Request):
    body = await request.json()
    evidence = body.get("evidence", {})
    if not isinstance(evidence, dict):
        return JSONResponse({"error": "evidence must be a dict"}, status_code=400)
    from contract_risk_analysis.bn.pgmpy_adapter import DIMENSION_NODES, build_model, load_v2_config
    from contract_risk_analysis.constants import DIMENSION_LABELS as DL
    from pgmpy.inference import VariableElimination
    config = load_v2_config()
    model = build_model(config)
    try:
        inference = VariableElimination(model)
    except Exception:
        return JSONResponse({"error": "BN model build failed"}, status_code=500)
    posteriors: dict[str, dict[str, float]] = {}
    for target in DIMENSION_NODES + ["overall_contract_risk"]:
        try:
            result = inference.query(variables=[target], evidence=evidence if evidence else None)
            dist = {str(state): round(float(prob), 4) for state, prob in zip(result.state_names[target], result.values)}
            posteriors[target] = dist
        except Exception:
            posteriors[target] = {"error": "computation failed"}
    return JSONResponse({"evidence": evidence, "posteriors": posteriors, "dimension_labels": DL})


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


# ── Direct v2 endpoint (same pipeline, explicit route) ──


@app.post("/api/v2/review")
async def api_v2_review(request: Request) -> JSONResponse:
    """Direct v2 pipeline endpoint — mirrors /api/review with v2_combined mode."""
    body: dict[str, Any] = await request.json()
    return await _run_v2_pipeline(body)


# ── Export endpoints ──


@app.post("/api/export/pdf")
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


@app.post("/api/export/md")
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


# ── History & Report Management ──


@app.get("/api/reports")
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


@app.get("/api/reports/{report_id}")
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


@app.get("/api/reports/diff")
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


# ── Company Redlines CRUD ──


@app.get("/api/redlines")
async def api_list_redlines():
    from contract_risk_analysis.db.repository import list_all_redlines
    try:
        redlines = list_all_redlines()
        return JSONResponse({"redlines": redlines, "count": len(redlines)})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


@app.post("/api/redlines")
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


@app.delete("/api/redlines/{redline_id}")
async def api_delete_redline(redline_id: int):
    from contract_risk_analysis.db.repository import delete_redline
    try:
        ok = delete_redline(redline_id)
        if not ok:
            return JSONResponse({"error": "规则不存在"}, status_code=404)
        return JSONResponse({"status": "ok"})
    except Exception as exc:
        return JSONResponse({"error": f"删除失败：{exc}"}, status_code=500)


@app.get("/api/redlines/types")
async def api_redline_types():
    from contract_risk_analysis.db.repository import get_redline_contract_types
    try:
        types = get_redline_contract_types()
        return JSONResponse({"types": types})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


# ── BN Feedback ──


@app.post("/api/feedback")
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


@app.get("/api/feedback/summary")
async def api_feedback_summary():
    from contract_risk_analysis.bn.feedback import get_feedback_summary
    try:
        rows = get_feedback_summary()
        return JSONResponse({"nodes": rows, "count": len(rows)})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


# ── Dual-Perspective Review ──


@app.post("/api/v2/review/dual")
async def api_v2_dual_review(request: Request):
    body = await request.json()
    contract_text = str(body.get("contract_text", "")).strip()
    contract_id = str(body.get("contract_id", "")).strip() or "unnamed"
    source_document = body.get("source_document")
    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)

    results: dict[str, dict] = {}
    for party in ("buyer", "seller"):
        t0 = _time.time()
        try:
            free_output = free_review_contract_text(
                contract_text, contract_id, source_document, party)
            consistency = build_consistency_report(free_output)
            polished = generate_combined_report(free_output, consistency, party)
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
