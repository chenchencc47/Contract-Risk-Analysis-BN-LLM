import { useState } from "react";
import { marked } from "marked";
import { Header } from "./components/Header";
import { ContractInput } from "./components/ContractInput";
import { RiskReport } from "./components/RiskReport";
import { SandboxPanel } from "./components/SandboxPanel";
import { ReportHistory } from "./components/ReportHistory";
import { useReview } from "./hooks/useReview";

type Page =
  | { name: "input" }
  | { name: "report" }
  | { name: "sandbox" }
  | { name: "history" }
  | { name: "history-detail"; reportId: number }
  | { name: "history-diff"; id1: number; id2: number };

function App() {
  const { status, data, error, submitReview, submitDualReview, dualData, reset } = useReview();
  const [page, setPage] = useState<Page>({ name: "input" });

  const handleSubmit = (text: string, id: string, party: "buyer" | "seller", dual: boolean, strategy: boolean) => {
    if (dual) {
      submitDualReview(text, id);
      setPage({ name: "report" });
    } else {
      submitReview(text, id, party, strategy);
      setPage({ name: "report" });
    }
  };

  // ── Pages ──

  if (page.name === "history") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <ReportHistory
          onBack={() => setPage({ name: "input" })}
          onViewReport={(id) => setPage({ name: "history-detail", reportId: id })}
          onCompare={(id1, id2) => setPage({ name: "history-diff", id1, id2 })}
        />
      </div>
    );
  }

  if (page.name === "history-detail") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <HistoryDetail
          reportId={page.reportId}
          onBack={() => setPage({ name: "history" })}
        />
      </div>
    );
  }

  if (page.name === "history-diff") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <HistoryDiff
          id1={page.id1}
          id2={page.id2}
          onBack={() => setPage({ name: "history" })}
        />
      </div>
    );
  }

  if (page.name === "sandbox") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <div className="max-w-7xl mx-auto px-6 pt-4">
          <button
            onClick={() => setPage({ name: "report" })}
            className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium
                       transition-colors duration-200 flex items-center gap-1.5"
          >
            <span className="text-lg leading-none">←</span> 返回审查
          </button>
        </div>
        <SandboxPanel />
      </div>
    );
  }

  // ── Main: Input / Loading / Report ──
  return (
    <div className="min-h-screen bg-[#FAF8F5]">
      <Header />

      {status === "success" && data ? (
        <div>
          {/* Toolbar */}
          <div className="max-w-6xl mx-auto px-6 pt-6 flex items-center justify-between flex-wrap gap-2">
            <div className="flex gap-2">
              <button
                onClick={reset}
                className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium
                           transition-colors duration-200 flex items-center gap-1.5"
              >
                <span className="text-lg leading-none">←</span> 审查新合同
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage({ name: "history" })}
                className="text-sm text-[#7B8B6F] hover:text-[#5A6B4F] font-medium
                           transition-colors duration-200 border border-[#C4D4B8]
                           rounded-lg px-3 py-1.5 hover:bg-[#F0F5EA]"
              >
                📋 历史报告
              </button>
              <button
                onClick={() => setPage({ name: "sandbox" })}
                className="text-sm text-[#7B8B6F] hover:text-[#5A6B4F] font-medium
                           transition-colors duration-200 border border-[#C4D4B8]
                           rounded-lg px-3 py-1.5 hover:bg-[#F0F5EA]"
              >
                ⚙ 条款优化沙盒
              </button>
            </div>
          </div>

          {/* Dual review summary */}
          {dualData && (
            <div className="max-w-6xl mx-auto px-6 mt-4">
              <div className="bg-white border border-[#E8E2DB] rounded-xl p-4 shadow-sm">
                <h3 className="font-serif text-[#8B6F5C] text-sm mb-2">
                  🔄 双视角对比摘要
                </h3>
                <div className="grid grid-cols-2 gap-4 text-xs">
                  {(() => {
                    const b = dualData.buyer as Record<string, number|string> | null;
                    const s = dualData.seller as Record<string, number|string> | null;
                    return (
                      <>
                        <div>
                          <span className="font-medium text-blue-700">买方视角</span>
                          <span className="text-[#9B8E83] ml-2">
                            {b?.risk_segments_count ?? "?"} 项风险 ·{" "}
                            {b?.counterfactuals_count ?? "?"} 项反事实
                          </span>
                        </div>
                        <div>
                          <span className="font-medium text-amber-700">卖方视角</span>
                          <span className="text-[#9B8E83] ml-2">
                            {s?.risk_segments_count ?? "?"} 项风险 ·{" "}
                            {s?.counterfactuals_count ?? "?"} 项反事实
                          </span>
                        </div>
                      </>
                    );
                  })()}
                </div>
                {dualData.comparison && (
                  <div className="mt-3 pt-3 border-t border-[#E8E2DB] grid grid-cols-2 gap-3 text-[10px]">
                    <div>
                      <span className="text-[#9B8E83]">买方独有关切：</span>
                      {(() => {
                        const v = (dualData.comparison as Record<string, string[]>).buyer_unique_concerns;
                        return v?.length ? v.join("、") : "无";
                      })()}
                    </div>
                    <div>
                      <span className="text-[#9B8E83]">卖方独有关切：</span>
                      {(() => {
                        const v = (dualData.comparison as Record<string, string[]>).seller_unique_concerns;
                        return v?.length ? v.join("、") : "无";
                      })()}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <RiskReport data={data} />
        </div>
      ) : status === "error" ? (
        <div className="max-w-2xl mx-auto px-6 pt-20 text-center">
          <div className="bg-[#FDF0ED] border border-[var(--color-risk-high)]/30 rounded-xl p-8">
            <span className="text-4xl">⚠</span>
            <h2 className="font-serif text-[var(--color-risk-high)] text-xl mt-3 mb-2">
              审查未能完成
            </h2>
            <p className="text-sm text-[#6B5E53] mb-4">{error}</p>
            <button
              onClick={reset}
              className="px-6 py-2 bg-[#8B6F5C] text-white text-sm rounded-lg
                         hover:bg-[#6B5243] transition-colors duration-200"
            >
              重试
            </button>
          </div>
        </div>
      ) : (
        <ContractInput
          onSubmit={(text, id, party, dual, strategy) => handleSubmit(text, id, party, dual, strategy)}
          isLoading={status === "loading"}
        />
      )}

      {status === "loading" && (
        <div className="max-w-2xl mx-auto px-6 pb-20 animate-fade-in">
          <div className="space-y-4">
            {[
              "LLM 正在对合同进行全面自由审查...",
              "贝叶斯网络正在进行一致性校验...",
              "BN 正在执行反事实模拟分析...",
              "正在生成综合风险评估报告...",
            ].map((msg, i) => (
              <div
                key={i}
                className="flex items-center gap-3 animate-slide-up"
                style={{ animationDelay: `${i * 400}ms` }}
              >
                <div className="w-5 h-5 border-2 border-[#E8E2DB] border-t-[#8B6F5C] rounded-full animate-spin" />
                <span className="text-sm text-[#9B8E83]">{msg}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <footer className="border-t border-[#E8E2DB] mt-12 py-6 text-center">
        <p className="text-[10px] text-[#C4B8AC] tracking-wide">
          ContractLens · LLM（自由审查）→ BN（一致性校验）→ LLM（综合报告） · pgmpy 推理引擎
        </p>
      </footer>
    </div>
  );
}

// ── History Detail (report view from DB) ──

function HistoryDetail({
  reportId,
  onBack,
}: {
  reportId: number;
  onBack: () => void;
}) {
  const [html, setHtml] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useState(() => {
    fetch(`/api/reports/${reportId}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.report_content_md) {
          setHtml(marked.parse(data.report_content_md) as string);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  });

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
      ) : (
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
                     prose-blockquote:text-[#6B5E53]
                     prose-li:text-[#3D3226] prose-li:leading-relaxed
                     prose-code:bg-[#F5F0EB] prose-code:px-1.5 prose-code:py-0.5
                     prose-code:rounded prose-code:text-xs prose-code:font-mono
                     prose-hr:border-[#E8E2DB]"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}
    </div>
  );
}

// ── History Diff (side-by-side comparison) ──

function HistoryDiff({
  id1,
  id2,
  onBack,
}: {
  id1: number;
  id2: number;
  onBack: () => void;
}) {
  const [diff, setDiff] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useState(() => {
    fetch(`/api/reports/diff?id1=${id1}&id2=${id2}`)
      .then((r) => r.json())
      .then((data) => {
        setDiff(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  });

  return (
    <div className="max-w-5xl mx-auto px-6 pb-20 animate-fade-in">
      <div className="pt-6 mb-4">
        <button
          onClick={onBack}
          className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium
                     transition-colors duration-200 flex items-center gap-1.5"
        >
          <span className="text-lg leading-none">←</span> 返回历史列表
        </button>
        <h2 className="font-serif text-2xl text-[#2C2416] mt-2">报告对比</h2>
      </div>

      {loading ? (
        <div className="text-center text-[#9B8E83] py-12">加载中...</div>
      ) : diff?.error ? (
        <div className="text-center text-red-600 py-12">{String(diff.error)}</div>
      ) : (
        <div className="space-y-6">
          {/* Meta comparison */}
          <div className="grid grid-cols-2 gap-4">
            {(["report_1", "report_2"] as const).map((key) => {
              const r = (diff as Record<string, Record<string, string|number>|undefined>)?.[key];
              return (
                <div key={key} className="bg-white border border-[#E8E2DB] rounded-xl p-4 shadow-sm">
                  <h3 className="font-serif text-[#8B6F5C] text-sm mb-2">
                    {key === "report_1" ? "报告 1" : "报告 2"}
                  </h3>
                  <div className="text-xs space-y-1 text-[#6B5E53]">
                    <div>风险等级：<span className="font-semibold">{String(r?.risk_level ?? "-")}</span></div>
                    <div>BN反事实：{String(r?.counterfactuals ?? "-")} 项</div>
                    <div>时间：{String(r?.created_at ?? "-")}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Risk changes */}
          {(() => {
            const d = diff as Record<string, unknown>;
            const changes = d.risk_changes as Array<Record<string,string>> | undefined;
            if (!changes || changes.length === 0) return null;
            return (
            <div className="bg-white border border-[#E8E2DB] rounded-xl p-4 shadow-sm">
              <h3 className="font-serif text-[#8B6F5C] text-sm mb-2">风险等级变化</h3>
              <div className="space-y-1">
                {changes.map((c, i) => (
                  <div key={i} className="text-xs text-[#6B5E53] flex items-center gap-2">
                    <span>{c.name}</span>
                    <span className="text-red-600">{c.from}</span>
                    <span>→</span>
                    <span className="text-green-600">{c.to}</span>
                  </div>
                ))}
              </div>
            </div>
            );
          })()}

          {(() => {
            const d = diff as Record<string, unknown>;
            const added = d.risks_added as string[] | undefined;
            return added && added.length > 0 && (
              <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                <span className="text-xs text-green-700">+ 新增风险：{added.join("、")}</span>
              </div>
            );
          })()}
          {(() => {
            const d = diff as Record<string, unknown>;
            const removed = d.risks_removed as string[] | undefined;
            return removed && removed.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <span className="text-xs text-red-700">- 消除风险：{removed.join("、")}</span>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

export default App;
