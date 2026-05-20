# BN-Contract-Risk-Analysis 工作清单（v2.17）

> 最后更新：2026-05-20（后续方案制定）

---

## 当前总目标

v2.17 已完成 BN 节点扩展（90→110）、合同类型覆盖（3→10）、法条引用增强、角色自动检测。
下一阶段目标：**质量收口 — 先做直接改善报告的事（Delta阈值 + CPT校准），再做对外展示的事（评测管线修复）。**

---

## 待实施项

### Phase 1：直接改善报告质量（优先执行）

| 编号 | 事项 | 说明 | 涉及文件 |
|:--:|------|------|---------|
| P1-1 | **Delta 阈值校准** ✅ | 用 CPT source 的采样分辨率做精度地板；加相对阈值 `delta/baseline > 0.05`；min-3 兜底。已完成 2026-05-20 | `src/contract_risk_analysis/bn/pgmpy_adapter.py` |
| P1-2 | **CUAD CPT 验证 + 重校准** ✅ | 30 个节点逐类别统计验证，28 个一致，2 个修正（cuad_license_grant、cuad_no_solicit_of_customers） | `config/bayesian_network_v2.json` |
| P1-3 | **LEDGAR 辅助 CPT 校准** ✅ | 13 个 CUAD 锚点线性回归 → 35 节点更新，数据驱动比例 35%→67% | `config/bayesian_network_v2.json`, `scripts/apply_ledgar_calibration.py` |

### Phase 2：评测管线修复（提升外部可信度）

| 编号 | 事项 | 说明 | 涉及文件 |
|:--:|------|------|---------|
| P2-1 | **CUAD 映射修复 + 评测** ✅ | 41→8 类映射重写 + 精确类别名匹配；5 份端到端验证通过 | `src/contract_risk_analysis/evaluation/runner.py` |
| P2-2 | **ContractNLI 评测扩展** ✅ | 确认无法扩展：17 个 hypothesis 全部关于保密协议，仅覆盖 confidentiality 维度。已有 500 条 BN-only 评测数据可用 | — |
| P2-3 | **Benchmark 数字整理** ✅ | 已有：ContractNLI 500条 BN-only(41.8%风险准确率) + CUAD 5条初步(per-type F1 0.40-0.89)。全量 CUAD 需 `--max 510 --use-llm`（约 510 次 API 调用） | `sample_data/benchmark_*.json` |

### Phase 3：暂缓项（学术论文/对外发布前执行）

| 编号 | 事项 | 说明 |
|:--:|------|------|
| P3-1 | **Baseline 消融实验** ✅ | LLM-only vs LLM+BN；20 条：LLM-only 25% vs LLM+BN 65%，实证 BN 核心价值 | `src/contract_risk_analysis/evaluation/runner.py` |
| P3-2 | **ECE 校准误差** ✅ | ECE=0.155（差），但 500 条全落在同一 bin——confidentiality 节点无路径到 output，反映结构缺陷非校准问题 | `evaluation/ece_benchmark.py` |
| P3-3 | **反事实消融 + BN 边补全** ✅ | 新建 `counterfactual_ablation.py`；发现 37 节点孤立 → 创建 5 个子 aggregate，115 节点全联通；98.1% 方向正确 | `evaluation/counterfactual_ablation.py`, `config/bayesian_network_v2.json` |

---

## 明确排除（不在本次计划内）

| 事项 | 排除原因 |
|------|---------|
| 新合同类型红线规则 | 跟随合同类型扩展按需添加，非本次质量收口范围 |
| 中文合同 CPT 校准 | 需人工标注，暂无资源。LEDGAR 辅助校准是当前最优替代 |
| 前端角色选择器优化 | 功能已可用 |
| 合同范本数据清洗 | 已完成（F-2），后续按需 |

---

## 当前架构总览

```
合同类型路由: 10 种
  ├─ 销售合同    ├─ 技术开发合同  ├─ 劳动/聘用合同
  ├─ 采购合同    ├─ 服务合同      ├─ 工程承包/施工合同
  ├─ 煤炭合同    ├─ 租赁合同      └─ 借款/抵押/担保合同
  └─ 保密协议

BN 节点: 110 个
  ├─ contract_fact: 71 节点 (cuad_empirical 30 + expert_estimated 25 + LEDGAR expert 35 + contractnli 2)
  ├─ legal_semantics: 33 节点
  ├─ risk_dimension: 5 节点
  ├─ overall_contract_risk: 1 节点
  └─ CPT 来源: LEDGAR_calibrated(35) / cuad_empirical(30) / expert_estimated(25) / cuad_aggregate(7) / noisy_max(6) / contractnli(2) / missing(5)

数据集:
  ├─ CUAD: 510 份英文合同 (41 种风险类别标注)
  ├─ ContractNLI: 9,788 条 NLI 标注 (607 份合同)
  ├─ LEDGAR: 80K 条合同条款分类
  ├─ chinese_contract_templates: 10K 中文合同范本
  ├─ DISC-Law-SFT: 103K 中文法律QA
  └─ ALeaseBert: 257 份英文租赁NER

管线:
  LLM₁(自由审查+法条速查) → BN(110节点一致性校验) → LLM₂(受约束报告渲染)
    ↑ party_role_label                            ↑ bn_confidence分层
    ↑ 合同类型路由                                   ↑ 轻量模式(risk≤3)
```

---

## 续做规则

- 每完成一个事项，更新本文件和 PROGRESS.md
- 完成的事项从 WORKLIST.md 移除，写入 PROGRESS.md
- 每次改动后运行 `.venv/Scripts/python.exe -m pytest tests/ -q` 确认无回归
- 数据集改动较大时先创建新分支再提交
