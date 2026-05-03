from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import tempfile

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.domain.review_schema import RiskEvidence
from contract_risk_analysis.pipeline.build_evidence import build_evidence
from contract_risk_analysis.review.ai_review import review_contract_text, free_review_contract_text
from contract_risk_analysis.review.report_writer import polish_report, generate_combined_report
from contract_risk_analysis.bn.consistency_validator import build_consistency_report

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

from contract_risk_analysis.constants import DIMENSION_LABELS, RISK_LABELS

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
    review_party = body.get("review_party", "buyer")  # "buyer" | "seller"
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


# ── V2 Pipeline API (LLM₁ → BN → LLM₂) ──────────────────────────


@app.post("/api/v2/review")
async def api_v2_review(request: Request):
    """Full v2 pipeline: LLM₁ free review → BN consistency → LLM₂ report."""
    body = await request.json()
    contract_text = body.get("contract_text", "").strip()
    contract_id = body.get("contract_id", "").strip()
    source_document = body.get("source_document")
    review_party = body.get("review_party", "buyer")

    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)
    if not contract_id:
        contract_id = "unnamed-contract"

    import time as _time
    _t0 = _time.time()

    try:
        free_output = free_review_contract_text(
            contract_text, contract_id, source_document, review_party
        )
        consistency = build_consistency_report(free_output)

        # ── P2: Quality gate — counterfactual output check ──
        cf_count = len(consistency.counterfactuals) if consistency else 0
        core_dims = {
            "financial_exposure_risk", "performance_delivery_risk",
            "legal_enforceability_risk", "dispute_resolution_risk",
            "clause_balance_risk",
        }
        covered_dims: set[str] = set()
        if consistency and consistency.counterfactuals:
            for cf in consistency.counterfactuals:
                for dd in cf.dimension_deltas:
                    covered_dims.add(dd.dimension_key)
        uncovered_core = core_dims - covered_dims
        quality_warnings: list[str] = []
        if cf_count < 3:
            msg = (
                f"BN反事实产出不足：仅{cf_count}项（目标≥5）。"
                f"核心维度未覆盖：{uncovered_core or '无'}。"
            )
            quality_warnings.append(msg)
            logger.warning("QUALITY_GATE: %s", msg)
        if uncovered_core:
            quality_warnings.append(
                f"以下核心维度无BN反事实数据：{uncovered_core}"
            )

        polished = generate_combined_report(free_output, consistency, review_party)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"审查失败：{exc}"}, status_code=502)

    # ── P3: Save to MySQL for history management ──
    report_id: int | None = None
    try:
        from contract_risk_analysis.db.repository import (
            save_report, save_report_risks, save_report_counterfactuals,
            upsert_contract,
        )
        cid = upsert_contract(
            contract_name=contract_id,
            contract_text=contract_text,
            file_name=source_document,
        )
        # Extract overall P(high) from BN posteriors
        overall_ph = None
        if consistency and consistency.bn_posteriors:
            ov = consistency.bn_posteriors.get("overall_contract_risk")
            if ov:
                overall_ph = round(ov.get("high", 0.0) * 100, 1)

        report_id = save_report(
            contract_id=cid,
            report_content_md=polished.narrative_report,
            review_party=review_party,
            overall_p_high=overall_ph,
            summary_text=polished.executive_summary,
            bn_counterfactual_count=cf_count,
            review_duration_ms=int((_time.time() - _t0) * 1000),
        )
        # Save risk details
        risk_records: list[dict] = []
        for seg in free_output.risk_segments:
            risk_records.append({
                "name": seg.risk_title,
                "level": {"critical": "致命", "high": "高", "medium": "中", "low": "低", "positive": "低"}.get(seg.severity, "中"),
                "category": seg.clause_type,
                "confidence": int(seg.confidence * 100),
                "bn_verified": False,
            })
        save_report_risks(report_id, risk_records)
        # Save counterfactuals
        cf_records: list[dict] = []
        if consistency and consistency.counterfactuals:
            for cf in consistency.counterfactuals:
                cf_records.append({
                    "node_label": cf.node_label,
                    "base_high_risk": cf.base_high_risk,
                    "counterfactual_high_risk": cf.counterfactual_high_risk,
                    "delta_high_risk": cf.delta_high_risk,
                    "dimension_deltas": [
                        {"base_high": dd.base_high,
                         "counterfactual_high": dd.counterfactual_high,
                         "delta": dd.delta}
                        for dd in cf.dimension_deltas
                    ],
                })
        save_report_counterfactuals(report_id, cf_records)
    except Exception as db_exc:
        logger.warning("DB_SAVE_FAILED: %s", db_exc)

    return JSONResponse({
        "generation_mode": "combined",
        "contract_id": contract_id,
        "review_party": review_party,
        "narrative_report": polished.narrative_report,
        "executive_summary": polished.executive_summary,
        "signing_advice": polished.signing_advice,
        "action_plan": polished.action_plan,
        "cross_dimension_notes": polished.cross_dimension_notes,
        "free_review": {
            "segments_count": len(free_output.risk_segments),
            "missing_clauses": free_output.missing_clauses,
            "strengths": free_output.strengths,
            "overall_assessment": free_output.overall_assessment,
        },
        "consistency": {
            "annotations_count": len(consistency.annotations) if consistency else 0,
            "counterfactuals_count": len(consistency.counterfactuals) if consistency else 0,
            "bn_summary": consistency.bn_summary if consistency else "",
        },
        "bn_derived_claims": polished.bn_derived_claims,
        "llm_judgment_claims": polished.llm_judgment_claims,
        "quality_gate": {
            "counterfactuals_count": cf_count,
            "core_dimensions_covered": sorted(covered_dims),
            "core_dimensions_uncovered": sorted(uncovered_core),
            "warnings": quality_warnings,
            "passed": len(quality_warnings) == 0,
        },
        "report_id": report_id,         # MySQL record id for history lookup
        "saved_to_db": report_id is not None,
    })


# ── BN Interactive Sandbox API ────────────────────────────────────


@app.get("/api/bn/nodes")
async def api_bn_nodes():
    """Return adjustable evidence nodes for the interactive sandbox."""
    from contract_risk_analysis.bn.pgmpy_adapter import load_v2_config

    config = load_v2_config()
    nodes: list[dict] = []
    for node_name, node_cfg in config["nodes"].items():
        layer = node_cfg.get("layer", "")
        if layer not in ("contract_fact", "legal_semantics"):
            continue
        if node_name.startswith("cuad_agg_"):
            continue
        # Determine which dimension this node affects
        from contract_risk_analysis.bn.pgmpy_adapter import _build_node_to_dimension_map
        node_map = _build_node_to_dimension_map(config)
        dims = node_map.get(node_name, [])
        nodes.append({
            "node_name": node_name,
            "label": node_cfg.get("label", node_name),
            "layer": layer,
            "states": node_cfg.get("states", []),
            "affects_dimensions": dims,
            "affects_dimension_labels": [DIMENSION_LABELS.get(d, d) for d in dims],
        })
    return JSONResponse({"nodes": nodes, "dimension_labels": DIMENSION_LABELS})


@app.post("/api/bn/simulate")
async def api_bn_simulate(request: Request):
    """Run BN inference with custom evidence and return posteriors.

    Body: { "evidence": { "payment_structure": "favorable", ... } }
    Returns full posterior distributions for all dimension nodes + overall.
    """
    body = await request.json()
    evidence = body.get("evidence", {})
    if not isinstance(evidence, dict):
        return JSONResponse({"error": "evidence must be a dict"}, status_code=400)

    from contract_risk_analysis.bn.pgmpy_adapter import (
        DIMENSION_NODES,
        build_model,
        load_v2_config,
    )

    config = load_v2_config()
    model = build_model(config)
    from pgmpy.inference import VariableElimination

    try:
        inference = VariableElimination(model)
    except Exception:
        return JSONResponse({"error": "BN model build failed"}, status_code=500)

    posteriors: dict[str, dict[str, float]] = {}
    target_nodes = DIMENSION_NODES + ["overall_contract_risk"]

    for target in target_nodes:
        try:
            result = inference.query(
                variables=[target],
                evidence=evidence if evidence else None,
            )
            dist: dict[str, float] = {}
            for state, prob in zip(result.state_names[target], result.values):
                dist[str(state)] = round(float(prob), 4)
            posteriors[target] = dist
        except Exception:
            posteriors[target] = {"error": "computation failed"}

    from contract_risk_analysis.constants import DIMENSION_LABELS as DL
    return JSONResponse({
        "evidence": evidence,
        "posteriors": posteriors,
        "dimension_labels": DL,
    })


# ── Report Export API ──────────────────────────────────────────


@app.post("/api/export/pdf")
async def api_export_pdf(request: Request):
    """Export a Markdown report to PDF.

    Body: { "markdown": "...", "filename": "report-name" }
    Returns: PDF file download.
    """
    body = await request.json()
    md_text = body.get("markdown", "").strip()
    filename = body.get("filename", "contract-review-report")

    if not md_text:
        return JSONResponse({"error": "markdown 内容不能为空"}, status_code=400)

    from contract_risk_analysis.export.pdf_exporter import export_pdf

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        output_path = export_pdf(md_text, tmp.name)
        tmp.flush()
        return FileResponse(
            path=str(output_path),
            media_type="application/pdf",
            filename=f"{filename}.pdf",
        )


@app.post("/api/export/md")
async def api_export_md(request: Request):
    """Export a report as raw Markdown download.

    Body: { "markdown": "...", "filename": "report-name" }
    Returns: .md file download.
    """
    body = await request.json()
    md_text = body.get("markdown", "").strip()
    filename = body.get("filename", "contract-review-report")

    if not md_text:
        return JSONResponse({"error": "markdown 内容不能为空"}, status_code=400)

    from contract_risk_analysis.export.pdf_exporter import export_md

    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as tmp:
        output_path = export_md(md_text, tmp.name)
        tmp.flush()
        return FileResponse(
            path=str(output_path),
            media_type="text/markdown; charset=utf-8",
            filename=f"{filename}.md",
        )


# ── History & Report Management API (P3) ──────────────────────


@app.get("/api/reports")
async def api_list_reports(request: Request):
    """List historical reports.

    Query params: ?review_party=buyer&contract_type=销售合同&limit=50
    """
    review_party = request.query_params.get("review_party")
    contract_type = request.query_params.get("contract_type")
    limit = min(int(request.query_params.get("limit", "50")), 200)

    from contract_risk_analysis.db.repository import list_reports

    try:
        reports = list_reports(
            review_party=review_party,
            contract_type=contract_type,
            limit=limit,
        )
        # Convert datetime to string
        for r in reports:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return JSONResponse({"reports": reports, "count": len(reports)})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


@app.get("/api/reports/{report_id}")
async def api_get_report(report_id: int):
    """Get a single report with full content."""
    from contract_risk_analysis.db.repository import get_report

    try:
        report = get_report(report_id)
        if not report:
            return JSONResponse({"error": "报告不存在"}, status_code=404)
        return JSONResponse({
            "id": report.id,
            "contract_id": report.contract_id,
            "report_version": report.report_version,
            "review_party": report.review_party,
            "overall_risk_level": report.overall_risk_level,
            "overall_p_high": report.overall_p_high,
            "summary_text": report.summary_text,
            "report_content_md": report.report_content_md,
            "bn_counterfactual_count": report.bn_counterfactual_count,
            "review_duration_ms": report.review_duration_ms,
            "created_at": report.created_at.isoformat(),
        })
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


@app.get("/api/reports/diff")
async def api_diff_reports(request: Request):
    """Compare two reports.

    Query params: ?id1=1&id2=2
    """
    id1 = request.query_params.get("id1")
    id2 = request.query_params.get("id2")
    if not id1 or not id2:
        return JSONResponse({"error": "需要 id1 和 id2 参数"}, status_code=400)

    from contract_risk_analysis.db.repository import get_report_diff

    try:
        diff = get_report_diff(int(id1), int(id2))
        return JSONResponse(diff)
    except Exception as exc:
        return JSONResponse({"error": f"对比失败：{exc}"}, status_code=500)


# ── BN Feedback API (P6.2) ─────────────────────────────────────


@app.post("/api/feedback")
async def api_save_feedback(request: Request):
    """Record human review feedback on a BN claim.

    Body: { "report_id": 1, "node_name": "liability_cap_strength",
            "verdict": "correct", "reviewer_note": "..." }
    """
    body = await request.json()
    report_id = body.get("report_id")
    node_name = body.get("node_name", "").strip()
    verdict = body.get("verdict", "").strip()
    reviewer_note = body.get("reviewer_note")

    if not report_id or not node_name or not verdict:
        return JSONResponse({"error": "report_id, node_name, verdict 必填"}, status_code=400)

    from contract_risk_analysis.bn.feedback import save_feedback

    try:
        fid = save_feedback(
            report_id=int(report_id),
            node_name=node_name,
            verdict=verdict,
            reviewer_note=reviewer_note,
        )
        return JSONResponse({"id": fid, "status": "ok"})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"保存失败：{exc}"}, status_code=500)


@app.get("/api/feedback/summary")
async def api_feedback_summary():
    """Get aggregated BN feedback accuracy per node."""
    from contract_risk_analysis.bn.feedback import get_feedback_summary

    try:
        rows = get_feedback_summary()
        return JSONResponse({"nodes": rows, "count": len(rows)})
    except Exception as exc:
        return JSONResponse({"error": f"查询失败：{exc}"}, status_code=500)


# ── Dual-Perspective Review API (P6.3) ─────────────────────────


@app.post("/api/v2/review/dual")
async def api_v2_dual_review(request: Request):
    """Run both buyer and seller reviews for the same contract.

    Returns side-by-side comparison with key differences highlighted.

    Body: same as /api/v2/review (contract_text, contract_id, source_document)
    """
    body = await request.json()
    contract_text = body.get("contract_text", "").strip()
    contract_id = body.get("contract_id", "").strip()
    source_document = body.get("source_document")

    if not contract_text:
        return JSONResponse({"error": "合同文本不能为空"}, status_code=400)
    if not contract_id:
        contract_id = "unnamed-contract"

    import time as _time

    results: dict[str, dict] = {}
    for party in ("buyer", "seller"):
        t0 = _time.time()
        try:
            free_output = free_review_contract_text(
                contract_text, contract_id, source_document, party
            )
            consistency = build_consistency_report(free_output)
            polished = generate_combined_report(free_output, consistency, party)
            results[party] = {
                "executive_summary": polished.executive_summary,
                "signing_advice": polished.signing_advice,
                "overall_assessment": free_output.overall_assessment,
                "risk_segments_count": len(free_output.risk_segments),
                "counterfactuals_count": (
                    len(consistency.counterfactuals) if consistency else 0
                ),
                "strengths": free_output.strengths,
                "missing_clauses": free_output.missing_clauses,
                "duration_ms": int((_time.time() - t0) * 1000),
            }
        except Exception as exc:
            results[party] = {"error": str(exc)}

    # Build comparison
    comparison: dict = {}
    if "buyer" in results and "seller" in results:
        b = results["buyer"]
        s = results["seller"]
        # Find shared risks (clause types that appear in both)
        b_strengths = set(b.get("strengths", []))
        s_strengths = set(s.get("strengths", []))
        b_missing = set(b.get("missing_clauses", []))
        s_missing = set(s.get("missing_clauses", []))

        comparison = {
            "shared_strengths": sorted(b_strengths & s_strengths),
            "buyer_unique_strengths": sorted(b_strengths - s_strengths),
            "seller_unique_strengths": sorted(s_strengths - b_strengths),
            "shared_missing": sorted(b_missing & s_missing),
            "buyer_unique_concerns": sorted(b_missing - s_missing),
            "seller_unique_concerns": sorted(s_missing - b_missing),
        }

    return JSONResponse({
        "contract_id": contract_id,
        "buyer": results.get("buyer", {}),
        "seller": results.get("seller", {}),
        "comparison": comparison,
    })
