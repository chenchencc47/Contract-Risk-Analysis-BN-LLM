interface Props {
  actions: string[];
  crossDimensionNotes: string[];
}

export function ActionPlan({ actions, crossDimensionNotes }: Props) {
  return (
    <div className="space-y-5">
      {crossDimensionNotes.length > 0 && (
        <div>
          <h3 className="font-serif text-[#8B6F5C] text-lg mb-3">维度关联风险</h3>
          <div className="bg-[#FDF0ED] border border-[var(--color-risk-high)]/20 rounded-lg p-4">
            {crossDimensionNotes.map((note, i) => (
              <p key={i} className="text-sm text-[#6B5E53] leading-relaxed flex gap-2">
                <span className="text-[var(--color-risk-high)] shrink-0">↗</span>
                {note}
              </p>
            ))}
          </div>
        </div>
      )}

      {actions.length > 0 && (
        <div>
          <h3 className="font-serif text-[#8B6F5C] text-lg mb-3">整改计划</h3>
          <div className="space-y-2">
            {actions.map((action, i) => (
              <div
                key={i}
                className="flex items-start gap-3 bg-white border border-[#E8E2DB] rounded-lg
                           px-4 py-3 hover:border-[#7B8B6F]/50 hover:shadow-sm
                           transition-all duration-200 animate-slide-up"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <span className="font-serif text-[#7B8B6F] text-lg leading-none mt-0.5 shrink-0">
                  {i + 1}
                </span>
                <p className="text-sm text-[#2C2416] leading-relaxed">{action}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
