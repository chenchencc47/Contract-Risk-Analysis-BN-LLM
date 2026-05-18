import { useEffect, useState, useMemo } from "react";
import type { ReportDiffResponse } from "../../types";
import { Badge } from "../Badge";
import { riskVariant } from "../../utils/badgeVariants";

interface Props {
  id1: number;
  id2: number;
  onBack: () => void;
}

type Verdict = "improved" | "degraded" | "unchanged" | "unknown";

export function HistoryDiffPage({ id1, id2, onBack }: Props) {
  const [diff, setDiff] = useState<ReportDiffResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    fetch(`/api/reports/diff?id1=${id1}&id2=${id2}`)
      .then((r) => r.json())
      .then((data: ReportDiffResponse) => {
        if (cancelled) return;
        setDiff(data);
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
  }, [id1, id2]);

  const verdict = useMemo((): Verdict => {
    if (!diff || diff.error) return "unknown";
    const changes = diff.risk_changes ?? [];
    const added = diff.risks_added ?? [];
    const removed = diff.risks_removed ?? [];

    const improved = changes.filter(
      (c) =>
        (c.from === "高" || c.from === "致命") &&
        (c.to === "中" || c.to === "低")
    ).length;
    const worsened = changes.filter(
      (c) =>
        (c.from === "中" || c.from === "低") &&
        (c.to === "高" || c.to === "致命")
    ).length;

    if (removed.length > added.length && improved >= worsened) return "improved";
    if (added.length > removed.length && worsened > improved) return "degraded";
    if (changes.length === 0 && added.length === 0 && removed.length === 0) return "unchanged";
    return "unknown";
  }, [diff]);

  const verdictConfig: Record<Verdict, { label: string; className: string; desc: string }> = {
    improved: {
      label: "报告 2 更优",
      className: "bg-green-50 text-green-700 border-green-200",
      desc: "消除的风险多于新增，风险等级整体下降。报告 2 的审查结果更正面。",
    },
    degraded: {
      label: "报告 1 更优",
      className: "bg-red-50 text-red-700 border-red-200",
      desc: "新增的风险多于消除，或风险等级出现上升。报告 1 的审查结果更正面。",
    },
    unchanged: {
      label: "无明显差异",
      className: "bg-[#F5F0EB] text-[#8B6F5C] border-[#E8E2DB]",
      desc: "两份报告的风险等级和风险项未发生显著变化。",
    },
    unknown: {
      label: "无法自动判定",
      className: "bg-[#F5F0EB] text-[#9B8E83] border-[#E8E2DB]",
      desc: "两份报告的风险变化方向不一致，建议人工对比完整正文判断。",
    },
  };

  const v = verdictConfig[verdict];

  return (
    <div className="max-w-6xl mx-auto px-6 pb-20 animate-fade-in">
      <div className="relative bg-white border border-[#E8E2DB] rounded-xl p-6 mb-6 shadow-sm bg-texture overflow-hidden">
        <div className="absolute top-0 right-0 w-44 h-44 rounded-bl-full bg-[#F5F0EB]/60 -mr-8 -mt-8 pointer-events-none" />
        <div className="relative">
          <button
            onClick={onBack}
            className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium transition-colors duration-200 flex items-center gap-1.5"
          >
            <span className="text-lg leading-none">←</span> 返回历史列表
          </button>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <h2 className="font-serif text-2xl text-[#2C2416]">报告对比</h2>
            <span className="text-[10px] font-semibold bg-[#F5F0EB] text-[#8B6F5C] px-2 py-0.5 rounded-full tracking-wider">
              WORKBENCH
            </span>
          </div>
          <p className="text-sm text-[#9B8E83] mt-2">
            对比两份历史审查结果，快速判断版本优劣。仅基于结构化字段做方向性判断，完整报告正文请在归档页查看。
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-[#9B8E83] py-12">加载中...</div>
      ) : diff?.error ? (
        <div className="bg-white border border-red-200 rounded-xl text-center text-red-600 py-12">{String(diff.error)}</div>
      ) : (
        <div className="space-y-6">
          {/* Verdict card */}
          <div className={`rounded-2xl border p-6 shadow-sm ${v.className}`}>
            <div className="flex items-center gap-3 mb-2">
              <div className="h-8 w-8 rounded-full bg-white/60 flex items-center justify-center text-sm">
                {verdict === "improved" ? "↑" : verdict === "degraded" ? "↓" : "="}
              </div>
              <h3 className="font-serif text-lg">{v.label}</h3>
            </div>
            <p className="text-sm">{v.desc}</p>
          </div>

          {/* Side-by-side comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {([
              ["report_1", diff?.report_1],
              ["report_2", diff?.report_2],
            ] as const).map(([key, report]) => (
              <div key={key} className="bg-white border border-[#E8E2DB] rounded-xl p-5 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-serif text-[#2C2416] text-lg">
                    {key === "report_1" ? "报告 1" : "报告 2"}
                  </h3>
                  <span className="text-[11px] text-[#9B8E83] font-medium px-2 py-0.5 rounded-full bg-[#F5F0EB]">
                    历史版本
                  </span>
                </div>
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-sm text-[#9B8E83]">风险等级</span>
                    <Badge variant={riskVariant(report?.risk_level ?? null)}>{report?.risk_level ?? "-"}</Badge>
                  </div>
                  <div className="flex justify-between gap-4 text-sm">
                    <span className="text-[#9B8E83]">BN反事实</span>
                    <span className="font-medium text-[#2C2416]">{report?.counterfactuals ?? "-"} 项</span>
                  </div>
                  <div className="flex justify-between gap-4 text-sm">
                    <span className="text-[#9B8E83]">生成时间</span>
                    <span className="text-right text-[#2C2416]">{report?.created_at ?? "-"}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Risk level changes */}
          {diff?.risk_changes && diff.risk_changes.length > 0 && (
            <div className="bg-white border border-[#E8E2DB] rounded-xl p-5 shadow-sm">
              <h3 className="font-serif text-[#2C2416] text-lg mb-4">风险等级变化</h3>
              <div className="space-y-2">
                {diff.risk_changes.map((change, index) => (
                  <div key={index} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-lg border border-[#F0EAE3] bg-[#FCFAF8] px-4 py-3 text-sm">
                    <span className="text-[#2C2416] font-medium">{change.name}</span>
                    <div className="flex items-center gap-2 text-xs sm:text-sm">
                      <Badge variant={riskVariant(change.from)}>{change.from}</Badge>
                      <span className="text-[#B7ADA4]">→</span>
                      <Badge variant={riskVariant(change.to)}>{change.to}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Added / Removed */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white border border-green-200 rounded-xl p-5 shadow-sm">
              <h3 className="font-serif text-green-800 text-lg mb-3">新增风险</h3>
              {diff?.risks_added && diff.risks_added.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {diff.risks_added.map((item, index) => (
                    <span key={index} className="text-xs bg-green-50 text-green-700 px-2.5 py-1 rounded-full">
                      {item}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[#9B8E83]">本次对比未发现新增风险。</p>
              )}
            </div>

            <div className="bg-white border border-red-200 rounded-xl p-5 shadow-sm">
              <h3 className="font-serif text-red-800 text-lg mb-3">消除风险</h3>
              {diff?.risks_removed && diff.risks_removed.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {diff.risks_removed.map((item, index) => (
                    <span key={index} className="text-xs bg-red-50 text-red-700 px-2.5 py-1 rounded-full">
                      {item}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[#9B8E83]">本次对比未发现已消除风险。</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
