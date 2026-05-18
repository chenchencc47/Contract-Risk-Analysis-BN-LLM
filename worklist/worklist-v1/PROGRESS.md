# 实施进度记录

> 最后更新：2026-05-13（报告稳定性与泛化能力优化首批实现完成）

---

## 2026-05-13：报告稳定性与泛化能力优化首批实现完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 去除付款担保结构检测中的样本锚点（不再依赖 `80%` / `1228万`） | `src/contract_risk_analysis/review/adjudicate.py` | ✅ |
| 2 | Golden 分数改为“回归匹配分”语义，并补充说明文案 | `src/contract_risk_analysis/evaluation/golden_score.py` `frontend/src/components/RiskReport.tsx` `frontend/src/types/index.ts` | ✅ |
| 3 | API 返回运行态元数据（生成时间、后端启动时间、模式、是否启用回归评分） | `backend/routers/review.py` `frontend/src/types/index.ts` | ✅ |
| 4 | 新增客户版成品 lint：内部编号、占位符、无来源数字 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | 回归/评分/渲染测试补强 | `tests/regression/test_judgment_regression.py` `tests/evaluation/test_golden_score.py` | ✅ |
| 6 | 前端展示运行态元数据并完成端到端构建验证 | `frontend/src/components/RiskReport.tsx` `frontend/src/types/index.ts` | ✅ |

### 关键结果

- **生产检测更泛化**：付款担保倒挂检测已改为结构信号驱动，不再绑定当前买卖合同样本数字。
- **评分语义更准确**：前端徽章从 `Golden XX分` 调整为 `回归 XX分`，tooltip 明确“不是任何合同都通用的质量总分”。
- **运行态更可观测**：报告页现在直接显示生成时间，tooltip 可看到后端启动时间、生成模式和是否启用回归评分，便于排查热修改/重启差异。
- **客户版更干净**：预渲染一致性检查现在会拦截 `ISSUE-xxxx`、`【X】/TODO/TBD`、以及“诉讼成本约20-50万/成功回收率低于60%”这类无来源数字。
- **前端类型更贴近真实返回**：`ReviewResponse` 已补齐 `review_party`、扁平化报告字段、`runtime_metadata` 和 `debug.routing`，前端构建通过。

### 测试结果

- `tests/regression/test_judgment_regression.py`：44 passed
- `tests/evaluation/test_golden_score.py`：13 passed
- `tests/review/test_report_writer_negotiation_chip.py`：4 passed
- 聚焦 Python 测试集：61 passed
- `frontend`：`npm run build` 通过

---

## 2026-05-13：报告稳定性与泛化能力优化方案 spec 完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 报告稳定性与泛化能力优化方案 spec | `docs/superpowers/specs/2026-05-13-report-stability-and-generalization-design.md` | ✅ |
| 2 | 明确 golden case / golden pattern / production rule 边界 | 同上 | ✅ |
| 3 | 明确禁止把个案底线、具体数字、个案结论硬编码进生产规则 | 同上 | ✅ |
| 4 | 给出分层收口的渐进式稳定化路线（规则层/评分层/生成层/lint层/运行态可观测性） | 同上 | ✅ |
| 5 | 单列 `contract-review-买卖合同-13.md` 个案修复附录，并明确不产品化 | 同上 | ✅ |

### 方案要点

- **主体只写可产品化优化**：去样本锚点、重定义 Golden 分数语义、降低正式报告随机性、增加成品级 lint。
- **附录单列个案修复**：`-13` 的预付款底线冲突、风险转移放松、管辖事实互撞、无来源数字、内部编号污染客户版，只修当前报告，不沉淀为生产规则。
- **强调运行态区分**：区分“同代码仓库”和“同运行态”，避免把热修改未重启误判为模型质量退步。

---

## 2026-05-12：v2.16-E LLM-as-judge 脚手架完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 7维度评分框架（总分100分，含评分指引） | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 2 | `build_llm_judge_prompt` 评测 prompt 构造函数 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 3 | 评测 JSON Schema 输出格式定义 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 4 | 测试覆盖（5个新测试） | `tests/evaluation/test_golden_score.py` | ✅ |

### 评分维度

| 维度 | 分值 | 关键约束 |
|------|:--:|------|
| 核心风险识别 | 25 | 是否抓住真正致命问题 |
| 立场正确性 | 20 | 是否正确按买方/卖方立场判断 |
| 原文证据绑定 | 15 | 是否引用准确条款 |
| 修改建议质量 | 15 | 是否可直接落地 |
| 谈判策略质量 | 15 | 是否有筹码意识和退让阶梯 |
| BN使用合理性 | 5 | 是否符合v2.13-C护栏 |
| 表达与结构 | 5 | 是否清晰可读 |

### 设计原则

- **Judge 必须基于 golden case/pattern 标准，不得自行制定评分标准。**
- prompt 已构造完成，但未接入真实 LLM 调用——作为后续增强，不阻塞 MVP。
- 评分 JSON Schema 包含 `total_score`、`dimensions`、`overall_assessment`、`top_issues`、`top_strengths`。

### 测试结果

- `tests/evaluation/test_golden_score.py`：12 passed

---

## 2026-05-12：v2.16-D Production Rules 对齐完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | `PATTERN_PRODUCTION_COVERAGE` 映射表（5个pattern × 生产规则覆盖） | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 2 | `check_pattern_production_alignment` 对齐检查函数 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 3 | `PatternAlignmentReport` 报告数据模型 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 4 | 测试覆盖（3个新测试） | `tests/evaluation/test_golden_score.py` | ✅ |

### 对齐结果

| Pattern | party_aware_rules | adjudication | BN interpretation |
|---------|:--:|:--:|:--:|
| high_prepayment_without_security | ✅ payment_structure | ✅ structural detection | — |
| deposit_after_prepayment_inversion | ✅ payment_security_structure | ✅ structural detection | — |
| liability_cap_by_party_stance | ✅ liability_cap | — | ✅ defensive_chip_only |
| jurisdiction_by_party_stance | ✅ jurisdiction | — | ✅ defensive_chip_only |
| early_risk_transfer_before_final_acceptance | ✅ risk_transfer | — | — |

**5/5 patterns aligned to production rules。** 每个 pattern 至少在两层有覆盖。

### 测试结果

- `tests/evaluation/test_golden_score.py`：12 passed（4 原有 + 8 新增 v2.16-D/E）

---

## 2026-05-12：v2.15 前端接入 + v2.16 前端接入 + 渲染器备注强化 + CSS 优化

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 后端 API 自动生成修订清单 + BN附录，返回给前端 | `backend/routers/review.py` | ✅ |
| 2 | 后端 API 自动对报告进行 Golden Case 评分 | `backend/routers/review.py` | ✅ |
| 3 | `auto_score_report_text` 函数 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 4 | 前端新增「审查报告/修订清单/BN附录」格式切换标签 | `frontend/src/components/RiskReport.tsx` | ✅ |
| 5 | 前端显示 Golden Score 评分徽章 | `frontend/src/components/RiskReport.tsx` | ✅ |
| 6 | 前端 Markdown 排版优化（h1-h4 标题层级、表格、引用块样式） | `frontend/src/components/RiskReport.tsx` | ✅ |
| 7 | 渲染器备注强制执行（system prompt + user prompt 双重强化） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 8 | 前端类型定义更新 | `frontend/src/types/index.ts` | ✅ |

### 用户可见变化

1. **审查报告页新增格式标签**：📄审查报告 / 📋修订清单 / 🔬BN附录，点击即可切换
2. **Golden Score 评分徽章**：报告生成后自动与 golden case 比对，显示 🏅 Golden XX分
3. **Markdown 排版优化**：h1 有底部双线分隔、h2 有底部分隔线、表格表头加粗、引用块有背景色
4. **渲染器备注**：prompt 强制要求每份报告末尾必须包含「渲染器备注」章节

### Report-11 Golden Score 实测

- 买卖合同 golden case `sales_purchase_contract_001`：**96.9 分**
- must_find: 5/5 ✅（80%预付款、质保金倒挂、初验即交付、交付地点不精确、保修期起算）
- must_not: 4/4 ✅（无误判无责任上限、无误判BN反事实、无编造数字、无误判间接损失）
- should_find_advantages: 4/5（发票前置付款条件未识别）

### 测试结果

- `tests/regression/` + `tests/evaluation/` + `tests/review/`：56 passed

---

## 2026-05-12：v2.15 多形态报告输出完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | `MultiFormatReports` 数据模型 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 2 | v2.15-A 管理层摘要版（LLM prompt ~4K tokens） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | v2.15-B 法务审查详版（复用现有 `generate_combined_report`） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | v2.15-C 谈判作战手册（LLM prompt ~8K tokens） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | v2.15-D 合同修订清单（确定性生成，无需LLM） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 6 | v2.15-E BN/方法论附录（确定性生成，无需LLM） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 7 | `generate_multi_format_reports` 统一入口 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 8 | 回归测试（8个新测试） | `tests/regression/test_judgment_regression.py` | ✅ |

### 五种输出形态

| 格式 | 受众 | 生成方式 | 长度控制 |
|------|------|---------|---------|
| 管理层摘要 (A) | 管理层决策者 | LLM prompt | 1-2页（~500-800字） |
| 法务审查详版 (B) | 法务团队 | 复用现有 combined report | 完整8章 |
| 谈判作战手册 (C) | 业务/谈判团队 | LLM prompt | 6章：筹码总览→对手预判→防御策略→退让阶梯→交换方案→路线图 |
| 合同修订清单 (D) | 合同起草团队 | 确定性（从Dossier提取） | 按优先级排列，含原文+建议 |
| BN附录 (E) | 技术/审计团队 | 确定性（从Counterfactuals提取） | 方法论+反事实详情+局限+冲突 |

### 设计原则

- **同一Dossier，多版本输出**：所有格式共享同一个冻结的 ReportDossier
- **DDD 按需生成**：`generate_multi_format_reports` 的各 `include_*` 参数控制生成哪些格式
- **确定性格式无需LLM**：修订清单和BN附录直接从结构化数据生成，零API调用
- **LLM格式受约束**：管理层摘要和谈判手册仍通过LLM生成，但严格遵守Dossier约束

### 测试结果

- `tests/regression/test_judgment_regression.py`：40 passed（32 + 8 新增 v2.15）
- `tests/regression/` + `tests/evaluation/` + `tests/review/`：48 passed

---

## 2026-05-12：v2.14 质保金倒挂与付款担保结构检测完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | `_detect_payment_security_inversion` 结构性风险检测函数 | `src/contract_risk_analysis/review/adjudicate.py` | ✅ |
| 2 | 集成到 `adjudicate()` 管线（Step 4） | `src/contract_risk_analysis/review/adjudicate.py` | ✅ |
| 3 | buyer/seller 双视角 `payment_security_structure` 裁决规则 | `config/party_aware_rules.yaml` | ✅ |
| 4 | 回归测试（5个新测试） | `tests/regression/test_judgment_regression.py` | ✅ |

### 结构性检测逻辑

当 LLM₁ 输出的风险项同时命中以下条件时，触发「付款担保结构倒挂」检测：

1. **高额预付款**：`payment_structure` 类型风险项中检出「预付款/预付/80%/高比例」等信号
2. **保证金后置**：任何风险项中检出「质保金/保证金/质量保证金」且提交节点晚于预付款

触发后：
- 如已有描述结构性问题的风险项 → 增强其严重度至 critical/high、优先级至 P1
- 如无 → 新建 `payment_security_structure` 类型风险项（severity=critical, priority=P1）

卖方视角下不触发此检测（高预付款对卖方是优势）。

### 测试结果

- `tests/regression/test_judgment_regression.py`：32 passed（原 27 + 新增 5）
- `tests/regression/` + `tests/evaluation/` + `tests/review/`：40 passed

---

## 2026-05-12：v2.13-D 渲染前一致性校验完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | `_run_pre_render_consistency_checks` 函数（5项确定性检查） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 2 | 检查集成到 `generate_combined_report`，违规自动写入 `dossier.internal_conflicts` | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | 回归测试覆盖（4个新测试） | `tests/regression/test_judgment_regression.py` | ✅ |

### 五项渲染前一致性检查

| # | 检查内容 | 说明 |
|---|---------|------|
| 1 | 买方优势不得误入风险项 | `favorable_terms` 中的条款不得同时出现在 `risk_items` 中 |
| 2 | 响应筹码不得列为签署禁止条件 | `响应筹码` 类型的条款如出现在 `signing_forbidden` 中，报告矛盾 |
| 3 | BN防守筹码 vs 签署条件冲突 | `defensive_chip_only` 的反事实条款如出现在签署条件中，护栏被违反 |
| 4 | 筹码-签署对齐 | 防守型筹码（底线/响应）如被列为签署修改条件，定位矛盾 |
| 5 | 有利条款角色一致性 | `favorable_terms` 中的条款 `negotiation_role` 不得为 `must_fix` |

违规信息在 LLM prompt 构建前注入 `dossier.internal_conflicts`，LLM₂ 在报告的「⚠️ 内部一致性警告」章节中看到，无法跳过。

### 测试结果

- `tests/regression/test_judgment_regression.py`：27 passed（原23 + 新增4）
- `tests/regression/` + `tests/evaluation/` + `tests/review/`：35 passed

---

## 2026-05-12：v2.13-C BN 反事实解释护栏完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | CounterfactualResult 增加 `report_usage` 字段 | `src/contract_risk_analysis/domain/free_review_schema.py` | ✅ |
| 2 | BN 解释规则字典（6个高风险变量，买方/卖方双视角） | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | `_counterfactual_takeaway` 按 report_usage 分类生成谈判解读 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | Dossier BN反事实表格增加「数据使用层级」列和护栏提醒 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | LLM₂ system prompt 增加「BN数据不得推翻法务裁决层」规则 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 6 | LLM₂ user prompt BN数据使用规则改为层级护栏+自检清单 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 7 | 回归测试覆盖（10个新测试） | `tests/regression/test_judgment_regression.py` | ✅ |

### 护栏效果

- `liability_cap` / `liability_cap_strength` / `damages_exposure` / `jurisdiction_fairness` 在买方视角下全部标注为「🟡 仅防守筹码说明」，LLM₂ prompt 明确禁止写成主动修改建议。
- `termination_right_balance` / `termination_clause_completeness` 标注为「🔴 仅人工复核备注」。
- `_counterfactual_takeaway` 对防守筹码输出「此为筹码价值说明，**不是主动修改建议**」，对人工复核输出「建议人工复核后再决定谈判策略」。
- Dossier 反事实表格新增「数据使用层级」列，LLM₂ 在撰写前就能看到每条数据的用途限制。
- LLM₂ system prompt 和 user prompt 均加入护栏自检清单和「BN不得推翻法务裁决」的层级规则。

### 测试结果

- `tests/regression/test_judgment_regression.py`：23 passed（13 原有 + 10 新增 BN 护栏）
- `tests/regression/` + `tests/evaluation/` + `tests/review/`：31 passed

---

## 2026-05-12：v2.13-B Dossier 法律方向字段完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | DossierRiskItem 增加 `affected_party` / `review_stance` / `legal_direction` / `negotiation_role` | `src/contract_risk_analysis/domain/free_review_schema.py` | ✅ |
| 2 | FavorableTerm 增加同组法律方向字段 | `src/contract_risk_analysis/domain/free_review_schema.py` | ✅ |
| 3 | Dossier 构造层确定性派生法律方向字段 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | Dossier prompt 展示法律方向和谈判角色 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | Dossier 字段与渲染测试 | `tests/review/test_report_writer_negotiation_chip.py` | ✅ |

### 稳定化效果

- 风险项现在能在 Dossier 中明确表达对当前审查立场 `favorable` / `unfavorable` / `neutral` / `mixed`。
- 渲染层可直接读取 `negotiation_role`，避免自行把优势条款误写成主动修改项。
- 有利条款在 `favorable_terms` 中保留法律方向字段，继续与风险项分离。

### 测试结果

- `tests/review/test_report_writer_negotiation_chip.py` + `tests/regression/test_judgment_regression.py`：17 passed
- `tests/review/test_report_writer_negotiation_chip.py` + `tests/regression/test_judgment_regression.py` + `tests/evaluation/test_golden_score.py` + `tests/cli/test_main.py`：29 passed, 1 warning

---

## 2026-05-12：v2.13-A 立场感知裁决规则补强完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 买方高额预付款/付款早于交付验收裁决规则 | `config/party_aware_rules.yaml` | ✅ |
| 2 | 买方最终验收前风险转移裁决规则 | `config/party_aware_rules.yaml` | ✅ |
| 3 | 卖方风险提前转移优势裁决规则 | `config/party_aware_rules.yaml` | ✅ |
| 4 | 回归测试补强 | `tests/regression/test_judgment_regression.py` | ✅ |

### 稳定化效果

- 买方视角下，高额预付款或付款早于实质交付/最终验收会稳定标记为 `buyer_unfavorable` 和底线筹码。
- 买方视角下，初验、到货或交付承运人即风险转移会稳定标记为 `buyer_unfavorable` 和底线筹码。
- 卖方视角下，风险提前转移给买方会稳定识别为卖方优势/底线筹码。
- 未命中的自定义 canonical type 保持不受 party-aware 规则影响。

### 测试结果

- `tests/regression/test_judgment_regression.py`：13 passed
- `tests/regression/test_judgment_regression.py` + `tests/evaluation/test_golden_score.py` + `tests/cli/test_main.py`：25 passed, 1 warning

---

## 2026-05-12：v2.16-C CLI 使用手册 + 新增真实合同 Golden Cases

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | Golden Case / Golden Pattern CLI 使用手册 | `docs/golden-cli-usage.md` | ✅ |
| 2 | 租赁合同真实样本 golden case | `tests/fixtures/golden_cases/lease_contract_001.yaml` | ✅ |
| 3 | 技术开发合同真实样本 golden case | `tests/fixtures/golden_cases/technology_development_contract_001.yaml` | ✅ |
| 4 | UNDP 专家服务合同真实样本 golden case | `tests/fixtures/golden_cases/service_contract_001.yaml` | ✅ |
| 5 | 保密协议真实样本 golden case | `tests/fixtures/golden_cases/nda_contract_001.yaml` | ✅ |

### 沉淀重点

- 租赁合同：付款与履约保证金顺序倒挂、任意解除权法律脆弱性、违约金双重处罚、疑似关联方交易背景、无责任上限双刃剑。
- 技术开发合同：50%高额预付款、免费维护期起算点矛盾、验收流程不清、维护范围不清、发票前置付款优势。
- 服务合同：仲裁条款无效风险、10天终止通知期、背景/前景知识产权边界、尾款主观验收、任务书交付标准不完整。
- 保密协议：无上限赔偿与间接损失暴露、披露方单方终止权、北京仲裁与英文优先、保密例外举证责任。

### 测试结果

- `tests/evaluation/test_golden_score.py` + `tests/cli/test_main.py`：12 passed, 1 warning

---

## 2026-05-12：v2.16-B CLI 评分入口完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 单个 golden case 报告评分 CLI | `src/contract_risk_analysis/cli.py` | ✅ |
| 2 | golden patterns 列表 CLI | `src/contract_risk_analysis/cli.py` | ✅ |
| 3 | CLI 测试覆盖 | `tests/cli/test_main.py` | ✅ |

### 新增命令

```bash
python -m contract_risk_analysis.cli \
  --score-golden-case tests/fixtures/golden_cases/sales_purchase_contract_001.yaml \
  --report 合同检测报告/买卖合同/contract-review-买卖合同-10.md
```

输出该报告相对指定 golden case 的 JSON 评分，包括 `must_find`、`must_not`、`should_find_advantages` 命中情况。

```bash
python -m contract_risk_analysis.cli --list-golden-patterns
```

输出当前已沉淀的 golden pattern 元数据。

### 测试结果

- `tests/cli/test_main.py` + `tests/evaluation/test_golden_score.py`：12 passed, 1 warning

### 用户协作偏好

已记录：完成已有任务时只更新 `worklist/PROGRESS.md`；只有新增任务或修改任务定义时才更新 `worklist/WORKLIST.md`。

---

## 2026-05-12：v2.16-B 基础规则评分器完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | golden case 评分器 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 2 | golden pattern 元数据汇总 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 3 | 最小测试覆盖 | `tests/evaluation/test_golden_score.py` | ✅ |
| 4 | worklist 更新 | `worklist/WORKLIST.md` | ✅ |

### 能力范围

- 读取 `tests/fixtures/golden_cases/*.yaml`；
- 检查 `must_find` 是否命中关键词；
- 检查 `must_not` 是否触犯禁止模式；
- 检查 `should_find_advantages` 是否命中；
- 输出基础分、命中项、缺失项和违规项；
- 汇总 `tests/fixtures/golden_patterns/*.yaml` 元数据。

### 测试结果

- `tests/evaluation/test_golden_score.py`：4 passed
- `tests/evaluation/test_golden_score.py` + `tests/regression/test_judgment_regression.py`：15 passed

### 后续增强

1. 增加 CLI 调用入口；
2. 支持对真实报告文件批量评分；
3. 增加 golden pattern 条件命中评分，而不只是元数据汇总；
4. 将成熟 pattern 对齐到 production rules。

---

## 2026-05-12：Golden Patterns 首批沉淀完成

### 完成内容

新建目录：`tests/fixtures/golden_patterns/`

| # | Pattern | 文件 | 状态 |
|---|---------|------|:--:|
| 1 | 高额预付款且无有效担保 | `high_prepayment_without_security.yaml` | ✅ |
| 2 | 付款担保或质保金提交节点倒挂 | `deposit_after_prepayment_inversion.yaml` | ✅ |
| 3 | 责任上限按审查立场判断 | `liability_cap_by_party_stance.yaml` | ✅ |
| 4 | 管辖地按审查立场判断 | `jurisdiction_by_party_stance.yaml` | ✅ |
| 5 | 最终验收前风险过早转移 | `early_risk_transfer_before_final_acceptance.yaml` | ✅ |

### 设计原则

- Pattern 是“可泛化候选规则”，不是直接替代真实审查逻辑；
- 每个 pattern 都包含适用合同类型、审查立场、触发条件、买方/卖方不同期待、禁止误判、证据信号和晋升 production rule 的条件；
- 成熟 pattern 后续再对齐到 `party_aware_rules.yaml`、Dossier 裁决层或 BN 解释层。

### 下一步

实现规则评分器：

1. golden case 回归评分：检查固定样本是否退步；
2. golden pattern 命中评分：检查新报告是否在满足模式条件时给出正确方向；
3. 输出缺失项、违规项、可晋升 production rule 候选项。

---

## 2026-05-12：评测体系方向修正 — Golden Case 回归测试 + Golden Pattern 泛化

### 用户确认

用户指出：真实业务中一份合同通常只审查一次，当前反复检查同一份合同是为了测试项目性能。因此，针对具体合同沉淀的 golden case 不应被误用为未来同类合同的业务审查规则。

### 方案修正

已将评测体系调整为三层：

```text
golden case = 固定合同样本的回归测试，检查系统改动后是否退步
golden pattern = 从多个样本中抽象出的可泛化风险模式
production rule / party-aware rule = 真实审查新合同时使用的裁决规则
```

### 已更新文件

| 文件 | 调整 |
|------|------|
| `docs/superpowers/specs/2026-05-12-contract-review-agent-optimization-design.md` | 明确 case / pattern / production rule 边界 |
| `worklist/WORKLIST.md` | v2.16 改为“双层评测体系 MVP” |

### 新的 v2.16 方向

1. `golden_cases`：买卖合同、销售合同等固定样本用于回归评分；
2. `golden_patterns`：高额预付款无担保、付款担保倒挂、责任上限按立场判断等可泛化模式；
3. `production rules`：成熟 pattern 再进入真实审查规则；
4. 新合同只按命中的 pattern / production rule 检查，不套用具体 golden case 的结论。

---

## 2026-05-12：内部评测集起步 — 首批 Golden Cases 沉淀

### 完成内容

| # | 样本 | 文件 | 视角 | 来源 | 状态 |
|---|------|------|------|------|:--:|
| 1 | 买卖合同真实样本 | `tests/fixtures/golden_cases/sales_purchase_contract_001.yaml` | 买方 | 网上真实合同 | ✅ |
| 2 | 瓷砖销售合同样本 | `tests/fixtures/golden_cases/sales_contract_001.yaml` | 卖方 | AI 生成合同 | ✅ |

### 买卖合同沉淀重点

- `must_find`：80%/1228万元预付款无担保、质保金/保证金倒挂、初验即视为交付、交付地点不精确、保修期起算过早。
- `must_not`：买方视角不得把乙方无责任上限/未排除间接损失误判为甲方主动修改风险；不得把 BN 责任上限反事实解释为主动新增责任上限；不得编造概率数字。
- `should_find_advantages`：甲方住所地管辖、无乙方责任上限、未排除间接损失、发票前置付款、外观验收不免除内在质量责任。

### 销售合同沉淀重点

- `must_find`：卖方发货前收取90%货款、质保金受验收合格控制、卖方责任上限缺失、未排除间接损失、解除权/救济不平衡、验收异议模糊、承运人交付后风险转移、乙方所在地管辖。
- `must_not`：卖方视角不得把90%发货前回款简单定性为卖方风险；不得忽略质保金尾款控制、责任暴露和解除权失衡；不得把 AI 生成合同当作真实行业惯例。
- `should_find_advantages`：付款结构、本地管辖、风险前移、质量标准框架、直接损失表述。

### 下一步

实现 v2.16-B 规则评分器，将 YAML 中的 `must_find` / `must_not` / `should_find_advantages` 转换为自动评分报告。

---

## 2026-05-12：上传体验修复 — 暂停旧版 .doc 支持

### 问题

前端上传旧版 Word `.doc` 文件后，后端返回 `422 Unprocessable Entity`。

### 根因

后端入口允许 `.doc`，但解析器实际使用 `python-docx` 读取 Word 文件；`python-docx` 只支持 `.docx`，不支持旧版二进制 `.doc`，导致解析失败。

### 处理策略

采用短期稳定方案：暂不支持 `.doc`，提示用户另存为 `.docx` 后上传。

| 文件 | 改动 |
|------|------|
| `backend/routers/upload.py` | `.doc` 直接返回 400，并提示转 `.docx` |
| `frontend/src/components/ContractInput.tsx` | 前端拦截 `.doc`，提示转 `.docx`；支持列表移除 `.doc` |
| `src/contract_risk_analysis/utils/file_extractor.py` | 文档声明移除 `.doc` 支持 |

### 后续可选增强

如后续经常处理旧版 `.doc`，可在 v2.17+ 增加 LibreOffice headless 自动转换能力。

---

## 2026-05-12：v2.13+ 规划完成 — 合同审查 Agent 系统优化路线

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 编写合同审查 Agent 系统优化方案 | `docs/superpowers/specs/2026-05-12-contract-review-agent-optimization-design.md` | ✅ |
| 2 | 更新后续实施工作清单 | `worklist/WORKLIST.md` | ✅ |
| 3 | 压缩并更新进度记录 | `worklist/PROGRESS.md` | ✅ |

### 方案核心

从“高质量报告生成器”升级为“事实可核验、立场可裁决、数据可追溯、策略可执行、版本可评测”的合同风控 Agent。

目标架构：

```text
合同输入与证据抽取层
→ Dossier 事实清单层
→ 法务裁决层
→ BN 数据与交叉校验层
→ 多形态报告生成层
→ 自动评测与版本对比层
```

### 后续实施主线

| 版本 | 主题 | 目标 |
|------|------|------|
| v2.13 | 立场裁决与 BN 解释稳定化 | 消除责任上限、间接损失、管辖等方向性误判 |
| v2.14 | 质保金倒挂与付款担保结构检测 | 固化“高额预付款 + 担保后置/不足”的结构性风险识别 |
| v2.15 | 多形态报告输出 | 管理层摘要、法务详版、谈判作战版、修订清单、BN 附录 |
| v2.16 | 内部自动评测集 MVP | 建立个人项目可维护的 golden case 与规则评分器 |

### 自动评测集方向

个人项目无需等待外部法务专家，可先用“弱监督 golden set”：

1. 以当前买卖合同作为第一个 golden case；
2. 标准答案采用 `must_find` / `must_not` / `should_find_advantages`；
3. 先做规则评分器，再预留 LLM-as-judge；
4. 每次人工对比后的确定正确/错误点沉淀为机器可检查规则。

---

## 2026-05-11：v2.12 完成 — 报告策略质量增强

### 实施内容

| # | 任务 | 文件 | 状态 |
|---|------|------|:--:|
| v2.12-B | 跨筹码联动矩阵（dossier模板 + prompt指令） | `report_writer.py` | ✅ |
| v2.12-A | 反事实分析精简（按维度合并 + 谈判意义解读） | `report_writer.py` | ✅ |
| v2.12-E | LLM₁ 策略思维轻量注入 | `ai_review.py` | ✅ |
| v2.12-C | 商业语言温度（核心行为准则第 6 条） | `report_writer.py` | ✅ |
| v2.12-D | 章节一致性 prompt 自检 | `report_writer.py` | ✅ |

### 测试

- 92 passed, 0 failed
- 不改 schema、不碰 JSON、不碰 BN、不碰 adjudicate

### 待报告验证

1. ⏳ 第五章含 ≥1 个量化交换比率 + ≥1 个三档退让阶梯
2. ⏳ BN 反事实独立行 ≤5
3. ⏳ LLM₁ strategy 字段跨条款联动频次提升
4. ⏳ 对抗性措辞减少，桥接性措辞增加
5. ⏳ 第 5 章与第 6 章无策略矛盾
6. ✅ 92+ passed
7. ⏳ 新报告评分 ≥92

---

## 2026-05-11：v2.11 完成 — NegotiationChip 结构化 + JSON 稳定性修复

### 提交信息

- Commit: `28ef3b0` — `Release v2.11: LLM₁ JSON稳定性修复 + negotiation_chip结构化对象端到端改造`
- Branch: `release/v2.8`

### 完成内容

| # | 任务 | 文件 | 状态 |
|---|------|------|:--:|
| Task 1 | NegotiationChip 数据模型 | `free_review_schema.py` | ✅ |
| Task 2 | 解析层：对象解析 + 入口字符串降级兼容 | `ai_review.py` | ✅ |
| Task 3 | 保留一次 JSON 解析失败重试 | `ai_review.py` | ✅ |
| Task 4 | adjudicate.py 写入结构化 NegotiationChip 对象 | `adjudicate.py` | ✅ |
| Task 5 | report_writer.py 移除字符串分支 | `report_writer.py` | ✅ |
| Task 6 | API fact_sheet 序列化修复 | `backend/routers/review.py` | ✅ |
| Task 7 | 全量测试验证 | `tests/` | ✅ |

### 关键成就

- `negotiation_chip` 从字符串假设统一为结构化对象；
- 解析入口保持窄兼容，内部全按对象处理；
- party-aware 规则正确将 `liability_cap` 标记为响应筹码；
- 报告不再出现 `NegotiationChip` 对象 repr 泄漏。

---

## 历史关键节点（压缩）

| 日期 | 版本 | 事件 |
|------|------|------|
| 2026-04-28 | v1→v2 | LLM₁+BN+LLM₂ 管线上线，63 节点 BN |
| 2026-04-29 | v2.3 | 立场锚定，修复 DeepSeek 不及格 |
| 2026-04-30 | v2.5 | BN 反事实稳定性，CPT 数据驱动，75 节点 |
| 2026-04-30 | v2.6 | 数字→推理规则，让步梯度，战略层开关，民法典精选 |
| 2026-05-03 | v2.7 | LLM₁ 覆盖强制化 |
| 2026-05-06 | v2.8 | 合同类型分层路由，公司红线配置化 |
| 2026-05-07 | v2.9 | 开源化：Docker/CI/英文README/社区文件/拆分backend |
| 2026-05-08 | v2.10 | LLM₂降级为受约束渲染器，Dossier，canonicalization/adjudication |
| 2026-05-08 | v2.11 | Phase A 回归修复：立场感知裁决，回归测试 |
| 2026-05-11 | v2.11 | NegotiationChip 结构化端到端，JSON 重试，报告-9 产出 |
| 2026-05-11 | v2.12 | 报告策略质量增强：筹码联动、反事实精简、商业语言、一致性自检 |
