# 实施进度记录（v2）

> 最后更新：2026-05-18（阶段 E-3 完成：租赁合同专项红线规则）

---

## 当前状态

- **当前主线**：阶段 E：BN 自适应可信度分层 + 跨合同类型证据收口（进行中，E-1/E-2/E-3 已完成）
- **当前计划文件**：`docs/superpowers/specs/2026-05-18-bn-adaptive-confidence-design.md`
- **当前进展**：E-1（bn_confidence）、E-2（路由修复）、E-3（租赁红线）均已完成。系统合同类型覆盖从 3 种扩展到 7 种，每种均有关联 BN 节点和专属红线规则。聚焦回归 67 passed。
- **下次继续入口**：E-4（轻量合同报告框架自适应简化）或直接跑一轮完整验证

---

## 2026-05-18：阶段 E-2 — contract_type_routing 链路排查 + 四种合同类型路由补充（已完成）

### 根因

`contract_type_routing.yaml` 的 `contract_types` 段原来只有销售/采购/煤炭三种类型。技术开发合同和服务合同没有匹配入口，导致 LLM₁ 的系统性审查清单中不会出现 `cuad_source_code_escrow`、`cuad_license_grant`、`cuad_ip_ownership_assignment` 等节点。

另外 `fallback.low_confidence_threshold = 0.6` 过高——技术开发合同 13 个关键词需匹配 8 个才过线，实际合理匹配（如 7/13=53.8%）被拒绝。

### 修复

| # | 事项 | 状态 |
|---|------|:--:|
| 新增技术开发合同路由 (11 节点: source_code_escrow, license_grant, IP ownership 等) | ✅ |
| 新增服务合同路由 (9 节点: termination_for_convenience, confidentiality, non_solicit 等) | ✅ |
| 新增租赁合同路由 (8 节点: risk_transfer_point, warranty, insurance 等) | ✅ |
| 新增保密协议路由 (8 节点: confidentiality, non_compete, anti_assignment 等) | ✅ |
| `low_confidence_threshold` 0.6 → 0.25 | ✅ |
| 修复 YAML 注释中全角冒号导致的解析错误 | ✅ |
| 验证：五种测试文本均正确匹配并加载对应节点 | ✅ |

### 下次继续入口

→ E-3：company_redlines.yaml 补充租赁合同专项红线规则

---

## 2026-05-18：阶段 E-1 — BN自适应可信度分层 + 维度对配置化（已完成）

### 做了什么

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| E-1a | `contract_type_parameters.yaml` 四种资产类型加 `bn_confidence` 字段 | `config/contract_type_parameters.yaml` | ✅ |
| E-1b | `contract_type_parameters.yaml` 新增 `bn_dimension_pairs` 段 (universal 2对 + optional 4对) | `config/contract_type_parameters.yaml` | ✅ |
| E-1c | `consistency_validator.py` 维度对从配置读取，按 bn_confidence 选数量 | `src/contract_risk_analysis/bn/consistency_validator.py` | ✅ |
| E-1d | `contract_type_routing.yaml` 各合同类型加 `bn_config_override: null` 占位 | `config/contract_type_routing.yaml` | ✅ |
| E-1e | `report_writer.py` LLM₂ prompt 加 BN 可信度层级 framing + 各函数线程化 bn_confidence | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| E-1f | `bn_mapping.py` `CROSS_DIMENSION_RISK_PAIRS` 加注释标注为通用回退 | `src/contract_risk_analysis/bn/bn_mapping.py` | ✅ |
| E-1g | `ai_review.py` 新增 `detect_bn_confidence()` + `load_bn_dimension_pairs()` | `src/contract_risk_analysis/review/ai_review.py` | ✅ |
| — | 后端路由 (review.py + dual.py) 传入 bn_confidence | `backend/routers/review.py`, `dual.py` | ✅ |
| — | 聚焦回归 67 passed | 测试 | ✅ |

### bn_confidence 三级行为

| 级别 | 适用合同 | 维度对数量 | LLM₂ prompt 措辞 | BN 数据展示 |
|:--:|------|:--:|------|------|
| **high** | 标准设备采购 | 6对 (universal + optional) | "可用于谈判中的数字论证" | 完整表格+数字 |
| **medium** | 定制开发/大宗商品 | 3对 (universal + top 1) | "方向性参考，建议结合行业惯例" | 简化表格 |
| **low** | 轻资产服务 | 2对 (universal only) | "量化模型校准尚不充分，以法律判断为主" | 方向性描述，无数字 |

### 后续扩展点

数据集到位后：运行 CPT 校准 → 将对应 `bn_confidence` 翻为 high → 报告自动恢复完整量化。如需合同类型特定 BN 配置，在 `contract_type_routing.yaml` 中设 `bn_config_override` 指向新配置文件即可。

### 下次继续入口

→ E-2：contract_type_routing 链路排查（技术开发合同源码托管/SLA 节点未触发）

---

## 2026-05-18：阶段 D 完成 — 跨合同类型泛化验证 + 问题诊断

### 做了什么

| # | 事项 | 状态 |
|---|------|:--:|
| 1 | 买卖合同卖方视角 - 乙方-1 报告生成 + 立场翻转验证 | ✅ |
| 2 | 保密协议-1 报告生成 | ✅ |
| 3 | 技术开发合同-1 报告生成 | ✅ |
| 4 | 服务合同-1 报告生成 | ✅ |
| 5 | 租赁合同-1 报告生成 | ✅ |
| 6 | 五类合同横向对比分析 | ✅ |
| 7 | BN 乘数效应数字来源追查（`pgmpy_adapter.py` → 确认动态计算、非硬编码） | ✅ |
| 8 | 诊断：BN CPT 全合同类型共用同一套先验 | ✅ |
| 9 | 诊断：`consistency_validator.py:78-85` 6 对维度组合硬编码 | ✅ |
| 10 | 诊断：技术开发合同 `cuad_source_code_escrow` / `cuad_license_grant` 未触发 | ✅ |
| 11 | 诊断：服务合同 light_service context 可能未注入 prompt | ✅ |
| 12 | 制定 BN 自适应可信度分层方案 | ✅ |
| 13 | 输出 spec：`docs/superpowers/specs/2026-05-18-bn-adaptive-confidence-design.md` | ✅ |

### 关键发现

**立场翻转验证（买卖合同买方 vs 卖方）：** 系统立场感知基本正确——BN 解读规则翻转、筹码分类自洽、对手预判方向正确。唯一瑕疵：卖方报告退让阶梯设计深度不及买方报告。

**BN 乘数效应：** 数字本身是动态计算的（`pgmpy_adapter.py:718`），不同合同确实输出不同乘数（1.40x~1.69x）。核心问题是 BN CPT 参数全部基于 CUAD 商业合同训练，用于租赁/NDA 时先验不匹配。

**合同类型路由：** `contract_type_routing.yaml` 定义了技术开发合同的 `cuad_source_code_escrow` / `cuad_license_grant` 节点，但实际报告未触发——路由链路需排查。

### 下次继续入口

→ 阶段 E-1：bn_confidence 分层机制 + 维度对配置化

---

## 2026-05-15：阶段 D — 第一层：当前架构内收口（已完成）

### 最新进展

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 更新 WORKLIST.md 切换至阶段 D 主线 | `worklist/worklist-v2/WORKLIST.md` | ✅ |
| 2 | 更新 PROGRESS.md 记录新阶段开始 | `worklist/worklist-v2/PROGRESS.md` | ✅ |
| 3 | 1-1：LLM₂ prompt 退让阶梯指令——"目标写成方向+条件而非另一个独立百分比" | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | 1-1：更新 test_consistency_repairs + test_signing_guardrail 断言 | `tests/review/test_report_writer_negotiation_chip.py` | ✅ |
| 5 | 1-2：LLM₂ prompt 第四章——"同一结论的多条数据必须合并去重" | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 6 | 1-3：MultiFormatReports 增加 `redline_appendix` 字段 + `include_redline` 参数 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 7 | 聚焦回归 89 passed | 测试记录见下 | ✅ |

### 测试记录

```text
tests/review/test_ai_review.py: 22 passed
tests/review/test_report_writer_negotiation_chip.py: 14 passed
tests/regression/test_judgment_regression.py: 53 passed
Focus全部: 89 passed in 5.52s
```

### 第一层总结

| 编号 | 改进项 | 效果 |
|:---:|------|------|
| 1-1 | 退让阶梯方向化 | 三档阶梯中的目标值必须写成"从合同原文 X% 降至方向+保护条件"，禁止独立目标百分比 |
| 1-2 | BN 数据去重 | 结论相同的多条防守筹码数据合并为一个汇总段落 |
| 1-3 | Redline 接入 | `generate_multi_format_reports()` 现在默认生成 Redline 条款对照表 |

### 下次继续入口

第一层完成，买卖合同基线收口。聚焦回归 89 passed。
下一阶段：第二层（跨合同类型泛化验证）——由用户启动。
第三层（中长期方向）——用户规划。

---

### 最新进展

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 更新 WORKLIST.md 切换至阶段 C 主线 | `worklist/worklist-v2/WORKLIST.md` | ✅ |
| 2 | 更新 PROGRESS.md 记录新阶段开始 | `worklist/worklist-v2/PROGRESS.md` | ✅ |
| 3 | P0-3：LLM₂ prompt 第四章用语规范——新增禁用术语替换表，示例格式改为商业语言 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | P0-3：REPORT_SECTIONS 常量与章节模板标题同步更新 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | P0-3：新增 `test_combined_prompt_includes_chapter_4_terminology_ban` | `tests/review/test_report_writer_negotiation_chip.py` | ✅ |
| 6 | 聚焦回归 63 passed；真实样本验证待 P0 三项全完后统一跑 | — | ⏳ |

### 测试记录

```text
tests/review/test_report_writer_negotiation_chip.py + tests/regression/test_judgment_regression.py: 63 passed in 3.00s
```

### 下次继续入口

P0-3 已完成。进入 P0-1（签署底线数字去硬编码）。

---

## 2026-05-15：阶段 C — P0-1 签署底线数字去硬编码（已完成）

### 最新进展

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | P0-3 BN 术语去学术化已完成 | 同上表 | ✅ |
| 2 | P0-1：LLM₂ prompt 第六章新增"签署底线数字纪律"——严禁在签署建议中自行补写 Dossier 未出现的数字 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | P0-1：新增 `test_combined_prompt_includes_signing_guardrail_number_discipline` | `tests/review/test_report_writer_negotiation_chip.py` | ✅ |
| 4 | 聚焦测试 14 passed | 测试记录见下 | ✅ |

### 测试记录

```text
tests/review/test_report_writer_negotiation_chip.py: 14 passed in 2.20s
```

### 说明

Dossier 层的 signing 文本已通过 `_rewrite_unsourced_payment_thresholds()` 在上阶段间接净化。本条新增的 prompt 约束针对 LLM₂ 在第六章自发生成数字的行为。

### 下次继续入口

P0-1 已完成。进入 P0-2（攻击预判去模板化）。

---

## 2026-05-15：阶段 C — P2 低优先级三项（已完成）

### 最新进展

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | P2-1：新增 `test_stance_stability_buyer_key_clauses` 立场稳定性回归——锁定 liability_cap/jurisdiction/damages_exposure 对买方必须为 favorable | `tests/regression/test_judgment_regression.py` | ✅ |
| 2 | P2-2：新增 `_build_redline_appendix()` 确定性生成原条款 vs 修改建议双栏对照表 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | P2-2：新增 `test_redline_appendix_contains_original_vs_recommendation` | `tests/regression/test_judgment_regression.py` | ✅ |
| 4 | P2-3：新建标准化评测 prompt 模板，记录五份外部评价参数和历史评测数据 | `合同检测报告/评价prompt/标准化评测prompt模板.md` | ✅ |
| 5 | 聚焦回归 89 passed | 测试记录见下 | ✅ |

### 测试记录

```text
tests/review/test_ai_review.py: 22 passed
tests/review/test_report_writer_negotiation_chip.py: 15 passed
tests/regression/test_judgment_regression.py: 52 passed
Focus全部: 89 passed in 4.59s
```

### P0+P1+P2 总计

| 阶段 | 数量 | 改动文件 | 新建文件 | 测试增量 |
|:---:|:---:|:---:|:---:|:---:|
| P0 | 3 项 | 3 | 0 | +3 |
| P1 | 3 项 | 3 | 2 | +9 |
| P2 | 3 项 | 3 | 1 | +2 |
| **合计** | **9 项** | **6** | **3** | **+14** |

### 当前状态

方案 `2026-05-15-post-evaluation-improvement.md` 所列 9 项改进全部实施完成。
聚焦回归 89 passed。WORKLIST 和 PROGRESS 同步更新。

## 2026-05-15：真实样本端到端验证（已完成）

### 验证结果

| 检验项 | 结果 | 说明 |
|--------|:--:|------|
| P0-3：第四章无学术术语 | ✅ | P(high)/维度级/BN模拟效果/反事实分析 均 x0 |
| P0-1：第六章无固定阈值 | ✅ | 30%/20%以下/10%以上 均 x0 |
| P0-2：第五章攻击话术 | ✅ | 条款号引用 x21，合同数字引用 x15 |
| P1-1：资产类型检测 | 🛠️→✅ | 修复 OCR 字符间空格 + 改为最佳匹配算法，正确识别"标准工业设备" |
| P1-3：缺失条款分层 | ✅ | Dossier 层 P0/P1/P2 三级分层展示正常 |
| 客户版清洁度 | ✅ | ISSUE-/DeepSeek/渲染器备注/TODO/TBD 均 x0 |
| 报告八章结构 | ✅ | 全部存在 |
| 聚焦回归 | ✅ | 89 passed |

### 修复项

P1-1 资产类型检测在真实 PDF（OCR 风格带字符间空格）上初始返回空。
修复：增加 CJK 字符间空格折叠 + 改用最佳匹配评分算法替代首次命中。

### 下次继续入口

```text
方案文档所列 9 项改进全部实施并验证完成。聚焦回归 89 passed。
下一阶段新主线待定。
```

---


## 2026-05-15：谈判阈值去硬编码闭环（已完成）

### 最新进展

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 定位固定谈判阈值来源：party_aware_rules → Dossier 推荐/签署底线 → LLM₂ prompt | 同上表文件 | ✅ |
| 2 | 将 `party_aware_rules.yaml` 中 “至20%” 改为方向性表述 | `config/party_aware_rules.yaml` | ✅ |
| 3 | 新增 `_rewrite_unsourced_payment_thresholds()` 净化 Dossier 推荐与 LLM₁ 摘要中的无来源固定阈值 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | 修改 LLM₂ 四段 prompt：退让阶梯、筹码矩阵、代码手册、主 prompt 策略指令——从”必须给数字”改为”有来源引用，无来源写方向+条件” | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | 新增 `test_dossier_payment_guardrails_do_not_invent_fixed_thresholds` 锁定 Dossier 层不放行 30%/10%/15% | `tests/regression/test_judgment_regression.py` | ✅ |
| 6 | 更新 `test_adjudicate_assigns_structured_chip_from_party_rule` 以匹配新的方向性表述 | `tests/review/test_ai_review.py` | ✅ |
| 7 | 聚焦回归 80 passed；真实样本 Dossier 验证：固定阈值已不可见 | 测试记录见下 | ✅ |

### 测试记录

```text
tests/review/test_ai_review.py: 18 passed
tests/review/test_report_writer_negotiation_chip.py + tests/regression/test_judgment_regression.py: 62 passed
Focus全部: 80 passed in 1.66s
```

### 关键判断

真实样本重跑后，**Dossier 层（系统裁决）已不再夹带 30%/10%/10%-15% 固定阈值**，推荐文本全部改为方向性表述。客户版报告仍可能出现具体数字（如 LLM 基于合同 80% 预付款分析后建议的付款节点、或引用 20% 违约金），但这些属于 LLM 基于合同的独立法律推理，**与代码层硬编码有本质区别**。

符合用户补充口径：”不是不让出现数字，而是根据不同的合同可以有不同的判断”。

### 下次继续建议

```text
1. 如需进一步控制 LLM 自发数字，走合同类型→行业参数映射的结构性方案
   （如重资产 vs 小商品零售对应不同合理预付款区间）
2. 当前 Dossier 护栏已成立，后续优化提升报告质量时，新增测试也应走
   “不允许未从合同或 Dossier 派生的固定阈值” 断言路径
```

---

## 2026-05-15：报告泛化实施限制固化（进行中）

### 最新进展

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 已为 LLM₁ 泛化提示纪律补入失败测试并完成实现转绿 | `tests/review/test_ai_review.py` `src/contract_risk_analysis/review/ai_review.py` | ✅ |
| 2 | 已为 LLM₂ 去硬编码与客户版清洁约束补入失败测试并完成实现转绿 | `tests/review/test_report_writer_negotiation_chip.py` `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | 已为规则层推荐泛化表述补回归护栏，现状直接通过，无需新增特判逻辑 | `tests/regression/test_judgment_regression.py` `src/contract_risk_analysis/review/adjudicate.py` | ✅ |
| 4 | 已为成品级 lint 补入“外部评价痕迹/无来源数字”护栏并完成转绿 | `tests/review/test_report_writer_negotiation_chip.py` `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | 已重跑真实样本并生成 `contract-review-买卖合同-20.md`，确认未覆盖旧版且客户版清洁护栏成立；但仍发现固定谈判数字回灌，当前不能判定整体验收通过 | `合同检测报告/买卖合同/contract-review-买卖合同-20.md` | ✅ |

### 当前暂停点

1. 已开始正式实施，但目前仅完成 Task 1 的失败测试落地。
2. 下一步先运行 `tests/review/test_ai_review.py` 确认该新测试如预期失败，再最小化修改 `ai_review.py` 使其转绿。

### 下次继续入口

```text
1. 跑 tests/review/test_ai_review.py，确认新泛化护栏测试失败
2. 修改 src/contract_risk_analysis/review/ai_review.py 加入泛化约束与外评隔离约束
3. 重跑 tests/review/test_ai_review.py 直至通过
```

---

## 2026-05-14：报告泛化护栏方案与执行前清单准备完成（未开始实施）

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 生成泛化护栏实施方案文档 | `docs/superpowers/plans/2026-05-14-report-generalization-guardrails.md` | ✅ |
| 2 | 将“不能硬编码/不能回灌外部评价/不能编造数字/客户版必须清洁”等限制整理为强制约束 | 同上 | ✅ |
| 3 | 更新 `WORKLIST.md`，把主线切换为待启动的“报告泛化实施限制固化” | `worklist/worklist-v2/WORKLIST.md` | ✅ |
| 4 | 更新 `PROGRESS.md`，明确当前仅完成准备、等待开始指令 | `worklist/worklist-v2/PROGRESS.md` | ✅ |

### 当前结论

1. **准备工作已完成，但实施尚未开始**
   - 目前只有方案、worklist、progress 已就位；源码、测试、真实样本输出均未因本次主线发生新改动。

2. **后续会严格按“开始”指令推进**
   - 在收到开始指令前，不进入代码修改、测试变更或报告重跑。

### 下次继续建议

```text
等待用户发出“开始”指令后，再进入实施阶段。
```

---

## 2026-05-14：真实样本端到端抽查完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 用项目内置 PDF 提取器抽取真实买卖合同文本，并直连 `_run_v2_pipeline` 做端到端抽查 | `src/contract_risk_analysis/utils/file_extractor.py` `backend/routers/review.py` | ✅ |
| 2 | 扩展量化抽取，支持 OCR 风格 `合 同 的 总 金 额 为 人 民 币 : ¥_15350000.00 _ 元` 写法 | `src/contract_risk_analysis/review/quantification.py` `tests/review/test_quantification.py` | ✅ |
| 3 | 放宽付款锚点识别范围，使真实样本中的 `canonical_type="payment"` 也能产出 80% 预付款锚点 | `src/contract_risk_analysis/review/quantification.py` `tests/review/test_quantification.py` | ✅ |
| 4 | 修复 pre-render consistency check 遇到非字符串 `manual_review_items` 时的崩溃 | `src/contract_risk_analysis/review/report_writer.py` `tests/regression/test_judgment_regression.py` | ✅ |
| 5 | 重跑聚焦回归并再次验证真实样本客户版输出清洁度 | `tests/review/test_quantification.py` `tests/regression/test_judgment_regression.py` | ✅ |

### 测试记录

```text
.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_quantification.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/regression/test_judgment_regression.py" -q
52 passed in 3.16s

真实样本：`合同检测报告/买卖合同/买卖合同.pdf` → `_run_v2_pipeline`
- fact_sheet.quantitative_context.contract_amount = 15350000.0
- fact_sheet.quantitative_context.amount_source_text = "总金额为人民币:¥15350000.00元"
- fact_sheet.quantitative_context.payment_anchors[0].amount = 12280000.0
- narrative_report 不含 “合同总价未识别”
- narrative_report 不含 `## 渲染器备注`
- narrative_report 不含 `ISSUE-`
```

### 当前结论

1. **-16 类真实合同误报已被端到端证伪**
   - 真实 OCR 风格买卖合同现在能识别出 `15350000` 合同总金额与 `12280000` 预付款金额，`fact_sheet.quantitative_context` 已恢复正确。

2. **客户版边界在真实样本上成立**
   - 最终 `narrative_report` 已确认不再出现“合同总价未识别”、`## 渲染器备注` 或 `ISSUE-` 内部编号泄漏。

3. **当前剩余问题更偏日志层噪声，而不是客户版事实错误**
   - pre-render consistency check 仍会对内部 `ISSUE-` 文本和部分数字来源做噪声告警，但这次抽查里未再污染最终客户版正文。

### 下次继续建议

直接按以下顺序继续：

```text
1. 收口 pre-render consistency check 对 internal_conflicts / manual_review_items 的噪声型 ISSUE- 告警
2. 针对真实样本里仍会触发的“无来源数字问题”日志做一次可见文本范围校准
3. 如需再抽样，换一份不同版式合同复测 OCR 风格金额与客户版边界
```

---

## 2026-05-14：报告事实准确性与客户版输出收口首轮完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 写出新的实施计划，覆盖合同总价识别、客户版/内部版边界、`视为交付` 双面分析 | `docs/superpowers/plans/2026-05-14-report-fact-accuracy-and-customer-output-hardening.md` | ✅ |
| 2 | 将 `worklist-v2` 当前主线切换到本次 hardening 任务 | `worklist/worklist-v2/WORKLIST.md` `worklist/worklist-v2/PROGRESS.md` | ✅ |
| 3 | 扩展确定性合同总价抽取，覆盖 table-style / spaced-text / OCR 风格变体 | `src/contract_risk_analysis/review/quantification.py` `tests/review/test_quantification.py` | ✅ |
| 4 | 移除客户版 prompt 中对 `## 渲染器备注` 的强制输出要求，并增加内部信息不可外泄规则 | `src/contract_risk_analysis/review/report_writer.py` `tests/review/test_report_writer_negotiation_chip.py` | ✅ |
| 5 | 为 `视为交付 / 风险转移` 条款补强双面分析 prompt 纪律 | `src/contract_risk_analysis/review/ai_review.py` `tests/review/test_ai_review.py` | ✅ |
| 6 | 跑通聚焦报告链路回归 | `tests/review/test_quantification.py` `tests/review/test_report_writer.py` `tests/review/test_report_writer_negotiation_chip.py` `tests/review/test_ai_review.py` `tests/regression/test_judgment_regression.py` | ✅ |

### 测试记录

```text
.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_quantification.py" -q
4 passed in 1.98s

.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer_negotiation_chip.py" -q
11 passed in 2.08s

.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_ai_review.py" -q
16 passed in 2.14s

.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_quantification.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer_negotiation_chip.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_ai_review.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/regression/test_judgment_regression.py" -q
77 passed in 2.28s
```

### 当前结论

1. **-16 报告暴露的三类问题已各自落到对应护栏上**
   - 合同总价识别从狭窄 `合同总价为...` 扩展到 `总价15,350,000元`、`合同货物总价 人民币 15,350,000 元` 等真实合同写法。
   - 客户版 prompt 不再强制输出内部“渲染器备注”章节，只保留“建议人工复核”的对外表达。
   - `视为交付` 条款的 prompt 现在要求同时审查提前风险转移与剩余买方保护是否仍在。

2. **当前切片已经形成可续做检查点**
   - 代码改动与测试入口均已固定；下一步更适合做真实样本输出抽查，而不是继续扩写规则。

### 下次继续建议

直接按以下顺序继续：

```text
1. 选一份带“总价15,350,000元”或类似表格写法的真实合同跑端到端输出
2. 验证 fact_sheet.quantitative_context 与最终客户版报告已不再出现“合同总价未识别”误报
3. 抽查客户版正文，确认不再出现“渲染器备注”、ISSUE-内部编号或系统自检过程
```

---

## 2026-05-14：阶段 B 批量 golden-case 回归完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 为 golden score 增加目录批量扫描与聚合结果对象 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 2 | 为批量回归增加失败容忍与终端摘要格式化 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 3 | 为 CLI 增加 `--score-golden-case-batch` / `--reports-dir` 入口 | `src/contract_risk_analysis/cli.py` | ✅ |
| 4 | 补齐批量评测与 CLI 回归测试 | `tests/evaluation/test_golden_score.py` `tests/cli/test_main.py` | ✅ |
| 5 | 更新 golden CLI 使用说明 | `docs/golden-cli-usage.md` | ✅ |

### 测试记录

```text
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py tests/cli/test_main.py -q
27 passed, 1 warning in 89.21s
```

### 当前结论

1. **阶段 B 已完成首个可用闭环**
   - 目录级 batch golden-case 回归、CLI 入口、结构化结果和终端摘要均已就位。

2. **后续可转入结果解释与规则收口**
   - 下一步更适合补“谁进步/谁退步”的版本对比摘要，或继续推进 golden pattern / production rule 收口。

### 下次继续建议

直接按以下顺序继续：

```text
1. 基于批量结果生成“谁进步/谁退步”的自动摘要
2. 或进入 golden pattern / production rule 的进一步收口
3. 保持当前 batch regression 作为后续版本回归入口
```

---

## 2026-05-14：v15 报告量化与交换比率增强完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 新增确定性量化上下文提取（合同总价/预付款比例/金额换算） | `src/contract_risk_analysis/review/quantification.py` `src/contract_risk_analysis/domain/free_review_schema.py` | ✅ |
| 2 | 将量化上下文接入 Dossier / fact_sheet | `backend/routers/review.py` `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | 第三/四/五章改为优先消费可追溯量化锚点 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | LLM₁ prompt 补强数字引用纪律 | `src/contract_risk_analysis/review/ai_review.py` | ✅ |
| 5 | 客户版报告数字 lint 升级为来源感知 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 6 | 回归与渲染测试补强 | `tests/review/test_quantification.py` `tests/review/test_report_writer.py` `tests/review/test_report_writer_negotiation_chip.py` `tests/review/test_ai_review.py` `tests/regression/test_judgment_regression.py` | ✅ |

### 测试记录

```text
.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_quantification.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer_negotiation_chip.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_ai_review.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/regression/test_judgment_regression.py" -q
73 passed in 2.80s
```

### 当前结论

1. **v15 主线本阶段已闭环**
   - 确定性量化抽取、Dossier/API 接线、报告章节量化锚点接入、LLM₁ 数字纪律、来源感知 lint 均已完成。

2. **本阶段现在满足可中断、可续做、可回溯**
   - 进度记录、测试入口、下一步候选方向都已明确。

### 下次继续建议

直接按以下顺序继续：

```text
1. 进入阶段 B：报告泛化与评测收口
2. 先选“不同合同类型的量化锚点泛化”或“报告质量自动评测增强”其一作为下一主线
3. 再为新主线建立新的阶段性实施计划与回归入口
```

---

## 2026-05-14：P1 数字纪律与来源感知 lint 完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 为 LLM₁ prompt 增加数字纪律：数字必须来自合同原文；无总价时禁止自行金额换算 | `src/contract_risk_analysis/review/ai_review.py` | ✅ |
| 2 | 为 LLM₁ prompt 纪律补测试断言 | `tests/review/test_ai_review.py` | ✅ |
| 3 | 将 report_writer 的数字 lint 从关键词黑名单升级为来源感知校验 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | 允许来源：合同原文证据、定量锚点、换算公式、交换比率提示；阻断无来源金额化/概率化表述 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | 为来源感知 lint 补回归测试（拦截无总价金额化表达；放行来自定量锚点的数字） | `tests/regression/test_judgment_regression.py` | ✅ |
| 6 | 跑通 P1 聚焦与合并回归 | 见下方测试记录 | ✅ |

### 测试记录

```text
.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_ai_review.py" -q
15 passed in 2.30s

.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer_negotiation_chip.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/regression/test_judgment_regression.py" -q
53 passed in 3.63s

.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_quantification.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer_negotiation_chip.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_ai_review.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/regression/test_judgment_regression.py" -q
73 passed in 2.80s
```

### 当前结论

1. **LLM₁ 现在被前置约束**
   - prompt 已明确：所有百分比/金额/天数必须来自合同原文。
   - 若合同未出现总价基准，LLM₁ 必须保留百分比/天数表达，不得自行补金额。

2. **LLM₂ 前的数字 lint 现在是来源感知的**
   - 不再只靠少数可疑短语拦截。
   - 现在会对照 Dossier 的证据文本、定量锚点、换算公式、交换比率提示来判断数字是否合法。
   - “无总价却出现金额化表达”会被明确拦截。

3. **当前 P1 已可视为完成**
   - 计划中的“补强 LLM₁ 数字纪律 + 来源感知 lint”两步已经闭环。

### 下次继续建议

直接按以下顺序继续：

```text
1. 检查是否需要补端到端接口级测试，验证 fact_sheet.quantitative_context 与 prompt/lint 联动
2. 如需样例验证，选一份带总价的买卖合同和一份不带总价的合同做真实输出抽查
3. 更新 WORKLIST.md，把已完成的 P0/P1 从待办里收口，仅保留剩余阶段
```

---

## 2026-05-14：P0 确定性量化上下文与报告渲染接入完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 新增确定性量化模块，抽取合同总价 / 百分比锚点 / 金额换算提示 | `src/contract_risk_analysis/review/quantification.py` | ✅ |
| 2 | 为量化能力补充 schema：`QuantitativeAnchor` / `QuantitativeContext` | `src/contract_risk_analysis/domain/free_review_schema.py` | ✅ |
| 3 | 将量化上下文接入 Dossier | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | 将量化上下文接入后端 fact_sheet 输出 | `backend/routers/review.py` | ✅ |
| 5 | 在 Dossier 文本中渲染“定量锚点”区块 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 6 | 在 LLM₂ prompt 中加入金额换算纪律：无合同总价时禁止金额化表达 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 7 | 补充量化与渲染相关测试 | `tests/review/test_quantification.py`, `tests/review/test_report_writer_negotiation_chip.py` | ✅ |
| 8 | 跑通聚焦测试 | 见下方测试记录 | ✅ |

### 测试记录

```text
.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_quantification.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer_negotiation_chip.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer.py" -q
12 passed in 2.16s

.venv/Scripts/python.exe -m pytest "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_quantification.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_report_writer_negotiation_chip.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/review/test_ai_review.py" "E:/myProgram/BN-Contract-Risk-Analysis/tests/regression/test_judgment_regression.py" -q
70 passed in 2.35s
```

### 当前结论

1. **金额换算现在有系统护栏**
   - 只有识别到合同总价时，才允许把百分比锚点换算成金额。
   - 未识别合同总价时，Dossier 和 prompt 会显式写出“禁止把百分比换算成金额”。

2. **report_writer 已能消费量化上下文**
   - Dossier 会向 LLM₂暴露合同总价、支付比例锚点、对应金额、换算公式、交换比率提示与警告。
   - 第三/四/五章的金额表达被约束为只能引用 Dossier 中已有定量锚点，不能自行补算。

3. **当前 P0 已可视为完成**
   - 计划中的“确定性量化抽取 → Dossier/API 接入 → 报告章节量化锚点接入”三步已经闭环。

### 下次继续建议

直接按以下顺序继续：

```text
1. 修改 src/contract_risk_analysis/review/ai_review.py，补强 LLM₁ 数字纪律
2. 为 tests/review/test_ai_review.py 增加 prompt 约束断言
3. 升级 report_writer.py 的来源感知数字 lint
4. 为 lint 补测试并重跑聚焦回归
```

---

## 2026-05-14：worklist-v2 初始化完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 新建 `worklist-v2` 工作区 | `worklist/worklist-v2/` | ✅ |
| 2 | 新建阶段工作清单 | `worklist/worklist-v2/WORKLIST.md` | ✅ |
| 3 | 新建持续进度记录 | `worklist/worklist-v2/PROGRESS.md` | ✅ |
| 4 | 将当前主线切换为 v15 报告量化与交换比率增强 | 同上 | ✅ |
| 5 | 记录当前对应实施计划文件 | `docs/superpowers/plans/2026-05-14-v15-report-optimization.md` | ✅ |

### 当前待实施项

1. **P0：确定性量化上下文抽取**
   - 新增 `src/contract_risk_analysis/review/quantification.py`
   - 为 `ReportDossier` 增加量化上下文
   - 为量化提取补单元测试

2. **P0：接入 Dossier / API / report_writer**
   - 把合同总价、比例、金额锚点送进 Dossier
   - 让 fact_sheet 可见
   - 验证不破坏现有立场护栏

3. **P0：增强第 3/4/5 章量化能力**
   - 商业影响优先引用确定性数字
   - 第五章增加量化交换比率提示
   - 缺总价时明确拒绝金额化表达

4. **P1：补强 LLM₁ 数字纪律 + 来源感知 lint**
   - prompt 约束数字引用方式
   - 升级报告数字 lint

5. **P2：跑聚焦测试并更新进度**
   - 聚焦测试通过后，把结果写回本文件

### 下次继续建议

直接按以下顺序继续：

```text
1. 实现 quantification.py
2. 接入 ReportDossier / backend review router
3. 调整 report_writer 的 Dossier / prompt / lint
4. 补测试并跑聚焦回归
5. 更新本文件记录实施结果
```

---

## 续做规则

- 每完成一个阶段或关键子任务，就在本文件顶部追加新记录；
- 已完成实现细节写入 `PROGRESS.md`；
- `WORKLIST.md` 只保留当前和未来待做内容，不堆积历史实现细节；
- 如果中途切换主线，先在本文件写清“暂停点”和“下次继续入口”。
