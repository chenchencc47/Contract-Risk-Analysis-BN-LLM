# BN-Contract-Risk-Analysis 工作清单（v2.17）

> 最后更新：2026-05-18（release/v2.17 推送）

---

## 当前总目标

v2.17 已完成 BN 节点扩展（55→90）、合同类型覆盖（3→10）、法条引用增强、角色自动检测。
下一阶段目标：**质量收口 + 开源发布准备**。

---

## 待实施项

### 第一层：立即执行（低投入，高收益）

| 编号 | 事项 | 说明 | 涉及文件 |
|:--:|------|------|---------|
| 1 | **新合同类型红线规则** | 劳动/工程/借款 3 种新类型没有 `company_redlines.yaml` 规则 | `config/company_redlines.yaml` |
| 2 | **全量回归验证** | 用修复后的系统（角色检测+轻量修复）重跑 5 份合同类型，确认身份混淆已解决 | 手动运行 |
| 3 | **GitHub README** | 项目架构、10 种合同类型覆盖、BN 90 节点、快速开始指引 | `README.md` |

### 第二层：中期规划（中投入）

| 编号 | 事项 | 说明 | 涉及文件 |
|:--:|------|------|---------|
| 4 | **合同范本数据清洗** | 从 chinese_contract_templates 筛出真正的合同（~3,500 份，剔除演讲稿/读后感等），做条款类型分布统计 | `scripts/` |
| 5 | **BN 边关系补全** | 当前 90 节点只有独立 CPT 没有边——需要为新增节点建立到 aggregate→risk_dimension 的边 | `config/bayesian_network_v2.json` |
| 6 | **前端角色选择器优化** | 未识别到角色时显示通用"甲方 / 乙方"（当前已做）；识别到角色后可加一个确认提示 | `frontend/src/components/ContractInput.tsx` |

### 第三层：需要数据（高投入，远期）

| 编号 | 事项 | 说明 |
|:--:|------|------|
| 7 | **中文合同 CPT 校准** | 需要中文合同标注数据。目前无公开数据集可用。开源后社区贡献可能是一个途径 |
| 8 | **ALeaseBert schema 复用** | 翻译好的 25 个实体标注体系留作模板，等中文租赁标注数据到位后复用 |
| 9 | **DISC-Law-SFT 微调** | 103K 中文法律 QA 可用于微调 LLM，但工程成本高，暂不推荐个人项目做 |

---

## 当前架构总览

```
合同类型路由: 10 种
  ├─ 销售合同    ├─ 技术开发合同  ├─ 劳动/聘用合同
  ├─ 采购合同    ├─ 服务合同      ├─ 工程承包/施工合同
  ├─ 煤炭合同    ├─ 租赁合同      └─ 借款/抵押/担保合同
  └─ 保密协议

BN 节点: 90 个
  ├─ universal_core: 32 节点 (11 原有 + 21 LEDGAR)
  ├─ contract-type-specific: 14 节点
  ├─ text_triggers: 4 组低频节点
  └─ CPT 来源: CUAD实证 / expert_estimated(LEDGAR) / expert_estimated

数据集:
  ├─ chinese_contract_templates: 10K 中文合同范本
  ├─ DISC-Law-SFT: 103K 中文法律QA
  ├─ LEDGAR: 80K 英文合同条款分类
  └─ ALeaseBert: 257 英文租赁NER

管线:
  LLM₁(自由审查+法条速查) → BN(90节点一致性校验) → LLM₂(受约束报告渲染)
    ↑ party_role_label                            ↑ bn_confidence分层
    ↑ 合同类型路由                                   ↑ 轻量模式(risk≤3)
```

---

## 续做规则

- 每完成一个事项，更新本文件和 PROGRESS.md
- 完成的事项从 WORKLIST.md 移除，写入 PROGRESS.md
- 数据集改动较大时先创建新分支（如 release/v2.18）再提交
