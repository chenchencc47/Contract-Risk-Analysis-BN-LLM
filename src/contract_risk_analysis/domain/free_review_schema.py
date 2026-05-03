"""Free-form review data models for the refactored LLM→BN→LLM pipeline.

In the new architecture, LLM₁ produces unconstrained risk analysis (no fixed
finding_key), the BN acts as a consistency validator rather than a central
risk scorer, and LLM₂ synthesizes both into the final report.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── LLM₁ output ──────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskSegment:
    """A single risk item identified by LLM₁ free-form review.

    Unlike ReviewFinding, this does not depend on a fixed finding_key
    or a predefined set of clause types. LLM₁ is free to identify any
    risk in any contract domain.
    """

    clause_type: str
    """Free-form category, e.g. 'payment', 'delivery', 'warranty', 'termination'."""

    risk_title: str
    """Short Chinese label, e.g. '预付款比例过高'."""

    risk_description: str
    """Detailed analysis, 2-5 sentences explaining the risk."""

    evidence_text: str
    """Excerpt from the contract text supporting this finding."""

    confidence: float
    """LLM's self-assessed confidence, 0-1."""

    severity: str
    """LLM's severity rating: 'critical' | 'high' | 'medium' | 'low' | 'positive'."""

    counterparty_impact: str | None = None
    """Who benefits: 'buyer_favorable' | 'seller_favorable' | 'neutral'."""

    recommendation: str | None = None
    """Suggested revision or action item."""

    suggested_bn_nodes: list[str] | None = None
    """Best-effort hint mapping to BN node names, may be empty or absent.
    Used by BnMappingService as a starting point for heuristic matching."""

    legal_basis: str | None = None
    """Relevant legal principle or statute reference, e.g. '民法典第622条'."""


@dataclass(frozen=True)
class FreeReviewOutput:
    """LLM₁'s complete free-form contract review output.

    Contains rich, unconstrained risk analysis covering any risk type
    the LLM identifies, without being limited to a predefined BN node set.
    """

    contract_id: str

    overall_assessment: str
    """2-4 paragraph executive summary written by LLM₁."""

    risk_segments: list[RiskSegment]
    """All identified risks, in any number and any category."""

    missing_clauses: list[str]
    """Clause types that LLM₁ found to be completely absent from the contract."""

    strengths: list[str]
    """Positive or favorable aspects of the contract."""

    review_type: str | None = None
    source_document: str | None = None


# ── BN validator output ──────────────────────────────────────────


@dataclass(frozen=True)
class ValidationAnnotation:
    """A single validation note produced by the BN consistency checker.

    These are NOT risk scores — they are observations about the quality
    and completeness of LLM₁'s analysis, identified by the BN's causal
    domain knowledge.
    """

    annotation_type: str
    """One of:
    - 'missing_dimension': BN graph expects a dimension LLM₁ didn't cover.
    - 'contradiction': BN posteriors conflict with LLM₁'s severity rating.
    - 'confidence_mismatch': LLM₁ confidence seems too high/low vs historical data.
    - 'causal_incoherence': LLM₁'s causal chain contradicts BN graph structure.
    - 'cross_dimension_risk': Multiplicative risk combination BN identified.
    - 'gap_detected': LLM₁ identified a risk that has no corresponding BN node.
    """

    severity: str
    """'info' | 'warning' | 'error' — how serious this annotation is."""

    message: str
    """Human-readable Chinese explanation."""

    bn_node: str | None = None
    """Relevant BN node name, if applicable."""

    llm_clause_type: str | None = None
    """Back-reference to RiskSegment.clause_type, if applicable."""

    detail: dict | None = None
    """Structured data, e.g. {'probability': 0.78, 'threshold': 0.7}."""


@dataclass(frozen=True)
class CounterfactualResult:
    """What-if analysis: how changing a clause would affect overall risk.

    Repackaged from the BN sensitivity analysis. Unlike the legacy
    RiskItem, this is clearly labeled as a BN simulation, not a risk finding.
    """

    node_name: str
    node_label: str
    current_state: str
    proposed_state: str
    base_high_risk: float
    counterfactual_high_risk: float
    delta_high_risk: float
    description: str
    """Natural-language explanation in Chinese."""

    # ── Dimension-level deltas (v2.1) ──
    dimension_deltas: list["DimensionDelta"] = field(default_factory=list)
    """Per-dimension probability changes, e.g. financial_exposure -50%."""

    # ── Derivation chain (P1) ──
    derivation_chain: str = ""
    """Traceable derivation: evidence → CPT prior → inference → posterior delta."""


@dataclass(frozen=True)
class DimensionDelta:
    """Probability change for a specific risk dimension under a counterfactual."""

    dimension_key: str  # e.g. "financial_exposure_risk"
    dimension_label: str  # e.g. "财务暴露风险"
    base_high: float  # P(dim="high" | current evidence)
    counterfactual_high: float  # P(dim="high" | improved)
    delta: float  # base_high - counterfactual_high


@dataclass(frozen=True)
class ConsistencyReport:
    """Complete BN validator output.

    Contains validation annotations, counterfactual simulations,
    full BN posterior distributions (informational), and a human-readable
    BN summary.
    """

    contract_id: str

    annotations: list[ValidationAnnotation]
    """All validation notes from the BN checks."""

    counterfactuals: list[CounterfactualResult]
    """Top-N counterfactual simulations."""

    bn_posteriors: dict[str, dict[str, float]]
    """Full posterior distributions for all BN risk/decision nodes.
    Informational — these are NOT treated as authoritative risk scores."""

    bn_summary: str
    """2-3 paragraph BN perspective in Chinese.
    Explains what the BN validated, what it flagged, and its confidence."""

    joint_risks: list[dict] = field(default_factory=list)
    """P6.1: Joint probability analysis results.
    Each entry: {dim_a, dim_b, p_a_high, p_b_high, p_joint_high, multiplier, description}"""

    bn_config_version: str = "2.0"
