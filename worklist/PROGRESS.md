# 实施进度记录

> 最后更新：2026-05-08（新增报告-6 vs 报告-7 对比评估 + v2.11 工作项）

---

## 2026-05-08：v2.10 版本发布 + 报告稳定性路线确定

### v2.10 发布 ✅
- 已创建新提交：`98a20e2` — `Release v2.10: 开源化基础设施完善与后端路由拆分`
- 已创建并推送标签：`v2.10`
- 已推送远端分支：`origin/release/v2.8`
- 本次发布未混入本地分析材料、合同 PDF 与临时评估文件，保持源码版本边界清晰

### 报告稳定性路线结论（已确认，待实施）
基于对当前链路 `LLM₁ 自由审查 → BN 一致性校验/反事实 → LLM₂ 最终报告` 的复盘，确认：

1. 当前核心问题是**架构问题**，不是单纯 prompt 问题；
2. 第一阶段优先 **先稳结论**，先保证核心风险、严重度、优先级、BN数字、签署底线稳定一致；
3. 未来采用 **稳定事实核 + LLM解释层** 路线：
   - LLM 负责合同理解、法律解释、修改建议与律师式表达；
   - BN / 规则 / 裁决层负责稳定事实；
   - LLM₂ 不再拥有最终改判权，只负责受约束渲染。

### 外部咨询确认（2026-05-08） ✅
用户就"AI合同审查是否应每次结果完全一致"做了外部咨询，结论与本方案**总体一致**：
- 不需要追求整份报告逐字逐句绝对一致；
- 必须锁定**事实层**和**核心判断层**的一致性；
- 允许**表达层**存在有限自然差异；
- 特别强调**单次报告内部一致性**（同份报告前后不打仗）与跨轮稳定性同等重要。

此结论已同步进方案文档（`方向/报告稳定性优先与架构演进方案.md`），并新增"分层一致性目标"章节和"单次报告内部一致性验证"验证项。

### 文档产出 ✅
- 新增方案文档：`方向/报告稳定性优先与架构演进方案.md`
- `WORKLIST.md` 已补充 **v2.10：报告稳定性优先 + 架构演进** 路线

### 下一阶段实施焦点
- P0：LLM₂ 降级为受约束渲染器
- P1：引入结构化 Report Dossier 作为最终事实源
- P2：稳定 LLM₁ → BN 的 canonicalization / issue_id 层
- P3：新增 adjudication layer
- P4：重复运行稳定性与 narrative guardrail 质量门禁

---

## 2026-05-08：Phase A 实施 — LLM₂ 降级为受约束渲染器

### P0：LLM₂ 角色改造 ✅
改造文件：`src/contract_risk_analysis/review/report_writer.py`

1. **`_combined_system_prompt()`**：LLM₂ 角色从"最终判断者"改为"受约束渲染器"
   - 移除"你拥有最终判断权"和"以你的法律判断为准"
   - 新增"绝对禁止的行为"清单（8条：禁改风险项、禁改严重度、禁改优先级、禁改BN数字、禁改签署底线、禁压制人工复核标记等）
   - 明确 LLM₂ 的任务是"把 Dossier 翻译成专业中文法律报告"

2. **`_build_combined_prompt()`**：信息来源从两层改为三层
   - 信息来源一：Report Dossier（系统最终结论，必须严格遵循）—— 新增
   - 信息来源二：AI初审法律分析（用于展开论述和撰写话术）—— 降级
   - 信息来源三：BN校验摘要（仅供参考）—— 降级
   - "审核与判断原则"替换为"核心规则：你的角色是受约束渲染器"（7条）
   - "严禁行为"新增5条 dossier 相关禁令

3. **`generate_combined_report()`**：
   - 新增 `dossier` 参数（可选，None 时自动构建）
   - temperature 从 0.5 → 0.1
   - `generation_mode` 改为 "combined_phase_a"
   - 新增内部一致性日志记录

### P1：结构化 Report Dossier ✅
改造文件：`src/contract_risk_analysis/domain/free_review_schema.py`

- 新增 `DossierRiskItem` dataclass：issue_id、severity、priority_rank、evidence、bn_coverage、manual_review、internal_conflict
- 新增 `ReportDossier` dataclass：risk_items、counterfactuals、bn_annotations、signing_forbidden、signing_acceptable、negotiation_bottom_lines、internal_conflicts

改造文件：`src/contract_risk_analysis/review/report_writer.py`

- 新增 `_build_dossier()`：确定性构建 dossier，冻结所有 risk items 的 severity/priority/evidence，生成签署底线，标记人工复核项，检测内部不一致
- 新增 `_fmt_dossier_section()`：将 dossier 格式化为 LLM₂ prompt 中的权威数据段

### P5：内部一致性校验 ✅
改造文件：`src/contract_risk_analysis/review/report_writer.py` + `backend/routers/review.py`

- dossier 构建时自动检测 BN 矛盾标注和 gap_detected 并标记为 manual_review
- `_run_v2_pipeline` 中新增 `QUALITY_GATE_INTERNAL_CONSISTENCY` 日志告警
- manual_review 标记通过 Dossier 传递给 LLM₂，LLM₂ 被禁止绕过

### 管线集成 ✅
改造文件：`backend/routers/review.py`

- v2 管线在 LLM₂ 调用前构建 dossier
- dossier 内部冲突通过 quality_gate 日志输出

---

## 2026-05-08：Phase A P2 — 稳定 LLM₁ → BN 交接层

### P2：Canonicalization 层 ✅
改造文件：
- `src/contract_risk_analysis/domain/free_review_schema.py`：RiskSegment 解除 frozen + 新增 `canonical_type` 字段
- `src/contract_risk_analysis/review/canonicalize.py`（新文件）：确定性 clause_type 归一化模块
  - `canonicalize_clause_type()`：3 层匹配策略（精确→归一化→子串），基于 `clause_type_mapping.yaml` 词汇表
  - `canonicalize_free_review()`：批量归一化所有 risk segments
  - 中英文双向映射（付款→payment, delivery→delivery 等）
- `src/contract_risk_analysis/bn/bn_mapping.py`：`_heuristic_match()` 优先使用 `canonical_type`，回退到原始 `clause_type`
- `backend/routers/review.py`：管线中在 LLM₁ 输出后、BN 映射前执行 canonicalization，含日志统计

### 设计要点
- canonical_type 由系统确定性赋值，不依赖 LLM 生成
- canonical vocabulary 来自 `config/clause_type_mapping.yaml`，贡献者可编辑
- BnMappingService 三层回退：canonical → clause_type exact → clause_type substring
- 同一风险的多种写法（payment/Payment/付款/支付方式）归一化到同一 canonical type

### 测试：68/68 全部通过（BN 75节点，API 20路由）

---

## 2026-05-08：Phase A P3 — 裁决层（Adjudication Layer）

### P3：Adjudication Layer ✅
新建文件：`src/contract_risk_analysis/review/adjudicate.py`

1. **去重**：基于 canonical_type 匹配 + 中文标题字符级 Jaccard 相似度（≥0.5）+ 证据重叠度（≥0.3），合并重复风险项
2. **严重度归一化**：对比 LLM₁ severity 与 BN posterior P(high)，检测不一致但暂不自动改判
3. **优先级强制执行**：critical→P1、high→P2 硬规则
4. **证据质量评估**：低置信度+无BN覆盖的弱证据项标记

管线接入：`backend/routers/review.py` — canonicalization 之后、BN mapping 之前执行，带去重统计日志

### 测试：68/68 全部通过（BN 75节点，API 20路由）

---

## 2026-05-08：Phase A P4 — 稳定性验证基础设施

### P4：稳定性验证 + Narrative Guardrail ✅
新建文件：`tests/stability/__init__.py` + `tests/stability/test_report_stability.py`

1. **`DossierSnapshot`**：从 pipeline 响应中提取稳定字段
2. **`StabilityReport`**：跨 N 次运行的聚合分析
3. **`check_narrative_guardrail()`**：检查 narrative 是否引入 dossier 中不存在的新风险
4. **`TestAdjudicationStability`**（离线）：验证裁决层去重的确定性
5. **`TestReportStability`**（在线，需 API Key）：3 次全链路运行 + 稳定性校验

### 测试：69 通过（+1 稳定性单元测试），5 skipped（需后端运行的集成测试）

---

## Phase A 全部完成总结（2026-05-08）

| 任务 | 内容 | 状态 |
|------|------|:--:|
| P0 | LLM₂ 降级为受约束渲染器 | ✅ |
| P1 | 结构化 Report Dossier | ✅ |
| P2 | Canonicalization 层（稳定 LLM₁→BN） | ✅ |
| P3 | Adjudication Layer（去重+裁决） | ✅ |
| P4 | 稳定性验证基础设施 | ✅ |
| P5 | 单次报告内部一致性校验 | ✅ |

**新增文件（3个）：**
- `src/contract_risk_analysis/review/canonicalize.py`
- `src/contract_risk_analysis/review/adjudicate.py`
- `tests/stability/test_report_stability.py`

**改造文件（5个）：**
- `src/contract_risk_analysis/domain/free_review_schema.py`
- `src/contract_risk_analysis/review/report_writer.py`
- `src/contract_risk_analysis/bn/bn_mapping.py`
- `backend/routers/review.py`

**关键参数变更：**
- LLM₂ temperature: 0.5 → 0.1
- 管线链路：LLM₁ → canonicalize → adjudicate → BN → dossier → LLM₂（受约束渲染）

### E2E 线上验证 ✅ (2026-05-08)
启动后端（localhost:9527），使用买卖合同样本跑完整 v2 管线：
- 状态码：200
- 耗时：307s（含 BN 推理 ~5min）
- 风险项：5 个，全部 5/5 (100%) canonicalization 覆盖率
- BN 反事实：8 个
- BN 校验标注：65 个
- 管线链路验证通过：LLM₁ → canonicalize → adjudicate → BN → dossier → LLM₂

### 最终测试统计
- **单元测试：69 passed**（68 原有 + 1 新增稳定性单元测试）
- **5 skipped**（需 API Key + 后端运行的集成测试，可手动触发）
- 0 failed

### 向后兼容
- `generate_combined_report()` 的 dossier 参数默认为 None，自动构建
- `dual.py`、旧版 `web/server.py` 等调用方无需改动
- 旧 API 行为完全不受影响

---

## 2026-05-08：Phase B/C 逐条完成度审计

> 对照方案文档 `方向/报告稳定性优先与架构演进方案.md` 逐动作核实。

### Phase B：稳定 LLM₁ → BN 的交接

| # | 动作 | 状态 | 说明 |
|---|------|:--:|------|
| 1 | `canonical_type` 字段 | ✅ | `RiskSegment.canonical_type` 已加 |
| 2 | canonicalization 层 | ✅ | `canonicalize.py`，基于 `clause_type_mapping.yaml` |
| 3 | 归并同义标签+重复风险项 | ⚠️ | canonicalize 做了映射；adjudicate 做了同 canonical_type 去重；**不同 canonical_type 但描述同一风险的跨类型归并未做** |
| 4 | 稳定 issue_id（内容派生） | ❌ | 当前为顺序编号 ISSUE-001，两次运行同一风险可能拿不同 ID |
| 5 | BnMappingService 优先 canonical | ✅ | `_heuristic_match()` 已优先 `canonical_type` |

### Phase C：新增裁决层

| # | 职责 | 状态 | 说明 |
|---|------|:--:|------|
| 1 | 合并重复 finding | ✅ | `adjudicate.py` `_deduplicate()` |
| 2 | 分配统一 issue_id | ❌ | 同上，顺序编号不稳定 |
| 3 | 规则决定 severity | ❌ | priority 已强制执行（critical→P1），但 **severity 仍完全来自 LLM₁，无规则裁决** |
| 4 | 结合 BN 输出生成 dossier | ✅ | `_build_dossier()` |
| 5 | 人工复核标记 | ✅ | BN 矛盾/gap_detected → `manual_review` |

### 真正未完成的缺口（3 项）→ 全部修复于 2026-05-08

---

## 2026-05-08：Phase B/C 缺口修复 + Phase D 实施

### B-1：稳定 issue_id ✅
改造文件：`src/contract_risk_analysis/review/report_writer.py`

- issue_id 从顺序编号改为内容派生：`ISSUE-{canonical_type[:12]}-{sha256(ctype|evidence[:80])[:8]}`
- 新增碰撞保护：同一 run 内相同 hash 自动追加序号
- 同一 canonical_type + 同一证据 → 永远产出同一个 issue_id

### B-2：跨 canonical_type 归并 ✅
改造文件：`src/contract_risk_analysis/review/adjudicate.py`

- `_deduplicate()` 从单 pass 改为双 pass
- Pass 1：同 canonical_type 内去重（ev_threshold=0.3）
- Pass 2：跨 canonical_type 去重（ev_threshold=0.5，更保守）
- 新增 `_should_merge()` 辅助函数

### C-1：severity 规则裁决 ✅
改造文件：
- `src/contract_risk_analysis/review/adjudicate.py`：移除 `_normalize_severity` 调用（需 BN 数据）
- `src/contract_risk_analysis/review/report_writer.py`：`_build_dossier()` 中新增三条规则
  - Rule 1: BN P(high) > 0.6 AND LLM₁ 标 medium/low → 升级为 high
  - Rule 2: BN P(high) < 0.1 AND LLM₁ 标 critical → 降级为 high
  - Rule 3: critical 无 BN 覆盖 → 降级为 high

### Phase D：两层输出 ✅
改造文件：`backend/routers/review.py`

- API 响应新增 `fact_sheet` 字段
- 包含：risk_items（含 stable issue_id）、counterfactuals、signing_guardrails、manual_review_items、internal_conflicts
- 零 LLM 参与，数据完全来自 dossier

### 测试：69/69 全部通过

### 验证项 V-2/V-3/V-4 离线测试 ✅
改造文件：`tests/stability/test_report_stability.py`

新增 3 个测试类（7 个测试方法）：
- **TestMappingStability（V-3）**：22 组中英同义表述映射一致性 + 确定性验证 + 未知类型返回 None
- **TestNarrativeGuardrail（V-2）**：检测 narrative 越权扩写 + 清洁 narrative 通过
- **TestConflictEscalation（V-4）**：BN 矛盾触发 manual_review + critical 无 BN 覆盖降级验证

修复：`canonicalize.py` 新增中文 YAML key → English canonical 反向映射（第二 pass）

### 最终测试统计
- **离线单元测试：76 passed**
- **8 个稳定性专项测试全部通过**（离线）
- **5 skipped**（需 API Key + 后端运行：V-1 重复运行稳定性 × 3 + narrative guardrail × 1 + 3-run × 1）
- **0 failed**

### Phase A-D 全部实施完成，方案文档完整闭环

### P0：BN反事实产出稳定性 ✅
**根因分析：**
1. `favorable_states` 硬编码仅覆盖 ~15 节点，其余靠猜测——猜不到就跳过
2. BnMappingService 只映射到 legal_semantics 子节点，不传播证据到 contract_fact 父节点→反事实 delta 因缺少父节点证据而过小
3. 双层 delta 阈值（0.001 + 0.01）过滤过度

**修复 (3 files)：**
- `pgmpy_adapter.py`：扩展 favorable_states 硬编码（+7 个销售合同节点），auto-discovery 候选从 6 个扩展到 14 个，加 fallback `states[-1]`
- `bn_validator.py`：delta 阈值 0.01→0.003，top_n 5→8，新增 fallback pool（维度级 delta≥5% 的低整体 delta 项也被保留）
- `bn_mapping.py`：新增 `_propagate_to_parents()` — legal_semantics 节点有证据时自动推断父 contract_fact 节点证据

### P1：反事实推导链可视化 ✅
- `free_review_schema.py`：CounterfactualResult 新增 `derivation_chain` 字段
- `bn_validator.py`：`_build_derivation_chain()` 生成 `条款状态X→Y | CPT来源 | pgmpy VE推理 → δ=-43.3%`
- `report_writer.py`：LLM₂ prompt 中注入推导链，格式示例更新含 📐 推导链

### P2：报告质量门禁 ✅
- `web/server.py`：`/api/v2/review` 中加入反事实产出检查
- 反事实 <3 项 → 日志 WARNING + 响应中 `quality_gate.warnings`
- 5 核心维度覆盖检查（financial/performance/legal/dispute/clause）
- 响应新增 `quality_gate` 字段

### P4.3：清理 Streamlit demo ✅
- 删除 `demo/streamlit_app.py`、`demo/report_page.py`、`tests/demo/`
- `pyproject.toml` 移除 `streamlit` 依赖
- 保留 `demo/app.py`（CLI 依赖 `render_report_payload`）

### P4.1 + P4.2：PDF 导出 + 多格式导出架构 ✅
- weasyprint → fpdf2（Windows 无 GTK3 依赖，纯 Python）
- 新增 `export/pdf_exporter.py`：`export_pdf()` + `export_md()` + `export_report(fmt)`
- API：`POST /api/export/pdf` + `POST /api/export/md`
- `EXPORTERS` 字典架构预留 html/docx 扩展
- 原有 MD 导出完全保留（独立函数 + API 端点）

### P3：报告历史管理与版本对比 ✅
- `db/connection.py`：pymysql 连接管理，读取 .env 配置
- `db/repository.py`：CRUD — contracts(upsert/get/list) + reports(save/get/list/diff) + risks + counterfactuals
- `web/server.py`：`/api/v2/review` 审查完成后自动写入 MySQL
- API：`GET /api/reports`（列表筛选）、`GET /api/reports/{id}`（详情+全文）、`GET /api/reports/diff?id1=&id2=`（差异对比）
- 数据库写入失败不阻断管线（logger.warning）

### P6.1：跨维度联合概率量化 ✅
- `pgmpy_adapter.py`：新增 `query_joint_probability()` + `JointRiskResult` dataclass
- 计算 P(A=high ∩ B=high) 联合概率 + 乘数因子（>1.3=乘数效应，<0.9=负相关）
- `consistency_validator.py`：6对关键维度组合自动分析（财务×争议、履约×法律等）
- `report_writer.py`：LLM₂ prompt 中注入联合概率数据 + 乘数因子表格
- `free_review_schema.py`：ConsistencyReport 新增 `joint_risks` 字段

### P6.2：BN知识图谱学习闭环 ✅
- 新增 `bn/feedback.py`：`save_feedback()` + `get_feedback_summary()` + `get_feedback_for_report()`
- 新增 MySQL 表：`bn_feedback`（report_id, node_name, verdict, reviewer_note）
- API：`POST /api/feedback`（记录复核）+ `GET /api/feedback/summary`（准确率汇总）
- CLI：`--feedback-summary`（节点准确率柱状图）
- 闭环：人工复核 → bn_feedback 表 → 汇总统计 → 驱动 CPT 校准

### P6.3：多视角切换产品化 ✅
- 新增 `POST /api/v2/review/dual`：同一合同同时生成买方+卖方两份报告
- 返回对比分析：shared_strengths / buyer_unique_strengths / seller_unique_strengths / buyer_unique_concerns / seller_unique_concerns
- 前端可基于 comparison 字段并排展示双视角关键差异

### 测试：58/58 全通过（BN 75节点，API 15路由）（BN 75节点 83边，推理时间 ~277s）

---

## 2026-04-30：v2.5 阶段二（P5 合同类型扩展）

### P5.1 + P5.2：采购合同 + 煤炭合同 BN 节点扩展 ✅
- BN 从 63→75 节点，83 条边
- 新增 7 个采购合同专属节点（原料验收标准、批次结算、能源计价、供货保障、质量检测权、价格调整机制、库存仓储责任）
- 新增 5 个煤炭合同专属节点（热值计价、试烧验收、计量争议解决、单方检验权、运输损耗承担）
- 全部 12 个新节点连接至 4 个风险维度（financial/performance/dispute/clause）
- CPT 标注为 expert_estimated（后续可用采购/煤炭合同数据集校准）
- `bn_mapping.py`：新增 50+ CLAUSE_TYPE_HINTS 中文映射（原料验收→raw_material_acceptance_std 等）
- LLM₁ 检查清单自动生效（`_build_bn_checklist()` 动态读取 BN 配置）

### P6.2（前置）：BN 节点自动发现系统 ✅
- 新增 `bn/node_discovery.py`：`record_gap()` + `discover_pending_nodes()` + `approve_node()` + `reject_node()`
- `bn_mapping.py`：管线中未映射 clause_type 自动记录到 `config/pending_nodes.json`
- CLI：`--discover-nodes`（查看）、`--approve-node X`（审核加入BN）、`--reject-node X`（丢弃）
- 半自动流程：管线自动检测 → 持久化 gap → 开发者审核 → 一键写入 BN 配置
- 自动推断：node_name（蛇形命名）、states（二分/三分）、dimension（关键词匹配）
- CPT 默认均匀分布 + expert_estimated 标注

### P6.1：跨维度联合概率量化 ✅
- `pgmpy_adapter.py`：新增 `query_joint_probability()` + `JointRiskResult` dataclass
- 计算 P(A=high ∩ B=high) 联合概率 + 乘数因子（>1.3=乘数效应，<0.9=负相关）
- `consistency_validator.py`：6对关键维度组合自动分析（财务×争议、履约×法律等）
- `report_writer.py`：LLM₂ prompt 中注入联合概率数据 + 乘数因子表格
- `free_review_schema.py`：ConsistencyReport 新增 `joint_risks` 字段

### P6.2：BN知识图谱学习闭环 ✅
- 新增 `bn/feedback.py`：`save_feedback()` + `get_feedback_summary()` + `get_feedback_for_report()`
- 新增 MySQL 表：`bn_feedback`（report_id, node_name, verdict, reviewer_note）
- API：`POST /api/feedback`（记录复核）+ `GET /api/feedback/summary`（准确率汇总）
- CLI：`--feedback-summary`（节点准确率柱状图）
- 闭环：人工复核 → bn_feedback 表 → 汇总统计 → 驱动 CPT 校准

### P6.3：多视角切换产品化 ✅
- 新增 `POST /api/v2/review/dual`：同一合同同时生成买方+卖方两份报告
- 返回对比分析：shared_strengths / buyer_unique_strengths / seller_unique_strengths / buyer_unique_concerns / seller_unique_concerns
- 前端可基于 comparison 字段并排展示双视角关键差异

### 测试：58/58 全通过（BN 75节点，API 15路由）

---

## 2026-04-30：LLM₂ Prompt 精简 + 卖方安全护栏

### 问题
Report-9（卖方）法律分析质量退步（DeepSeek 78→46）。
根因：system prompt 从 ~60 行膨胀到 ~120 行，LLM₂ 注意力被格式要求占据。

### 修复
- **Prompt 精简**：120行→40行（-67%），格式要求从 system prompt 移到 BN 数据注入区
- **卖方专项安全规则**（仅 seller 注入）：责任上限铁律（先排除间接损失再设上限）、
  不标客观风险为"有利"（民法典622条）、违约金对等性陷阱警告
- BN 数据内联格式提示：推导链、联合概率、数据优先级

### 测试：58/58 全通过（BN 75节点，API 15路由）

---

## v2.6 规划（2026-04-30 讨论确定，待执行）

基于 report-10 独立评估（89/100）+ DeepSeek 反馈，识别到的新优化方向：
- P0: 数字规则→推理规则（去掉无法律依据的具体数字）
- P1: 让步梯度规则（修改建议必须含开盘立场+可接受底线）
- P2: 战略层推理框架（可选开关，筹码识别+交换方案）
- P3: BN反事实诊断+门禁升级（致命风险覆盖检查）
- P4: 企业红线推理框架（损失×不可逆×触发概率）
- P5: 民法典合同编精选集（30-50条，config/civil_code_reference.md）
- P6: 联合概率场景化解读强制

### 执行记录（2026-04-30）

**P0/P1/P6/P5 已完成 ✅**

- P0：`report_writer.py` 中"合同总价100%"改为"具体比例由你结合合同金额、行业惯例和标的物属性判断"；新增"法律引用规范"章节
- P1：新增"让步梯度规则"——削弱对方权利时必须给开盘立场+可接受底线两个版本
- P6：联合概率要求改为"不只是展示数字，用一句话描述商业场景"
- P5：新建 `config/civil_code_reference.md`（30条精选，覆盖合同订立/效力/履行/违约/买卖/解除/争议解决）

### 执行记录（2026-04-30 第二批）

**P3/P4/P2 已完成 ✅**

- P3：门禁升级（致命风险BN覆盖率检查）+ 卖方自动说明（反事实天然较少）
- P4：新增"企业红线"三维推理框架（损失×不可逆×触发概率）
- P2：战略层可选开关（`strategy_mode=true`），新增第八章"谈判筹码与策略建议"

### 测试：58/58 全通过

---

## 2026-04-30：全版本纵向对比 + WORKLIST重构

完成了全部10份报告版本（初版→report-8）的纵向对比分析，识别出核心问题：**BN反事实产出稳定性是项目最大技术债务**（同一合同G报告8项→H报告0项）。

WORKLIST.md 全面重构：
- 旧 v2.4/v2.3+ 工作项经评估后吸收或降级
- 新优先级链：P0(BN稳定性) → P1(推导链可视化) → P2(质量门禁) → P3(历史管理) → P4(产品化) → P5(合同类型扩展) → P6(高级特性)
- v2.3（立场锚定+安全护栏）确认必要且已完成

**产出：** 新版 WORKLIST.md（6大优先级，从引擎稳定到产品化）

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

## 2026-05-03：合同类型分层路由方案确定（待实施）

### 背景
基于对当前项目代码、工作清单、销售合同原件、report-9/10/11 以及既有“合同类型智能路由与公司红线方案”的综合评估，确认：
- “按合同类型提取 BN 节点子集”方向值得做；
- 但不能做成“关键词命中后仅保留固定 20 节点”的硬裁剪；
- 当前项目更需要的是“降噪但不漏检”的分层路由，以及“企业红线配置化”的规则层。

### 结论
确定采用以下路线：
1. **通用核心节点始终保留**：付款、交付、验收、解除/终止、责任上限、争议解决、适用法律、不可抗力等不参与裁剪。
2. **合同类型节点包叠加**：销售/采购/煤炭等各自追加高相关节点，提升 LLM₁ 聚焦度。
3. **正文触发补集**：若正文出现“热值/收到基/保密信息/调价公式”等强信号，则补回对应节点，避免混合型合同漏检。
4. **低置信度回退**：类型识别不稳时回退到扩展清单或全量清单，保证“宁可多看，不可漏看”。
5. **公司红线配置化**：从 prompt 内联规则升级为 `hard_rules + reasoning_hints` 两层结构，避免把大量商业数字写死成规则。

### 产出
- 新增方案文档：`方向/合同类型分层路由与BN节点子集提取方案.md`
- `WORKLIST.md` 新增 **v2.8：合同类型分层路由 + 公司红线配置化** 路线说明和执行顺序

### 为什么这样定
- 当前 `ai_review.py` 的 `_build_bn_checklist()` 直接展开全部 evidence-layer 节点，确实存在噪音偏高问题；
- 但 report-11 暴露的更大问题不是“节点不够少”，而是“建议过满、主次不够聚焦、企业底线未独立建模”；
- 因此 v2.8 的定位应是：**在不牺牲覆盖率的前提下，提高 LLM₁ 审查聚焦度，并为企业级规则化输出铺路。**

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

---

## v2.9：开源化提升（2026-05-06 规划，待执行）

基于项目多维度量化评估（开源评分 63/100）制定。核心目标：降低"让别人跑起来"的门槛。

### 目标

开源评分从 63 → 75+。预计工期 5-7 天。

### 依赖关系

```
P0-1（.env.example + Demo）──→ P0-2（Docker Compose）──→ P0-3（拆分 main.py）
                                                              │
                                                              └──→ P0-6（CI）

P0-4（HINTS 配置化）──→ 独立并行
P0-5（英文 README）──→ 独立并行
P0-7（社区文件）─────→ 独立并行
```

### 执行任务清单

| 序号 | 任务 | 工期 | 依赖 | 说明 |
|------|------|:--:|------|------|
| P0-1 | `.env.example` + Demo 模式 | 1天 | 无 | ✅ 2026-05-06 | 模板配置 + 无 API Key demo |
| P0-2 | Docker Compose 一键启动 | 2-3天 | P0-1 | ✅ 2026-05-07 | mysql + backend + frontend 三服务编排 |
| P0-3 | 拆分 `backend/main.py` | 1天 | P0-2 | ✅ 2026-05-07 | 739行→41行main + 8 router文件 |
| P0-4 | `CLAUSE_TYPE_HINTS` 配置化 | 1天 | 无 | ✅ 2026-05-06 | 170行硬编码→YAML |
| P0-5 | 英文 README | 0.5天 | 无 | ✅ 2026-05-06 | Quick Start + 架构说明 |
| P0-6 | GitHub Actions CI | 0.5天 | P0-2 | ✅ 2026-05-07 | test + lint workflow |
| P0-7 | 社区基础文件 | 0.5天 | 无 | ✅ 2026-05-06 | CONTRIBUTING + Issue/PR 模板 |

### 执行记录

**P0-1/P0-4/P0-5/P0-7 已完成（2026-05-06）** ✅
- `.env.example`：模板配置 + DEMO_MODE 注释
- `/api/demo`：预计算 demo 响应，无需 API Key 即可展示系统输出
- `CLAUSE_TYPE_HINTS` 配置化：170 行硬编码 → `config/clause_type_mapping.yaml`
- 英文 README Quick Start + 架构说明
- 社区文件：CONTRIBUTING.md / CODE_OF_CONDUCT.md / Issue/PR 模板
- 回归验证：`test_bn_mapping.py` 保证映射变更不破坏报告质量

**P0-2 Docker Compose 一键启动（2026-05-07）** ✅
- 新建 6 个文件：
  - `backend/Dockerfile`：python:3.11-slim + `pip install .` + uvicorn 9527
  - `frontend/Dockerfile`：多阶段构建（node:20-alpine build → nginx:1.27-alpine serve）
  - `frontend/nginx.conf`：`/api/` 反向代理到 backend:9527，SPA fallback
  - `docker/mysql/init.sql`：6 张表（contracts/reports/report_risks/report_counterfactuals/company_redlines/bn_feedback），含索引和外键
  - `docker-compose.yml`：mysql(8.4) + backend + frontend 三服务编排，健康检查 + 数据卷持久化
  - `tests/docker/test_docker_stack.py`：5 个测试覆盖 Dockerfile/nginx/compose/SQL 结构
- **设计决策**：前端不改 fetch 路径，用 Nginx 反向代理 `/api/` → backend:9527，避免触碰报告主链路
- **数据库**：schema 直接从 `repository.py`/`feedback.py` 代码推导，非旧文档复制

**P0-6 GitHub Actions CI（2026-05-07）** ✅
- 新建 `.github/workflows/ci.yml`：push/PR 到 main 时自动运行 pytest
- Python 3.11 + `pip install .[test]` + `pytest tests/ -q`
- 超时 15 分钟，与 BN 推理时间（~5min）匹配
- 新增 `tests/docker/test_ci_workflow.py` 结构校验

**P0-3 拆分 backend/main.py（2026-05-07）** ✅
- `backend/main.py`：739 行 → 41 行（仅保留 app 创建 + CORS + 9 行 router 注册）
- 新建 `backend/__init__.py`：自动注入 `src/` 到 sys.path，所有子模块共享
- 新建 `backend/routers/` 目录，8 个功能域文件：

| 文件 | 行数 | 路由 |
|------|-----|------|
| `misc.py` | 141 | /favicon.ico, /api/health, /api/demo |
| `upload.py` | 43 | /api/upload |
| `sandbox.py` | 57 | /api/bn/nodes, /api/bn/simulate |
| `review.py` | 262 | /api/review, /api/v2/review + _run_v1_pipeline, _run_v2_pipeline, _score_to_level |
| `dual.py` | 63 | /api/v2/review/dual |
| `export.py` | 37 | /api/export/pdf, /api/export/md |
| `history.py` | 56 | /api/reports, /api/reports/{id}, /api/reports/diff |
| `redlines.py` | 68 | /api/redlines CRUD (4 routes) |
| `feedback.py` | 41 | /api/feedback, /api/feedback/summary |

- 所有 20 个 API 端点行为完全不变，import 路径无变更
- 更新 `tests/web/test_backend_main_demo.py` 适配新 import 路径
- **设计决策**：`_run_v1_pipeline`/`_run_v2_pipeline` 放在 `review.py`（仅 review 路由调用）；dual 端点独立文件（不经过管道函数）；每个 router 自包含所需 import

### 预期效果

| 维度 | 当前 | 预期 | 提升 |
|------|:---:|:---:|:---:|
| 上手体验 | 10/20 | 14/20 | +4（Docker + .env.example） |
| 代码可读性 | 16/20 | 17/20 | +1（拆分 main.py + HINTS 配置化） |
| 可扩展性 | 8/15 | 10/15 | +2（HINTS 配置化） |
| 社区就绪度 | 2/10 | 7/10 | +5（CI + 社区文件 + 英文 README） |
| **加权总分** | **63** | **~76** | **+13** |

---

## 2026-05-08：Phase A 回归分析 — 报告-6 vs 报告-7 对比评估

### 背景
Phase A（LLM₂ 降级为受约束渲染器 + Dossier + canonicalization + adjudication）实施后，
生成了报告-7。与 Phase A 前的报告-6（warning 模式下生成）进行对比，评估 Phase A 的实际效果。

### 评估方法
- 独立分析（六维度加权评分），形成自己的结论后再参考 DeepSeek 评价
- 评分框架与 DeepSeek 一致：风险识别(25%) + 分析深度(20%) + 建议价值(20%) + 策略有效性(20%) + 结构逻辑(10%) + 有利条款保护(5%)

### 独立评分结果

| 报告 | 风险识别 | 分析深度 | 建议价值 | 策略有效性 | 结构逻辑 | 亮点保护 | **总分** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 报告-6 (Phase A 前) | 7.5 | 9.0 | 9.0 | 9.3 | 9.0 | 9.5 | **8.71** |
| 报告-7 (Phase A 后) | 7.0 | 7.5 | 5.0 | 6.5 | 8.5 | 6.0 | **6.70** |

### DeepSeek 评分对比

| 报告 | 独立评分 | DeepSeek 评分 | 差异 |
|:---|:---:|:---:|:---|
| 报告-6 | 8.71 | 未评分 | — |
| 报告-7 | 6.70 | 8.15 | -1.45（我更低） |

DeepSeek 与我完全一致地指出报告-7 的核心问题：**对「责任上限」条款的战略价值判断出现根本性偏差**。
分歧在于严重程度——DeepSeek 给了 8.15（排名 5/7），我认为这个错误是致命级的（30% 责任上限的建议如果被客户采纳会导致灾难性后果）。

### 核心发现：Phase A 的约束机制放大了上游错误

**报告-6（Phase A 前）：** LLM₂ 有「最终判断权」，可以将 LLM₁ 误标的「责任上限缺失=风险」重新框定为「响应筹码」。
**报告-7（Phase A 后）：** LLM₂ 被禁止改判，Dossier 锁定上游错误分类，LLM₂ 只能照本宣科。

具体退化点：
1. **责任上限判断**：报告-6 正确识别为买方优势/响应筹码 → 报告-7 错误定性为 🟠高/P1 风险、建议设 30% 上限
2. **预付款严重度**：报告-6 标 🔴致命 → 报告-7 降为 🟠高
3. **BN 基线漂移**：财务暴露 P(high) 28.4%→55.4%，条款失衡 31.4%→45.6%，整体 26.8%→39.9%
4. **内部矛盾**：报告-7 第 5 章称责任上限为「响应筹码/等鱼上钩」，第 6 章却列为「可签署的必须条件」

### 根因

Phase A 的设计假设是「上游（LLM₁→canonicalize→adjudicate→BN）产出的事实是正确的，只需约束 LLM₂ 不乱改」。
但实际上，**当前 Adjudication 层缺少立场感知的商业判断能力**——它无法区分「真正的风险」和「对当前立场有利的条款」。
当上游产出错误事实时，约束机制会把这些错误锁死在最终报告中。

### P0-P1 实施完成（2026-05-08）

所有 P0+P1 任务已完成：

| 任务 | 内容 | 状态 |
|:---|:---|:--:|
| P0-1 | Adjudication 层立场感知规则 | ✅ |
| P0-2 | 修复 30% 责任上限危险建议 | ✅ |
| P0-3 | Dossier 构建时检测内部矛盾 | ✅ |
| P1-1 | Dossier 增加有利条款标记字段 | ✅ |
| P1-2 | LLM₂ 增加纠错上报机制 | ✅ |
| P1-3 | 完整立场感知商业判断规则（8 条款双向覆盖） | ✅ |

**新增文件（1个）：**
- `config/party_aware_rules.yaml`

**改造文件（4个）：**
- `src/contract_risk_analysis/review/adjudicate.py`：`_apply_party_aware_rules()` + review_party 参数
- `src/contract_risk_analysis/review/report_writer.py`：C-1 保护 positive 项 + 内部矛盾检测 + favorable_terms 提取 + 渲染器备注机制 + 责任上限底线强化
- `src/contract_risk_analysis/domain/free_review_schema.py`：`FavorableTerm` dataclass + `ReportDossier.favorable_terms`
- `config/company_redlines.yaml`：责任上限规则拆分为买方/卖方独立规则
- `backend/routers/review.py`：adjudicate() 传入 review_party

**测试：18/18 通过（非 BN），0 failed**

### P2 实施完成（2026-05-08）

| 任务 | 内容 | 状态 |
|:---|:---|:--:|
| P2-1 | 以报告-2（DeepSeek 9.49 分）为标杆编码博弈模式 | ✅ |
| P2-2 | 建立「已知正确判断」回归测试集（11 个测试） | ✅ |

**P2-1 改动：**
- `src/contract_risk_analysis/review/report_writer.py`：LLM₂ prompt 第五章（筹码策略）增强
  - 筹码识别增加"必须预判对方攻击话术"要求（带示例）
  - 三层防御增加"必须指明交换目标的具体条款和数字"
  - 让步阶梯增加"每一步退让附带交换要求"
  - 跨筹码联动规则（不得单向让步、交换比率必须明确）
  - 策略结论与签署建议一致性检查

**P2-2 改动：**
- `tests/regression/__init__.py`（新文件）
- `tests/regression/test_judgment_regression.py`（新文件，11 个测试）：
  - `TestPartyAwareRulesBuyer`（4 tests）：liability_cap→positive, jurisdiction→favorable, termination→favorable, unknown type pass-through
  - `TestPartyAwareRulesSeller`（1 test）：liability_cap seller stays critical
  - `TestLiabilityCapFloor`（2 tests）：100% floor rule exists, unlimited rule seller-only
  - `TestInternalConsistency`（2 tests）：favorable terms not in signing conditions, positive→favorable_terms extraction
  - `TestPartyAwareConfigIntegrity`（2 tests）：all 6 buyer rules + 8 seller rules present with action/note fields

### 最终测试统计
- **87 passed**（76 原有 + 11 新增回归测试），**5 skipped**，**0 failed**

### v2.11 P0-P2 全部完成总结

| 阶段 | 任务数 | 新增文件 | 改造文件 |
|:---|:---:|:---|:---|
| P0 | 3 | `config/party_aware_rules.yaml` | `adjudicate.py`, `report_writer.py`, `company_redlines.yaml`, `backend/routers/review.py` |
| P1 | 3 | — | `free_review_schema.py`, `report_writer.py`, `adjudicate.py`, `party_aware_rules.yaml` |
| P2 | 2 | `tests/regression/test_judgment_regression.py` | `report_writer.py` |

核心成果：裁决层现在能区分「真正的风险」和「对当前立场有利的条款」，
防止了报告-7 那种把买方核心优势当成风险来修的致命错误。
