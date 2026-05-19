import { useEffect, useState } from "react";
import type { ReportDetailResponse } from "../../types";
import { enhanceReportHtml } from "../../utils/reportHtml";
import { ReportDocument } from "../report/ReportDocument";
import { Badge } from "../Badge";
import { riskVariant, partyVariant } from "../../utils/badgeVariants";

interface Props {
  reportId: number;
  onBack: () => void;
}

function partyLabel(reviewParty: string) {
  return reviewParty === "buyer" ? "甲方视角" : reviewParty === "seller" ? "乙方视角" : reviewParty;
}

function extractExecSummary(markdown: string): string {
  const start = markdown.indexOf("## 一、执行摘要");
  if (start === -1) return "";
  const end = markdown.indexOf("\n## ", start + 1);
  return end === -1 ? markdown.slice(start) : markdown.slice(start, end);
}

const RISK_OVERALL_EXPLICIT = [
  { pattern: /(?:总体|整体|综合|合同整体)?风险等级[：:]\s*(致命)/, level: "致命" },
  { pattern: /(?:总体|整体|综合|合同整体)?风险等级[：:]\s*(高)/, level: "高" },
  { pattern: /(?:总体|整体|综合|合同整体)?风险等级[：:]\s*(中)/, level: "中" },
  { pattern: /(?:总体|整体|综合|合同整体)?风险等级[：:]\s*(低)/, level: "低" },
];

const RISK_OVERALL_DESCRIPTIVE = [
  { pattern: /(?:本合同|该合同|合同)\s*整体风险极高|整体风险极高/, level: "高" },
  { pattern: /(?:本合同|该合同|合同)\s*整体风险较高|整体风险较高|整体风险偏高/, level: "高" },
  { pattern: /(?:本合同|该合同|合同)\s*整体风险[为是]?高|整体风险高/, level: "高" },
  { pattern: /(?:本合同|该合同|合同)\s*整体风险中等|整体风险中等|整体风险居中/, level: "中" },
  { pattern: /(?:本合同|该合同|合同)\s*整体风险较低|整体风险较低|整体风险偏低/, level: "低" },
  { pattern: /(?:本合同|该合同|合同)\s*整体风险[为是]?低|整体风险低/, level: "低" },
];

const RISK_OVERALL_IMPLICIT = [
  { pattern: /属于\s*[极较]?高\s*风险(?:合同|等级|水平)?/, level: "高" },
  { pattern: /风险\s*[极较]?高[,，。]/, level: "高" },
  { pattern: /属于\s*中等\s*风险(?:合同|等级|水平)?/, level: "中" },
  { pattern: /风险\s*中等[,，。]/, level: "中" },
  { pattern: /属于\s*[较偏]?低\s*风险(?:合同|等级|水平)?/, level: "低" },
  { pattern: /风险\s*[较偏]?低[,，。]/, level: "低" },
];

function extractRiskLevelFromMarkdown(markdown: string | null): string | null {
  if (!markdown) return null;
  const summary = extractExecSummary(markdown);
  const scope = summary || markdown.slice(0, 2000);

  for (const { pattern, level } of RISK_OVERALL_EXPLICIT) {
    if (pattern.test(scope)) return level;
  }
  for (const { pattern, level } of RISK_OVERALL_DESCRIPTIVE) {
    if (pattern.test(scope)) return level;
  }
  for (const { pattern, level } of RISK_OVERALL_IMPLICIT) {
    if (pattern.test(scope)) return level;
  }

  return null;
}

export function HistoryDetailPage({ reportId, onBack }: Props) {
  const [report, setReport] = useState<ReportDetailResponse | null>(null);
  const [rawMarkdown, setRawMarkdown] = useState<string>("");
  const [html, setHtml] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    fetch(`/api/reports/${reportId}`)
      .then((r) => r.json())
      .then((data: ReportDetailResponse) => {
        if (cancelled) return;
        setReport(data);
        setRawMarkdown(data.report_content_md || "");
        setHtml(data.report_content_md ? enhanceReportHtml(data.report_content_md) : "");
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reportId]);

  const resolvedRiskLevel = report?.overall_risk_level || extractRiskLevelFromMarkdown(rawMarkdown);

  return (
    <div className="max-w-6xl mx-auto px-6 pb-20 animate-fade-in">
      <div className="pt-6 mb-4">
        <button
          onClick={onBack}
          className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium
                     transition-colors duration-200 flex items-center gap-1.5"
        >
          <span className="text-lg leading-none">←</span> 返回历史列表
        </button>
      </div>

      {loading ? (
        <div className="text-center text-[#9B8E83] py-12">加载中...</div>
      ) : !report || report.error ? (
        <div className="rounded-xl border border-red-200 bg-white py-12 text-center text-red-600">
          {report?.error || "历史报告加载失败"}
        </div>
      ) : (
        <div className="space-y-6">
          <section className="relative overflow-hidden rounded-2xl border border-[#E8E2DB] bg-white p-6 shadow-sm bg-texture">
            <div className="absolute right-0 top-0 h-40 w-40 -mr-8 -mt-8 rounded-bl-full bg-[#F5F0EB]/60 pointer-events-none" />
            <div className="relative space-y-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs font-semibold tracking-[0.18em] text-[#9B8E83]">ARCHIVED REPORT</p>
                  <h2 className="mt-2 font-serif text-3xl text-[#2C2416]">历史审查归档报告</h2>
                  <p className="mt-3 max-w-2xl text-sm leading-6 text-[#6B5E53]">
                    这是已保存版本的正式归档视图。下方完整保留当时生成的报告正文，不做删减或改写。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 lg:justify-end">
                  <Badge>版本 v{report.report_version}</Badge>
                  <Badge variant={partyVariant(report.review_party)}>
                    {partyLabel(report.review_party)}
                  </Badge>
                  <Badge variant={resolvedRiskLevel ? riskVariant(resolvedRiskLevel) : "neutral"}>
                    风险等级：{resolvedRiskLevel || "见报告正文"}
                  </Badge>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-[#E8E2DB] bg-[#FCFAF8] p-4 shadow-sm">
                  <div className="text-[11px] font-semibold tracking-wide text-[#9B8E83]">归档时间</div>
                  <div className="mt-2 text-sm font-medium text-[#2C2416]">
                    {new Date(report.created_at).toLocaleString("zh-CN")}
                  </div>
                </div>
                <div className="rounded-xl border border-[#E8E2DB] bg-[#FCFAF8] p-4 shadow-sm">
                  <div className="text-[11px] font-semibold tracking-wide text-[#9B8E83]">反事实分析</div>
                  <div className="mt-2 text-sm font-medium text-[#2C2416]">
                    {report.bn_counterfactual_count > 0 ? `${report.bn_counterfactual_count} 项` : "未记录"}
                  </div>
                </div>
                <div className="rounded-xl border border-[#E8E2DB] bg-[#FCFAF8] p-4 shadow-sm">
                  <div className="text-[11px] font-semibold tracking-wide text-[#9B8E83]">合同标识</div>
                  <div className="mt-2 text-sm font-medium text-[#2C2416]">#{report.contract_id}</div>
                </div>
              </div>


            </div>
          </section>

          <ReportDocument html={html} />
        </div>
      )}
    </div>
  );
}
