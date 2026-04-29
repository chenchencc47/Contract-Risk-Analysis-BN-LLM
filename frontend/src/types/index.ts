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
  findings_count?: number;
  node_observations?: NodeObservation[];
  evidence_summary?: EvidenceSummary;
  report: ReviewReport;
  polished: PolishedReport | null;
  free_review?: {
    segments_count: number;
    missing_clauses: string[];
    strengths: string[];
    overall_assessment: string;
    risk_segments: FreeReviewSegment[];
  };
  consistency?: ConsistencyData;
}

export type RequestState = "idle" | "loading" | "success" | "error";

export interface ReviewState {
  status: RequestState;
  data: ReviewResponse | null;
  error: string | null;
}
