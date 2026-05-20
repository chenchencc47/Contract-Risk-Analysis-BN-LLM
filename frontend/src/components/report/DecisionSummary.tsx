import type { ReviewResponse, ReviewReport, RiskItem } from "../../types";

interface Props {
  data: ReviewResponse;
  report: ReviewReport | null;
  isV2: boolean;
  signingAdvice: string;
  actionPlan: string[];
}

function RiskLevelBadge({ recommendation }: { recommendation: string }) {
  const className = recommendation.includes("不建议") || recommendation.includes("暂不")
    ? "bg-red-50 text-red-700"
    : recommendation.includes("有条件")
      ? "bg-yellow-50 text-yellow-700"
      : "bg-green-50 text-green-700";

  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${className}`}>
      {recommendation || "有条件签署"}
    </span>
  );
}

function ManualReviewBadge({ required }: { required: boolean }) {
  if (!required) return null;
  return (
    <span className="inline-flex items-center rounded-full bg-[#FDF0ED] px-3 py-1 text-xs font-semibold text-red-600">
      需人工复核
    </span>
  );
}

function TopRiskCard({ risk, index }: { risk: RiskItem; index: number }) {
  return (
    <div className="rounded-xl border border-[#E8E2DB] bg-[#FCFAF8] p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[#F5F0EB] text-[11px] font-semibold text-[#8B6F5C]">
          {index + 1}
        </span>
        <h4 className="font-serif text-base text-[#2C2416]">{risk.title}</h4>
      </div>
      <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
        <span className="rounded-full bg-[#F5F0EB] px-2 py-0.5 text-[#8B6F5C]">{risk.dimension}</span>
        {risk.risk_level_label && (
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-red-700">{risk.risk_level_label}</span>
        )}
      </div>
      <p className="text-sm leading-6 text-[#6B5E53]">{risk.reason}</p>
      {risk.recommendation && (
        <div className="mt-3 rounded-lg border border-[#DCE8CF] bg-[#F5FAEF] px-3 py-2 text-sm text-[#2C2416]">
          {risk.recommendation}
        </div>
      )}
    </div>
  );
}

export function DecisionSummary({ data, report, isV2, signingAdvice, actionPlan }: Props) {
  const recommendation = report?.signing_recommendation || signingAdvice || "有条件签署";
  const topRisks = (report?.top_risks || []).slice(0, 3);
  const immediateActions = actionPlan.slice(0, 3);
  const confidenceFacts = [
    data.findings_count ? `${data.findings_count} 项发现` : null,
    data.evidence_summary?.total_nodes ? `${data.evidence_summary.total_nodes} 个节点校验` : null,
    typeof data.consistency?.counterfactuals_count === "number" ? `${data.consistency.counterfactuals_count} 项反事实` : null,
    data.debug?.routing?.primary_type ? `合同类型识别：${data.debug.routing.primary_type}` : null,
    data.golden_score ? `回归评分 ${data.golden_score.score.toFixed(0)} 分` : null,
    isV2 ? "LLM + BN 联合生成" : "BN 风险推理支撑",
  ].filter((item): item is string => Boolean(item));

  return (
    <section className="mb-6 space-y-6">
      <div className="relative overflow-hidden rounded-2xl border border-[#E8E2DB] bg-white p-6 shadow-sm bg-texture">
        <div className="absolute right-0 top-0 h-40 w-40 -mr-8 -mt-8 rounded-bl-full bg-[#F5F0EB]/60 pointer-events-none" />
        <div className="relative grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <p className="text-xs font-semibold tracking-[0.18em] text-[#9B8E83]">DECISION SUMMARY</p>
            <h3 className="mt-2 font-serif text-2xl text-[#2C2416]">先判断能不能签，再阅读完整报告</h3>
            <p className="mt-3 text-sm leading-6 text-[#6B5E53]">
              这一层只提取现有结构化结论做阅读入口，完整审查正文仍在下方完整保留。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <RiskLevelBadge recommendation={recommendation} />
              <span className="inline-flex items-center rounded-full bg-[#F5F0EB] px-3 py-1 text-xs font-semibold text-[#8B6F5C]">
                总体风险：{report?.overall_risk_label ?? "—"}
              </span>
              <ManualReviewBadge required={report?.requires_manual_review ?? false} />
            </div>
          </div>
          <div className="rounded-xl border border-[#E8E2DB] bg-[#FCFAF8] p-4">
            <p className="text-xs font-semibold tracking-[0.16em] text-[#9B8E83]">可信说明</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {confidenceFacts.map((fact) => (
                <span key={fact} className="rounded-full bg-white px-3 py-1 text-xs text-[#6B5E53] border border-[#E8E2DB]">
                  {fact}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {topRisks.length > 0 && (
        <div className="space-y-3">
          <div>
            <h3 className="font-serif text-xl text-[#2C2416]">最需要先看的 3 个问题</h3>
            <p className="mt-1 text-sm text-[#9B8E83]">优先展示当前结构化结果里最值得立刻关注的高优先级问题。</p>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            {topRisks.map((risk, index) => (
              <TopRiskCard key={`${risk.title}-${index}`} risk={risk} index={index} />
            ))}
          </div>
        </div>
      )}

      {immediateActions.length > 0 && (
        <div className="rounded-2xl border border-[#E8E2DB] bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 className="font-serif text-xl text-[#2C2416]">立刻要改的条款 / 动作</h3>
              <p className="mt-1 text-sm text-[#9B8E83]">不改写原报告，只把已有行动建议前置展示。</p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {immediateActions.map((item, index) => (
              <div key={`${item}-${index}`} className="rounded-xl border border-[#E8E2DB] bg-[#FCFAF8] px-4 py-3 text-sm leading-6 text-[#2C2416]">
                <div className="mb-2 text-[11px] font-semibold tracking-wide text-[#8B6F5C]">动作 {index + 1}</div>
                {item}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
