"""BN sandbox endpoints — node listing and simulation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/api/bn/nodes")
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


@router.post("/api/bn/simulate")
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
