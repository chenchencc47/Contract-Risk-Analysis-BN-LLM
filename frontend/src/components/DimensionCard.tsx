import { RiskGauge } from "./RiskGauge";

interface Props {
  dimKey: string;
  label: string;
  score: number;
  riskLevel: string;
  summary?: string;
  insight?: string;
}

export function DimensionCard({ dimKey, label, score, riskLevel, summary, insight }: Props) {
  const barWidth = Math.min(Math.max(score * 100, 5), 100);
  const barColor =
    riskLevel === "high"
      ? "var(--color-risk-high)"
      : riskLevel === "medium"
        ? "var(--color-risk-medium)"
        : "var(--color-risk-low)";

  return (
    <div className="group bg-white border border-[#E8E2DB] rounded-lg p-4
                    hover:border-[#D4A574]/50 hover:shadow-sm
                    transition-all duration-300 ease-out">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="font-serif text-[#2C2416] text-base">{label}</h4>
          <p className="text-[10px] text-[#9B8E83] font-mono mt-0.5">{dimKey}</p>
        </div>
        <RiskGauge level={riskLevel} size="sm" />
      </div>

      <div className="h-1.5 rounded-full bg-[#F5F0EB] overflow-hidden mb-2">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${barWidth}%`, backgroundColor: barColor }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-[#9B8E83] font-mono">
        <span>0</span>
        <span>{(score * 100).toFixed(0)}%</span>
        <span>100%</span>
      </div>

      {(summary || insight) && (
        <p className="mt-2.5 text-xs text-[#6B5E53] leading-relaxed opacity-0
                      group-hover:opacity-100 transition-opacity duration-300">
          {insight || summary}
        </p>
      )}
    </div>
  );
}
