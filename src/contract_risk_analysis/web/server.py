from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.domain.review_schema import RiskEvidence
from contract_risk_analysis.pipeline.build_evidence import build_evidence
from contract_risk_analysis.review.ai_review import review_contract_text, free_review_contract_text
from contract_risk_analysis.review.report_writer import polish_report, generate_combined_report
from contract_risk_analysis.bn.consistency_validator import build_consistency_report

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

    try:
        free_output = free_review_contract_text(
            contract_text, contract_id, source_document, review_party
        )
        consistency = build_consistency_report(free_output)
        polished = generate_combined_report(free_output, consistency, review_party)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except Exception as exc:
        return JSONResponse({"error": f"审查失败：{exc}"}, status_code=502)

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
