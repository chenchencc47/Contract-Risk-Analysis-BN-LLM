import { Header } from "./components/Header";
import { ContractInput } from "./components/ContractInput";
import { RiskReport } from "./components/RiskReport";
import { useReview } from "./hooks/useReview";

function App() {
  const { status, data, error, submitReview, reset } = useReview();

  return (
    <div className="min-h-screen bg-[#FAF8F5]">
      <Header />

      {status === "success" && data ? (
        /* ── Report view ── */
        <div>
          <div className="max-w-6xl mx-auto px-6 pt-6">
            <button
              onClick={reset}
              className="text-sm text-[#8B6F5C] hover:text-[#6B5243] font-medium
                         transition-colors duration-200 flex items-center gap-1.5"
            >
              <span className="text-lg leading-none">←</span> 审查新合同
            </button>
          </div>
          <RiskReport data={data} />
        </div>
      ) : status === "error" ? (
        /* ── Error view ── */
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
        /* ── Input view ── */
        <ContractInput onSubmit={submitReview} isLoading={status === "loading"} />
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

      {/* ── Footer ── */}
      <footer className="border-t border-[#E8E2DB] mt-12 py-6 text-center">
        <p className="text-[10px] text-[#C4B8AC] tracking-wide">
          ContractLens · LLM（自由审查）→ BN（一致性校验）→ LLM（综合报告） · pgmpy 推理引擎
        </p>
      </footer>
    </div>
  );
}

export default App;
