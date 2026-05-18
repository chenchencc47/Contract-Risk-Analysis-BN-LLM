import { useState, useEffect, useMemo } from "react";
import type { ReportHistoryItem, ReportHistoryResponse } from "../types";
import { Badge } from "./Badge";
import { riskVariant, partyVariant } from "../utils/badgeVariants";

interface Props {
  onViewReport: (id: number) => void;
  onCompare: (id1: number, id2: number) => void;
  onBack: () => void;
}

export function ReportHistory({ onViewReport, onCompare, onBack }: Props) {
  const [reports, setReports] = useState<ReportHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");
  const [selected, setSelected] = useState<number[]>([]);

  useEffect(() => {
    fetch("/api/reports?limit=100")
      .then((r) => r.json())
      .then((data: ReportHistoryResponse) => {
        setReports(data.reports || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const toggleSelect = (id: number) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-2)
    );
  };

  const filtered = useMemo(
    () =>
      filter
        ? reports.filter(
            (r) =>
              r.contract_name.includes(filter) ||
              r.review_party.includes(filter) ||
              (r.contract_type || "").includes(filter)
          )
        : reports,
    [reports, filter],
  );

  const partyLabel = (p: string) => (p === "buyer" ? "买方" : p === "seller" ? "卖方" : p);

  return (
    <div className="max-w-6xl mx-auto px-6 pb-20 animate-fade-in">
      <div className="relative bg-white border border-[#E8E2DB] rounded-xl p-6 mb-6 shadow-sm bg-texture overflow-hidden">
        <div className="absolute top-0 right-0 w-44 h-44 rounded-bl-full bg-[#F5F0EB]/60 -mr-8 -mt-8 pointer-events-none" />
        <div className="relative space-y-4">
          <div>
            <button
              onClick={onBack}
              className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium transition-colors duration-200 flex items-center gap-1.5"
            >
              <span className="text-lg leading-none">←</span> 返回审查
            </button>
            <div className="flex items-center gap-3 mt-2 flex-wrap">
              <h2 className="font-serif text-2xl text-[#2C2416]">历史报告</h2>
              <span className="text-[10px] font-semibold bg-[#F5F0EB] text-[#8B6F5C] px-2 py-0.5 rounded-full tracking-wider">
                WORKBENCH
              </span>
            </div>
            <p className="text-sm text-[#9B8E83] mt-2">
              版本工作台：筛选、选择、对比既往审查版本。查看完整报告请在归档详情页确认。
            </p>
          </div>

          {/* Stats bar */}
          {!loading && (
            <div className="flex flex-wrap items-center gap-3 text-xs text-[#9B8E83]">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F5F0EB] px-3 py-1.5 font-medium text-[#6B5E53]">
                <span className="text-[#8B6F5C]">{reports.length}</span> 个版本
              </span>
              {filter && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F5F0EB] px-3 py-1.5 font-medium text-[#6B5E53]">
                  匹配 <span className="text-[#8B6F5C]">{filtered.length}</span> 条
                  <button
                    onClick={() => setFilter("")}
                    className="ml-1 text-[#B7ADA4] hover:text-[#6B5E53]"
                  >
                    ✕
                  </button>
                </span>
              )}
              {selected.length > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F3F8EE] px-3 py-1.5 font-medium text-[#5A6B4F]">
                  已选 {selected.length}/2
                  <button
                    onClick={() => setSelected([])}
                    className="ml-1 text-[#A0B890] hover:text-[#5A6B4F]"
                  >
                    ✕ 清除
                  </button>
                </span>
              )}
            </div>
          )}

          {/* Filter + Compare bar */}
          <div className="flex flex-col sm:flex-row gap-2 sm:items-center pt-1">
            <input
              type="text"
              placeholder="筛选合同名称 / 类型 / 立场"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="text-sm px-3 py-2.5 border border-[#E8E2DB] rounded-lg focus:outline-none focus:border-[#8B6F5C] bg-white min-w-[240px]"
            />
            <button
              onClick={() => onCompare(selected[0], selected[1])}
              disabled={selected.length !== 2}
              className={`text-sm font-medium px-4 py-2.5 rounded-lg transition-all ${
                selected.length === 2
                  ? "text-white bg-[#7B8B6F] hover:bg-[#5A6B4F]"
                  : "text-[#B7ADA4] bg-[#F5F0EB] cursor-not-allowed"
              }`}
            >
              对比选中报告
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-[#9B8E83] py-12">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white border border-[#E8E2DB] rounded-xl shadow-sm text-center text-[#9B8E83] py-12">
          {filter ? "没有匹配的报告，请调整筛选条件。" : "暂无历史报告。审查合同后会自动保存。"}
        </div>
      ) : (
        <div className="bg-white border border-[#E8E2DB] rounded-xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-sm">
              <thead>
                <tr className="bg-[#F7F3EE] text-[#6B5E53] text-xs uppercase tracking-wider">
                  <th className="px-4 py-3 text-left w-12">选</th>
                  <th className="px-4 py-3 text-left">合同名称</th>
                  <th className="px-4 py-3 text-left">类型</th>
                  <th className="px-4 py-3 text-left">立场</th>
                  <th className="px-4 py-3 text-left">风险等级</th>
                  <th className="px-4 py-3 text-left">BN反事实</th>
                  <th className="px-4 py-3 text-left">时间</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    className={`border-t border-[#F5F0EB] transition-colors ${
                      selected.includes(r.id) ? "bg-[#F3F8EE]" : "hover:bg-[#FAF8F5]"
                    }`}
                  >
                    <td className="px-4 py-4 align-top">
                      <input
                        type="checkbox"
                        checked={selected.includes(r.id)}
                        onChange={() => toggleSelect(r.id)}
                        className="rounded mt-1"
                      />
                    </td>
                    <td className="px-4 py-4 align-top">
                      <div className="font-medium text-[#2C2416]">{r.contract_name}</div>
                      <div className="text-[11px] text-[#B7ADA4] mt-1">版本 v{r.report_version}</div>
                    </td>
                    <td className="px-4 py-4 align-top text-[#9B8E83]">{r.contract_type || "-"}</td>
                    <td className="px-4 py-4 align-top">
                      <Badge variant={partyVariant(r.review_party)}>
                        {partyLabel(r.review_party)}
                      </Badge>
                    </td>
                    <td className="px-4 py-4 align-top">
                      <Badge variant={riskVariant(r.overall_risk_level)}>
                        {r.overall_risk_level || "-"}
                      </Badge>
                    </td>
                    <td className="px-4 py-4 align-top text-[#6B5E53]">
                      {r.bn_counterfactual_count > 0 ? `${r.bn_counterfactual_count} 项` : "-"}
                    </td>
                    <td className="px-4 py-4 align-top text-[#9B8E83] text-xs whitespace-nowrap">
                      {new Date(r.created_at).toLocaleString("zh-CN")}
                    </td>
                    <td className="px-4 py-4 align-top text-right">
                      <button
                        onClick={() => onViewReport(r.id)}
                        className="text-xs text-[#8B6F5C] hover:text-[#6B5243] font-medium bg-[#F8F4EF] hover:bg-[#F1E8DF] px-3 py-1.5 rounded-md transition-colors"
                      >
                        查看报告
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
