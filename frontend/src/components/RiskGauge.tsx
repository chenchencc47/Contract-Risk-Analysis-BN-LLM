const LABELS: Record<string, { label: string; color: string; bg: string }> = {
  high: { label: "高风险", color: "var(--color-risk-high)", bg: "var(--color-risk-high-bg)" },
  medium: { label: "中风险", color: "var(--color-risk-medium)", bg: "var(--color-risk-medium-bg)" },
  low: { label: "低风险", color: "var(--color-risk-low)", bg: "var(--color-risk-low-bg)" },
};

interface Props {
  level: string;
  score?: number;
  label?: string;
  size?: "sm" | "lg";
}

export function RiskGauge({ level, score, label, size = "lg" }: Props) {
  const info = LABELS[level] ?? LABELS.medium;
  const isLg = size === "lg";

  return (
    <div
      className={`inline-flex flex-col items-center ${isLg ? "gap-1.5" : "gap-0.5"}`}
      style={{ color: info.color }}
    >
      <div
        className={`rounded-full flex items-center justify-center font-serif font-semibold
          ${isLg ? "w-20 h-20 text-2xl" : "w-14 h-14 text-lg"}`}
        style={{ backgroundColor: info.bg }}
      >
        {info.label.slice(0, 1)}
      </div>
      <span className={`font-medium tracking-wide ${isLg ? "text-sm" : "text-xs"}`}>
        {label ?? info.label}
      </span>
      {score !== undefined && (
        <span className="text-[10px] opacity-60 font-mono">
          {(score * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
}
