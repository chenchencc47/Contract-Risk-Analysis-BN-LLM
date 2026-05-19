export interface Finding {
  clause_type: string;
  status: string;
  evidence_text: string;
  confidence: number;
  hypothesis: string | null;
  risk_factor: string | null;
  finding_key: string | null;
  finding_label: string | null;
  counterparty_favorability: string | null;
}

export interface NodeObservation {
  node_name: string;
  observed_state: string;
  observation_confidence: number;
  supporting_evidence_ids: string[];
  conflict_flag: boolean;
}

export interface RiskItem {
  title: string;
  dimension: string;
  risk_level: "low" | "medium" | "high";
  reason: string;
  evidence: string[];
  recommendation: string;
  node_name: string | null;
  clause_type: string | null;
  risk_level_label?: string;
}

export interface IssueReport {
  issue_id: string;
  title: string;
  risk_level: string;
  problem_analysis: string;
  original_clause: string;
  legal_basis: string;
  best_practice: string;
  suggested_revision: string;
  revision_reason: string;
}

export interface PolishedReport {
  narrative_report: string;
  executive_summary: string;
  dimension_insights: Record<string, string>;
  signing_advice: string;
  action_plan: string[];
  cross_dimension_notes: string[];
  issue_reports: IssueReport[];
  legal_view: string;
  business_view: string;
  executive_view: string;
}

export interface ReviewReport {
  contract_id: string;
  overall_risk: "low" | "medium" | "high";
  overall_risk_label: string;
  requires_manual_review: boolean;
  signing_recommendation: string;
  category_scores: Record<string, number>;
  dimension_scores: Record<string, number>;
  dimension_labels: Record<string, string>;
  dimension_risk_labels: Record<string, string>;
  dimension_summaries: Record<string, string>;
  top_risks: RiskItem[];
  summary_reasons: string[];
  manual_review_items: string[];
}

export interface EvidenceSummary {
  total_nodes: number;
  triggered: number;
  states: Record<string, string>;
}

export interface FreeReviewSegment {
  clause_type: string;
  risk_title: string;
  risk_description: string;
  evidence_text: string;
  confidence: number;
  severity: string;
  counterparty_impact: string | null;
  recommendation: string | null;
  suggested_bn_nodes: string[] | null;
  legal_basis: string | null;
}

export interface ConsistencyAnnotation {
  annotation_type: string;
  severity: string;
  message: string;
  bn_node: string | null;
  llm_clause_type: string | null;
  detail: Record<string, unknown> | null;
}

export interface ConsistencyData {
  annotations: ConsistencyAnnotation[];
  counterfactuals: CounterfactualResult[];
  counterfactuals_count?: number;
  bn_summary: string;
}

export interface CounterfactualResult {
  node_name: string;
  node_label: string;
  current_state: string;
  proposed_state: string;
  base_high_risk: number;
  counterfactual_high_risk: number;
  delta_high_risk: number;
  description: string;
}

export interface ReviewResponse {
  generation_mode: string;
  contract_id: string;
  review_party?: string;
  findings_count?: number;
  node_observations?: NodeObservation[];
  evidence_summary?: EvidenceSummary;
  report: ReviewReport;
  polished: PolishedReport | null;
  narrative_report?: string;
  executive_summary?: string;
  signing_advice?: string;
  action_plan?: string[];
  cross_dimension_notes?: string[];
  free_review?: {
    segments_count: number;
    missing_clauses: string[];
    strengths: string[];
    overall_assessment: string;
    risk_segments: FreeReviewSegment[];
  };
  consistency?: ConsistencyData;
  /** v2.15: Deterministic multi-format reports */
  revision_checklist?: string;
  bn_appendix?: string;
  /** v2.16: Auto golden case scoring */
  golden_score?: {
    score_kind: string;
    score_label: string;
    regression_note: string;
    case_id: string;
    case_label: string;
    score: number;
    must_find_total: number;
    must_find_passed: number;
    must_not_total: number;
    must_not_passed: number;
    should_total: number;
    should_passed: number;
    must_find_missed: string[];
    must_not_violated: string[];
    advantages_found: string[];
  };
  runtime_metadata?: {
    generated_at: string;
    backend_started_at: string;
    generation_mode: string;
    golden_scoring_enabled: boolean;
  };
  debug?: {
    routing?: {
      primary_type: string;
      confidence: number;
      selected_nodes: string[];
    };
  };
}

export type RequestState = "idle" | "loading" | "success" | "error";

export interface ReviewState {
  status: RequestState;
  data: ReviewResponse | null;
  error: string | null;
}

export interface ReportHistoryItem {
  id: number;
  contract_id: number;
  report_version: number;
  review_party: string;
  overall_risk_level: string | null;
  overall_p_high: number | null;
  bn_counterfactual_count: number;
  created_at: string;
  contract_name: string;
  contract_type: string;
}

export interface ReportHistoryResponse {
  reports: ReportHistoryItem[];
}

export interface ReportDetailResponse {
  error?: string;
  id: number;
  contract_id: number;
  report_version: number;
  review_party: string;
  overall_risk_level: string | null;
  overall_p_high: number | null;
  summary_text: string | null;
  report_content_md: string | null;
  bn_counterfactual_count: number;
  created_at: string;
}

export interface ReportDiffSummary {
  risk_level: string;
  counterfactuals: number;
  created_at: string;
}

export interface ReportRiskChange {
  name: string;
  from: string;
  to: string;
}

export interface ReportDiffResponse {
  error?: string;
  report_1?: ReportDiffSummary;
  report_2?: ReportDiffSummary;
  risk_changes?: ReportRiskChange[];
  risks_added?: string[];
  risks_removed?: string[];
}

// ── BN Sandbox types ──

export interface BnNode {
  node_name: string;
  label: string;
  layer: string;
  states: string[];
  affects_dimensions: string[];
  affects_dimension_labels: string[];
}

export interface BnSimulation {
  evidence: Record<string, string>;
  posteriors: Record<string, Record<string, number>>;
  dimension_labels: Record<string, string>;
}
