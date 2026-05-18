import { useState } from "react";
import { Header } from "./components/Header";
import { ContractInput } from "./components/ContractInput";
import { RiskReport } from "./components/RiskReport";
import { SandboxPanel } from "./components/SandboxPanel";
import { ReportHistory } from "./components/ReportHistory";
import { RedlineManager } from "./components/RedlineManager";
import { HistoryDetailPage } from "./components/history/HistoryDetailPage";
import { HistoryDiffPage } from "./components/history/HistoryDiffPage";
import { useReview } from "./hooks/useReview";

type Page =
  | { name: "input" }
  | { name: "report" }
  | { name: "sandbox" }
  | { name: "history" }
  | { name: "history-detail"; reportId: number }
  | { name: "history-diff"; id1: number; id2: number }
  | { name: "redlines" };

function App() {
  const { status, data, error, submitReview, submitDualReview, dualData, reset } = useReview();
  const [page, setPage] = useState<Page>({ name: "input" });

  const handleSubmit = (text: string, id: string, party: "buyer" | "seller", dual: boolean, partyRoleLabel?: string) => {
    if (dual) {
      submitDualReview(text, id);
      setPage({ name: "report" });
    } else {
      submitReview(text, id, party, dual, partyRoleLabel);
      setPage({ name: "report" });
    }
  };

  const navigate = (name: string) => {
    switch (name) {
      case "input": reset(); setPage({ name: "input" }); break;
      case "history": setPage({ name: "history" }); break;
      case "sandbox": setPage({ name: "sandbox" }); break;
      case "report": setPage({ name: "report" }); break;
      case "redlines": setPage({ name: "redlines" }); break;
    }
  };

  // ── Pages ──

  if (page.name === "history") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header currentPage={page.name} onNavigate={navigate} />
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
        <Header currentPage={page.name} onNavigate={navigate} />
        <HistoryDetailPage
          reportId={page.reportId}
          onBack={() => setPage({ name: "history" })}
        />
      </div>
    );
  }

  if (page.name === "history-diff") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header currentPage={page.name} onNavigate={navigate} />
        <HistoryDiffPage
          id1={page.id1}
          id2={page.id2}
          onBack={() => setPage({ name: "history" })}
        />
      </div>
    );
  }

  if (page.name === "redlines") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header currentPage={page.name} onNavigate={navigate} />
        <RedlineManager onBack={() => setPage({ name: "input" })} />
      </div>
    );
  }

  if (page.name === "sandbox") {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header currentPage={page.name} onNavigate={navigate} />
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
      <Header currentPage={page.name} onNavigate={navigate} />

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
          onSubmit={(text, id, party, dual) => handleSubmit(text, id, party, dual)}
          isLoading={status === "loading"}
        />
      )}

      {status === "loading" && <LoadingScreen />}

      <footer className="border-t border-[#E8E2DB] mt-12 py-6 text-center">
        <p className="text-[10px] text-[#C4B8AC] tracking-wide">
          ContractLens · LLM（自由审查）→ BN（一致性校验）→ LLM（综合报告） · pgmpy 推理引擎
        </p>
      </footer>
    </div>
  );
}

// ── Loading Screen with timer ──

function LoadingScreen() {
  const [elapsed, setElapsed] = useState(0);
  useState(() => {
    const start = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  });
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const timeStr = mins > 0 ? `${mins}分${secs}秒` : `${secs}秒`;

  const stages = [
    { label: "LLM 正在对合同进行全面自由审查...", min: 0 },
    { label: "贝叶斯网络正在进行一致性校验...", min: 15 },
    { label: "BN 正在执行反事实模拟分析...", min: 40 },
    { label: "正在生成综合风险评估报告...", min: 90 },
  ];

  const currentStage = stages.reduce((best, s) => (elapsed >= s.min ? s : best), stages[0]);

  return (
    <div className="max-w-2xl mx-auto px-6 pb-20 animate-fade-in">
      <div className="text-center mb-6">
        <span className="text-3xl text-[#8B6F5C] font-mono font-bold">{timeStr}</span>
        <p className="text-xs text-[#9B8E83] mt-1">审查进行中，请耐心等待...</p>
      </div>
      <div className="space-y-3">
        {stages.map((s, i) => (
          <div key={i} className={`flex items-center gap-3 transition-all duration-500 ${elapsed >= s.min ? "opacity-100" : "opacity-30"}`}>
            {elapsed >= s.min
              ? (i < stages.indexOf(currentStage) ? <span className="text-green-500 text-sm">✓</span>
                : i === stages.indexOf(currentStage) ? <div className="w-5 h-5 border-2 border-[#E8E2DB] border-t-[#8B6F5C] rounded-full animate-spin" />
                : <span className="w-5 h-5" />)
              : <span className="w-5 h-5" />}
            <span className="text-sm text-[#9B8E83]">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
