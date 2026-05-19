import type { BadgeVariant } from "../components/Badge";

export function riskVariant(level: string | null): BadgeVariant {
  if (level === "致命" || level === "高") return "risk-high";
  if (level === "中") return "risk-medium";
  return "risk-low";
}

export function partyVariant(party: string): BadgeVariant {
  return party === "buyer" ? "party-buyer" : "party-seller";
}
