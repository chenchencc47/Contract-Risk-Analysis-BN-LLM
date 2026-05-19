# ContractLens — AI 合同风险审查系统

**LLM + Bayesian Network** dual-engine contract risk review with counterfactual simulation.

> LLM₁ free review → BN consistency check + counterfactual simulation → LLM₂ narrative report

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/chenchencc47/BN-Contract-Risk-Analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/chenchencc47/BN-Contract-Risk-Analysis/actions/workflows/ci.yml)

---

## Why ContractLens?

Most AI contract review tools stop at "LLM finds issues and writes a summary." ContractLens adds a **Bayesian Network as a validation layer** so the system can answer questions like:

> *"If we fix clause X, how much does the overall risk go down?"*

| | Pure LLM | Pure Rules | **ContractLens** |
|---|---|---|---|
| Semantic understanding | Strong | Weak | **Strong (LLM)** |
| Explainability | Weak (black-box) | Strong | **Strong (BN inference chain)** |
| Counterfactual reasoning | None | None | **Yes ("fix X → risk drops Y%")** |
| Uncertainty quantification | None | None | **Yes (pgmpy variable elimination)** |
| Cross-dimension consistency | Weak | Moderate | **Strong (BN graph constraints)** |

**What this means in practice:** ContractLens doesn't just list risks — it shows you which fixes have the biggest impact, backed by Bayesian inference. Every probability number has a traceable source: `cuad_empirical`, `contractnli_empirical`, or `expert_estimated`.

---

## Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/chenchencc47/BN-Contract-Risk-Analysis.git
cd BN-Contract-Risk-Analysis
cp .env.example .env
```

### 2. Try the Demo (no API key needed)

```bash
pip install -e .
python -m uvicorn backend.main:app --port 9527
# Open http://localhost:5173 — click "体验 Demo"
# Or: curl http://localhost:9527/api/demo
```

The demo shows a pre-computed review of a sales contract, including the full BN counterfactual analysis.

### 3. Full setup (requires DeepSeek API key + MySQL)

```bash
# Edit .env:
#   DEEPSEEK_API_KEY=sk-...
#   MYSQL_HOST=localhost MYSQL_USER=root MYSQL_PASSWORD=...

# Backend
python -m uvicorn backend.main:app --port 9527 --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev

# Open http://localhost:5173
# API docs: http://localhost:9527/docs
```

### 4. Docker

```bash
docker compose up
```

---

## Architecture

```text
┌──────────────────────────────────────────────────────────┐
│  Contract text input                                      │
│         │                                                 │
│         ▼                                                 │
│  ┌─────────────────────────────┐                         │
│  │ LLM₁: Free-form review      │  DeepSeek API            │
│  │ • Contract type routing      │  • 10 contract types    │
│  │ • Party role detection       │  • 90 BN nodes          │
│  │ • Risk segment extraction    │  • Legal basis lookup   │
│  └─────────────┬───────────────┘                         │
│                │                                          │
│                ▼                                          │
│  ┌─────────────────────────────┐                         │
│  │ BN: Consistency validation  │  pgmpy engine            │
│  │ • Clause → BN node mapping   │  • Variable elimination │
│  │ • Posterior probability      │  • 110 nodes, 83 edges  │
│  │ • Counterfactual simulation  │  • Noisy-MAX aggregation│
│  └─────────────┬───────────────┘                         │
│                │                                          │
│                ▼                                          │
│  ┌─────────────────────────────┐                         │
│  │ LLM₂: Narrative report      │  Structured dossier      │
│  │ • Party-stance anchoring     │  • Redline enforcement  │
│  │ • BN data injection          │  • Negotiation strategy │
│  │ • Civil Code references      │  • Multi-format output  │
│  └─────────────────────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

**Key design decision:** BN is a **validator**, not a scorer. LLM handles semantic understanding; BN ensures cross-dimension probability consistency and enables counterfactual reasoning.

### BN graph structure (v2, 110 nodes)

```
contract_fact (71 nodes) ──→ legal_semantics (33 nodes) ──→ risk_dimensions (5)
                                    │                              │
                                    └── direct edges ──────────────┘
                                                              │
                                                    overall_contract_risk (H/M/L)
```

CPT parameters sourced from: CUAD dataset (510 contracts) + ContractNLI dataset + expert estimates.

---

## Features

- **Free review + BN validation:** LLM₁ unconstrained review → BN cross-dimension reasoning → LLM₂ narrative report
- **Counterfactual simulation:** "Improving clause X from state A to B reduces high-risk probability by Y%"
- **Dual-perspective review:** One click generates both buyer and seller reports with side-by-side comparison
- **10 contract types:** Sales, procurement, coal, tech development, services, lease, NDA, labor, construction, loan/guarantee
- **Company redlines:** YAML-configurable hard rules + reasoning hints — LLM enforces your non-negotiable terms
- **Negotiation strategy:** Identifies leverage chips, concession gradients, and swap ratios
- **BN sandbox:** Manually adjust clause states and watch BN posteriors update in real time
- **Report history:** MySQL-stored reports with list filtering and diff comparison
- **PDF/Markdown export**
- **Civil Code integration:** 7 core articles extracted from DISC-Law-SFT dataset

---

## Project Structure

```
├── backend/              FastAPI entry point (port 9527)
│   ├── main.py           App creation, CORS, router registration
│   └── routers/          review, dual, sandbox, export, history, redlines, feedback
├── frontend/             React 19 + TypeScript + Tailwind CSS 4
│   └── src/components/   ContractInput, RiskReport, SandboxPanel, ReportHistory, etc.
├── src/contract_risk_analysis/
│   ├── bn/               Bayesian Network core (pgmpy adapter, inference, Noisy-OR, mapping)
│   ├── review/           LLM review (free review, report writer, quantification, adjudication)
│   ├── pipeline/         Evidence construction pipeline
│   ├── evaluation/       CPT calibrator (CUAD/ContractNLI driven), golden scoring
│   ├── evidence/         Evidence models, conflict detection, normalization
│   ├── export/           PDF/Markdown export
│   ├── db/               MySQL repository layer
│   └── domain/           Domain models & schemas
├── config/
│   ├── bayesian_network_v2.json      BN graph + CPT parameters (110 nodes)
│   ├── contract_type_routing.yaml     Contract type routing rules (10 types)
│   ├── company_redlines.yaml         Company redline rules
│   ├── contract_type_parameters.yaml  BN confidence tier configuration
│   ├── clause_type_mapping.yaml      LLM clause type → BN node mapping
│   └── evidence_mapping.json         Evidence mapping rules
├── dataset/             CUAD, ContractNLI, LEDGAR, DISC-Law-SFT, ALeaseBert
├── tests/               193 tests (187 passed)
└── docs/                Architecture docs, design specs
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+ · FastAPI · pgmpy (BN inference engine) |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS 4 |
| Database | MySQL (report history, redlines CRUD, feedback) |
| LLM | DeepSeek API (OpenAI-compatible protocol) |
| BN calibration | CUAD (510 contracts) · ContractNLI dataset |

---

## Data Traceability

```
CUAD / ContractNLI datasets
       │
       ├──→ cpt_calibrator.py  ← statistical CPT estimation
       │         │
       │         └──→ bayesian_network_v2.json  ← source field: cuad_empirical |
       │                                            contractnli_empirical |
       │                                            expert_estimated
       │
       ├──→ pgmpy_adapter.py   ← model construction
       │         │
       │         └──→ VariableElimination  ← exact inference
       │                   │
       │                   └──→ P(high | evidence)  ← posterior probability
       │
       └──→ run_sensitivity_analysis()  ← counterfactual simulation
                 │
                 └──→ delta = P(high | E) - P(high | E')
```

Every probability number in the system has exactly one of three legitimate sources. No manual tuning to make reports "look better."

---

## Project Status

**v2.17** — Active development. Open for community contributions.

- [x] 10 contract types
- [x] 110-node Bayesian Network with 83 edges
- [x] Dual-perspective (buyer/seller) review
- [x] BN sandbox
- [x] Report history + diff
- [x] Company redlines configuration
- [x] Counterfactual simulation
- [x] Demo mode
- [ ] Chinese contract CPT calibration (need annotated data)
- [ ] Redline rules for labor/construction/loan contracts
- [ ] BN edge completion for remaining contract types

See [`worklist/worklist-v2.17/`](worklist/worklist-v2.17/) for the current task list.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

Quick contribution areas:
- **YAML-only:** Add redline rules or clause type mappings — no Python needed
- **Domain expert:** Review and calibrate CPT parameters in `bayesian_network_v2.json`
- **Frontend:** UI improvements, accessibility, mobile support
- **Data:** New contract datasets for CPT calibration (see `cpt_calibrator.py`)

---

## License

MIT — see [LICENSE](https://opensource.org/licenses/MIT).

Built by [@chenchencc47](https://github.com/chenchencc47).
