# ContractLens — AI 合同风险智能审查系统

基于 **LLM + 贝叶斯网络** 双引擎的合同风险检测与反事实分析系统，面向中国合同场景。

> LLM₁ 自由审查 → BN 概率推理 + 反事实模拟 → LLM₂ 综合报告

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)

---

## 为什么需要这个项目

中国企业在签合同时面临两个实际问题：

1. **律师不够用。** 中小企业日常合同量大，律师只能审最重要的几份，其余"看看就签"。
2. **AI 审合同说不清为什么。** 市面上的 AI 审合同工具能找出问题，但给不出量化依据——"这条有风险"是主观判断，"修了这条风险从高降到中"才是可验证的结论。

ContractLens 用**贝叶斯网络做校验层**，解决的就是第二个问题。它不只是"找到风险"，而是告诉你：

> *"如果把无限赔偿责任改成上限 100 万，整体高风险概率从 43.8% 降到 25.6%，降幅 18.2 个百分点。"*

这个数字不是 LLM 拍脑袋给的——是 pgmpy 变量消元在你的合同证据上精确计算的后验概率差值。

---

## 核心差异化

| | 纯 LLM | 传统规则引擎 | **ContractLens** |
|---|---|---|---|
| 中文合同支持 | 取决于模型 | 弱 | **强（10 种中国合同类型）** |
| 可解释性 | 弱（黑箱） | 强 | **强（116 节点 BN 推理链可追溯）** |
| 反事实推理 | 不支持 | 不支持 | **支持（修 X 条款 → 风险降 Y%）** |
| 不确定性量化 | 无 | 无 | **支持（P(high)=73%，非简单"高风险"）** |
| 买方/卖方双视角 | 需手动切换 | 不支持 | **一键生成两份报告 + 差异对比** |
| 中国民法典引用 | 可能编造 | 固定模板 | **从 DISC-Law-SFT 提取 7 条核心法条** |
| 概率数字溯源 | 无 | 无 | **每个数字标注来源（数据/专家）** |
| 数据自主可控 | 依赖云服务 | 本地部署 | **开源本地部署，数据不出境** |

---

## 快速开始

### 体验 Demo（无需 API Key、无需数据库）

```bash
git clone https://github.com/chenchencc47/Contract-Risk-Analysis-BN-LLM.git
cd Contract-Risk-Analysis-BN-LLM
pip install -e .

# 启动后端
python -m uvicorn backend.main:app --port 9527

# 新终端，启动前端
cd frontend && npm install && npm run dev

# 浏览器打开 http://localhost:5173，点击「体验 Demo」
```

Demo 展示了一份买卖合同预计算审查报告，包含完整的 BN 反事实分析数据。

### 完整部署（需要 API Key + MySQL）

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和数据库连接信息

python -m uvicorn backend.main:app --port 9527 --reload
cd frontend && npm run dev
```

MySQL 不可用时审查仍然正常返回结果，只是不保存历史记录。Demo 模式完全不需要数据库。

### Docker

```bash
docker compose up
```

API 文档：http://localhost:9527/docs

---

## 架构

```
┌──────────────────────────────────────────────────────┐
│  合同文本输入（支持粘贴文本或上传文件）                   │
│         │                                             │
│         ▼                                             │
│  ┌─────────────────────────────┐                     │
│  │ LLM₁：自由审查               │                     │
│  │ · 合同类型自动识别（10种）    │  角色自动检测        │
│  │ · 风险条款提取 + 分类        │  （甲方/乙方）       │
│  │ · 中国民法典条文速查          │                     │
│  └─────────────┬───────────────┘                     │
│                │                                      │
│                ▼                                      │
│  ┌─────────────────────────────┐                     │
│  │ BN：概率推理引擎             │  pgmpy VE 精确推理  │
│  │ · 条款 → 116 节点映射        │  126 条边           │
│  │ · 后验概率计算（5 维度）     │  5 个风险维度       │
│  │ · 反事实模拟                 │  67% CPT 数据驱动   │
│  └─────────────┬───────────────┘                     │
│                │                                      │
│                ▼                                      │
│  ┌─────────────────────────────┐                     │
│  │ LLM₂：综合报告生成           │                     │
│  │ · BN 数据注入 + 立场锚定     │  公司红线自动执行    │
│  │ · 反事实建议排序             │  谈判策略生成        │
│  │ · 多格式导出（PDF/Markdown） │                     │
│  └─────────────────────────────┘                     │
└──────────────────────────────────────────────────────┘
```

BN 三层结构：

```
contract_fact（71 节点）→ legal_semantics（38 节点）→ risk_dimensions（5）
        │                          │                          │
        └── 合同事实层 ────────────┴── 法律语义层 ───────────┘
         CUAD/LEDGAR 校准           aggregate 聚合          overall_risk
                                                         （高/中/低）
```

---

## 功能

- **自由审查 + BN 校验：** LLM₁ 不受限扫描 → BN 116 节点跨维度推理 → LLM₂ 生成结构化报告
- **反事实模拟：** "将条款 X 从 unfavorable 改善为 favorable，高风险概率下降 Y 个百分点"——每个 delta 标注 CPT 精度地板
- **双视角审查：** 买方/卖方两份独立报告，差异对比，自动识别立场冲突
- **10 种中国合同类型：** 销售、采购、煤炭、技术开发、服务、租赁、保密协议、劳动/聘用、工程承包/施工、借款/抵押/担保
- **公司红线配置：** YAML 可配置硬红线 + 推理指引，自动执行不可妥协条款
- **谈判策略生成：** 筹码识别、让步梯度、交换比率
- **BN 交互沙盒：** 手动调节条款状态，实时查看后验概率变化
- **报告历史管理：** MySQL 存储，列表筛选 + diff 对比
- **PDF / Markdown 导出**
- **中国民法典集成：** 第 585 条（违约金）、第 496/497 条（格式条款）、第 563 条（解除）、第 527 条（不安抗辩）、第 577 条（违约）、第 604 条（风险转移）

---

## 评测数据（v2.18）

### 条款识别准确率（CUAD 50 份英文合同）

| 条款类型 | Precision | Recall | F1 |
|---------|:---------:|:------:|:--:|
| 适用法律 | 0.96 | 0.96 | **0.96** |
| 终止条款 | 0.93 | 0.91 | **0.92** |
| 责任限制 | 0.74 | 0.89 | **0.81** |
| 交付条款 | 0.71 | 0.77 | **0.74** |
| 付款条款 | 0.39 | 0.75 | **0.51** |

注：CUAD 为英文合同数据集，中文合同评测数据待构建。三类（保密/争议解决/验收）CUAD 不覆盖。

### 消融实验（ContractNLI 测试集）

| 配置 | 风险准确率 | 说明 |
|------|:---------:|------|
| LLM only | 25.0% | LLM 直接判风险，≈随机 |
| **LLM + BN** | **65.0%** | 完整管线，BN 纠偏 +40pp |

### BN 结构验证

| 指标 | 值 |
|------|:--:|
| 参与推理节点 | 114/116 |
| flip 方向正确率 | 98.1% |
| 自动推测 favorable state 错误 | 0 |
| CPT 数据驱动比例 | 67%（74/110） |

---

## 项目结构

```
├── backend/              FastAPI 后端入口（端口 9527）
│   ├── main.py
│   └── routers/          review, dual, sandbox, export, history, redlines, feedback
├── frontend/             React 19 + TypeScript + Tailwind CSS 4
│   └── src/components/   ContractInput, RiskReport, SandboxPanel, ReportHistory
├── src/contract_risk_analysis/
│   ├── bn/               BN 核心（pgmpy 适配、推理、Noisy-OR、节点映射、网络验证）
│   ├── review/           LLM 审查（自由审查、报告生成、量化提取、裁决、协商）
│   ├── pipeline/         证据构建管线
│   ├── evaluation/       CPT 校准器、回归评分、CUAD/ContractNLI 评测、反事实消融
│   ├── evidence/         证据模型、冲突检测、归一化
│   ├── export/           PDF/Markdown 导出
│   ├── db/               MySQL 数据层
│   └── domain/           领域模型与 Schema
├── config/
│   ├── bayesian_network_v2.json        BN 图结构 + CPT 参数（116 节点 / 126 边）
│   ├── contract_type_routing.yaml      合同类型路由规则（10 种）
│   ├── company_redlines.yaml           公司红线规则
│   ├── clause_type_mapping.yaml        LLM 条款类型 → BN 节点映射
│   └── evidence_mapping.json           证据映射规则
├── scripts/             数据处理（LEDGAR 映射、BN 覆盖验证、CPT 校准、边关系修复）
├── tests/               测试套件
├── sample_data/         样本合同 + 评测结果
└── docker/              Docker 部署
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · pgmpy（贝叶斯推理引擎） |
| 前端 | React 19 · TypeScript · Vite · Tailwind CSS 4 |
| 数据库 | MySQL 8.0+（报告历史、红线 CRUD、反馈收集） |
| LLM | OpenAI 兼容 API（DeepSeek、OpenAI、Moonshot 等均可） |
| BN 校准 | CUAD（510 份）· ContractNLI（607 份）· LEDGAR（80,000 条） |

---

## 数据集

| 数据集 | 规模 | 用途 |
|--------|------|------|
| CUAD | 510 份 | contract_fact 层 CPT 校准 |
| ContractNLI | 607 份 | legal_semantics 层 CPT 校准 |
| LEDGAR | 80,000 条 | 条款分类标签体系 |
| DISC-Law-SFT | 103,000 条 | 中国民法条文引用 |
| Chinese Contract Templates | 10,000 份 | 中文合同条款分布验证 |

---

## 贡献

低门槛贡献方向：
- **纯 YAML：** 补充红线规则或条款类型映射，不需要写 Python
- **领域专家（中国法律）：** 审查和校准 CPT 参数，提供中文合同标注
- **前端：** UI 优化、移动端适配
- **数据：** 中文合同评测集构建

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## License

MIT

Built by [@chenchencc47](https://github.com/chenchencc47).
