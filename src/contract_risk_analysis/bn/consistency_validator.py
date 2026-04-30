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
) -> ConsistencyReport:
    """Orchestrate BN validation and return a ConsistencyReport.

    This is the main entry point for the v2 pipeline's BN layer.
    It maps LLM findings to BN nodes, runs all consistency checks,
    performs counterfactual simulation, and produces a structured report.
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

    return ConsistencyReport(
        contract_id=free_output.contract_id,
        annotations=all_annotations,
        counterfactuals=counterfactuals,
        bn_posteriors=bn_posteriors,
        bn_summary=bn_summary,
    )
