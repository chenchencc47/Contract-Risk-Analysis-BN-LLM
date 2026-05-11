# LLM₁ JSON 稳定性与 negotiation_chip 结构化设计

## 背景

当前 `/api/v2/review` 的 LLM₁ 自由审查阶段存在两类耦合问题：

1. LLM 返回内容偶发不是严格合法 JSON，导致 `src/contract_risk_analysis/review/ai_review.py` 中 `json.loads(...)` 失败，最终在 `backend/routers/review.py` 返回 422。
2. `negotiation_chip` 字段在 prompt、schema、Python dataclass、后处理逻辑和报告渲染层之间没有统一契约：
   - prompt 语义要求它承载结构化信息
   - `_free_review_schema()` 目前把它定义为 `string | null`
   - 实际运行中 LLM 可能返回对象
   - `report_writer.py` 和部分测试又把它当字符串处理

这两个问题叠加后，造成 LLM₁ 输出不稳定、下游字段解释不一致，并放大了整条 `/api/v2/review` 管线的失败概率。

## 目标

本设计只解决 LLM₁ 输出契约稳定性，不扩展到整条审查管线重构。

目标如下：

1. `negotiation_chip` 在模型、schema、解析层、后处理层、报告层、API 输出层统一为单一主形态。
2. LLM₁ 偶发一次非法 JSON 时，不应直接导致整单失败。
3. 下游代码不再以字符串包含判断为核心处理 `negotiation_chip`。
4. 报告渲染保持现有业务语义，但读取结构化字段而非自由字符串。
5. 迁移范围保持在 free-review 调用链，避免无关重构。

## 非目标

以下内容不在本次设计范围内：

- 重写整套 LLM₁ 提示词策略
- 更换 LLM 供应商或 OpenAI 兼容层
- 大范围改写报告模板与前端展示设计
- 重构 BN 推理、canonicalize、adjudicate 的职责边界
- 引入长期双格式兼容方案

## 推荐方案

采用“结构化对象 + 入口窄兼容 + 单次 JSON 重试”的方案。

- `negotiation_chip` 统一升级为结构化对象
- `free_review_contract_text()` 保留一次针对 JSON 解析失败的重试
- 仅在 free-review 解析入口允许短期兼容旧字符串形态
- 解析后的内部世界全部按对象处理
- API 输出以对象为真实契约

不采用“长期字符串/对象双格式共存”，因为这会延续当前的不稳定根因。

## 数据模型设计

在 `src/contract_risk_analysis/domain/free_review_schema.py` 中新增结构化类型 `NegotiationChip`：

- `chip_type`: `"底线筹码" | "交换筹码" | "响应筹码"`
- `location`: `str | None`
- `reason`: `str | None`
- `counterparty_attack`: `str | None`
- `strategy`: `str | None`

并统一更新以下字段：

- `RiskSegment.negotiation_chip: NegotiationChip | None`
- `DossierRiskItem.negotiation_chip: NegotiationChip | None`

### 设计原则

1. 存储结构化，展示时再转成中文句子。
2. 对象字段固定，内容允许为 `null`，但字段形状不漂移。
3. 不再把 `negotiation_chip` 作为自由文本黑盒传递。

## 调用链设计

### 1. LLM₁ 输入/输出契约

修改 `src/contract_risk_analysis/review/ai_review.py`：

- `_free_review_schema()` 中将 `negotiation_chip` 从 nullable string 改为 nullable object
- `_free_review_prompt()` 中把 `negotiation_chip` 的输出要求写成明确对象结构，而不是仅用自然语言描述
- `free_review_contract_text()` 保留一次针对 `JSON 解析失败` 的重试

### 2. 解析层

在 `_parse_free_review_payload()` 中：

- 如果 `negotiation_chip is None`，则保持 `None`
- 如果 `negotiation_chip` 是 dict，则解析为 `NegotiationChip`
- 如果 `negotiation_chip` 是 str，则在迁移期包成降级对象
- 其他类型视为无效输入并按解析失败处理

解析完成后，下游只看到 `NegotiationChip | None`。

### 3. 后处理层

修改 `src/contract_risk_analysis/review/adjudicate.py`：

- 任何给 `seg.negotiation_chip` 赋值的逻辑都改为写入 `NegotiationChip` 对象
- 不再写入裸字符串

### 4. 报告渲染层

修改 `src/contract_risk_analysis/review/report_writer.py`：

- 显式读取 `chip_type`、`reason`、`strategy` 等字段
- 移除把 `negotiation_chip` 当字符串做 `in` 判断的核心分支
- 渲染时再将结构化对象转为报告文本

### 5. API 输出层

修改 `backend/routers/review.py`：

- `free_review.risk_segments[*].negotiation_chip` 输出对象或 `null`
- `fact_sheet.risk_items[*].negotiation_chip` 输出对象或 `null`

API 契约的真实形态是对象，不再以字符串为标准。

## 兼容策略

本次迁移采用“单次统一迁移 + 入口窄兼容”，不引入长期双格式兼容。

### 入口兼容规则

仅在 `_parse_free_review_payload()` 允许以下兼容：

- `None` → `None`
- `dict` → 标准 `NegotiationChip`
- `str` → 降级包装为 `NegotiationChip`

建议字符串降级映射如下：

- 优先把原字符串写入 `reason`
- 如果字符串等于 `底线筹码` / `交换筹码` / `响应筹码`，同时填充 `chip_type`
- 其余字段设为 `None`

### 兼容边界

- 兼容仅存在于解析入口
- 一旦进入 dataclass / report_writer / router / tests，下游全部按对象处理
- 不新增“字符串或对象都可以”的长期业务分支

## 错误处理设计

### JSON 稳定性

保留当前已经验证过的最小修复：

- 当 LLM₁ 首次返回非法 JSON 且报 `JSON 解析失败` 时，自动重试一次
- 第二次仍失败，则保留原始错误向上抛出
- 除 `JSON 解析失败` 外的错误不做吞并式重试

### 字段结构错误

对于 `negotiation_chip`：

- `dict` 但关键结构不合法 → 解析失败
- `str` → 仅在解析入口做降级包装
- 非 `dict` / `str` / `null` → 解析失败

原则是：允许迁移缓冲，不允许脏类型在系统内扩散。

## 测试设计

### 1. 解析单测

放在 `tests/review/test_ai_review.py`：

- 合法对象可成功解析
- `None` 可成功解析
- 非法对象按预期失败
- 首次非法 JSON、二次成功时可重试通过
- 连续两次非法 JSON 时继续报错

### 2. 迁移兼容单测

验证旧字符串输入：

- 旧字符串能被包成降级 `NegotiationChip`
- 下游逻辑读取到的始终是对象

### 3. 报告回归测试

补充或更新 `report_writer` 相关测试：

- 正确渲染 `chip_type`
- 正确渲染 `reason` / `strategy`
- 不再依赖字符串包含判断

### 4. 接口级验证

使用真实 `/api/v2/review` 请求验证：

- 返回 200
- `free_review.risk_segments[*].negotiation_chip` 为对象或 `null`
- `fact_sheet.risk_items[*].negotiation_chip` 为对象或 `null`
- 不再因单次坏 JSON 直接 422

## 验收标准

满足以下条件即可验收：

1. `negotiation_chip` 在模型、schema、解析、后处理、报告层、API 输出层只有一种主形态：对象。
2. LLM₁ 单次非法 JSON 不再直接导致整单失败。
3. `report_writer.py` 不再将 `negotiation_chip` 当作字符串核心处理。
4. 相关单测、回归测试通过。
5. 本地真实接口验证通过。

## 影响范围

预计会触及以下文件：

- `src/contract_risk_analysis/domain/free_review_schema.py`
- `src/contract_risk_analysis/review/ai_review.py`
- `src/contract_risk_analysis/review/adjudicate.py`
- `src/contract_risk_analysis/review/report_writer.py`
- `backend/routers/review.py`
- `tests/review/test_ai_review.py`
- 可能涉及少量回归/稳定性测试文件

## 风险与缓解

### 风险 1：报告渲染逻辑仍有隐藏字符串假设

缓解：在 `report_writer.py` 中做全文搜索和针对性测试，移除字符串包含判断。

### 风险 2：旧测试数据仍使用字符串

缓解：统一迁移测试夹具；仅在解析入口保留短过渡兼容。

### 风险 3：模型仍偶发返回非严格 JSON

缓解：保留一次重试；同时通过更明确的对象字段说明降低出错概率。

## 实施顺序建议

1. 引入 `NegotiationChip` dataclass 并更新领域模型
2. 更新 `_free_review_schema()` 与 prompt 字段说明
3. 更新 `_parse_free_review_payload()`，实现对象解析与入口兼容
4. 更新 `adjudicate.py` 写入逻辑
5. 更新 `report_writer.py` 渲染逻辑
6. 更新 `backend/routers/review.py` 输出结构
7. 更新并补齐测试
8. 跑单测与接口级验证
