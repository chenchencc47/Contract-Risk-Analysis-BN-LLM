"""Free-form review data models for the refactored LLM→BN→LLM pipeline.

In the new architecture, LLM₁ produces unconstrained risk analysis (no fixed
finding_key), the BN acts as a consistency validator rather than a central
risk scorer, and LLM₂ synthesizes both into the final report.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── LLM₁ output ──────────────────────────────────────────────────


@dataclass
class NegotiationChip:
    """Structured bargaining chip analysis for a risk segment."""

    chip_type: str | None = None
    location: str | None = None
    reason: str | None = None
    counterparty_attack: str | None = None
    strategy: str | None = None


@dataclass
class RiskSegment:
    """A single risk item identified by LLM₁ free-form review.

    Unlike ReviewFinding, this does not depend on a fixed finding_key
    or a predefined set of clause types. LLM₁ is free to identify any
    risk in any contract domain.

    NOT frozen — canonical_type is populated AFTER LLM₁ output by the
    canonicalization layer, then frozen by the adjudication layer.
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

    canonical_type: str | None = None
    """Deterministic normalized clause category assigned by the canonicalization layer.
    Populated AFTER LLM₁ output. Used by BnMappingService as the primary lookup key.
    Falls back to clause_type heuristic only when canonical_type is absent.
    This field STABILIZES the LLM₁→BN handoff across repeated runs."""

    counterparty_impact: str | None = None
    """Who benefits: 'buyer_favorable' | 'seller_favorable' | 'neutral'."""

    recommendation: str | None = None
    """Suggested revision or action item."""

    suggested_bn_nodes: list[str] | None = None
    """Best-effort hint mapping to BN node names, may be empty or absent.
    Used by BnMappingService as a starting point for heuristic matching."""

    legal_basis: str | None = None
    """Relevant legal principle or statute reference, e.g. '民法典第622条'."""

    negotiation_chip: NegotiationChip | None = None
    """Bargaining chip assessment. Three types (not every type exists in every contract):
    - 底线筹码 (defensive): favorable term the counterparty wants to change; must defend
    - 交换筹码 (trading): unfavorable term the counterparty wants to keep; concede strategically
    - 响应筹码 (responsive): term the counterparty fears; wait for them to raise, then trade
    Include: chip type, clause location, why it's a chip, counterparty's likely attack, strategy."""

    counterparty_attack_vector: str | None = None
    """Predicted counterparty negotiation angle: legal (显失公平/违反强制性规定),
    commercial (行业惯例/合作意愿), or strategic (用次要条款换我方让步)."""

    priority_rank: int | None = None
    """Negotiation priority 1-5:
    1=签约底线(必须修改), 2=核心谈判目标, 3=可交易项,
    4=低优先级, 5=仅供参考."""

    commercial_impact: str | None = None
    """Business impact beyond legal risk: cash flow, operations, relationship,
    market competitiveness."""


@dataclass
class FreeReviewOutput:
    """LLM₁'s complete free-form contract review output.

    Contains rich, unconstrained risk analysis covering any risk type
    the LLM identifies, without being limited to a predefined BN node set.

    NOT frozen — risk_segments are mutated in-place by canonicalization
    and adjudication layers before being frozen by the dossier builder.
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

    overall_strategic_assessment: str | None = None
    """Optional high-level strategic assessment: key bargaining chips,
    power balance between parties, recommended negotiation posture."""


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
    """Traceable derivation: 条款状态X→Y | CPT来源 | pgmpy VE推理 → δ=-43.3%"""


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

    bn_config_version: str = "2.0"

    # ── Joint probability risks (P6.1) ──
    joint_risks: list[dict] = field(default_factory=list)
    """Cross-dimension joint probability analysis results."""


# ── Report Dossier (Phase A: stable fact sheet) ───────────────────


@dataclass
class DossierRiskItem:
    """A frozen risk fact in the report dossier.

    These fields are DETERMINISTIC and must not be altered by LLM₂.
    LLM₂ may only translate them into professional Chinese prose.
    """

    issue_id: str
    """Stable identifier, e.g. 'ISSUE-001'. Assigned by the adjudication layer."""

    risk_title: str
    """Short Chinese label, frozen from LLM₁ output."""

    clause_type: str
    """Original free-form clause category from LLM₁."""

    severity: str
    """Frozen severity: 'critical' | 'high' | 'medium' | 'low' | 'positive'."""

    priority_rank: int
    """Frozen negotiation priority 1-5."""

    evidence_text: str
    """Contract excerpt supporting this finding."""

    confidence: float
    """LLM₁ self-assessed confidence, informational only."""

    canonical_type: str | None = None
    """Deterministic normalized clause category from the canonicalization layer."""

    recommendation: str | None = None
    legal_basis: str | None = None
    negotiation_chip: NegotiationChip | None = None
    counterparty_impact: str | None = None
    commercial_impact: str | None = None

    # ── BN linkage ──
    bn_node: str | None = None
    """Mapped BN node name, if any."""
    bn_coverage: bool = False
    """Does BN have counterfactual data for this item?"""

    # ── Quality flags ──
    manual_review: bool = False
    """Flagged for human review (conflict / low evidence / unstable)."""
    internal_conflict: str | None = None
    """If this item conflicts with another in the same report, describe the conflict."""


@dataclass
class ReportDossier:
    """Structured, deterministic fact sheet — the system's single source of truth.

    This is NOT narrative. It is the stable core that LLM₂ must render faithfully.
    LLM₂ is FORBIDDEN from:
    - Adding or removing risk items
    - Changing severity, priority_rank, or signing advice
    - Altering BN probability numbers
    - Suppressing manual_review flags

    Phase A: The dossier is the authoritative conclusion. The narrative report
    is a professional Chinese translation of this dossier.
    """

    contract_id: str
    review_party: str

    risk_items: list[DossierRiskItem]
    """All risk items with frozen severity, priority, evidence, and flags."""

    counterfactuals: list[CounterfactualResult]
    """BN counterfactual simulations — these numbers are BN-owned and immutable."""

    bn_annotations: list[ValidationAnnotation]
    """BN validation notes — gap_detected, contradiction, cross_dimension_risk, etc."""

    joint_risks: list[dict]
    """Cross-dimension joint probability risks."""

    bn_summary: str
    """BN perspective summary in Chinese."""

    overall_assessment: str
    """LLM₁ executive summary — treated as frozen context, not editable by LLM₂."""

    strengths: list[str]
    missing_clauses: list[str]

    # ── Signing guardrails (frozen) ──
    signing_forbidden: list[str]
    """Conditions under which the contract MUST NOT be signed."""
    signing_acceptable: list[str]
    """Conditions that must ALL be met before signing."""
    negotiation_bottom_lines: list[str]
    """Absolute red lines — must not be traded away."""

    # ── Post-v2.10 fields with defaults ──
    favorable_terms: list[FavorableTerm] = field(default_factory=list)
    """Terms that are advantageous to the review party — NOT risks. LLM₂ must
    render these as advantages to protect, not as risks to fix."""

    # ── Quality ──
    manual_review_items: list[str] = field(default_factory=list)
    """issue_ids flagged for mandatory human review."""
    internal_conflicts: list[str] = field(default_factory=list)
    """Descriptions of internal consistency violations found in this report."""


@dataclass
class FavorableTerm:
    """A contract term that is advantageous to the review party — NOT a risk.

    These are identified by the adjudication layer through party-aware rules.
    LLM₂ must render them as advantages to PROTECT, not as risks to FIX.
    """

    term_name: str
    """Short label, e.g. '无责任上限' or '争议管辖在甲方住所地'."""

    clause_type: str
    """Normalized clause category, e.g. 'liability_cap'."""

    description: str
    """Why this term is favorable to the review party."""

    defense_priority: str = "坚守"
    """'坚守' | '可交换' | '可让步' — how hard to defend this term."""

    evidence_text: str = ""
    """Contract excerpt showing this term."""

    chip_type: str = ""
    """Negotiation chip classification: '底线筹码' | '响应筹码' | '交换筹码'."""
