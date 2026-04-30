# 实施进度记录

> 最后更新：2026-04-30

---

## 2026-04-30：report-8 vs AI网页检测 系统性对比分析

完成了report-8（本项目卖方视角）与AI网页检测报告（买方视角）的逐维度对比，并参照Ironclad/LawGeex/Kira等商业产品进行了量化评分。

**关键发现：**
- report-8在所有可对比维度上均优于AI网页检测，核心优势在BN量化增强（反事实模拟、交叉验证、乘数效应）
- 个人产品维度评分：**7.8/10**（方法论创新9.0、分析深度8.5、数据严谨性8.5）
- 商业产品维度评分：**4.5/10**（核心AI能力7.5、产品完整度3.0、差异化壁垒7.0）
- 最大gap：BN覆盖不全（责任上限等关键条款无反事实数据）、产品化工程化不足

**产出：** WORKLIST.md 新增 v2.4+ 5项优化工作（P0反事实全覆盖→P1联合概率量化→P2呈现优化→P3多视角切换→P4工程化基础）

---

## 当前阶段：v2.3 立场锚定 + 安全护栏

基于煤炭购销合同审查报告的DeepSeek评价（不及格）和自评分析，完成两项关键修复：

| 序号 | 任务 | 状态 | 备注 |
|------|------|------|------|
| P0-1 | LLM₁/LLM₂立场锚定 | ✅ | 2026-04-29 | 系统prompt改为"代理律师"角色，前端加身份选择器 |
| P0-2 | LLM₂输出安全护栏 | ✅ | 2026-04-29 | 禁止"逾期视为接受"等危害客户权利的建议 |
| Bug | 沙盒全白 | ✅ | 2026-04-29 | NDA子图校准边连接confidentiality_nli导致pgmpy CPD校验失败 |

**核心改动文件：**
- `review/report_writer.py` — `_combined_system_prompt(review_party)` 锚定为"代理律师"；新增"立场规则"和"安全性规则"；`generate_combined_report()` 接受review_party
- `review/ai_review.py` — `_free_review_prompt(review_party)` + `free_review_contract_text(review_party)` 立场注入
- `web/server.py` — 新增 `POST /api/v2/review`（完整LLM₁→BN→LLM₂管线+review_party）；原有 `/api/review` 也加入review_party
- `evaluation/cpt_calibrator.py` — 修复DataCalibrationFn签名兼容性；NDA子图不再添加edges（节点保留为独立contract_fact节点）
- `frontend/src/components/ContractInput.tsx` — 新增审查立场选择器（甲方/乙方toggle）
- `frontend/src/hooks/useReview.ts` — 调用 `/api/v2/review` 传递review_party
- `frontend/src/App.tsx` — 传递review_party给ContractInput

**效果：**
- LLM不再扮演"中立合同设计者"，而是客户代理律师
- 前端用户可选择甲方/乙方身份
- 安全性规则防止"15个工作日煤炭异议期"类法律错误
- v2 API端点完整可用

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
| P2.1 | CUAD 共现统计验证跨维度边 | ✅ | 2026-04-29 | 30%混合权重+0.4上限，4条边全部校准 |
| P2.2 | ContractNLI NDA 专项子图 | ✅ | 2026-04-29 | 新增4个NDA节点（披露/使用/返还/存续），BN 63→67节点 |
| P0 (新增) | LLM₂ prompt微调 | ✅ | 2026-04-29 | 必须用完所有BN反事实+优先维度级数据+淡化整体概率 |

---

## 数据使用说明

| 数据集 | 校准 BN 哪层 | 节点数 | CPT 来源 | 局限 |
|--------|-------------|--------|---------|------|
| CUAD | contract_fact | ~35 | 统计 P(present) | 仅商业合同，缺购销专属维度 |
| ContractNLI | legal_semantics | 保密相关 | NLI 转移概率 | 仅 NDA |
| 专家补充 | contract_fact | ~7 | expert_estimated | 付款/交货/验收等 CUAD 不覆盖 |
