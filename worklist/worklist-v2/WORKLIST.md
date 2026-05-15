# BN-Contract-Risk-Analysis 工作清单（v2）

> 最后更新：2026-05-14（切换到“报告泛化实施限制固化”待启动主线）

---

## 使用说明

- `WORKLIST.md`：记录各阶段要做什么、做到什么算完成。
- `PROGRESS.md`：记录已经做了什么、做到哪一步、下次从哪里继续。
- 已完成事项只写入 `PROGRESS.md`；`WORKLIST.md` 只维护当前和后续待实施内容。

---

## 当前总目标

围绕买方合同审查报告主线，把系统从“当前样本上效果较好”继续推进到“真正适配不同合同、客户版清洁、规则不硬编码、数字可追溯”的状态。

当前主线状态：

```text
阶段 B 后续：报告泛化实施限制固化（待启动）
→ 先把“不能硬编码/不能写死样本答案/不能引用外部评价回灌系统”固化进源码与测试
→ 再补客户版清洁度与无来源数字 lint
→ 最后用真实样本重跑验证，但在收到开始指令前不实施
```

当前已完成计划：
- `docs/superpowers/plans/2026-05-14-v15-report-optimization.md`
- `docs/superpowers/plans/2026-05-14-report-fact-accuracy-and-customer-output-hardening.md`
- `docs/superpowers/plans/2026-05-14-report-generalization-guardrails.md`

当前待实施项（等待开始指令）：
1. **P0：固化 LLM₁ 泛化提示纪律**
   - 在 `src/contract_risk_analysis/review/ai_review.py` 中加入去硬编码与外评隔离约束
   - 在 `tests/review/test_ai_review.py` 中加入对应回归测试
2. **P0：固化 LLM₂ 去硬编码与客户版清洁约束**
   - 在 `src/contract_risk_analysis/review/report_writer.py` 中加入禁止样本模板回灌的组合提示约束
   - 在 `tests/review/test_report_writer_negotiation_chip.py` 中补充对应断言
3. **P1：收紧规则层推荐措辞**
   - 保持 `src/contract_risk_analysis/review/adjudicate.py` 中推荐为结构性泛化表述
   - 用 `tests/regression/test_judgment_regression.py` 防止回退到样本化答案
4. **P1：增加成品级 lint**
   - 拦截外部评价痕迹、内部标记、占位符与无来源数字估算
5. **P2：真实样本重跑与验收**
   - 用买卖合同 PDF 重跑新版本报告
   - 只验证不覆盖旧版，并确认客户版清洁度与泛化限制成立

---

## 下一阶段候选（当前主线完成后再选）

### 阶段 B 后续：报告泛化与评测收口

**候选方向：**
1. 基于批量结果生成“谁进步/谁退步”的自动摘要；
2. golden case / golden pattern / production rule 的进一步收口；
3. 不同合同类型的量化锚点泛化。

**进入前提：**
- 先完成当前“报告事实准确性与客户版输出收口”主线；
- 保留本次聚焦回归入口作为后续版本回归基线。

---

### 阶段 C：更多合同类型扩展

**候选方向：**
1. 采购/销售之外的常见合同类型；
2. 合同类型专属红线与策略模板；
3. 对应报告主线的结构化复用。

**启动前完成标准：**
- 先完成阶段 B 中至少一条泛化/评测主线；
- 明确目标合同类型及最小测试集；
- 明确不复用旧阶段的临时假设。

---

## 下次继续建议

等待你的“开始”指令后，再按以下顺序继续：

```text
1. 先实施 LLM₁ 泛化提示纪律与测试
2. 再实施 LLM₂ 去硬编码约束与客户版清洁 lint
3. 然后收紧规则层推荐措辞并补回归
4. 最后重跑真实样本验证，不覆盖旧报告
```

---

## 续做规则

- 每完成一个阶段或关键子任务，就在 `PROGRESS.md` 顶部追加记录；
- `WORKLIST.md` 只保留未完成阶段与后续候选，不重复写历史实现细节；
- 如果开始新阶段，先更新本文件的“当前总目标/当前主线状态/下次继续建议”。
