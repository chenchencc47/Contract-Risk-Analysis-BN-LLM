import type { RiskItem } from "../types";

const LEVEL_COLORS: Record<string, string> = {
  high: "border-l-[var(--color-risk-high)] bg-[var(--color-risk-high-bg)]",
  medium: "border-l-[var(--color-risk-medium)] bg-[var(--color-risk-medium-bg)]",
  low: "border-l-[var(--color-risk-low)] bg-[var(--color-risk-low-bg)]",
};

interface Props {
  risks: RiskItem[];
}

export function AttributionChain({ risks }: Props) {
  if (!risks.length) return null;

  return (
    <div className="space-y-3">
      <h3 className="font-serif text-[#8B6F5C] text-lg">
        风险归因链
        <span className="text-xs font-sans text-[#9B8E83] ml-2 font-normal">
          证据 → 节点 → 维度 → 总体风险
        </span>
      </h3>
      {risks.map((risk, i) => (
        <div
          key={risk.node_name || i}
          className={`border-l-[3px] rounded-r-md pl-4 py-3 pr-3
                      animate-slide-up transition-all duration-300
                      hover:translate-x-1 ${LEVEL_COLORS[risk.risk_level] ?? LEVEL_COLORS.medium}`}
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full
              ${risk.risk_level === "high"
                ? "bg-[var(--color-risk-high)]/15 text-[var(--color-risk-high)]"
                : risk.risk_level === "medium"
                  ? "bg-[var(--color-risk-medium)]/20 text-[#8B6914]"
                  : "bg-[var(--color-risk-low)]/15 text-[var(--color-risk-low)]"
              }`}>
              {risk.risk_level_label || risk.risk_level}
            </span>
            <span className="font-medium text-sm text-[#2C2416]">{risk.title}</span>
            <span className="text-[10px] text-[#9B8E83]">→ {risk.dimension}</span>
          </div>
          <p className="text-xs text-[#6B5E53] leading-relaxed">{risk.reason}</p>
          {risk.evidence.length > 0 && (
            <div className="mt-1.5 text-[11px] text-[#9B8E83] italic">
              证据摘录：「{risk.evidence[0].slice(0, 120)}{risk.evidence[0].length > 120 ? "..." : ""}」
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
