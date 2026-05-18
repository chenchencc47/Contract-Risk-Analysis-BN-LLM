"""BN Consistency Validator — orchestrator.

Orchestrates the BN validation pipeline:
  FreeReviewOutput → BnMappingService (bn_mapping)
                  → BnValidator (bn_validator)
                  → build_consistency_report
"""

from __future__ import annotations

from contract_risk_analysis.bn.bn_mapping import BnMappingService
from contract_risk_analysis.bn.bn_validator import BnValidator
from contract_risk_analysis.bn.pgmpy_adapter import (
    DIMENSION_NODES,
    build_model,
    load_v2_config,
    run_inference,
    run_sensitivity_analysis,
)
from contract_risk_analysis.constants import DIMENSION_LABELS, NODE_LABELS
from contract_risk_analysis.domain.free_review_schema import (
    ConsistencyReport,
    CounterfactualResult,
    DimensionDelta,
    FreeReviewOutput,
    RiskSegment,
    ValidationAnnotation,
)

#  Top-level orchestrator
# ═══════════════════════════════════════════════════════════════════


def build_consistency_report(
    free_output: FreeReviewOutput,
    bn_confidence: str = "high",
) -> ConsistencyReport:
    """Orchestrate BN validation and return a ConsistencyReport.

    This is the main entry point for the v2 pipeline's BN layer.
    It maps LLM findings to BN nodes, runs all consistency checks,
    performs counterfactual simulation, and produces a structured report.

    bn_confidence controls the depth of BN analysis:
      'high'   → CUAD-calibrated, full 6-pair multiplier analysis
      'medium' → partial coverage, top 3 pairs queried
      'low'    → minimal coverage, universal pairs only
    """
    # Step 1: Map LLM findings to BN nodes
    mapping_service = BnMappingService()
    node_states, mapping_annotations = mapping_service.map_risk_segments(
        free_output.risk_segments
    )

    # Step 2: Run BN validation checks
    validator = BnValidator()
    validation_annotations = validator.validate(free_output, node_states)

    # Step 3: Counterfactual simulation
    counterfactuals = validator.run_counterfactual_analysis(node_states)

    # Step 4: Generate BN summary
    all_annotations = mapping_annotations + validation_annotations
    bn_summary = validator.generate_bn_summary(
        node_states, all_annotations, counterfactuals
    )

    # Step 5: Run full BN inference for posterior reference
    try:
        inference_result = run_inference(evidence=node_states)
        bn_posteriors = {
            name: posterior.state_distribution
            for name, posterior in inference_result.posteriors.items()
        }
    except Exception:
        bn_posteriors = {}

    # Step 6 (P6.1): Joint probability analysis for multiplicative risk pairs.
    # Dimension pairs are loaded from contract_type_parameters.yaml (bn_dimension_pairs).
    # Selection depends on bn_confidence tier:
    #   high   → universal + optional (all pairs)
    #   medium → universal + top 1 from optional (by multiplier, queried together)
    #   low   → universal only
    joint_risks: list[dict] = []
    try:
        from contract_risk_analysis.bn.pgmpy_adapter import (
            DIMENSION_NODES, query_joint_probability,
        )
        from contract_risk_analysis.review.ai_review import load_bn_dimension_pairs

        universal_pairs, optional_pairs = load_bn_dimension_pairs()

        if bn_confidence == "low":
            dim_pairs = universal_pairs
            joint_results = query_joint_probability(
                dim_pairs=dim_pairs, evidence=node_states,
            )
        elif bn_confidence == "medium":
            # Query all pairs, sort by multiplier, keep universal + top 1 optional
            all_pairs = universal_pairs + optional_pairs
            joint_results_all = query_joint_probability(
                dim_pairs=all_pairs, evidence=node_states,
            )
            universal_set = set(universal_pairs)
            optional_results = [r for r in joint_results_all if (r.dim_a, r.dim_b) not in universal_set]
            optional_results.sort(key=lambda r: -r.multiplier)
            top_optional = optional_results[:1] if optional_results else []
            universal_results = [r for r in joint_results_all if (r.dim_a, r.dim_b) in universal_set]
            joint_results = universal_results + top_optional
        else:  # high
            dim_pairs = universal_pairs + optional_pairs
            joint_results = query_joint_probability(
                dim_pairs=dim_pairs, evidence=node_states,
            )

        for jr in joint_results:
            joint_risks.append({
                "dim_a": jr.dim_a,
                "dim_b": jr.dim_b,
                "dim_a_label": jr.dim_a_label,
                "dim_b_label": jr.dim_b_label,
                "p_a_high": jr.p_a_high,
                "p_b_high": jr.p_b_high,
                "p_joint_high": jr.p_joint_high,
                "multiplier": jr.multiplier,
                "description": jr.description,
            })
    except Exception:
        pass

    return ConsistencyReport(
        contract_id=free_output.contract_id,
        annotations=all_annotations,
        counterfactuals=counterfactuals,
        bn_posteriors=bn_posteriors,
        bn_summary=bn_summary,
        joint_risks=joint_risks,
    )
