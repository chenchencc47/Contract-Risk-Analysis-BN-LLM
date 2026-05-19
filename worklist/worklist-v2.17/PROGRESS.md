# 实施进度记录（v2.17）

> 最后更新：2026-05-18（release/v2.17 竣工推送）

---

## 当前状态

- **当前分支**：`release/v2.17`（已推送）
- **阶段 F 已全部完成**。v2.17 在 v2.8 基础上完成：BN 节点 55→90、合同类型 3→10、法条引用增强、角色自动检测、轻量模式修复。
- **下次继续入口**：第一层第 1 项（劳动/工程/借款合同红线规则）

---

## v2.17 版本演进总览

```
v2.8 (基线)
 ├─ 阶段 D: 买卖合同基线收口 + 跨合同类型泛化验证
 │    ├─ v2.13: 谈判阈值去硬编码
 │    ├─ v2.14: P0-P2 质量提升
 │    └─ v2.15: -23 报告 + 六方评测
 │
 ├─ 阶段 E: BN自适应可信度分层 + 跨合同类型证据收口
 │    ├─ E-1: bn_confidence 三级分层 (high/medium/low)
 │    ├─ E-2: contract_type_routing 链路修复 (3→7种)
 │    ├─ E-3: 租赁合同专项红线规则
 │    └─ E-4: 轻量合同报告框架自适应简化
 │
 └─ 阶段 F: 数据集利用 + BN扩展 + 法条增强 + 角色检测
      ├─ F-1: LEDGAR 100类标签→BN节点映射 (55→90节点)
      ├─ F-2: chinese_contract_templates 条款分布验证
      ├─ F-3: DISC-Law-SFT 法条引用注入 LLM₁ prompt
      ├─ 合同类型 7→10 (劳动/工程/借款)
      ├─ 角色自动检测 (前端+后端)
      ├─ 轻量模式修复 (仅 risk≤3 触发)
      └─ 全量回归验证 + ChatGPT 评测交叉验证
```

---

## 阶段 E 详细记录

### E-1: bn_confidence 三级分层

| 资产类型 | bn_confidence | 维度对数量 | 效果 |
|---------|:--:|:--:|------|
| standard_equipment | high | 6对 | 完整量化展示 |
| custom_equipment / bulk_commodity | medium | 3对 | 简化表格 |
| light_service | low | 2对 | 方向性描述，无数字表格 |

涉及文件：`contract_type_parameters.yaml`, `consistency_validator.py`, `report_writer.py`, `ai_review.py`, `review.py`, `dual.py`

### E-2: 合同类型路由扩展

原只有 3 种（销售/采购/煤炭）→ 新增 4 种（技术开发/服务/租赁/保密协议）。
修复 `low_confidence_threshold` 0.6→0.25，避免关键词多的类型匹配失败。
修复 `cuad_non_solicit`→`cuad_no_solicit` 节点名。

涉及文件：`contract_type_routing.yaml`

### E-3: 租赁合同红线规则

新增 6 条 hard_rules：押金退还时限、逾期腾房违约金上限、配合融资不得触发立即解约、年付租金须有担保、装修添附物权属、维修责任划分。
新增 4 条 reasoning_hints：租金调涨透明、转租权合理、水电实报实销、提前解约对等。

涉及文件：`company_redlines.yaml`

### E-4: 轻量模式

触发条件：`risk_count <= 3`（不再与 bn_confidence 挂钩）。
实际效果：只有保密协议触发精简模式。

涉及文件：`report_writer.py`

---

## 阶段 F 详细记录

### F-1: LEDGAR → BN 节点映射

- 翻译 LEDGAR 100 类英文条款标签
- 39 类已有对应 BN 节点
- 21 类新增为通用节点（universal_core）
- 14 类新增为合同专属节点
- 26 类不适用（美国法律特有/雇佣条款）
- 5 个低频节点从 universal_core 降级为 text_triggers

涉及文件：`bayesian_network_v2.json`, `contract_type_routing.yaml`, `scripts/ledgar_bn_mapping.py`, `scripts/add_ledgar_nodes.py`

### F-2: 中文合同范本验证

- 10K 份范本中 ~3,500 份可分类（"其他"6,500份含大量非合同内容）
- 新节点在对应类型的真实范本中覆盖率 30%-90%
- 发现 `cuad_contra_proferentem` 等 3 个节点关键词不足 → 补关键词
- 发现 5 个节点在中文合同中真实低频 → 降级为 text_triggers

涉及文件：`scripts/validate_bn_coverage.py`

### F-3: 法条引用增强

- 从 DISC-Law-SFT 33,853 条合同相关 QA 提取法律条文引用
- 数据集实际以婚姻法为主，合同法信号占比小
- 提取 7 条核心合同法条文注入 LLM₁ prompt：
  第585条(违约金)、第496/497条(格式条款)、第563条(解除)、第527条(不安抗辩)、第577条(违约)、第604条(风险转移)
- 效果：报告法条引用从"根据相关法律规定"变为精准引用

涉及文件：`ai_review.py`, `scripts/build_legal_reference.py`, `config/legal_reference_from_disc_law_sft.txt`

### 合同类型扩展

- 新增 3 种：劳动/聘用合同、工程承包/施工合同、借款/抵押/担保合同（10 节点/种）
- 现有类型关键词扩充：销售(+3)、采购(+4)、服务(+3)、租赁(+3)

涉及文件：`contract_type_routing.yaml`

### 角色自动检测

- 后端：`detect_party_roles()` 从合同文本提取甲方/乙方角色标签
- API：`POST /api/detect-party-roles`
- 前端：上传/粘贴合同后自动检测，选择器显示动态标签
- LLM 收到"贵司（承租方）"而非"甲方（买方）"，解决租赁合同身份混淆

涉及文件：`ai_review.py`, `misc.py`, `report_writer.py`, `ContractInput.tsx`, `App.tsx`, `useReview.ts`

### 全量回归验证

| 合同 | 风险数 | 法条引用 | 轻量模式 | 验证结论 |
|------|:--:|:--:|:--:|------|
| 技术开发 | 8 | 24 | — | F-3 生效，第585条正确引用 |
| 保密协议 | 2 | 1 | ✅ | 轻量模式正常 |
| 服务合同 | 5 | 30 | — | BN数字表正确抑制 |
| 租赁合同 | 4 | 48 | — | F-3 显著，LLM₁ 标注了 4 个 legal_basis |
| 买卖合同 | — | — | — | 回归测试 67 passed |

---

## 数据集入库

| 数据集 | 规模 | 用途 |
|--------|-----:|------|
| chinese_contract_templates | 10,000 份 | 条款分布验证、关键词覆盖检查 |
| DISC-Law-SFT Pair QA | 79,692 条 | 法条引用提取（合同相关约 6,400 条） |
| DISC-Law-SFT Triplet QA | 23,331 条 | 同上（合同相关约 4,400 条） |
| LEDGAR | 80,000 条 | 合同条款分类标签体系参考 |
| ALeaseBert | 257 份 | 租赁合同 NER 标注 schema 模板 |

---

## 下次继续入口

→ WORKLIST.md 第一层第 1 项：新合同类型红线规则（`company_redlines.yaml`）
