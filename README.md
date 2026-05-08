# ContractLens — AI 合同风险审查系统

基于 **LLM + 贝叶斯网络（Bayesian Network）** 的智能合同风险检测与反事实分析系统。

> LLM₁ 自由审查 → BN 一致性校验 & 反事实模拟 → LLM₂ 综合报告

## English Quick Start

**What it is**

ContractLens is an AI-assisted contract review system that combines:

- **LLM₁** for free-form legal/commercial review
- **Bayesian Network** for consistency checking and counterfactual simulation
- **LLM₂** for the final narrative report

**Why BN instead of pure LLM**

Most AI contract review tools stop at "LLM finds issues and writes a summary." ContractLens adds a Bayesian Network as a validation layer so the system can answer questions like:

> "If we fix clause X, how much does the overall risk go down?"

That gives the project two differentiators:

- more transparent cross-dimension reasoning
- counterfactual analysis grounded in BN inference instead of pure text generation

**Quick Start**

```bash
# 1. Clone the repository
git clone https://github.com/chenchencc47/BN-Contract-Risk-Analysis.git
cd BN-Contract-Risk-Analysis

# 2. Copy environment template
cp .env.example .env

# 3. Start in demo mode (optional, no API key required)
# edit .env and set DEMO_MODE=true

# 4. Or configure real API/database credentials in .env
# OPENAI_API_KEY=...
# DEEPSEEK_API_KEY=...
# MYSQL_HOST=...

# 5. Run backend
python -m uvicorn backend.main:app --port 9527 --reload

# 6. Run frontend (new terminal)
cd frontend && npm install && npm run dev

# 7. Open the app
# http://localhost:5173
# API docs: http://localhost:9527/docs
# Demo endpoint: http://localhost:9527/api/demo
```

**Architecture**

```text
Contract text
  → LLM₁ free review
  → BN consistency check + counterfactual simulation
  → LLM₂ final report
```

---

## 核心思路

传统 AI 合同审查直接让 LLM 打分，结果不稳定、不可解释。ContractLens 把 **贝叶斯网络作为一致性校验器**：LLM 先自由审查合同条款，BN 再对审查结果进行交叉维度的概率推理和反事实模拟（"如果修掉这个条款，整体风险降多少？"），最后 LLM 基于 BN 的量化数据生成可信的综合报告。

**BN 的 CPT 参数由 CUAD（510 份合同）和 ContractNLI 数据集统计校准**，每个概率数字有可追溯的数据来源。

## 功能

- **自由审查 + BN 校验**：LLM₁ 不受限审查 → BN 跨维度推理 → LLM₂ 生成报告
- **反事实模拟**："将条款 X 从状态 A 改善为状态 B，整体高风险概率下降多少"
- **双视角审查**：同一份合同一键生成买方/卖方两份独立报告，并排对比关键差异
- **合同类型分层路由**：自动识别销售/采购/煤炭/NDA 等合同类型，加载对应的 BN 节点和审查清单
- **公司红线配置化**：独立 YAML 配置文件定义企业不可妥协的底线条款（硬红线 + 推理指引）
- **策略模式**：开启后报告新增"谈判筹码与策略建议"章节
- **BN 交互沙盒**：手动调整条款状态，实时查看 BN 后验概率变化
- **报告历史管理**：MySQL 存储所有报告，支持列表筛选和两份报告 diff 对比
- **PDF/Markdown 导出**

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · pgmpy（贝叶斯推理引擎） |
| 前端 | React 19 · TypeScript · Vite · Tailwind CSS 4 |
| 数据库 | MySQL（报告历史、公司红线 CRUD、反馈收集） |
| LLM | DeepSeek API（OpenAI 兼容协议） |
| BN 校准 | CUAD 数据集（510 份合同）· ContractNLI 数据集 |

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/chenchencc47/BN-Contract-Risk-Analysis.git
cd BN-Contract-Risk-Analysis

# 2. 安装依赖
pip install -e .

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 和数据库连接信息

# 4. 启动后端（终端 1）
python -m uvicorn backend.main:app --port 9527 --reload

# 5. 启动前端（终端 2）
cd frontend && npm install && npm run dev

# 6. 浏览器打开 http://localhost:5173
```

API 文档：http://localhost:9527/docs

## 项目结构

```
├── backend/              # FastAPI 后端入口
│   └── main.py           # API 路由（审查、导出、历史、反馈、双视角）
├── frontend/             # React + TypeScript 前端
│   └── src/components/   # 合同输入、风险报告、沙盒面板、历史管理、红线管理
├── src/contract_risk_analysis/
│   ├── bn/               # 贝叶斯网络核心（pgmpy 适配、推理、反事实、Noisy-OR）
│   ├── review/           # LLM 审查（自由审查、报告生成、验证）
│   ├── pipeline/         # 证据构建管线
│   ├── evaluation/       # CPT 校准器（CUAD/ContractNLI 驱动）
│   ├── evidence/         # 证据模型、冲突检测、归一化
│   ├── export/           # PDF/Markdown 导出
│   ├── db/               # MySQL 数据库层
│   └── domain/           # 领域模型与 Schema
├── config/
│   ├── bayesian_network_v2.json   # BN 图结构 + CPT 参数
│   ├── contract_type_routing.yaml  # 合同类型路由配置
│   └── company_redlines.yaml      # 公司红线规则
├── dataset/              # CUAD & ContractNLI 数据集
├── tests/                # 测试
└── 合同检测报告/          # 历史报告存档
```

## 版本演进

| 版本 | 内容 |
|---|---|
| v2.1 | 初始版本：BN 模块重构、CPT 校准器增强 |
| v2.2 | BN 模块重构、CPT 校准器增强、报告体系整理 |
| v2.3 | 立场锚定（买方/卖方代理律师角色）+ 安全护栏 |
| v2.8 | 合同类型分层路由 + 公司红线配置化 + 筹码防御分析（策略模式） |

进度与规划详见 [`worklist/WORKLIST.md`](worklist/WORKLIST.md)。

## 核心理念

- **每一个概率数字必须有可追溯的来源**：CUAD 统计、ContractNLI 统计或专家估计，不做无依据的手动调参
- **BN 是校验器，不是打分器**：LLM 负责理解合同语义，BN 负责跨维度概率一致性和反事实推理
- **区分"真问题"和"呈现问题"**：数据或模型结构有缺陷是真问题；数字不好看是呈现问题，应通过改进展示而非修改数字来解决

## License

MIT
