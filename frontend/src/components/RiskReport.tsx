import type { ReviewResponse } from "../types";
import { RiskGauge } from "./RiskGauge";
import { DimensionCard } from "./DimensionCard";
import { AttributionChain } from "./AttributionChain";
import { IssueReportList } from "./IssueReport";
import { ActionPlan } from "./ActionPlan";
import { ExportButtons } from "./ExportButtons";
import { useState, useMemo } from "react";
import { marked } from "marked";

const ISSUE_ID_INLINE_PATTERN = /[（(]\s*ISSUE-[A-Za-z0-9_-]+\s*[)）]/g;
const ISSUE_ID_PREFIX_PATTERN = /\bISSUE-[A-Za-z0-9_-]+\b\s*[：:]?\s*/g;
const ISSUE_ID_LABEL_PATTERN = /\b(?:风险ID|Issue ID|IssueID)\b\s*[：:]?\s*/gi;

function stripInternalIds(text: string): string {
  return text
    .replace(ISSUE_ID_INLINE_PATTERN, "")
    .replace(ISSUE_ID_PREFIX_PATTERN, "")
    .replace(ISSUE_ID_LABEL_PATTERN, "");
}

function stripInternalIdsFromDocument(doc: Document): void {
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  let currentNode = walker.nextNode();

  while (currentNode) {
    textNodes.push(currentNode as Text);
    currentNode = walker.nextNode();
  }

  textNodes.forEach((node) => {
    const original = node.textContent ?? "";
    const cleaned = stripInternalIds(original);
    if (cleaned !== original) {
      node.textContent = cleaned;
    }
  });
}

function removeEmptyLeadingColumns(doc: Document): void {
  Array.from(doc.querySelectorAll("table")).forEach((table) => {
    const rows = Array.from(table.querySelectorAll("tr"));
    const firstCells = rows
      .map((row) => row.children.item(0) as HTMLTableCellElement | null)
      .filter((cell): cell is HTMLTableCellElement => cell !== null);

    if (firstCells.length > 0 && firstCells.every((cell) => !(cell.textContent?.trim()))) {
      firstCells.forEach((cell) => cell.remove());
    }
  });
}

export function enhanceReportHtml(markdown: string): string {
  const rawHtml = marked.parse(markdown) as string;
  if (typeof window === "undefined") return rawHtml;

  const parser = new DOMParser();
  const doc = parser.parseFromString(rawHtml, "text/html");
  stripInternalIdsFromDocument(doc);
  removeEmptyLeadingColumns(doc);

  Array.from(doc.querySelectorAll("h2")).forEach((heading, index) => {
    heading.classList.add(index === 0 ? "report-title" : "report-h1");
  });

  Array.from(doc.querySelectorAll("h3")).forEach((heading) => {
    const text = heading.textContent?.trim() ?? "";
    if (/^风险\d+/.test(text)) {
      heading.classList.add("report-risk-title");
      heading.setAttribute(
        "data-risk-level",
        text.includes("P1") ? "critical" : text.includes("P2") ? "high" : text.includes("P3") ? "medium" : "default",
      );
    } else {
      heading.classList.add("report-h2");
    }
  });

  Array.from(doc.querySelectorAll("h4")).forEach((heading) => {
    heading.classList.add("report-h3");
  });

  Array.from(doc.querySelectorAll("p")).forEach((paragraph) => {
    const text = paragraph.textContent?.trim() ?? "";
    if (text.includes("核心建议是：")) {
      paragraph.classList.add("report-key-conclusion");
    }
  });

  Array.from(doc.querySelectorAll("strong")).forEach((strong) => {
    const text = strong.textContent?.trim() ?? "";
    if (/\d/.test(text) || text.includes("%") || text.includes("倍") || text.includes("万元")) {
      strong.classList.add("report-metric");
    }
    if (text.includes("底线，不可退让")) {
      strong.classList.add("report-bottom-line-tag");
    }
  });

  Array.from(doc.querySelectorAll("li")).forEach((item) => {
    const label = item.querySelector("strong")?.textContent?.trim() ?? "";
    if (label.startsWith("条款原文")) {
      item.classList.add("report-clause-original");
    }
    if (label.startsWith("修改方案")) {
      item.classList.add("report-callout-block", "report-callout-modify");
    }
    if (label.startsWith("法律依据")) {
      item.classList.add("report-callout-block", "report-callout-legal");
    }
    if (label.startsWith("筹码分析")) {
      item.classList.add("report-callout-block", "report-callout-chip");
    }
    if (label.startsWith("对手预判")) {
      item.classList.add("report-callout-block", "report-callout-opponent");
    }
  });

  Array.from(doc.querySelectorAll("table")).forEach((table) => {
    const wrapper = doc.createElement("div");
    wrapper.className = "report-table-scroll";
    table.parentNode?.insertBefore(wrapper, table);
    wrapper.appendChild(table);

    Array.from(table.querySelectorAll("th, td")).forEach((cell) => {
      const tableCell = cell as HTMLTableCellElement;
      const text = tableCell.textContent?.trim() ?? "";
      if (tableCell.cellIndex === 0) {
        tableCell.classList.add("report-cell-first");
      } else if (/\d/.test(text) || /^P\d/.test(text) || /^[🔴🟠🟡✅]/.test(text)) {
        tableCell.classList.add("report-cell-numeric");
      } else {
        tableCell.classList.add("report-cell-text");
      }
    });
  });

  Array.from(doc.querySelectorAll("h3.report-risk-title")).forEach((heading) => {
    const wrapper = doc.createElement("section");
    const level = heading.getAttribute("data-risk-level") ?? "default";
    wrapper.className = `report-risk-section report-risk-${level}`;
    heading.parentNode?.insertBefore(wrapper, heading);

    let current: ChildNode | null = heading;
    while (current) {
      const next: ChildNode | null = current.nextSibling;
      wrapper.appendChild(current);
      if (next && next.nodeType === Node.ELEMENT_NODE) {
        const nextElement = next as Element;
        if (nextElement.tagName === "H2" || nextElement.tagName === "H3") {
          break;
        }
      }
      current = next;
    }
  });

  return doc.body.innerHTML;
}

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
  const signingAdvice = polished?.signing_advice || data.signing_advice || "";
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
                  {signingAdvice && (<><span className="text-[#C4B8AC] mx-1">|</span><span className="text-[#7B8B6F] font-medium">{signingAdvice.slice(0, 40)}{signingAdvice.length > 40 ? "…" : ""}</span></>)}
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
          <article className="report-document bg-white border border-[#E8E2DB] rounded-xl p-6 md:p-10 shadow-sm max-w-none
            prose prose-stone
            prose-headings:font-sans prose-headings:font-bold
            prose-p:text-[#1D2129] prose-p:leading-[1.6] prose-p:text-[14px]
            prose-li:text-[#1D2129] prose-li:text-[14px]
            prose-code:bg-[#F2F3F5] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
            prose-code:text-xs prose-code:font-mono prose-a:text-[#165DFF] prose-a:underline"
            dangerouslySetInnerHTML={{ __html: reportHtml }} />
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
