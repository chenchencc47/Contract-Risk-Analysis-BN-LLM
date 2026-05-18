# 阶段 B 设计：报告质量自动评测增强（批量回归）

## 1. 目标

把当前“单份报告 golden-case 评测”升级为**目录级批量回归评测能力**，让系统可以一次性对一批报告做结构化评分与汇总，直接服务后续版本对比、回归检查和阶段收口。

本阶段 B 的目标不是提升报告生成能力本身，而是补齐**评测闭环**：让已有的 golden case 评测骨架从“单点可用”变成“批量可用、可汇总、可比较”。

---

## 2. 背景与动机

当前仓库已经具备较成熟的单报告评测骨架：

- `auto_score_report_text()`
- `score_golden_case()`
- `tests/evaluation/test_golden_score.py`
- golden case / golden pattern 文档与 CLI 使用说明

同时，`docs/golden-cli-usage.md` 已明确记录当前限制，其中之一就是：

- **暂不支持批量评测整个文件夹**

因此，阶段 B 最自然且边界最清晰的增强方向是：

> **把单报告 golden-case 评测，稳定升级成目录级批量回归与结构化汇总输出。**

---

## 3. 作用范围

### 3.1 本次要做

1. 输入一个报告目录；
2. 自动扫描其中的 Markdown 报告；
3. 对每份报告运行现有 golden-case 评分；
4. 输出批量评测结果；
5. 输出整批汇总摘要；
6. 保持现有单报告 CLI 行为不退化。

### 3.2 本次明确不做

1. 不新增前端页面；
2. 不接入 LLM-as-judge；
3. 不做 golden pattern 条件命中评分；
4. 不修改现有单报告评分语义；
5. 不把 golden case 自动推断成 production rule；
6. 不做复杂的“报告自动匹配 case”智能识别。

---

## 4. 核心设计

## 4.1 总体架构

沿用现有评测链路，只增加一个**批量调度 + 汇总层**：

### A. 目录扫描层
职责：
- 接收报告目录路径；
- 过滤出 `.md` 文件；
- 跳过非报告文件；
- 以稳定顺序返回待评测文件列表。

### B. 单报告评测复用层
职责：
- 读取单个 Markdown 报告文本；
- 复用现有 `auto_score_report_text()` 或 `score_golden_case()` 逻辑；
- 不改评分规则，只做封装调用。

### C. 批量汇总层
职责：
- 收集每份报告的得分和关键统计；
- 计算整批平均分、最高分、最低分、排序结果；
- 形成结构化批量结果对象。

### D. CLI 输出层
职责：
- 在终端打印人类可读摘要；
- 可选输出 JSON 或 Markdown 汇总文件；
- 作为后续“版本对比评测报告”的输入基础。

---

## 4.2 输入模式

本阶段只支持**最稳的一种模式**：

### 模式：单 case 批量评多份报告
输入：
- 一个 golden case 文件；
- 一个报告目录。

语义：
- 用同一个 golden case 去评目录中的所有报告。

适用场景：
- 同一合同、同一路线下的多版本报告对比。

### 为什么先不做复杂匹配
如果一上来支持“case 目录 + 报告目录自动配对”，范围会立刻扩大到：
- 文件命名约定；
- 合同类型推断；
- case-report 对应关系错误处理。

这会让阶段 B 从“批量回归”变成“批量回归 + 匹配系统”，不利于收口。

---

## 4.3 输出结构

### 4.3.1 终端摘要
终端输出应简洁、可直接比较，例如：

```text
Batch golden-case regression summary
Reports scanned: 6
Reports scored: 6
Average score: 84.2

Top reports:
1. contract-review-买卖合同-15.md — 92.0
2. contract-review-买卖合同-14.md — 88.0
3. contract-review-买卖合同-13.md — 83.0

Lowest report:
- contract-review-买卖合同-11.md — 71.0
```

最少应包含：
- 扫描文件数；
- 成功评分文件数；
- 平均分；
- 最高分报告；
- 最低分报告；
- 排序后的简要列表。

### 4.3.2 结构化结果
建议返回一个清晰的 dict / JSON 结构，后续可被脚本或报告生成器复用。

示例：

```json
{
  "score_kind": "golden_case_batch_regression",
  "reports_scanned": 6,
  "reports_scored": 6,
  "average_score": 84.2,
  "best_report": {
    "report_name": "contract-review-买卖合同-15.md",
    "score": 92.0
  },
  "worst_report": {
    "report_name": "contract-review-买卖合同-11.md",
    "score": 71.0
  },
  "results": [
    {
      "report_path": ".../contract-review-买卖合同-15.md",
      "report_name": "contract-review-买卖合同-15.md",
      "case_id": "sales_purchase_contract_001",
      "score": 92.0,
      "must_find_passed": 5,
      "must_find_total": 6,
      "must_not_passed": 4,
      "must_not_total": 4,
      "advantages_passed": 2,
      "advantages_total": 3
    }
  ]
}
```

这样设计是为了同时满足两种后续用途：
1. 直接给人看；
2. 继续生成“版本对比评测报告”。

---

## 5. CLI 接口设计

建议在现有 CLI 上新增一个明确入口，例如：

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli \
  --score-golden-case-batch tests/fixtures/golden_cases/sales_purchase_contract_001.yaml \
  --reports-dir 合同检测报告/买卖合同
```

### 5.1 本阶段最低可交付参数

- `--score-golden-case-batch`
- `--reports-dir`

### 5.2 预留但不强求本阶段全部实现的参数

- `--output-json <path>`
- `--output-markdown <path>`
- `--limit <N>`
- `--sort-by score|name`

本阶段最低目标是先形成**可批量跑、可批量看结果**的闭环。

---

## 6. 数据模型设计

建议新增两个轻量对象：

### 6.1 BatchReportScore
表示单份报告在批量运行中的结果，包含：
- `report_path`
- `report_name`
- `case_id`
- `score`
- `score_label`
- `must_find_passed`
- `must_find_total`
- `must_not_passed`
- `must_not_total`
- `advantages_passed`
- `advantages_total`
- `regression_note`

### 6.2 BatchGoldenScoreReport
表示整批结果，包含：
- `reports_scanned`
- `reports_scored`
- `average_score`
- `best_report`
- `worst_report`
- `results`

### 6.3 设计原则

- 不复用过重的对象；
- 不改变现有单报告评分对象结构；
- 只在批量层新增包装对象。

---

## 7. 文件边界

### 7.1 主要生产代码
- `src/contract_risk_analysis/evaluation/golden_score.py`
  - 新增批量评分入口与汇总逻辑。

- `src/contract_risk_analysis/cli.py`
  - 新增批量 CLI 参数与输出逻辑。

### 7.2 测试
- `tests/evaluation/test_golden_score.py`
  - 批量目录扫描；
  - 批量汇总统计；
  - 空目录/无 markdown 文件处理；
  - 排序与结果结构断言。

### 7.3 文档
- `docs/golden-cli-usage.md`
  - 补充批量用法；
  - 明确本阶段仍然不支持自动 case 匹配。

### 7.4 跟踪文件
- `worklist/worklist-v2/WORKLIST.md`
- `worklist/worklist-v2/PROGRESS.md`

---

## 8. 错误处理策略

### 8.1 目录不存在
- 直接报错；
- 不静默跳过。

### 8.2 目录里没有 `.md`
- 返回空结果或明确提示；
- 不应伪装成“0 分”。

### 8.3 某一份报告读取失败
- 记录失败项并继续跑其他文件；
- 在最终 summary 中显示 `reports_scored < reports_scanned`。

### 8.4 某份报告评分失败
- 同样记录失败项；
- 不影响整批其余报告。

### 8.5 原则
批量工具最重要的是：
- **尽量跑完**；
- **清楚标明哪里失败**；
- **不要把失败伪装成正常低分**。

---

## 9. 测试策略

本阶段优先做确定性测试，不引入外部模型依赖。

### 9.1 核心测试

1. **批量扫描测试**
   - 给一个 fixtures 目录；
   - 断言只扫描 `.md`。

2. **批量评分结构测试**
   - 断言返回结果数量正确；
   - 每条结果字段齐全。

3. **批量统计测试**
   - 断言平均分、最高分、最低分计算正确。

4. **排序测试**
   - 断言按分数排序稳定。

5. **失败容忍测试**
   - 某份报告损坏或不可读时，整批仍能继续。

6. **CLI 参数测试**
   - 新参数能进入正确分支；
   - 输出包含 batch summary 关键字段。

---

## 10. 取舍说明

### 10.1 为什么不先做 LLM-as-judge
它虽然“更像人”，但当前阶段会引入：
- 不稳定性；
- 成本；
- prompt 设计问题；
- 新的测试复杂度。

当前更需要的是先把**机械可重复的批量回归能力**补齐。

### 10.2 为什么不先做 golden pattern 条件评分
因为它会把当前阶段从“批量执行”扩成“评测语义升级”。
这条线适合作为阶段 B 的下一子阶段，而不是第一步。

---

## 11. 阶段完成标准

当满足以下条件时，本阶段 B 的这条主线可视为完成：

1. 可以对一个目录中的多份 Markdown 报告一次性跑 golden-case 回归；
2. 能输出终端摘要；
3. 能输出结构化批量结果；
4. 现有单报告评分能力不退化；
5. 有对应测试覆盖批量扫描、汇总和 CLI 入口。

---

## 12. 后续衔接

本子阶段完成后，后面可以顺接两条路线之一：

1. **版本对比摘要增强**
   - 在批量结构化结果之上生成“谁进步/谁退步”的自动总结。

2. **pattern / production rule 收口**
   - 在批量回归能力稳定后，再补 pattern 维度的统计与对齐。
