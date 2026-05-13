# Golden Case / Golden Pattern CLI 使用手册

> 适用项目：BN-Contract-Risk-Analysis  
> 用途：离线评测报告质量、查看已沉淀的泛化规则。  
> 注意：这些命令用于项目测试和回归评测，不参与真实合同审查链路。

---

## 1. 功能概览

当前 CLI 支持两类 golden 评测相关能力：

| 命令 | 用途 |
|---|---|
| `--score-golden-case` | 用指定 golden case 评测一份 Markdown 报告 |
| `--list-golden-patterns` | 查看当前已沉淀的 golden patterns 元数据 |

核心区别：

```text
golden case
= 固定合同样本的回归测试
= 检查系统改动后是否把已知样本做差

golden pattern
= 从多个样本抽象出的可泛化风险模式
= 用于后续沉淀 production rules
```

---

## 2. 运行前提

请在项目根目录执行命令：

```bash
E:/myProgram/BN-Contract-Risk-Analysis
```

建议使用项目虚拟环境 Python：

```bash
.venv/Scripts/python.exe
```

完整命令形式：

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli <参数>
```

---

## 3. 对单份报告进行 Golden Case 评分

### 3.1 基本命令

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli \
  --score-golden-case tests/fixtures/golden_cases/sales_purchase_contract_001.yaml \
  --report 合同检测报告/买卖合同/contract-review-买卖合同-10.md
```

含义：

- 使用 `sales_purchase_contract_001.yaml` 作为标准答案；
- 检查 `contract-review-买卖合同-10.md` 是否命中该样本的关键点；
- 输出 JSON 评分结果。

---

### 3.2 参数说明

| 参数 | 必填 | 说明 |
|---|:--:|---|
| `--score-golden-case` | 是 | golden case YAML 文件路径 |
| `--report` | 是 | 要评测的 Markdown 报告路径 |

如果只传 `--score-golden-case`，不传 `--report`，CLI 会报错：

```text
--score-golden-case requires --report
```

---

### 3.3 输出示例

输出为 JSON，结构类似：

```json
{
  "case_id": "sales_purchase_contract_001",
  "report_path": "合同检测报告/买卖合同/contract-review-买卖合同-10.md",
  "score": 86.67,
  "summary": {
    "must_find": "4/5",
    "must_not": "4/4",
    "should_find_advantages": "3/5"
  },
  "must_find": [],
  "must_not": [],
  "should_find_advantages": []
}
```

---

### 3.4 输出字段解释

| 字段 | 说明 |
|---|---|
| `case_id` | 使用的 golden case 编号 |
| `report_path` | 被评测报告路径 |
| `score` | 基础规则评分，满分 100 |
| `summary.must_find` | 必须识别项命中数量 |
| `summary.must_not` | 禁止错误通过数量 |
| `summary.should_find_advantages` | 建议识别优势命中数量 |
| `must_find` | 每个必须识别项的命中详情 |
| `must_not` | 每个禁止错误的违规详情 |
| `should_find_advantages` | 每个建议优势项的命中详情 |

---

## 4. 评分规则

当前基础评分器采用加权规则：

| 类型 | 权重 | 含义 |
|---|---:|---|
| `must_find` | 3 | 应该识别出的关键风险或核心点 |
| `must_not` | 3 | 绝不能犯的方向性错误 |
| `should_find_advantages` | 1 | 建议识别的优势或加分点 |

计算方式：

```text
得分 = 已命中加权分 / 总加权分 × 100
```

例如：

```text
must_find 4/5
must_not 4/4
should_find_advantages 3/5

得分 = (4×3 + 4×3 + 3×1) / (5×3 + 4×3 + 5×1) × 100
```

---

## 5. 如何理解 must_find / must_not / should_find_advantages

### 5.1 must_find

表示这份固定样本中报告必须识别的关键点。

例如买卖合同：

```yaml
must_find:
  - 80%预付款且无担保
  - 质保金/保证金提交晚于预付款
  - 初验即视为交付
```

如果漏掉，说明报告在该样本上有明显退步。

---

### 5.2 must_not

表示报告绝不能犯的方向性错误。

例如买方视角下：

```yaml
must_not:
  - 不得把乙方无责任上限直接定性为甲方风险
  - 不得把 BN 责任上限反事实解释为买方主动修改目标
```

如果触犯，通常比漏掉一个普通风险更严重。

---

### 5.3 should_find_advantages

表示最好识别出的优势或加分点。

例如：

```yaml
should_find_advantages:
  - 甲方住所地法院管辖
  - 未排除间接损失
  - 发票前置付款条件
```

漏掉不一定说明报告不可用，但会影响完整性和策略价值。

---

## 6. 查看当前 Golden Patterns

### 6.1 基本命令

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli --list-golden-patterns
```

输出当前 `tests/fixtures/golden_patterns/` 下已沉淀的 pattern 元数据。

---

### 6.2 指定 patterns 目录

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli \
  --list-golden-patterns \
  --golden-patterns-dir tests/fixtures/golden_patterns
```

---

### 6.3 输出示例

```json
{
  "patterns": [
    {
      "pattern_id": "high_prepayment_without_security",
      "pattern_name": "高额预付款且无有效担保",
      "status": "candidate",
      "source_cases": ["sales_purchase_contract_001", "sales_contract_001"],
      "applies_to": {
        "contract_types": ["买卖合同", "采购合同", "销售合同"],
        "review_stances": ["buyer", "seller"]
      }
    }
  ]
}
```

---

## 7. Golden Case 与 Golden Pattern 的边界

不要把 golden case 当成真实审查规则。

```text
golden case：
  针对某一份固定合同的标准答案。
  用于反复测试系统是否退步。

golden pattern：
  从多个样本中抽象出来的通用风险模式。
  用于未来提炼 production rule。

production rule / party-aware rule：
  真实合同审查时使用的裁决规则。
```

例如：

```text
sales_purchase_contract_001 中有 80% 预付款。
这不代表所有买卖合同都必须识别“80%预付款”。

可泛化的是：
如果合同存在高额预付款且无有效担保，
买方视角应识别为高风险或致命风险。
```

---

## 8. 常用示例

### 8.1 评测买卖合同报告 -10

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli \
  --score-golden-case tests/fixtures/golden_cases/sales_purchase_contract_001.yaml \
  --report 合同检测报告/买卖合同/contract-review-买卖合同-10.md
```

### 8.2 评测销售合同报告 -15

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli \
  --score-golden-case tests/fixtures/golden_cases/sales_contract_001.yaml \
  --report 合同检测报告/销售合同/contract-review-销售合同-15.md
```

### 8.3 查看所有泛化模式

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli --list-golden-patterns
```

---

## 9. 当前限制

当前 CLI 是基础版，有以下限制：

1. 主要基于关键词命中，不等同于完整语义理解；
2. `golden_patterns` 目前只支持元数据列表，还没有做条件命中评分；
3. 暂不支持批量评测整个文件夹；
4. 暂不支持 LLM-as-judge；
5. 对 PDF 合同原文不做直接证据核验，只评测报告 Markdown。

---

## 10. 后续计划

建议后续增强：

1. 批量评测某个目录下的所有报告；
2. 输出 Markdown 格式评分报告；
3. 支持 golden pattern 条件命中评分；
4. 接入受约束的 LLM-as-judge；
5. 将成熟 golden pattern 对齐到 `party_aware_rules.yaml` 和 Dossier 裁决层。
