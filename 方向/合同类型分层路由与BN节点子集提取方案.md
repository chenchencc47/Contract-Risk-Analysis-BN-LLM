# 合同类型分层路由与 BN 节点子集提取方案

> 日期：2026-05-03  
> 状态：方案已确定，待实施

---

## 一、结论先行

当前项目确实需要“按合同类型提取 BN 节点子集”，但**不能做成一次关键词命中后只保留固定 20 个节点的硬裁剪方案**。

更稳妥的做法是：

1. **始终保留通用核心节点**，避免漏掉责任上限、争议解决、解除权、付款、交付、验收等高价值风险；
2. **按合同类型叠加专属节点包**，降低噪音、提高 LLM₁ 审查聚焦度；
3. **按正文触发词补回特殊节点**，避免销售合同里出现煤炭、软件、保密等特殊条款时被误裁；
4. **在低置信度场景自动回退到扩展清单或全量清单**，保证“降噪”而不是“漏检”；
5. **企业红线单独配置**，并区分“硬红线”与“推理指引”，不要把大量商业数字写死成规则。

一句话概括：**路由的目标是降噪，不是删掉世界。**

---

## 二、为什么要做这件事

### 2.1 当前真实问题

当前 `src/contract_risk_analysis/review/ai_review.py` 中 `_build_bn_checklist()` 会把全部 evidence-layer 节点统一展开给 LLM₁。这样做的优点是覆盖面全，但缺点也很明显：

- 销售合同会看到煤炭、采购、软件许可等并不常用的节点；
- LLM₁ 注意力被稀释，容易把真正关键的风险点与低相关节点混在一起；
- `missing_clauses` 和补充建议有时会“写得太满”，像在重写理想合同，而不是聚焦本合同最值钱的风险；
- 报告会出现“泛化补条款”的倾向，例如对所有合同都给出价格调整、保密、任意终止、保险等建议。

### 2.2 设计目标

本方案的目标不是减少 token 本身，而是提高以下三件事：

1. **提高 LLM₁ 的审查聚焦度**：让它先看最 relevant 的节点；
2. **保持风险召回率**：不能因为路由而漏掉特殊但关键的条款；
3. **为企业规则注入做准备**：合同类型路由与公司红线应是同一层配置能力的两面。

---

## 三、设计原则

### 原则 1：通用核心节点永远保留

任何合同都应先检查一批通用核心节点。这些节点不是“某类合同才重要”，而是绝大多数商事合同都高价值：

- `payment_structure`
- `delivery_terms`
- `acceptance_process_clarity`
- `termination_clause_completeness`
- `termination_right_balance`
- `liability_cap_strength`
- `damages_exposure`
- `dispute_resolution_clarity`
- `jurisdiction_fairness`
- `governing_law_clarity`
- `force_majeure_completeness`

这些节点构成 LLM₁ 的“基础骨架”，不能被合同类型路由裁掉。

### 原则 2：合同类型路由做“加权/优先展示”，不做绝对删减

对于销售合同、采购合同、煤炭合同、NDA、软件许可等不同类型，应叠加各自的高相关节点包，但不建议直接删除所有非本类型节点。

更推荐的策略是：

- **核心节点**：强制审查；
- **类型节点**：强制审查；
- **扩展节点**：仅在正文触发或低置信度回退时纳入。

### 原则 3：正文触发词拥有“补回权”

如果合同主类型被识别为“销售合同”，但正文出现以下信号，也要补回对应节点：

- 出现“热值 / 收到基 / 发热量 / kcal” → 补入煤炭节点；
- 出现“技术资料 / 图纸 / 保密信息 / 商业秘密” → 补入保密/IP 节点；
- 出现“调价公式 / 原材料价格波动 / 指数联动” → 补入价格调整节点。

这样才能避免“主类型判断正确，但特殊条款被误删”。

### 原则 4：低置信度必须自动回退

当合同类型识别置信度低、命中多个类型、或类型节点包命中太少时，系统不能硬裁剪，而应回退到：

- **核心节点 + 多类型并集 + 扩展触发节点**，或
- **全量节点清单**。

回退机制的作用是保证“宁可多看，也不要漏看”。

### 原则 5：公司红线与合同类型路由分开建模

“合同类型节点包”解决的是**应该先看什么**；
“公司红线配置”解决的是**看到了以后哪些是不可妥协的底线**。

两者不要混成一个配置文件。

---

## 四、推荐的节点子集提取流程

### Step 0：合同类型候选识别

先识别合同类型候选，而不是一步给出唯一类型。

推荐信息源按优先级排序：

1. **标题 / 文件名 / 首段显式表述**  
   例如“销售合同”“采购合同”“煤炭购销合同”“保密协议”“软件许可协议”。

2. **正文高频行业词**  
   例如：
   - 销售：购销、供货、买卖、收货、发货；
   - 采购：采购、供应商、原料、检验、批次结算；
   - 煤炭：热值、收到基、矿发量、试烧、途耗；
   - NDA：保密、披露、机密信息、返还、存续；
   - 软件许可：授权、SaaS、源代码、许可、接口。

3. **LLM₁ 的弱判断（可选增强，不是前置依赖）**  
   后续可以在 free review 输出中增加 `contract_type_candidates` 和 `confidence` 字段，但这不是首版必需。

输出建议为：

```json
{
  "primary_type": "销售合同",
  "candidates": ["销售合同", "采购合同"],
  "confidence": 0.74,
  "signals": ["购销", "发货", "验收", "质保金"]
}
```

### Step 1：加载通用核心节点

无论合同类型如何，先加载一组 `universal_core` 节点。

这一步的目标是保证：

- 责任上限不会因合同类型路由而消失；
- 争议解决、解除权、付款、交付、验收这类高价值条款不会漏看；
- 系统始终保有基础骨架。

### Step 2：叠加合同类型专属节点包

根据 `primary_type` 和候选类型，把对应节点包做并集。

例如：

- 销售合同包：`risk_transfer_point`、`warranty_scope`、`cuad_warranty_duration`、`cuad_liquidated_damages`、`dispute_venue_fairness`
- 采购合同包：`raw_material_acceptance_std`、`batch_settlement_terms`、`quality_inspection_rights`、`price_adjustment_mechanism`
- 煤炭合同包：`calorific_value_pricing`、`trial_burn_acceptance`、`measurement_dispute_resolution`、`transportation_loss_allocation`

### Step 3：按正文触发词补入特殊节点

对合同全文做一次轻量触发扫描：

- 如果出现强信号词，就把对应节点补入 `triggered_nodes`；
- 这一步优先解决“混合型合同”或“主类型之外夹带特殊条款”的场景。

### Step 4：低置信度回退

出现以下任一情况时，不做激进裁剪：

- `confidence < 0.6`
- 命中两个及以上主类型，且分差很小
- 类型专属节点命中数过少
- 合同标题与正文信号冲突

回退策略：

1. `universal_core + type_union + triggered_nodes`
2. 若仍不足，则直接使用 `all_nodes`

### Step 5：把路由结果显式写入管线与报告

建议把以下元数据保留下来：

- `primary_type`
- `candidate_types`
- `confidence`
- `selected_node_count`
- `triggered_nodes`
- `fallback_mode`

这不仅便于调试，也能在报告或 debug 响应里解释“为什么本次优先审查这些节点”。

---

## 五、推荐配置结构

### 5.1 `config/contract_type_routing.yaml`

建议结构如下：

```yaml
universal_core:
  nodes:
    - payment_structure
    - delivery_terms
    - acceptance_process_clarity
    - termination_clause_completeness
    - termination_right_balance
    - liability_cap_strength
    - damages_exposure
    - dispute_resolution_clarity
    - jurisdiction_fairness
    - governing_law_clarity
    - force_majeure_completeness

contract_types:
  销售合同:
    keywords: [购销, 买卖, 供货, 发货, 收货]
    nodes:
      - risk_transfer_point
      - warranty_scope
      - cuad_warranty_duration
      - cuad_liquidated_damages
      - dispute_venue_fairness
      - cuad_cap_on_liability
      - cuad_uncapped_liability

  采购合同:
    keywords: [采购, 原料, 供应商, 批次结算, 第三方检测]
    nodes:
      - raw_material_acceptance_std
      - batch_settlement_terms
      - quality_inspection_rights
      - price_adjustment_mechanism
      - supply_guarantee_terms
      - inventory_storage_responsibility

  煤炭合同:
    keywords: [煤炭, 热值, 收到基, 试烧, 途耗, kcal]
    nodes:
      - calorific_value_pricing
      - trial_burn_acceptance
      - measurement_dispute_resolution
      - unilateral_inspection_rights
      - transportation_loss_allocation

text_triggers:
  保密信息:
    any_of: [保密, 机密信息, 技术资料, 商业秘密]
    nodes: [confidentiality_nli]

  价格联动:
    any_of: [调价, 价格波动, 指数, 原材料上涨]
    nodes: [price_adjustment_mechanism]

  软件交付:
    any_of: [源代码, license, SaaS, 软件授权]
    nodes: [cuad_source_code_escrow, cuad_license_grant]

fallback:
  low_confidence_threshold: 0.6
  sparse_type_hit_threshold: 3
  mode: expanded_then_full
```

### 5.2 `config/company_redlines.yaml`

建议不要把所有内容都写成“数字型红线”，而是拆成两层：

```yaml
通用:
  hard_rules:
    - id: no_unlimited_liability
      label: 禁止无限责任
      description: 任何合同不得接受无限赔偿责任或无上限直接损失赔偿
      severity: 企业红线

    - id: exclude_indirect_loss
      label: 间接损失必须排除或限制
      description: 应明确排除利润损失、商誉损失、第三方索赔等间接损失
      severity: 企业红线

  reasoning_hints:
    - id: liability_cap_rule
      label: 责任上限按交易规模与风险分配推理
      description: 责任上限比例不得拍脑袋固定，需结合合同金额、标的属性、行业惯例和议价地位判断

销售合同:
  hard_rules:
    - id: retention_not_subjective_acceptance
      label: 质保金不能完全依赖对方主观验收
      description: 尾款或质保金支付节点不能仅由对方单方认定是否“验收合格”决定
      severity: 高

  reasoning_hints:
    - id: acceptance_window_rule
      label: 异议期按标的物可检验性推理
      description: 外观异议期、内在质量异议期应结合瓷砖等标的物的可见性、施工依赖性和行业惯例判断
```

这样做的好处是：

- 红线可落地；
- 不违背“数字必须有依据”的原则；
- LLM 可以把规则解释成企业可接受的话术，而不是机械套数字。

---

## 六、推荐的代码改动点

### 6.1 `src/contract_risk_analysis/review/ai_review.py`

这是首要改动点。

建议新增以下能力：

1. `detect_contract_type_candidates(contract_text) -> ContractTypeRoutingResult`
2. `load_contract_type_routing_config()`
3. `_build_bn_checklist(routing_result=None)`
   - 支持根据路由结果只输出核心 + 类型 + 触发节点
   - 在低置信度时回退输出扩展清单或全量清单
4. `free_review_contract_text(...)`
   - 把路由元数据传给 prompt
   - 可选在返回结果中带回 `routing_metadata`

### 6.2 `backend/main.py`

建议在 `_run_v2_pipeline()` 中新增前置步骤：

1. 识别合同类型候选；
2. 生成节点子集；
3. 读取企业红线；
4. 将 `routing_metadata` 和 `redline_summary` 注入 LLM₁；
5. 在最终响应中透出 debug 元数据。

### 6.3 `src/contract_risk_analysis/domain/free_review_schema.py`

如果希望把路由结果变成正式数据结构，建议增加轻量字段，例如：

- `contract_type`
- `contract_type_confidence`
- `routing_nodes`
- `triggered_redlines`

这一步不是首版必需，但如果后续要做历史分析、前端展示、质量门禁，这些字段会很有价值。

### 6.4 报告输出层（`report_writer.py`）

建议后续补一个简短说明区块，而不是大篇幅暴露实现细节，例如：

- 识别合同类型：销售合同（置信度 0.74）
- 本次优先审查节点：通用核心 11 项 + 销售合同 7 项 + 文本触发 2 项
- 触发企业红线：无限责任、质保金支付依赖主观验收

这样可以增强报告的可解释性，但不要让实现细节压过法律分析正文。

---

## 七、哪些方案不要做

### 不建议 1：固定 20 节点硬裁剪

原因：会漏掉混合型合同和特殊条款。

### 不建议 2：只做关键词匹配，不做回退

原因：标题与正文不一致很常见，纯关键词方案太脆弱。

### 不建议 3：把所有红线写成具体数字

原因：很多数字并无法律依据，属于商业谈判结果，不适合写死。

### 不建议 4：为这件事引入多 agent 架构

原因：当前问题是规则组织和配置层能力，不是 agent 编排问题。

---

## 八、建议的实施顺序

### P0：合同类型分层路由最小闭环

- 新建 `config/contract_type_routing.yaml`
- 在 `ai_review.py` 中实现：
  - 合同类型候选识别
  - 核心节点 + 类型节点包 + 低置信度回退
- `_build_bn_checklist()` 支持输出分层清单

**完成标准：** 销售、采购、煤炭三类合同都能输出“核心+类型”的检查清单，且低置信度时可回退。

### P1：正文触发词补集机制

- 增加 `text_triggers`
- 支持正文出现特殊行业词时补回节点
- 为混合型合同加单测

**完成标准：** “销售合同 + 煤炭条款”“采购合同 + 保密附件”这类混合文本不会漏掉特殊节点。

### P2：企业红线配置化

- 新建 `config/company_redlines.yaml`
- 区分 `hard_rules` 与 `reasoning_hints`
- 在 LLM₁ prompt 中注入匹配到的红线

**完成标准：** 报告能区分“企业红线”与“一般优化建议”。

### P3：路由元数据透出与质量门禁联动

- 在 API debug 响应中输出 `routing_metadata`
- 当低置信度回退或节点数异常时，写入 `quality_gate.warnings`
- 后续可接前端展示

**完成标准：** 系统可解释“这次为什么优先看这些节点”。

---

## 九、验收标准

实施完成后，至少应满足：

1. 销售合同不会再默认把煤炭、软件许可等节点全部强制列为主审对象；
2. 混合型合同出现特殊条款时，对应节点能被补回；
3. 低置信度场景不会因为路由而漏检；
4. 报告中的“缺失条款”数量更聚焦，不再为了展示而泛化补全；
5. 企业红线能够作为独立规则层注入，而不是继续散落在 prompt 文案里；
6. 方案不违背项目现有原则：**先保覆盖，再做降噪；先保可信，再做产品化。**

---

## 十、与当前项目路线的关系

这项工作不是为了替代 v2.7 的“LLM₁ 覆盖强制化”，而是建立在它之上的下一层增强。

两者关系应当是：

- **v2.7 解决“不能静默跳过”**；
- **本方案解决“即使全回应，也不要把噪音节点和关键节点混成一锅”**；
- **公司红线配置化则进一步解决“哪些问题是企业底线，哪些只是一般建议”**。

因此，这项工作的正确定位是：

> **在不牺牲覆盖率的前提下，提高 LLM₁ 审查聚焦度，并为企业级规则化输出铺路。**
