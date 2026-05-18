# BN-Contract-Risk-Analysis 工作清单（v2）

> 最后更新：2026-05-18（BN自适应可信度分层 + 跨合同类型证据收口）

---

## 使用说明

- `WORKLIST.md`：记录各阶段要做什么、做到什么算完成。
- `PROGRESS.md`：记录已经做了什么、做到哪一步、下次从哪里继续。
- 已完成事项只写入 `PROGRESS.md`；`WORKLIST.md` 只维护当前和后续待实施内容。

---

## 当前总目标

阶段 D 跨合同类型泛化验证已完成（5 类合同 + 1 组双视角对比），明确了系统在买卖合同外的问题：BN 乘数效应数值在新合同类型上可信度不足、部分维度对硬编码、合同类型路由的部分节点未被触发。

当前主线：**阶段 E：BN 自适应可信度分层 + 跨合同类型证据收口**

```text
阶段 E：BN 自适应可信度分层 + 跨合同类型证据收口
→ E-1：bn_confidence 分层机制 + 维度对配置化（当前）
→ E-2：contract_type_routing 链路排查（源码托管/SLA 等节点未触发）
→ E-3：company_redlines.yaml 补充租赁合同专项
→ E-4：轻量合同报告框架自适应简化
```

当前对应计划文件：
- `docs/superpowers/specs/2026-05-18-bn-adaptive-confidence-design.md`

---

### E-1：bn_confidence 分层机制 + 维度对配置化（当前执行）

| 编号 | 实施项 | 涉及文件 | 完成标准 |
|:--:|------|---------|---------|
| E-1a | `contract_type_parameters.yaml` 加 `bn_confidence` 字段（high/medium/low） | `config/contract_type_parameters.yaml` | 四种资产类型均有标注 |
| E-1b | `contract_type_parameters.yaml` 加 `bn_dimension_pairs` 段（universal + optional） | `config/contract_type_parameters.yaml` | 维度对从代码移入配置 |
| E-1c | `consistency_validator.py` 从配置读取维度对 + 按 bn_confidence 选择数量 | `src/contract_risk_analysis/bn/consistency_validator.py` | high=6对, medium=3对, low=2对 |
| E-1d | `contract_type_routing.yaml` 各合同类型加 `bn_config_override: null` 占位 | `config/contract_type_routing.yaml` | 扩展点文档化 |
| E-1e | `report_writer.py` Ch.2/Ch.4 按 bn_confidence 调整展示深度 | `src/contract_risk_analysis/review/report_writer.py` | low时无数字表格、prompt措辞区分 |
| E-1f | `bn_mapping.py` `CROSS_DIMENSION_RISK_PAIRS` 加注释标注为通用回退 | `src/contract_risk_analysis/bn/bn_mapping.py` | 注释说明未来可配置化 |
| E-1g | 运行现有聚焦回归，确保 `bn_confidence=high` 行为不变 | 测试 | 全部通过 |

### E-2：contract_type_routing 链路排查（待 E-1 完成后启动）

| 编号 | 实施项 | 涉及文件 | 完成标准 |
|:--:|------|---------|---------|
| E-2a | 排查技术开发合同为何未触发 `cuad_source_code_escrow` / `cuad_license_grant` | `bn_mapping.py`, `contract_type_routing.yaml` | 定位根因 |
| E-2b | 排查服务合同 light_service context 是否注入到 LLM prompt | `report_writer.py` | context 字符串确认到位 |
| E-2c | 修复后重跑技术开发合同和服务合同验证 | 报告对比 | 缺失节点出现 |

### E-3：company_redlines.yaml 补充租赁合同专项（待 E-1 完成后启动）

增加租赁合同专属红线规则（押金保护、转租权、维修责任划分等）。

### E-4：轻量合同报告框架自适应简化（待 E-1 完成后启动）

保密协议等简单合同不套用完整的8章重型框架，BN章节按 `bn_confidence=low` 自动精简。

---

## 下一阶段候选

### 阶段 F：数据集扩充与 BN CPT 校准增强

**前提：** 获得新合同类型的结构化数据（网上公开数据集 或 社区贡献）

**方向：**
1. 为租赁/服务/技术开发合同收集训练数据
2. 运行 CPT 校准脚本生成合同类型特定参数
3. 将对应 `bn_confidence` 从 low 翻为 high

---

## 续做规则

- 每完成一个阶段或关键子任务，就在 `PROGRESS.md` 顶部追加记录；
- `WORKLIST.md` 只保留未完成阶段与后续候选，不重复写历史实现细节；
- 如果开始新阶段，先更新本文件的”当前总目标/当前主线状态/下次继续建议”。
- 每次 `PROGRESS.md` 续写时在顶部更新”下次继续入口”
