import type { ReviewResponse } from "../types";
import { RiskGauge } from "./RiskGauge";
import { DimensionCard } from "./DimensionCard";
import { AttributionChain } from "./AttributionChain";
import { IssueReportList } from "./IssueReport";
import { ActionPlan } from "./ActionPlan";
import { useState, useMemo } from "react";
import { marked } from "marked";

interface Props {
  data: ReviewResponse;
}

type ViewMode = "dashboard" | "document";

export function RiskReport({ data }: Props) {
  const { report, polished } = data;
  const [viewMode, setViewMode] = useState<ViewMode>(
    polished?.narrative_report ? "document" : "dashboard"
  );
  const overallScore = report.dimension_scores
    ? Object.values(report.dimension_scores).reduce((a, b) => a + b, 0) /
      Math.max(Object.values(report.dimension_scores).length, 1)
    : 0.5;

  const reportHtml = useMemo(() => {
    if (!polished?.narrative_report) return "";
    return marked.parse(polished.narrative_report) as string;
  }, [polished?.narrative_report]);

  const hasReport = !!polished?.narrative_report;

  return (
    <div className="max-w-6xl mx-auto px-6 pb-20 animate-fade-in">
      {/* ── View Toggle & Overview ── */}
      <div className="relative bg-white border border-[#E8E2DB] rounded-xl p-6 mb-6
                      shadow-sm bg-texture">
        <div className="absolute top-0 right-0 w-48 h-48 rounded-bl-full
                        bg-[#F5F0EB]/50 -mr-8 -mt-8 pointer-events-none" />

        <div className="relative flex flex-col sm:flex-row items-start gap-6">
          <RiskGauge
            level={report.overall_risk}
            score={overallScore}
            label={report.overall_risk_label}
          />

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <h2 className="font-serif text-2xl text-[#2C2416]">
                风险评估报告
              </h2>
              {report.requires_manual_review && (
                <span className="text-[10px] font-semibold bg-[#FDF0ED] text-[var(--color-risk-high)]
                                 px-2 py-0.5 rounded-full uppercase tracking-wider">
                  需人工复核
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs mb-3">
              <span className="text-[#9B8E83]">签署建议：</span>
              <span className={`font-semibold px-2 py-0.5 rounded-full
                ${report.signing_recommendation?.includes("不建议") || report.signing_recommendation?.includes("暂不")
                  ? "bg-[var(--color-risk-high)]/10 text-[var(--color-risk-high)]"
                  : report.signing_recommendation?.includes("有条件")
                    ? "bg-[var(--color-risk-medium)]/15 text-[#8B6914]"
                    : "bg-[var(--color-risk-low)]/10 text-[var(--color-risk-low)]"
                }`}>
                {report.signing_recommendation || "有条件签署"}
              </span>
              <span className="text-[#C4B8AC] mx-1">|</span>
              <span className="text-[#9B8E83]">
                {data.generation_mode === "v2_combined"
                  ? `${data.free_review?.segments_count ?? "?"} 项风险 · ${data.consistency?.annotations?.length ?? "?"} 条校验 · BN 校验器`
                  : `${data.findings_count} 项发现 · ${data.evidence_summary?.total_nodes ?? "?"} 节点 · BN v1`
                }
              </span>
              {hasReport && (
                <>
                  <span className="text-[#C4B8AC] mx-1">|</span>
                  <span className="text-[#7B8B6F] font-medium">AI 报告已生成</span>
                </>
              )}
            </div>

            {/* View mode toggle */}
            {hasReport && (
              <div className="flex gap-1 bg-[#F5F0EB] rounded-lg p-0.5 w-fit">
                <button
                  onClick={() => setViewMode("dashboard")}
                  className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200
                    ${viewMode === "dashboard"
                      ? "bg-white text-[#8B6F5C] shadow-sm"
                      : "text-[#9B8E83] hover:text-[#6B5E53]"
                    }`}
                >
                  📊 仪表盘
                </button>
                <button
                  onClick={() => setViewMode("document")}
                  className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all duration-200
                    ${viewMode === "document"
                      ? "bg-white text-[#8B6F5C] shadow-sm"
                      : "text-[#9B8E83] hover:text-[#6B5E53]"
                    }`}
                >
                  📄 审查报告
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Document View ── */}
      {viewMode === "document" && hasReport && (
        <div className="animate-fade-in">
          <div className="flex justify-end mb-4 gap-2">
            <button
              onClick={() => {
                const blob = new Blob([polished!.narrative_report], { type: "text/markdown" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `contract-review-${data.contract_id}.md`;
                a.click();
                URL.revokeObjectURL(url);
              }}
              className="text-xs text-[#8B6F5C] hover:text-[#6B5243] font-medium
                         px-3 py-1.5 border border-[#E8E2DB] rounded-md
                         hover:border-[#8B6F5C] transition-all duration-200"
            >
              ⬇ 下载 Markdown
            </button>
            <button
              onClick={() => window.print()}
              className="text-xs text-[#8B6F5C] hover:text-[#6B5243] font-medium
                         px-3 py-1.5 border border-[#E8E2DB] rounded-md
                         hover:border-[#8B6F5C] transition-all duration-200"
            >
              🖨 打印 PDF
            </button>
          </div>

          <article
            className="bg-white border border-[#E8E2DB] rounded-xl p-8 md:p-12
                       shadow-sm max-w-none
                       prose prose-stone prose-headings:font-serif
                       prose-headings:text-[#2C2416] prose-headings:font-semibold
                       prose-h2:text-xl prose-h2:mt-8 prose-h2:mb-4
                       prose-h2:pb-2 prose-h2:border-b prose-h2:border-[#E8E2DB]
                       prose-p:text-[#3D3226] prose-p:leading-relaxed prose-p:text-[15px]
                       prose-strong:text-[#2C2416]
                       prose-table:text-sm prose-table:border-collapse
                       prose-th:bg-[#F5F0EB] prose-th:text-[#6B5E53] prose-th:font-medium
                       prose-th:px-3 prose-th:py-2 prose-th:text-xs prose-th:text-left
                       prose-td:px-3 prose-td:py-2 prose-td:border-b prose-td:border-[#F5F0EB]
                       prose-td:text-[#3D3226]
                       prose-blockquote:border-l-[3px] prose-blockquote:border-[#8B6F5C]
                       prose-blockquote:bg-[#FAF8F5] prose-blockquote:py-2 prose-blockquote:px-4
                       prose-blockquote:text-[#6B5E53] prose-blockquote:italic
                       prose-li:text-[#3D3226] prose-li:leading-relaxed
                       prose-code:bg-[#F5F0EB] prose-code:px-1.5 prose-code:py-0.5
                       prose-code:rounded prose-code:text-xs prose-code:font-mono
                       prose-code:text-[#8B6F5C]
                       prose-hr:border-[#E8E2DB]
                       [&_table]:w-full [&_table]:border [&_table]:border-[#E8E2DB]
                       [&_table]:rounded-lg [&_table]:overflow-hidden
                       [&_tr:nth-child(even)]:bg-[#FAF8F5]
                       print:shadow-none print:border-none print:p-0
                       print:text-black print:prose-headings:text-black
                       print:prose-p:text-black"
            dangerouslySetInnerHTML={{ __html: reportHtml }}
          />
        </div>
      )}

      {/* ── Dashboard View ── */}
      {viewMode === "dashboard" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: 2/3 — main content */}
          <div className="lg:col-span-2 space-y-8">
            {/* Attribution chain */}
            <AttributionChain risks={report.top_risks || []} />

            {/* Issue reports */}
            {polished?.issue_reports && polished.issue_reports.length > 0 && (
              <IssueReportList issues={polished.issue_reports} />
            )}

            {/* Action plan */}
            <ActionPlan
              actions={polished?.action_plan || []}
              crossDimensionNotes={polished?.cross_dimension_notes || []}
            />

            {/* Manual review */}
            {report.manual_review_items && report.manual_review_items.length > 0 && (
              <div className="bg-[#FDF0ED] border border-[var(--color-risk-high)]/20 rounded-lg p-4">
                <h3 className="font-serif text-[var(--color-risk-high)] text-lg mb-2">
                  人工复核项
                </h3>
                <ul className="space-y-1.5">
                  {report.manual_review_items.map((item, i) => (
                    <li key={i} className="text-sm text-[#6B5E53] flex gap-2">
                      <span className="text-[var(--color-risk-high)] shrink-0">!</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Right: 1/3 — dimension sidebar */}
          <div className="space-y-4">
            <div className="sticky top-20">
              <h3 className="font-serif text-[#8B6F5C] text-sm mb-3 tracking-wide">
                风险维度
              </h3>
              <div className="space-y-3">
                {report.dimension_scores &&
                  Object.entries(report.dimension_scores).map(([key, score]) => (
                    <DimensionCard
                      key={key}
                      dimKey={key}
                      label={report.dimension_labels?.[key] || key}
                      score={score}
                      riskLevel={report.dimension_risk_labels?.[key] || "medium"}
                      summary={report.dimension_summaries?.[key]}
                      insight={polished?.dimension_insights?.[key]}
                    />
                  ))}
              </div>

              <div className="mt-6 pt-4 border-t border-[#E8E2DB]">
                <h4 className="text-[10px] text-[#9B8E83] uppercase tracking-wider mb-2">
                  {data.generation_mode === "v2_combined" ? "校验摘要" : "证据快照"}
                </h4>
                {data.generation_mode === "v2_combined" && data.consistency ? (
                  <div className="space-y-2">
                    {data.consistency.annotations.slice(0, 5).map((a, i) => (
                      <div key={i} className={`text-[10px] px-2 py-1 rounded
                        ${a.severity === "error" ? "bg-[var(--color-risk-high)]/8 text-[var(--color-risk-high)]"
                          : a.severity === "warning" ? "bg-[var(--color-risk-medium)]/10 text-[#8B6914]"
                          : "bg-[#F5F0EB] text-[#9B8E83]"
                        }`}>
                        {a.annotation_type}: {a.message.slice(0, 60)}...
                      </div>
                    ))}
                    {data.consistency.counterfactuals.length > 0 && (
                      <div className="text-[10px] text-[var(--color-risk-low)]">
                        {data.consistency.counterfactuals.length} 项反事实模拟
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {(data.evidence_summary?.states
                      ? Object.entries(data.evidence_summary.states)
                      : []
                    ).map(([node, state]) => (
                      <span
                        key={node}
                        className={`text-[10px] px-2 py-0.5 rounded-full font-mono
                          ${state === "missing" || state === "unfavorable" || state === "counterparty_favorable"
                            ? "bg-[var(--color-risk-high)]/8 text-[var(--color-risk-high)]"
                            : state === "unknown"
                              ? "bg-[#F5F0EB] text-[#9B8E83]"
                              : "bg-[var(--color-risk-low)]/8 text-[var(--color-risk-low)]"
                          }`}
                      >
                        {node}:{state}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
