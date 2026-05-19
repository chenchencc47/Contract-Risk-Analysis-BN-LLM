interface Props {
  currentPage?: string;
  onNavigate?: (name: string) => void;
}

export function Header({ currentPage, onNavigate }: Props) {
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

        <div className="flex items-center gap-2">
          {/* Nav buttons */}
          {onNavigate && currentPage !== "redlines" && (
            <button onClick={() => onNavigate("redlines")}
              className="text-xs text-[#8B6F5C] hover:text-[#6B5243] font-medium
                         transition-colors duration-200 border border-[#E8E2DB]
                         rounded-lg px-3 py-1.5 hover:border-[#8B6F5C]">
              🛡 企业红线
            </button>
          )}
          {onNavigate && currentPage !== "history" && (
            <button
              onClick={() => onNavigate("history")}
              className="text-xs text-[#7B8B6F] hover:text-[#5A6B4F] font-medium
                         transition-colors duration-200 border border-[#C4D4B8]
                         rounded-lg px-3 py-1.5 hover:bg-[#F0F5EA]"
            >
              📋 历史报告
            </button>
          )}
          {onNavigate && currentPage !== "sandbox" && currentPage !== "input" && currentPage !== "report" && (
            <button
              onClick={() => onNavigate("sandbox")}
              className="text-xs text-[#7B8B6F] hover:text-[#5A6B4F] font-medium
                         transition-colors duration-200 border border-[#C4D4B8]
                         rounded-lg px-3 py-1.5 hover:bg-[#F0F5EA]"
            >
              ⚙ 沙盒
            </button>
          )}
          {onNavigate && currentPage !== "input" && (
            <button
              onClick={() => onNavigate("input")}
              className="text-xs text-[#8B6F5C] hover:text-[#6B5243] font-medium
                         transition-colors duration-200 border border-[#E8E2DB]
                         rounded-lg px-3 py-1.5 hover:border-[#8B6F5C]"
            >
              + 新审查
            </button>
          )}

          <span className="hidden sm:inline text-xs text-[#9B8E83] ml-2">
            BN v2
          </span>
        </div>
      </div>
    </header>
  );
}
