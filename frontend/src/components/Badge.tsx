export type BadgeVariant =
  | "risk-critical"
  | "risk-high"
  | "risk-medium"
  | "risk-low"
  | "party-buyer"
  | "party-seller"
  | "neutral"
  | "accent"
  | "workbench-tag";

const VARIANT_CLASS: Record<BadgeVariant, string> = {
  "risk-critical": "bg-red-50 text-red-700",
  "risk-high": "bg-red-50 text-red-700",
  "risk-medium": "bg-yellow-50 text-yellow-700",
  "risk-low": "bg-green-50 text-green-700",
  "party-buyer": "bg-blue-50 text-blue-700",
  "party-seller": "bg-amber-50 text-amber-700",
  neutral: "bg-[#F5F0EB] text-[#8B6F5C]",
  accent: "bg-[#F3F8EE] text-[#5A6B4F]",
  "workbench-tag": "bg-[#F5F0EB] text-[#8B6F5C]",
};

interface Props {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = "neutral", children, className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${VARIANT_CLASS[variant]} ${className}`}
    >
      {children}
    </span>
  );
}


