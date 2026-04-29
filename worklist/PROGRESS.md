# 实施进度记录

> 最后更新：2026-04-29

---

## 当前阶段：报告质量优化（v2.1）

基于4份报告对比分析（A/C/D/E），发现E报告（最新版）在风险覆盖面、反事实数据说服力、BN-人工评级一致性三个维度存在明显短板。针对性完成以下优化：

| 序号 | 任务 | 状态 | 备注 |
|------|------|------|------|
| P0-1 | BN节点清单注入LLM₁ prompt | ✅ | 2026-04-29 | 动态读取BN config，~50项系统检查清单 |
| P0-2 | 维���级反事实敏感度分析 | ✅ | 2026-04-29 | 5维度节点独立计算P(high)，48节点→维度映射 |
| P1 | CPT校准器数据源适配层 | ✅ | 2026-04-29 | DataCalibrationFn协议 + register/calibrate接口 |
| P2 | PolishedReport来源标注字段 | ✅ | 2026-04-29 | bn_derived_claims + llm_judgment_claims自动提取 |

**核心改动文件：**
- `review/ai_review.py` — `_build_bn_checklist()`, `_get_all_evidence_node_names()`
- `bn/pgmpy_adapter.py` — `_build_node_to_dimension_map()`, `DIMENSION_NODES`, 维度级delta计算
- `bn/consistency_validator.py` — `run_counterfactual_analysis()` 传入dimension_targets
- `review/report_writer.py` — 维度级数据格式化, `bn_derived_claims`/`llm_judgment_claims` 提取
- `evaluation/cpt_calibrator.py` — `DataCalibrationFn`协议, `register_calibration_source()`
- `domain/free_review_schema.py` — 新增 `DimensionDelta` dataclass

**预期效果：**
- LLM₁风险识别覆盖面：7项 → ≥10项（通过系统性检查清单）
- 反事实数据说服力：整体级32.3%基线 → 维度级78-95%基线（如付款风险95%→45%）
- BN-人工评级一致性：系统性分歧 → 维度级delta与手动评级趋同
- 未来中国合同数据集可直接通过 `register_calibration_source()` 接入

**测试：** 58/58核心测试通过（1个Streamlit demo测试为预存问题）

---

## 上一阶段完成情况（v1→v2 架构重构）

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 新建 `free_review_schema.py` 数据模型（6 个新 dataclass） | ✅ |
| Phase 2 | LLM₁ 自由审查——去除 finding_key 约束 | ✅ |
| Phase 3 | BN 映射服务 BnMappingService | ✅ |
| Phase 4 | BN 一致性校验器 BnValidator（5 种检查） | ✅ |
| Phase 5 | LLM₂ 综合报告生成器——拥有最终判断权 | ✅ |
| Phase 6 | API 集成 `/api/review` 默认 v2，前后端对齐 | ✅ |

67/71 测试通过（4 个 Streamlit demo 测试为预存问题）。

---

## 当前阶段：数据驱动 BN + 诚实性优化

---

## P0：BN 节点扩展与 CPT 数据驱动

| 序号 | 任务 | 状态 | 备注 |
|------|------|------|------|
| P0.1 | CUAD 展开 contract_fact 节点（41→30） | ✅ | 2026-04-28 | BN 从 20→63 节点 |
| P0.2 | CUAD 统计校准 contract_fact 层 CPT | ✅ | 2026-04-28 | 30 节点 cuad_empirical |
| P0.3 | ContractNLI 扩展 legal_semantics 校准 | ✅ | 2026-04-28 | 置信度校准参数 + benchmark |
| P0.4 | 补充销售合同专属节点（6个） | ✅ | 2026-04-28 | payment/delivery/dispute_venue 等 |
| P0.5 | 验证反事实分析真实性 | ✅ | 2026-04-28 | 修复后 6 条反事实（原来 0 条） |

### P0 关键成果
- BN: 20 节点 → 63 节点 (30 CUAD + 6 sales + 7 aggregate + 20 original)
- CPT: expert_estimated 主导 → cuad_empirical 主导
- 反事实: 0 条 → 6 条（验收 4.9% / 付款 3.3% / 管辖 2.6%）

## P1：LLM₂ 报告诚实度

| 序号 | 任务 | 状态 | 备注 |
|------|------|------|------|
| P1.1 | prompt 增加数据来源诚实性约束 | ✅ | 2026-04-28 | "不得编造反事实数字" |
| P1.2 | PolishedReport 增加来源标注 | ✅ | 2026-04-29 | bn_derived_claims + llm_judgment_claims |

## P2：图结构持续优化

| 序号 | 任务 | 状态 | 备注 |
|------|------|------|------|
| P2.1 | CUAD 共现统计验证跨维度边 | ⬜ pending | |
| P2.2 | ContractNLI NDA 专项子图 | ⬜ pending | |

---

## 数据使用说明

| 数据集 | 校准 BN 哪层 | 节点数 | CPT 来源 | 局限 |
|--------|-------------|--------|---------|------|
| CUAD | contract_fact | ~35 | 统计 P(present) | 仅商业合同，缺购销专属维度 |
| ContractNLI | legal_semantics | 保密相关 | NLI 转移概率 | 仅 NDA |
| 专家补充 | contract_fact | ~7 | expert_estimated | 付款/交货/验收等 CUAD 不覆盖 |
