import type { ReviewResponse } from "../types";
import { useMemo, useState } from "react";
import { enhanceReportHtml } from "../utils/reportHtml";
import { RiskGauge } from "./RiskGauge";
import { DimensionCard } from "./DimensionCard";
import { AttributionChain } from "./AttributionChain";
import { IssueReportList } from "./IssueReport";
import { ActionPlan } from "./ActionPlan";
import { ExportButtons } from "./ExportButtons";
import { ReportDocument } from "./report/ReportDocument";

interface Props {
  data: ReviewResponse;
}

type ViewMode = "dashboard" | "document";
type DocFormat = "report" | "checklist" | "appendix";

function RoutingBadge({ data }: { data: ReviewResponse }) {
  const routing = data.debug?.routing;
  if (!routing?.primary_type) return null;
  const pct = Math.round(routing.confidence * 100);
  return (
    <div className="flex items-center gap-2 text-[11px] mb-3">
      <span className="text-[#9B8E83]">合同类型识别：</span>
      <span className="font-semibold text-[#2C2416]">{routing.primary_type}</span>
      <span className={`px-1.5 py-0.5 rounded-full font-mono text-[10px] ${pct >= 60 ? "bg-green-50 text-green-700" : "bg-yellow-50 text-yellow-700"}`}>
        {pct}%
      </span>
      <span className="text-[#C4B8AC]">· 优先审查 {routing.selected_nodes.length} 节点</span>
    </div>
  );
}

export function RiskReport({ data }: Props) {
  const { report, polished } = data;
  const isV2 = data.generation_mode === "v2_combined" || data.generation_mode === "combined";

  // v2 has flat fields, v1 has nested polished
  const narrativeReport = polished?.narrative_report || data.narrative_report || "";
  const actionPlan = polished?.action_plan || data.action_plan || [];
  const crossNotes = polished?.cross_dimension_notes || data.cross_dimension_notes || [];
  const issueReports = polished?.issue_reports || [];

  const [viewMode, setViewMode] = useState<ViewMode>(
    narrativeReport ? "document" : "dashboard"
  );
  const [docFormat, setDocFormat] = useState<DocFormat>("report");

  const hasChecklist = !!data.revision_checklist;
  const hasAppendix = !!data.bn_appendix;
  const hasMultiFormat = hasChecklist || hasAppendix;

  const overallScore = report?.dimension_scores
    ? Object.values(report.dimension_scores).reduce((a, b) => a + b, 0) /
      Math.max(Object.values(report.dimension_scores).length, 1)
    : 0.5;

  const currentDocMarkdown = docFormat === "checklist"
    ? (data.revision_checklist || "")
    : docFormat === "appendix"
    ? (data.bn_appendix || "")
    : narrativeReport;

  const reportHtml = useMemo(() => {
    if (!currentDocMarkdown) return "";
    return enhanceReportHtml(currentDocMarkdown);
  }, [currentDocMarkdown]);

  const hasReport = !!narrativeReport;
  const hasDashboard = !!report && !isV2;

  return (
    <div className="max-w-6xl mx-auto px-6 pb-20 animate-fade-in">
      {/* Overview card */}
      <div className="relative bg-white border border-[#E8E2DB] rounded-xl p-6 mb-6 shadow-sm bg-texture">
        <div className="absolute top-0 right-0 w-48 h-48 rounded-bl-full bg-[#F5F0EB]/50 -mr-8 -mt-8 pointer-events-none" />

        <div className="relative flex flex-col sm:flex-row items-start gap-6">
          {hasDashboard && (
            <RiskGauge level={report!.overall_risk} score={overallScore} label={report!.overall_risk_label} />
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <h2 className="font-serif text-2xl text-[#2C2416]">风险评估报告</h2>
              {data.review_party && (
                <span className="text-[10px] font-semibold bg-[#F5F0EB] text-[#8B6F5C] px-2 py-0.5 rounded-full uppercase tracking-wider">
                  {data.review_party === "buyer" ? "甲方视角" : "乙方视角"}
                </span>
              )}
              {hasDashboard && report!.requires_manual_review && (
                <span className="text-[10px] font-semibold bg-[#FDF0ED] text-red-600 px-2 py-0.5 rounded-full uppercase tracking-wider">
                  需人工复核
                </span>
              )}
            </div>

            <RoutingBadge data={data} />

            <div className="flex flex-wrap items-center gap-2 text-xs mb-3">
              {hasDashboard && (
                <>
                  <span className="text-[#9B8E83]">签署建议：</span>
                  <span className={`font-semibold px-2 py-0.5 rounded-full ${
                    report!.signing_recommendation?.includes("不建议") || report!.signing_recommendation?.includes("暂不")
                      ? "bg-red-50 text-red-700" : report!.signing_recommendation?.includes("有条件")
                      ? "bg-yellow-50 text-yellow-700" : "bg-green-50 text-green-700"}`}>
                    {report!.signing_recommendation || "有条件签署"}
                  </span>
                  <span className="text-[#C4B8AC] mx-1">|</span>
                  <span className="text-[#9B8E83]">
                    {data.findings_count} 项发现 · {data.evidence_summary?.total_nodes ?? "?"} 节点 · BN v1
                  </span>
                </>
              )}
              {isV2 && (
                <>
                  <span className="text-[#9B8E83]">
                    {data.free_review?.segments_count ?? "?"} 项风险 · {data.consistency?.counterfactuals_count ?? "?"} 项反事实 · BN v2
                  </span>
                </>
              )}
              {data.golden_score && (
                <>
                  <span className="text-[#C4B8AC] mx-1">|</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    data.golden_score.score >= 80 ? "bg-green-50 text-green-700" :
                    data.golden_score.score >= 60 ? "bg-yellow-50 text-yellow-700" :
                    "bg-red-50 text-red-700"
                  }`} title={`${data.golden_score.score_label}: ${data.golden_score.case_label}\nmust_find: ${data.golden_score.must_find_passed}/${data.golden_score.must_find_total}\nmust_not: ${data.golden_score.must_not_passed}/${data.golden_score.must_not_total}\n${data.golden_score.regression_note}`}>
                    🏅 回归 {data.golden_score.score.toFixed(0)}分
                  </span>
                </>
              )}
              {data.runtime_metadata && (
                <>
                  <span className="text-[#C4B8AC] mx-1">|</span>
                  <span
                    className="text-[#9B8E83]"
                    title={`后端启动: ${new Date(data.runtime_metadata.backend_started_at).toLocaleString()}\n生成模式: ${data.runtime_metadata.generation_mode}\n回归评分: ${data.runtime_metadata.golden_scoring_enabled ? "已启用" : "未启用"}`}
                  >
                    生成于 {new Date(data.runtime_metadata.generated_at).toLocaleString()}
                  </span>
                </>
              )}
              {hasReport && (<><span className="text-[#C4B8AC] mx-1">|</span><span className="text-[#7B8B6F] font-medium">AI 报告已生成</span></>)}
            </div>

            {hasReport && hasDashboard && (
              <div className="flex gap-1 bg-[#F5F0EB] rounded-lg p-0.5 w-fit">
                <button onClick={() => setViewMode("dashboard")} className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all ${viewMode === "dashboard" ? "bg-white text-[#8B6F5C] shadow-sm" : "text-[#9B8E83] hover:text-[#6B5E53]"}`}>
                  📊 仪表盘
                </button>
                <button onClick={() => setViewMode("document")} className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all ${viewMode === "document" ? "bg-white text-[#8B6F5C] shadow-sm" : "text-[#9B8E83] hover:text-[#6B5E53]"}`}>
                  📄 审查报告
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Document View */}
      {viewMode === "document" && hasReport && (
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
            {hasMultiFormat && (
              <div className="flex gap-1 bg-[#F5F0EB] rounded-lg p-0.5">
                <button onClick={() => setDocFormat("report")} className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all ${docFormat === "report" ? "bg-white text-[#8B6F5C] shadow-sm" : "text-[#9B8E83] hover:text-[#6B5E53]"}`}>
                  📄 审查报告
                </button>
                {hasChecklist && (
                  <button onClick={() => setDocFormat("checklist")} className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all ${docFormat === "checklist" ? "bg-white text-[#8B6F5C] shadow-sm" : "text-[#9B8E83] hover:text-[#6B5E53]"}`}>
                    📋 修订清单
                  </button>
                )}
                {hasAppendix && (
                  <button onClick={() => setDocFormat("appendix")} className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all ${docFormat === "appendix" ? "bg-white text-[#8B6F5C] shadow-sm" : "text-[#9B8E83] hover:text-[#6B5E53]"}`}>
                    🔬 BN附录
                  </button>
                )}
              </div>
            )}
            <div className={`${hasMultiFormat ? "" : "ml-auto"} flex gap-2`}>
              <ExportButtons contractId={data.contract_id} markdown={currentDocMarkdown} />
            </div>
          </div>
          <ReportDocument html={reportHtml} />
        </div>
      )}

      {/* Dashboard View */}
      {viewMode === "dashboard" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-8">
            {hasDashboard && <AttributionChain risks={report!.top_risks || []} />}
            {issueReports.length > 0 && <IssueReportList issues={issueReports} />}
            <ActionPlan actions={actionPlan} crossDimensionNotes={crossNotes} />

            {isV2 && data.free_review && (
              <div className="space-y-4">
                {data.free_review.missing_clauses.length > 0 && (
                  <div className="bg-white border border-[#E8E2DB] rounded-lg p-4">
                    <h3 className="font-serif text-[#2C2416] text-sm mb-2">缺失条款 ({data.free_review.missing_clauses.length})</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {data.free_review.missing_clauses.map((c, i) => (
                        <span key={i} className="text-[10px] bg-red-50 text-red-700 px-2 py-0.5 rounded-full">{c}</span>
                      ))}
                    </div>
                  </div>
                )}
                {data.free_review.strengths.length > 0 && (
                  <div className="bg-white border border-[#E8E2DB] rounded-lg p-4">
                    <h3 className="font-serif text-[#2C2416] text-sm mb-2">有利条款 ({data.free_review.strengths.length})</h3>
                    <div className="flex flex-wrap gap-1.5">
                      {data.free_review.strengths.map((s, i) => (
                        <span key={i} className="text-[10px] bg-green-50 text-green-700 px-2 py-0.5 rounded-full">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="space-y-4">
            <div className="sticky top-20">
              {hasDashboard && report!.dimension_scores && (
                <>
                  <h3 className="font-serif text-[#8B6F5C] text-sm mb-3 tracking-wide">风险维度</h3>
                  <div className="space-y-3">
                    {Object.entries(report!.dimension_scores).map(([key, score]) => (
                      <DimensionCard key={key} dimKey={key} label={report!.dimension_labels?.[key] || key}
                        score={score} riskLevel={report!.dimension_risk_labels?.[key] || "medium"}
                        summary={report!.dimension_summaries?.[key]} insight={polished?.dimension_insights?.[key]} />
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
