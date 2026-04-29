import type { IssueReport as IssueReportType } from "../types";

const LEVEL_LABELS: Record<string, string> = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

interface Props {
  issues: IssueReportType[];
}

export function IssueReportList({ issues }: Props) {
  if (!issues.length) return null;

  return (
    <div className="space-y-5">
      <h3 className="font-serif text-[#8B6F5C] text-lg">法务问题报告</h3>
      {issues.map((issue, i) => (
        <div
          key={issue.issue_id}
          className="bg-white border border-[#E8E2DB] rounded-lg overflow-hidden
                     animate-slide-up hover:shadow-md transition-all duration-300"
          style={{ animationDelay: `${i * 100}ms` }}
        >
          <div className="flex items-center justify-between px-5 py-3 border-b border-[#F5F0EB]">
            <h4 className="font-serif text-[#2C2416]">
              <span className="text-[#9B8E83] text-xs font-sans mr-2">
                {issue.issue_id}
              </span>
              {issue.title}
            </h4>
            <span className={`text-[11px] font-semibold px-2.5 py-1 rounded-full
              ${issue.risk_level === "high"
                ? "bg-[var(--color-risk-high)]/10 text-[var(--color-risk-high)]"
                : issue.risk_level === "medium"
                  ? "bg-[var(--color-risk-medium)]/15 text-[#8B6914]"
                  : "bg-[var(--color-risk-low)]/10 text-[var(--color-risk-low)]"
              }`}>
              {LEVEL_LABELS[issue.risk_level] || issue.risk_level}
            </span>
          </div>

          <div className="p-5 space-y-3">
            {issue.problem_analysis && (
              <div>
                <span className="text-[10px] uppercase tracking-wider text-[#9B8E83] font-medium">
                  问题分析
                </span>
                <p className="text-sm text-[#6B5E53] mt-1 leading-relaxed">
                  {issue.problem_analysis}
                </p>
              </div>
            )}

            {issue.original_clause && (
              <div className="bg-[#F5F0EB] rounded-md px-3 py-2 font-mono text-xs text-[#6B5E53] border-l-2 border-[#D4A574]">
                {issue.original_clause}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              {issue.legal_basis && (
                <div>
                  <span className="text-[10px] uppercase tracking-wider text-[#9B8E83]">
                    法律依据
                  </span>
                  <p className="text-[#6B5E53] mt-0.5">{issue.legal_basis}</p>
                </div>
              )}
              {issue.best_practice && (
                <div>
                  <span className="text-[10px] uppercase tracking-wider text-[#9B8E83]">
                    最佳实践
                  </span>
                  <p className="text-[#6B5E53] mt-0.5">{issue.best_practice}</p>
                </div>
              )}
            </div>

            {issue.suggested_revision && (
              <div>
                <span className="text-[10px] uppercase tracking-wider text-[#7B8B6F] font-semibold">
                  建议修改
                </span>
                <p className="text-sm text-[#2C2416] mt-0.5 bg-[var(--color-risk-low-bg)] rounded-md px-3 py-2 border border-[#7B8B6F]/20">
                  {issue.suggested_revision}
                </p>
                {issue.revision_reason && (
                  <p className="text-[11px] text-[#9B8E83] mt-1 italic">
                    {issue.revision_reason}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
