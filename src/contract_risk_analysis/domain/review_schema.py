from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReviewFinding:
    clause_type: str
    status: str
    evidence_text: str
    confidence: float
    hypothesis: str | None = None
    risk_factor: str | None = None
    finding_key: str | None = None
    finding_label: str | None = None
    counterparty_favorability: str | None = None


@dataclass(frozen=True)
class ReviewResult:
    contract_id: str
    findings: list[ReviewFinding]
    review_type: str | None = None
    source_document: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    contract_id: str
    node_name: str
    mapped_state: str
    node_layer: str | None
    node_priority: str | None
    source_text: str
    clause_type: str
    raw_status: str
    confidence: float
    finding_label: str | None = None
    finding_key: str | None = None


@dataclass(frozen=True)
class NodeObservation:
    node_name: str
    observed_state: str
    observation_confidence: float
    supporting_evidence_ids: list[str] = field(default_factory=list)
    conflict_flag: bool = False


@dataclass(frozen=True)
class RiskEvidence:
    contract_id: str
    node_states: dict[str, str]
    triggered_findings: list[str]
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    node_observations: list[NodeObservation] = field(default_factory=list)
    supporting_findings_by_node: dict[str, list[str]] = field(default_factory=dict)
    supporting_evidence_by_node: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskItem:
    title: str
    dimension: str
    risk_level: str
    reason: str
    evidence: list[str]
    recommendation: str
    node_name: str | None = None
    clause_type: str | None = None


@dataclass(frozen=True)
class ReportIssueInput:
    issue_id: str
    title: str
    risk_level: str
    dimension: str
    clause_type: str | None = None
    node_name: str | None = None
    problem_analysis_brief: str = ""
    clause_excerpt: str = ""
    evidence: list[str] = field(default_factory=list)
    legal_topic: str | None = None
    recommendation: str = ""
    revision_hint: str = ""
    manual_review_required: bool = False


@dataclass(frozen=True)
class LegalIssueReport:
    issue_id: str
    title: str
    risk_level: str
    problem_analysis: str
    original_clause: str
    legal_basis: str
    best_practice: str
    suggested_revision: str
    revision_reason: str


@dataclass(frozen=True)
class RiskReport:
    contract_id: str
    overall_risk: str
    requires_manual_review: bool
    category_scores: dict[str, float]
    summary_reasons: list[str]
    signing_recommendation: str = "有条件签署"
    dimension_scores: dict[str, float] = field(default_factory=dict)
    dimension_summaries: dict[str, str] = field(default_factory=dict)
    top_risks: list[RiskItem] = field(default_factory=list)
    report_issue_inputs: list[ReportIssueInput] = field(default_factory=list)
    manual_review_items: list[str] = field(default_factory=list)
