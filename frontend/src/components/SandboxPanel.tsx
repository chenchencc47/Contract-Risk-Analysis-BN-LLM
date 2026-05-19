import { useState, useEffect, useCallback } from "react";
import { RiskGauge } from "./RiskGauge";
import type { BnNode, BnSimulation } from "../types";

const DIM_ORDER = [
  "financial_exposure_risk",
  "performance_delivery_risk",
  "dispute_resolution_risk",
  "legal_enforceability_risk",
  "clause_balance_risk",
];

function stateLabel(s: string): string {
  const map: Record<string, string> = {
    favorable: "有利",
    neutral: "中立",
    unfavorable: "不利",
    balanced: "平衡",
    present: "存在",
    missing: "缺失",
    acceptable: "合理",
    moderate: "一般",
    counterparty_favorable: "偏向对方",
    severe: "严重",
  };
  return map[s] ?? s;
}

function probToLevel(p: number): "high" | "medium" | "low" {
  if (p >= 0.7) return "high";
  if (p >= 0.35) return "medium";
  return "low";
}

export function SandboxPanel() {
  const [nodes, setNodes] = useState<BnNode[]>([]);
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [baseline, setBaseline] = useState<Record<string, Record<string, number>>>({});
  const [simulation, setSimulation] = useState<Record<string, Record<string, number>>>({});
  const [dimLabels, setDimLabels] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/bn/nodes")
      .then((r) => r.json())
      .then((data) => {
        setNodes(data.nodes);
        setDimLabels(data.dimension_labels);
        // Run baseline with no evidence
        fetch("/api/bn/simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ evidence: {} }),
        })
          .then((r) => r.json())
          .then((sim: BnSimulation) => {
            setBaseline(sim.posteriors);
            setLoading(false);
          });
      });
  }, []);

  const runSimulation = useCallback(
    (ev: Record<string, string>) => {
      fetch("/api/bn/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ evidence: ev }),
      })
        .then((r) => r.json())
        .then((sim: BnSimulation) => setSimulation(sim.posteriors));
    },
    [],
  );

  const handleToggle = (nodeName: string, state: string) => {
    const next = { ...evidence, [nodeName]: state };
    setEvidence(next);
    runSimulation(next);
  };

  const handleReset = () => {
    setEvidence({});
    runSimulation({});
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-6 pt-20 text-center">
        <div className="animate-spin w-8 h-8 border-2 border-[#E8E2DB] border-t-[#8B6F5C] rounded-full mx-auto mb-3" />
        <p className="text-sm text-[#9B8E83]">正在加载BN模型...</p>
      </div>
    );
  }

  const active = simulation || baseline;
  const overallBaseline = baseline["overall_contract_risk"]?.["high"] ?? 0;
  const overallSim = simulation["overall_contract_risk"]?.["high"];

  // Group nodes by affected dimension
  const grouped: Record<string, BnNode[]> = {};
  for (const n of nodes) {
    const dim = n.affects_dimensions[0] || "other";
    if (!grouped[dim]) grouped[dim] = [];
    grouped[dim].push(n);
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-serif text-2xl text-[#4A3628]">
            条款优化沙盒
          </h1>
          <p className="text-sm text-[#9B8E83] mt-1">
            拨动条款状态，实时观察风险维度变化
          </p>
        </div>
        <button
          onClick={handleReset}
          className="px-4 py-2 text-sm text-[#8B6F5C] border border-[#E8E2DB] rounded-lg
                     hover:bg-[#F5F0E8] transition-colors duration-200"
        >
          重置
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: Node controls */}
        <div className="lg:col-span-2 space-y-6">
          {DIM_ORDER.filter((d) => grouped[d]?.length).map((dim) => (
            <div key={dim}>
              <h3 className="text-xs font-semibold text-[#8B6F5C] uppercase tracking-wider mb-3">
                {dimLabels[dim] || dim}
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {grouped[dim].map((node) => (
                  <div
                    key={node.node_name}
                    className="flex items-center justify-between bg-white border border-[#E8E2DB]
                               rounded-lg px-3 py-2.5 hover:border-[#C4B8AC] transition-colors"
                  >
                    <span className="text-xs text-[#4A3628] font-medium truncate" title={node.label}>
                      {node.label}
                    </span>
                    <select
                      className="text-xs border border-[#E8E2DB] rounded px-2 py-1
                                 bg-[#FAF8F5] text-[#4A3628] focus:outline-none
                                 focus:border-[#8B6F5C] max-w-[100px]"
                      value={evidence[node.node_name] || ""}
                      onChange={(e) => {
                        if (e.target.value) {
                          handleToggle(node.node_name, e.target.value);
                        }
                      }}
                    >
                      <option value="">默认</option>
                      {node.states.filter((s) => s !== "unknown").map((s) => (
                        <option key={s} value={s}>
                          {stateLabel(s)}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Right: Risk dashboard */}
        <div className="space-y-5">
          <div className="bg-white border border-[#E8E2DB] rounded-xl p-5">
            <h3 className="text-sm font-serif text-[#4A3628] mb-4">合同整体风险</h3>
            <div className="flex items-center gap-6">
              <div className="text-center">
                <p className="text-[10px] text-[#9B8E83] mb-1">默认</p>
                <RiskGauge
                  level={probToLevel(overallBaseline)}
                  score={overallBaseline}
                  size="sm"
                />
              </div>
              <span className="text-[#C4B8AC] text-lg">→</span>
              <div className="text-center">
                <p className="text-[10px] text-[#9B8E83] mb-1">优化后</p>
                <RiskGauge
                  level={probToLevel(overallSim ?? overallBaseline)}
                  score={overallSim ?? overallBaseline}
                  size="sm"
                />
              </div>
              {overallSim !== undefined && (
                <div className="text-center">
                  <p className="text-[10px] text-[#9B8E83] mb-1">降幅</p>
                  <span
                    className={`text-lg font-mono font-semibold ${
                      overallSim < overallBaseline
                        ? "text-green-600"
                        : "text-red-500"
                    }`}
                  >
                    {((overallBaseline - overallSim) * 100).toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </div>

          {DIM_ORDER.map((dim) => {
            const base = baseline[dim];
            const sim = active[dim];
            if (!base) return null;
            const baseHigh = base["high"] ?? 0;
            const simHigh = sim?.["high"] ?? baseHigh;
            return (
              <div
                key={dim}
                className="bg-white border border-[#E8E2DB] rounded-xl p-4"
              >
                <h4 className="text-xs font-medium text-[#6B5E53] mb-3">
                  {dimLabels[dim] || dim}
                </h4>
                <div className="flex items-center gap-3 justify-between">
                  <div className="text-center">
                    <p className="text-[10px] text-[#9B8E83]">当前</p>
                    <span className="text-lg font-mono font-semibold text-[#4A3628]">
                      {(baseHigh * 100).toFixed(0)}%
                    </span>
                  </div>
                  <span className="text-[#C4B8AC] text-sm">→</span>
                  <div className="text-center">
                    <p className="text-[10px] text-[#9B8E83]">优化后</p>
                    <span className="text-lg font-mono font-semibold text-[#4A3628]">
                      {(simHigh * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div
                    className={`text-xs font-mono font-semibold px-2 py-1 rounded ${
                      baseHigh - simHigh > 0.01
                        ? "bg-green-50 text-green-700"
                        : "bg-red-50 text-red-600"
                    }`}
                  >
                    {baseHigh - simHigh > 0.01 ? "↓" : "↑"}
                    {Math.abs(baseHigh - simHigh) > 0.001
                      ? (Math.abs(baseHigh - simHigh) * 100).toFixed(1) + "%"
                      : "—"}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
