# ContractLens — AI 合同风险审查系统

基于 **LLM + 贝叶斯网络** 的智能合同风险检测与反事实分析系统。

> LLM₁ 自由审查 → BN 一致性校验 + 反事实模拟 → LLM₂ 综合报告

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)

---

## 为什么用 BN + LLM？

大多数 AI 合同审查工具止步于"LLM 找到问题、写个总结"。ContractLens 把**贝叶斯网络作为校验层**，让系统能回答：

> *"如果把条款 X 修掉，整体风险降多少？"*

**BN 反事实模拟是什么？** 当你上传一份合同，LLM 先识别风险项（如"预付款比例过高"），BN 再对每个风险项做"假设推理"——假设这个条款被修好了，合同整体高风险概率会从 X% 降到 Y%，变化幅度即 delta。这个数字不是 LLM "拍脑袋"给的，而是 pgmpy 变量消元精确计算的后验概率差值。报告中每项反事实都标注了推导链（如 `条款状态 unfavorable→favorable | pgmpy VE delta=-3.3%`），用户可以根据 delta 大小判断"先改哪个条款收益最大"。

| | 纯 LLM | 纯规则 | **ContractLens** |
|---|---|---|---|
| 语义理解 | 强 | 弱 | **强（LLM）** |
| 可解释性 | 弱（黑箱） | 强 | **强（BN 推理链）** |
| 反事实推理 | 不支持 | 不支持 | **支持（修 X 条款 → 风险降 Y%）** |
| 不确定性量化 | 无 | 无 | **支持（pgmpy 变量消元）** |
| 跨维度一致性 | 弱 | 中 | **强（BN 图结构约束）** |

**核心差异化：** 不只列出风险——还告诉你改哪个条款效果最大，每个概率数字都有可追溯来源（`cuad_empirical` / `contractnli_empirical` / `expert_estimated`）。

---

## 快速开始

### 1. 体验 Demo（无需 API Key、无需数据库）

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

### 2. 完整部署（需要 API Key + MySQL）

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和数据库连接信息

python -m uvicorn backend.main:app --port 9527 --reload
cd frontend && npm run dev
```

**注意：** 完整审查需要 MySQL 8.0+ 存储报告历史。MySQL 不可用时审查仍然正常返回结果，只是不保存历史记录。Demo 模式完全不需要数据库。

### 3. Docker

```bash
docker compose up
```

API 文档：http://localhost:9527/docs

---

## 架构

```text
┌──────────────────────────────────────────────────────────┐
│  合同文本输入                                              │
│         │                                                 │
│         ▼                                                 │
│  ┌─────────────────────────────┐                         │
│  │ LLM₁：自由审查               │  OpenAI 兼容 API          │
│  │ · 合同类型自动识别（10种）    │  · 立场锚定（甲方/乙方）  │
│  │ · 风险段提取 + 法条速查      │  · 角色自动检测          │
│  └─────────────┬───────────────┘                         │
│                │                                          │
│                ▼                                          │
│  ┌─────────────────────────────┐                         │
│  │ BN：一致性校验               │  pgmpy 推理引擎          │
│  │ · 条款 → BN 节点映射         │  · 变量消元精确推理      │
│  │ · 后验概率计算               │  · 110 节点，83 条边     │
│  │ · 反事实模拟                 │  · Noisy-MAX 聚合模型    │
│  └─────────────┬───────────────┘                         │
│                │                                          │
│                ▼                                          │
│  ┌─────────────────────────────┐                         │
│  │ LLM₂：综合报告               │  结构化 Dossier 驱动     │
│  │ · 立场锚定 + BN 数据注入     │  · 公司红线自动执行      │
│  │ · 民法典条文引用             │  · 谈判策略生成          │
│  │ · 多格式输出（报告/清单/附录）│                         │
│  └─────────────────────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

BN 图结构：

```
contract_fact（71 节点）→ legal_semantics（33 节点）→ risk_dimensions（5）
                                    │                           │
                                    └─── 直连边 ────────────────┘
                                                          │
                                              overall_contract_risk（H/M/L）
```

---

## 功能

- **自由审查 + BN 校验：** LLM₁ 不受限审查 → BN 跨维度推理 → LLM₂ 生成报告
- **反事实模拟：** "将条款 X 从状态 A 改善为 B，高风险概率下降 Y%"
- **双视角审查：** 一键生成买方/卖方两份独立报告，并排对比关键差异
- **10 种合同类型：** 销售、采购、煤炭、技术开发、服务、租赁、保密协议、劳动/聘用、工程承包/施工、借款/抵押/担保
- **公司红线：** YAML 配置化硬红线 + 推理指引，LLM 自动执行不可妥协条款
- **谈判策略：** 筹码识别、让步梯度、交换比率、对手预判
- **BN 交互沙盒：** 手动调整条款状态，实时查看后验概率变化
- **报告历史管理：** MySQL 存储，支持列表筛选和 diff 对比
- **PDF / Markdown 导出**
- **民法典集成：** 从 DISC-Law-SFT 提取 7 条核心合同法条文

---

## 项目结构

```
├── backend/              FastAPI 后端入口（端口 9527）
│   ├── main.py           应用创建、CORS、路由注册
│   └── routers/          review, dual, sandbox, export, history, redlines, feedback
├── frontend/             React 19 + TypeScript + Tailwind CSS 4
│   └── src/components/   ContractInput, RiskReport, SandboxPanel, ReportHistory 等
├── src/contract_risk_analysis/
│   ├── bn/               BN 核心（pgmpy 适配、推理、Noisy-OR、节点映射）
│   ├── review/           LLM 审查（自由审查、报告生成、量化提取、裁决）
│   ├── pipeline/         证据构建管线
│   ├── evaluation/       CPT 校准器（CUAD/ContractNLI 驱动）、回归评分
│   ├── evidence/         证据模型、冲突检测、归一化
│   ├── export/           PDF/Markdown 导出
│   ├── db/               MySQL 数据层
│   └── domain/           领域模型与 Schema
├── config/
│   ├── bayesian_network_v2.json       BN 图结构 + CPT 参数（110 节点）
│   ├── contract_type_routing.yaml     合同类型路由规则（10 种）
│   ├── company_redlines.yaml          公司红线规则（6 种合同类型）
│   ├── contract_type_parameters.yaml  BN 可信度分层配置
│   ├── clause_type_mapping.yaml       LLM 条款类型 → BN 节点映射
│   └── evidence_mapping.json          证据映射规则
├── scripts/             数据集处理脚本（LEDGAR 映射、BN 覆盖验证、法条提取）
├── tests/               184 个测试
├── docs/                使用文档
├── sample_data/         样本合同和基准数据
└── docker/              Docker 部署配置
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · pgmpy（贝叶斯推理引擎） |
| 前端 | React 19 · TypeScript · Vite · Tailwind CSS 4 |
| 数据库 | MySQL 8.0+（报告历史、红线 CRUD、反馈收集） |
| LLM | OpenAI 兼容 API（deepseek、openai 等均可） |
| BN 校准 | CUAD 数据集（510 份合同）· ContractNLI 数据集 |

---

## 数据集

本项目使用以下公开数据集进行 BN 参数校准和覆盖验证：

| 数据集 | 规模 | 用途 | 下载 |
|--------|------|------|------|
| CUAD | 510 份合同 | contract_fact 层 CPT 校准 | [HuggingFace](https://huggingface.co/datasets/cuad) |
| ContractNLI | 607 份合同 | legal_semantics 层 CPT 校准 | [GitHub](https://github.com/stanfordnlp/contract-nli) |
| LEDGAR | 80,000 条 | 条款分类标签体系 | [HuggingFace](https://huggingface.co/datasets/ledgar) |
| DISC-Law-SFT | 103,000 条 | 法条引用提取 | [GitHub](https://github.com/FudanDISC/DISC-Law-SFT) |

下载后放入 `dataset/` 目录即可。`scripts/` 目录包含数据处理脚本。

---

## 项目状态

**v2.17** — 积极开发中，欢迎社区贡献。

- [x] 10 种合同类型
- [x] 110 节点贝叶斯网络（83 条边）
- [x] 双视角审查（买方/卖方）
- [x] BN 交互沙盒
- [x] 报告历史 + diff 对比
- [x] 公司红线配置化
- [x] 反事实模拟
- [x] Demo 模式（无需 API Key）
- [ ] 中文合同 CPT 校准（需要标注数据）
- [ ] BN 边关系进一步补全

---

## 贡献

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

低门槛贡献方向：
- **纯 YAML：** 补充红线规则或条款类型映射，不需要写 Python
- **领域专家：** 审查和校准 `bayesian_network_v2.json` 中的 CPT 参数
- **前端：** UI 优化、无障碍适配、移动端支持
- **数据：** 新的合同标注数据集（接入 `cpt_calibrator.py` 即可）

---

## License

MIT

Built by [@chenchencc47](https://github.com/chenchencc47).

---

## English

ContractLens is an AI contract risk review system combining **LLM + Bayesian Network** dual engines with counterfactual simulation ("if we fix clause X, risk drops Y%"). See [Quick Start](#1-体验-demo无需-api-key无需数据库) above — demo mode works without API key or database.

For detailed English documentation, see [README_EN.md](README_EN.md).
