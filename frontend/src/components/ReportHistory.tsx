import { useState, useEffect } from "react";

interface ReportItem {
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

interface Props {
  onViewReport: (id: number) => void;
  onCompare: (id1: number, id2: number) => void;
  onBack: () => void;
}

export function ReportHistory({ onViewReport, onCompare, onBack }: Props) {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");
  const [selected, setSelected] = useState<number[]>([]);

  useEffect(() => {
    fetch("/api/reports?limit=100")
      .then((r) => r.json())
      .then((data) => {
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

  const filtered = filter
    ? reports.filter(
        (r) =>
          r.contract_name.includes(filter) ||
          r.review_party.includes(filter) ||
          (r.contract_type || "").includes(filter)
      )
    : reports;

  const partyLabel = (p: string) => (p === "buyer" ? "买方" : p === "seller" ? "卖方" : p);

  return (
    <div className="max-w-5xl mx-auto px-6 pb-20 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 pt-6">
        <div>
          <button
            onClick={onBack}
            className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium
                       transition-colors duration-200 flex items-center gap-1.5"
          >
            <span className="text-lg leading-none">←</span> 返回审查
          </button>
          <h2 className="font-serif text-2xl text-[#2C2416] mt-2">
            历史报告
          </h2>
        </div>
        <div className="flex gap-2">
          {selected.length === 2 && (
            <button
              onClick={() => onCompare(selected[0], selected[1])}
              className="text-xs text-white bg-[#7B8B6F] hover:bg-[#5A6B4F] font-medium
                         px-4 py-2 rounded-lg transition-all"
            >
              对比选中报告
            </button>
          )}
          <input
            type="text"
            placeholder="筛选..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="text-xs px-3 py-2 border border-[#E8E2DB] rounded-lg
                       focus:outline-none focus:border-[#8B6F5C] w-40"
          />
        </div>
      </div>

      {loading ? (
        <div className="text-center text-[#9B8E83] py-12">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center text-[#9B8E83] py-12">
          暂无历史报告。审查合同后会自动保存。
        </div>
      ) : (
        <div className="bg-white border border-[#E8E2DB] rounded-xl overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#F5F0EB] text-[#6B5E53] text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left w-10">选</th>
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
                  className={`border-t border-[#F5F0EB] hover:bg-[#FAF8F5] transition-colors
                    ${selected.includes(r.id) ? "bg-[#F0F5EA]" : ""}`}
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.includes(r.id)}
                      onChange={() => toggleSelect(r.id)}
                      className="rounded"
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-[#2C2416]">
                    {r.contract_name}
                    <span className="text-[10px] text-[#C4B8AC] ml-1">v{r.report_version}</span>
                  </td>
                  <td className="px-4 py-3 text-[#9B8E83]">{r.contract_type}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full
                      ${r.review_party === "buyer"
                        ? "bg-blue-50 text-blue-700"
                        : "bg-amber-50 text-amber-700"
                      }`}>
                      {partyLabel(r.review_party)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full
                      ${r.overall_risk_level === "致命" || r.overall_risk_level === "高"
                        ? "bg-red-50 text-red-700"
                        : r.overall_risk_level === "中"
                          ? "bg-yellow-50 text-yellow-700"
                          : "bg-green-50 text-green-700"
                      }`}>
                      {r.overall_risk_level || "-"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[#9B8E83]">
                    {r.bn_counterfactual_count > 0
                      ? `${r.bn_counterfactual_count} 项`
                      : "-"}
                  </td>
                  <td className="px-4 py-3 text-[#9B8E83] text-xs">
                    {new Date(r.created_at).toLocaleDateString("zh-CN")}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => onViewReport(r.id)}
                      className="text-xs text-[#8B6F5C] hover:text-[#6B5243] font-medium"
                    >
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
