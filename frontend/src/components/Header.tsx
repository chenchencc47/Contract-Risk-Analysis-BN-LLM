export function Header() {
  return (
    <header className="border-b border-[#E8E2DB] bg-white/60 backdrop-blur-sm sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl select-none">⚖</span>
          <div>
            <h1 className="font-serif text-[#8B6F5C] text-xl tracking-tight leading-none">
              ContractLens
            </h1>
            <p className="text-[#9B8E83] text-xs tracking-wide mt-0.5">
              合同风险智能审查
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm text-[#6B5E53]">
          <span className="hidden sm:inline text-xs text-[#9B8E83]">
            LLM → BN → LLM
          </span>
          <div className="w-px h-4 bg-[#E8E2DB]" />
          <span className="text-xs font-medium text-[#7B8B6F]">
            Bayesian Network v2
          </span>
        </div>
      </div>
    </header>
  );
}
