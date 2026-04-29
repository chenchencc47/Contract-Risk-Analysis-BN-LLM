# 02 - Target Architecture

**Version:** 1.0  
**Status:** Draft  
**Scope:** Complete architectural specification for the probabilistic contract risk reasoning system

---

## Executive Summary

This document defines the target architecture for BN-Contract-Risk-Analysis after the three-phase evolution. The architecture emphasizes:

1. **Probabilistic Core:** True Bayesian inference with uncertainty quantification
2. **Explainability by Design:** Every decision traceable through the system
3. **Evaluability:** Built-in benchmarking and metrics collection
4. **Scalability:** Horizontal scaling of inference and trace storage
5. **Maintainability:** Clean separation of concerns, well-defined interfaces

The architecture maintains backward compatibility with the current weighted-sum system while enabling gradual migration to full probabilistic reasoning.

---

## Architecture Principles

### P1: Probabilistic First
All risk assessments are probability distributions, not point estimates. The system reasons about uncertainty explicitly.

### P2: Explainability is Non-Negotiable
Every output must be explainable. If we can't explain why the system made a decision, the architecture is wrong.

### P3: Evaluability by Design
Evaluation isn't an afterthought. The architecture includes hooks for metrics, benchmarks, and validation at every layer.

### P4: Separation of Concerns
Clear boundaries between: parsing, evidence extraction, probabilistic inference, reporting, and storage.

### P5: Backward Compatibility
Existing configs and APIs continue to work. New features are additive, not destructive.

### P6: Incremental Evolution
The architecture supports phased implementation. Each phase delivers value independently.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONTRACT RISK ANALYSIS SYSTEM                      │
│                           (Target Architecture v1.0)                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Input Layer   │    │ Processing Layer│    │   Output Layer  │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│                 │    │                 │    │                 │
│  Contract Text  │───▶│  LLM Reviewer   │───▶│ Risk Report     │
│  (PDF/TXT/Doc)  │    │  (Evidence      │    │ (Probabilistic) │
│                 │    │   Extraction)   │    │                 │
└─────────────────┘    └────────┬────────┘    └─────────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │   Evidence Mapper   │
                    │  (LLM Findings →    │
                    │   BN Node States)   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Probabilistic       │
                    │ Inference Engine    │
                    │ (Bayesian Network   │
                    │  Reasoning)         │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Explanation        │
                    │  Generator          │
                    │  (Traces,           │
                    │   Attribution)      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Report Polisher    │
                    │  (LLM-based         │
                    │   Narrative)        │
                    └─────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         Supporting Infrastructure                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Trace Store  │  │ Benchmark    │  │ Model        │  │ Config       │     │
│  │ (PostgreSQL/ │  │ Dataset      │  │ Registry     │  │ Management   │     │
│  │  Time-series)│  │ (Labeled     │  │ (Versioned   │  │ (BN configs, │     │
│  │              │  │  Contracts)  │  │  CPTs)       │  │  Mappings)   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Input Layer

**Purpose:** Accept contract documents in various formats and normalize for processing.

**Components:**
- `DocumentParser` - Extract text from PDF, DOCX, TXT
- `Preprocessor` - Normalize encoding, handle OCR errors, segment clauses
- `Validation` - Schema validation, size limits, format checks

**Interfaces:**
```python
class DocumentInput(BaseModel):
    contract_id: str
    content: Union[str, bytes]
    format: Literal["pdf", "txt", "docx"]
    metadata: ContractMetadata

class DocumentParser(Protocol):
    def parse(self, input: DocumentInput) -> ParsedContract: ...
```

**Current State:** CLI accepts text files, Streamlit accepts text input  
**Target State:** Multi-format parser with OCR support

---

### 2. LLM Reviewer (Evidence Extraction)

**Purpose:** Extract structured evidence from contract text using LLM.

**Components:**
- `ReviewEngine` - Orchestrates LLM calls (Moonshot/Kimi)
- `PromptManager` - Versioned prompts for different contract types
- `OutputValidator` - Validate LLM output against schema
- `ConfidenceScorer` - Estimate confidence of LLM findings

**Interfaces:**
```python
class ReviewFinding(BaseModel):
    finding_key: str
    clause_type: str
    status: Literal["pass", "fail", "concern"]
    evidence_text: str
    confidence: float  # 0.0 - 1.0
    risk_factor: Optional[str]
    hypothesis: Optional[str]
    counterparty_favorability: Optional[str]

class ReviewEngine(Protocol):
    def review(self, contract: ParsedContract) -> List[ReviewFinding]: ...
    def get_confidence(self, finding: ReviewFinding) -> float: ...
```

**Current State:** Uses Moonshot/Kimi API with structured output  
**Target State:** Confidence scoring, multi-model ensemble, active learning

---

### 3. Evidence Mapper

**Purpose:** Map LLM findings to Bayesian Network node states with uncertainty.

**Components:**
- `EvidenceMapper` - Core mapping logic
- `RuleEngine` - Evidence mapping rules from config
- `UncertaintyPropagator` - Convert confidence to probability distributions
- `ConflictResolver` - Handle contradictory findings

**Key Innovation:** Instead of hard mapping to single state, output probability distribution over states.

**Interfaces:**
```python
class NodeEvidence(BaseModel):
    node_id: str
    state_probabilities: Dict[str, float]  # state -> probability
    source_findings: List[ReviewFinding]
    confidence: float
    mapping_rule_applied: str

class EvidenceMapper(Protocol):
    def map_findings(
        self, 
        findings: List[ReviewFinding],
        config: EvidenceMappingConfig
    ) -> List[NodeEvidence]: ...
    
    def resolve_conflicts(
        self, 
        evidence_list: List[NodeEvidence]
    ) -> List[NodeEvidence]: ...
```

**Current State:** Hard mapping to single state, takes "most severe"  
**Target State:** Probabilistic evidence with uncertainty propagation

**Mapping Rules:**
```yaml
# Current (deterministic)
finding_key_rules:
  termination_clause_missing:
    node: termination_clause_completeness
    state: missing

# Target (probabilistic)
finding_key_rules:
  termination_clause_missing:
    node: termination_clause_completeness
    state_distribution:
      missing: 0.85      # High confidence it's missing
      incomplete: 0.10   # Could be incomplete
      present: 0.05      # Unlikely but possible (hallucination)
    confidence_weight: 1.0
```

---

### 4. Probabilistic Inference Engine

**Purpose:** Perform true Bayesian inference over the contract risk network.

**Components:**
- `BayesianNetwork` - Network structure, nodes, edges
- `InferenceEngine` - Belief propagation, variable elimination
- `CPTManager` - Conditional probability tables, parameter learning
- `QueryInterface` - Query marginal/conditional probabilities
- `UncertaintyQuantifier` - Compute entropy, confidence intervals

**Interfaces:**
```python
class BayesianNetwork:
    nodes: Dict[str, Node]
    edges: List[Tuple[str, str]]
    cpds: Dict[str, ConditionalProbabilityTable]
    
    def add_evidence(self, evidence: NodeEvidence) -> None: ...
    def infer(self, query_nodes: List[str]) -> InferenceResult: ...
    def get_marginal(self, node_id: str) -> ProbabilityDistribution: ...

class InferenceResult(BaseModel):
    marginal_distributions: Dict[str, ProbabilityDistribution]
    joint_probabilities: Optional[Dict[str, float]]
    computation_method: Literal["exact", "approximate"]
    convergence_info: Optional[Dict]
    
class ProbabilityDistribution(BaseModel):
    node_id: str
    states: List[str]
    probabilities: List[float]  # Sums to 1.0
    entropy: float
    mode: str  # Most likely state
    credible_interval: Optional[Tuple[float, float]]
```

**Algorithms:**
- Exact inference: Variable elimination for small networks (<30 nodes)
- Approximate: Loopy belief propagation for larger networks
- Sampling: Gibbs sampling, MCMC for complex queries

**Current State:** Weighted sums, no probabilistic reasoning  
**Target State:** Full Bayesian inference with multiple algorithms

**Example Inference:**
```python
# Given evidence: termination_clause is "missing" (prob 0.9)
evidence = NodeEvidence(
    node_id="termination_clause_completeness",
    state_probabilities={"missing": 0.9, "incomplete": 0.1}
)

# Query: What's the probability distribution of overall_contract_risk?
result = bn.infer(query_nodes=["overall_contract_risk"])

# Output: Full distribution, not just single value
print(result.marginals["overall_contract_risk"])
# {
#   "low": 0.05,
#   "medium": 0.25,
#   "high": 0.65,
#   "critical": 0.05
# }
```

---

### 5. Explanation Generator

**Purpose:** Generate human-readable explanations of inference decisions.

**Components:**
- `TraceCollector` - Capture every step of inference
- `AttributionEngine` - Calculate feature importance
- `ExplanationRenderer` - Generate text/visual explanations
- `CounterfactualGenerator` - "What if" scenarios

**Interfaces:**
```python
class ReasoningTrace(BaseModel):
    trace_id: str
    timestamp: datetime
    steps: List[TraceStep]
    final_result: InferenceResult
    
class TraceStep(BaseModel):
    step_number: int
    operation: str
    inputs: Dict
    outputs: Dict
    reasoning: str
    
class Explanation(BaseModel):
    trace_id: str
    summary: str  # Human-readable summary
    key_factors: List[FactorExplanation]
    visual_data: Optional[Dict]  # For UI rendering
    confidence_breakdown: Dict[str, float]
    
class ExplanationGenerator(Protocol):
    def generate_trace(
        self, 
        inference_result: InferenceResult,
        evidence: List[NodeEvidence]
    ) -> ReasoningTrace: ...
    
    def explain_attribution(
        self,
        trace: ReasoningTrace,
        target_node: str
    ) -> Explanation: ...
    
    def generate_counterfactual(
        self,
        trace: ReasoningTrace,
        hypothetical_changes: Dict[str, str]
    ) -> CounterfactualResult: ...
```

**Explanation Types:**
1. **Trace View:** Step-by-step inference log
2. **Attribution View:** Which evidence contributed most to each risk score
3. **Contrastive:** Why high risk vs low risk
4. **Counterfactual:** What if termination clause was complete?

**Current State:** Basic evidence tracking  
**Target State:** Full traceability with multiple explanation modes

---

### 6. Report Polisher

**Purpose:** Generate polished, human-readable risk reports from structured data.

**Components:**
- `ReportGenerator` - Orchestrate report creation
- `TemplateEngine` - Structured templates for different report types
- `LLMPolisher` - Use LLM for narrative generation (optional)
- `ReportValidator` - Ensure reports meet quality standards

**Interfaces:**
```python
class RiskReport(BaseModel):
    contract_id: str
    overall_risk_distribution: ProbabilityDistribution
    dimension_scores: Dict[str, ProbabilityDistribution]
    top_risks: List[RiskItem]
    signing_recommendation: str
    manual_review_items: List[str]
    reasoning_trace_id: str
    generated_at: datetime

class PolishedReport(BaseModel):
    executive_summary: str
    dimension_insights: Dict[str, str]
    signing_advice: str
    action_plan: List[ActionItem]
    risk_visualizations: List[ChartData]
    uncertainty_notes: str

class ReportPolisher(Protocol):
    def polish(
        self, 
        risk_report: RiskReport,
        explanation: Explanation,
        style: ReportStyle = ReportStyle.EXECUTIVE
    ) -> PolishedReport: ...
```

**Current State:** Basic LLM-based polishing  
**Target State:** Template-based with optional LLM enhancement, uncertainty-aware

---

### 7. Storage Layer

**Purpose:** Persist traces, benchmarks, models, and configurations.

**Components:**
- `TraceStore` - Time-series storage for reasoning traces
- `BenchmarkDB` - Labeled contracts and ground truth
- `ModelRegistry` - Versioned CPTs and network structures
- `ConfigStore` - Evidence mappings, thresholds, rules

**Schema Overview:**
```sql
-- Traces table
traces (
    id UUID PRIMARY KEY,
    contract_id VARCHAR(255),
    timestamp TIMESTAMP,
    trace_data JSONB,  -- Full reasoning trace
    inference_result JSONB,
    explanation JSONB
);

-- Benchmark dataset
benchmark_contracts (
    id UUID PRIMARY KEY,
    contract_text TEXT,
    ground_truth_risk VARCHAR(50),
    annotations JSONB,
    annotator_agreement FLOAT,
    contract_type VARCHAR(100)
);

-- Model registry
models (
    id UUID PRIMARY KEY,
    version VARCHAR(50),
    cpts JSONB,
    network_structure JSONB,
    training_data_version VARCHAR(50),
    validation_metrics JSONB,
    created_at TIMESTAMP
);

-- Configs
configs (
    id UUID PRIMARY KEY,
    config_type VARCHAR(100),
    version VARCHAR(50),
    data JSONB,
    created_at TIMESTAMP
);
```

**Current State:** JSON files in filesystem  
**Target State:** Database storage with versioning

---

## Data Flow

### Complete Request Flow

```
1. Client POST /analyze
   ├── Document uploaded (PDF/TXT/DOCX)
   └── Metadata (contract_id, type, jurisdiction)

2. Input Layer
   ├── Parse document → Extract raw text
   ├── Segment into clauses
   └── Validate and normalize

3. LLM Reviewer
   ├── Generate prompts based on contract type
   ├── Call LLM API (Moonshot/Kimi)
   ├── Validate structured output
   ├── Score confidence of each finding
   └── Return List[ReviewFinding]

4. Evidence Mapper
   ├── Apply evidence mapping rules
   ├── Convert findings → probability distributions
   ├── Resolve conflicts between findings
   └── Return List[NodeEvidence]

5. Probabilistic Inference Engine
   ├── Load Bayesian Network structure
   ├── Set evidence (soft evidence with uncertainty)
   ├── Run inference algorithm
   ├── Compute marginal distributions
   ├── Calculate uncertainty metrics
   └── Return InferenceResult

6. Explanation Generator
   ├── Capture trace of inference steps
   ├── Calculate attribution scores
   ├── Generate explanation text
   ├── Store trace in TraceStore
   └── Return Explanation

7. Report Polisher
   ├── Read templates for report type
   ├── Generate structured report
   ├── Optionally use LLM for narrative
   ├── Add uncertainty notes
   └── Return PolishedReport

8. Response
   ├── Serialize report to JSON
   ├── Include trace_id for later inspection
   └── Return to client
```

### Async Flow for Long Contracts

```
1. Client POST /analyze/async
2. Server returns job_id immediately
3. Processing happens in background worker
4. Client polls GET /status/{job_id}
5. On completion, client GET /result/{job_id}
```

---

## API Specification

### REST Endpoints (FastAPI)

**Core Analysis**
```
POST /api/v1/analyze
  - Request: { contract_text, contract_id, options }
  - Response: { report, trace_id, processing_time }

POST /api/v1/analyze/async
  - Request: { contract_text, contract_id }
  - Response: { job_id, status_url }

GET /api/v1/status/{job_id}
  - Response: { status, progress, result_url }
```

**Explainability**
```
GET /api/v1/traces/{trace_id}
  - Response: Full ReasoningTrace

GET /api/v1/explain/{trace_id}
  - Query: target_node, explanation_type
  - Response: Explanation

GET /api/v1/attribution/{trace_id}
  - Query: target_node
  - Response: Attribution scores

POST /api/v1/counterfactual/{trace_id}
  - Request: { hypothetical_changes }
  - Response: CounterfactualResult
```

**Probabilistic Queries**
```
GET /api/v1/distribution/{contract_id}/{node_id}
  - Response: ProbabilityDistribution

POST /api/v1/query
  - Request: { evidence, query_nodes }
  - Response: InferenceResult

GET /api/v1/uncertainty/{contract_id}
  - Response: Uncertainty metrics (entropy, variance)
```

**Benchmark & Evaluation**
```
POST /api/v1/benchmark/evaluate
  - Request: { model_version, dataset_id }
  - Response: Evaluation metrics

GET /api/v1/benchmark/datasets
  - Response: List of available datasets

GET /api/v1/metrics/{contract_id}
  - Response: Confidence, calibration metrics
```

---

## Technology Stack

### Current → Target Migration

| Layer | Current | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|-------|---------|----------------|----------------|----------------|
| **Language** | Python 3.9 | Python 3.11 | Python 3.11 | Python 3.11 |
| **Web Framework** | FastAPI | FastAPI | FastAPI | FastAPI |
| **LLM Client** | OpenAI SDK | OpenAI SDK + async | OpenAI SDK + ensemble | OpenAI SDK + active learning |
| **Inference** | Weighted sums | Weighted sums + traces | pgmpy / custom | pgmpy / custom + GPU |
| **Storage** | JSON files | PostgreSQL | PostgreSQL | PostgreSQL + Redis |
| **Queue** | None | None | Celery + Redis | Celery + Redis |
| **Monitoring** | Print logs | Structured logging | Prometheus | Prometheus + Grafana |
| **Testing** | pytest | pytest + coverage | pytest + hypothesis | pytest + fuzzing |

### New Dependencies

**Phase 1:**
- `structlog` - Structured logging
- `sqlalchemy` + `alembic` - Database ORM and migrations
- `pydantic` v2 (upgrade from v1) - Validation

**Phase 2:**
- `pgmpy` or custom inference - Probabilistic inference
- `networkx` - Graph operations
- `numpy` + `scipy` - Numerical computation
- `numba` - JIT compilation for inference

**Phase 3:**
- `scikit-learn` - Evaluation metrics
- `mlflow` or `weights & biases` - Experiment tracking
- `prometheus-client` - Metrics

---

## Deployment Architecture

### Container Layout

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose / K8s                 │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   API       │  │   Worker    │  │  Worker     │     │
│  │   Server    │  │   (Celery)  │  │  (Celery)   │     │
│  │   (FastAPI) │  │             │  │             │     │
│  │   Port 8000 │  │             │  │             │     │
│  └──────┬──────┘  └─────────────┘  └─────────────┘     │
│         │                                               │
│         │                                               │
│  ┌──────▼──────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ PostgreSQL  │  │    Redis    │  │ Prometheus  │     │
│  │  (Traces,   │  │   (Queue,   │  │  (Metrics)  │     │
│  │   Models)   │  │   Cache)    │  │             │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Grafana (Observability)            │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Scaling Strategy

**Horizontal Scaling:**
- API servers: Scale based on request rate
- Workers: Scale based on queue depth
- Database: Read replicas for trace queries

**Caching:**
- Inference results cache (Redis) for identical contracts
- CPT cache in memory
- LLM response cache (for deterministic prompts)

---

## Configuration Management

### Config Hierarchy

```yaml
# config/default.yaml - Base config
bayesian_network:
  structure_file: "config/bn_structure.json"
  inference_method: "variable_elimination"
  
evidence_mapping:
  rules_file: "config/evidence_rules.yaml"
  default_confidence: 0.8
  
llm:
  provider: "moonshot"
  model: "kimi-latest"
  temperature: 0.1
  
tracing:
  enabled: true
  storage: "postgresql"
  retention_days: 90

# config/production.yaml - Production overrides
llm:
  temperature: 0.0  # More deterministic
  
tracing:
  retention_days: 365
  
inference:
  cache_enabled: true
  max_nodes: 50
```

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/bn_risk

# LLM API
MOONSHOT_API_KEY=sk-...

# Inference
INFERENCE_MODE=bayesian  # or weighted_sum for legacy
DEFAULT_CONFIDENCE_THRESHOLD=0.7

# Feature flags
ENABLE_EXPLANATIONS=true
ENABLE_PROBABILISTIC_OUTPUT=true
ENABLE_COUNTERFACTUALS=false  # Gradual rollout
```

---

## Security Considerations

### Data Protection
- Contract text encrypted at rest (AES-256)
- PII redaction in traces (if contracts contain personal info)
- API authentication (JWT tokens or API keys)
- Rate limiting per client

### Model Security
- CPT versioning and rollback capability
- Input validation on all evidence
- Query timeout limits (prevent DoS via complex queries)
- Sandboxed inference (isolated from production data)

### Audit Trail
- All API calls logged with user_id, timestamp, request_id
- All trace access logged
- Model updates logged with approval chain

---

## Migration Strategy

### From Current to Target

**Phase 0: Preparation (Week 1-2)**
- [ ] Refactor current code into cleaner structure
- [ ] Add comprehensive tests for existing logic
- [ ] Set up database schema
- [ ] Create feature flag system

**Phase 1: Explainability (Months 1-4)**
- [ ] Add trace collection to existing weighted-sum code
- [ ] Build trace storage and retrieval
- [ ] Create attribution engine
- [ ] Update API to return trace_ids
- [ ] Build trace viewer UI

**Phase 2: Probabilistic (Months 5-8)**
- [ ] Implement Bayesian inference engine alongside weighted-sum
- [ ] Add feature flag `inference_mode=bayesian`
- [ ] Train initial CPTs on historical data
- [ ] Gradual rollout: 5% → 25% → 100%
- [ ] Monitor accuracy and latency

**Phase 3: Evaluation (Months 9-12)**
- [ ] Curate benchmark dataset
- [ ] Implement evaluation pipeline
- [ ] Human validation study
- [ ] Deprecate weighted-sum mode
- [ ] Full probabilistic mode default

### Backward Compatibility

```python
# API maintains backward compatibility
@app.post("/api/v1/analyze")
async def analyze(
    request: AnalysisRequest,
    inference_mode: InferenceMode = InferenceMode.BAYESIAN  # Default changes over time
):
    if inference_mode == InferenceMode.WEIGHTED_SUM:
        return legacy_analyze(request)
    else:
        return probabilistic_analyze(request)
```

---

## Performance Targets

### Latency Budgets

| Operation | P50 Target | P95 Target | P99 Target |
|-----------|------------|------------|------------|
| Document parse | 50ms | 100ms | 200ms |
| LLM review | 2s | 5s | 10s |
| Evidence mapping | 10ms | 20ms | 50ms |
| Inference (weighted) | 5ms | 10ms | 20ms |
| Inference (Bayesian) | 50ms | 100ms | 200ms |
| Explanation generation | 20ms | 50ms | 100ms |
| Report polish | 2s | 5s | 10s |
| **Total end-to-end** | **5s** | **10s** | **20s** |

### Throughput Targets

- **Phase 1:** 10 requests/minute
- **Phase 2:** 50 requests/minute
- **Phase 3:** 100 requests/minute

### Resource Usage

- Memory: <2GB per worker
- CPU: <2 cores per worker
- Database: <100GB storage for 1 year of traces

---

## Testing Strategy

### Unit Tests
- Every component has >80% coverage
- Property-based testing for probabilistic functions
- Mock external dependencies (LLM API)

### Integration Tests
- End-to-end contract analysis
- Database integration
- API contract tests

### Probabilistic Tests
- Inference correctness: Compare to reference implementation
- Calibration tests: Predicted probabilities match empirical frequencies
- Sensitivity tests: Small evidence changes → reasonable output changes

### Performance Tests
- Load testing: 100 concurrent requests
- Latency benchmarks under load
- Memory leak detection

---

## Monitoring & Observability

### Metrics

**Business Metrics:**
- Analysis requests per minute
- Success rate (%) 
- Average risk score distribution

**Technical Metrics:**
- LLM API latency (P50, P95, P99)
- Inference latency by algorithm
- Database query latency
- Cache hit rate

**Quality Metrics:**
- Confidence score distribution
- Uncertainty metrics (entropy)
- Calibration error (tracked in Phase 3)

### Alerting

**P1 (Page immediately):**
- Success rate <95%
- Inference latency P99 >5s
- Database connection failures

**P2 (Alert within 1 hour):**
- Cache hit rate <80%
- LLM API error rate >5%
- Queue depth >1000

**P3 (Alert within 24 hours):**
- Disk usage >80%
- Memory usage >90%
- Calibration error >0.1 (in Phase 3)

### Dashboards

- Real-time: Request rate, latency, error rate
- Quality: Confidence distributions, calibration plots
- Infrastructure: CPU, memory, database health
- Business: Contract types analyzed, risk trends

---

## Appendix: Glossary

- **BN**: Bayesian Network - Directed acyclic graph representing probabilistic relationships
- **CPT**: Conditional Probability Table - Defines P(child|parents) for each node
- **Evidence**: Observed values (or distributions) for specific nodes
- **Inference**: Computing posterior probabilities given evidence
- **Marginal**: Probability distribution of a single variable
- **Trace**: Step-by-step record of inference computation
- **Attribution**: Determining which inputs influenced an output
- **Calibration**: Whether predicted probabilities match empirical frequencies
- **KL Divergence**: Measure of difference between two probability distributions

---

**Last Updated:** 2026-04-23  
**Next Review:** End of Phase 1
