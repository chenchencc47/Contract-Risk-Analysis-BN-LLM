# 03 - Phase 1: Explainability Infrastructure Checklist

**Phase Goal:** Make every risk assessment decision transparent, traceable, and debuggable  
**Duration:** 4 months  
**Priority:** HIGH (foundation for everything else)

---

## Overview

Phase 1 builds the infrastructure for explainability without changing the core inference logic. We're keeping the weighted-sum scoring but adding:

1. **Reasoning traces** - Capture every step of the computation
2. **Attribution engine** - Identify which evidence contributed to each decision
3. **Trace storage** - Persist traces for later inspection
4. **Visualization** - Tools to view and understand traces

**Key Principle:** This phase should not change any risk scores - it only adds transparency to how they're computed.

---

## Pre-Phase: Setup (Week 1-2)

Before starting Phase 1 implementation, complete these setup tasks:

### 1.1 Repository Preparation
- [ ] Create feature branch: `feature/phase1-explainability`
- [ ] Set up database (PostgreSQL) locally or use SQLite for development
- [ ] Add new dependencies to `requirements.txt`:
  ```
  sqlalchemy>=2.0.0
  alembic>=1.12.0
  structlog>=23.0.0
  pydantic>=2.0.0
  ```
- [ ] Run `pip install -r requirements.txt`
- [ ] Create database migration setup
- [ ] Verify all existing tests pass: `pytest tests/ -v`

### 1.2 Code Refactoring (if needed)
- [ ] Refactor `inference.py` to extract pure scoring logic from I/O
- [ ] Ensure `build_evidence.py` returns intermediate mappings
- [ ] Add type hints to key functions for better documentation
- [ ] Add docstrings to public methods

**Success Criteria:**
- [ ] All tests pass
- [ ] No functional changes to risk scores
- [ ] Code is easier to instrument

---

## Module 1: Trace System Core (Weeks 3-6)

### 2.1 Design Trace Schema

Create file: `src/contract_risk_analysis/explainability/trace_schema.py`

```python
# Define these Pydantic models:

class TraceStep(BaseModel):
    step_number: int
    timestamp: datetime
    component: str  # e.g., "evidence_mapper", "inference_engine"
    operation: str  # e.g., "map_finding_to_node", "compute_dimension_score"
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    reasoning: str  # Human-readable explanation

class ReasoningTrace(BaseModel):
    trace_id: str  # UUID
    contract_id: str
    timestamp: datetime
    steps: List[TraceStep]
    final_result: Dict[str, Any]
    metadata: Dict[str, Any]  # version, config_hash, etc.
```

**Tasks:**
- [ ] Design schema to capture weighted-sum computation
- [ ] Include all inputs/outputs at each step
- [ ] Add version field for trace format evolution
- [ ] Review schema with team
- [ ] Create JSON schema for validation

### 2.2 Implement Trace Collector

Create file: `src/contract_risk_analysis/explainability/trace_collector.py`

**Key Class:**
```python
class TraceCollector:
    def __init__(self, contract_id: str):
        self.trace = ReasoningTrace(
            trace_id=str(uuid.uuid4()),
            contract_id=contract_id,
            timestamp=datetime.utcnow(),
            steps=[],
            final_result={},
            metadata={}
        )
        self._step_counter = 0
    
    def record_step(
        self, 
        component: str, 
        operation: str,
        inputs: Dict,
        outputs: Dict,
        reasoning: str
    ) -> None:
        """Record a single step in the trace"""
        pass  # TODO: Implement
    
    def finalize(self, final_result: Dict) -> ReasoningTrace:
        """Finalize and return the complete trace"""
        pass  # TODO: Implement
```

**Tasks:**
- [ ] Implement `record_step()` method
- [ ] Implement `finalize()` method
- [ ] Add validation that inputs/outputs are serializable
- [ ] Add timing information (duration_ms for each step)
- [ ] Unit tests for TraceCollector

**Test Criteria:**
```python
def test_trace_collector():
    collector = TraceCollector("test-contract-001")
    collector.record_step(
        component="evidence_mapper",
        operation="map_finding",
        inputs={"finding": {"key": "termination_missing"}},
        outputs={"node": "termination_clause", "state": "missing"},
        reasoning="Finding key 'termination_missing' maps to node 'termination_clause' state 'missing'"
    )
    trace = collector.finalize({"overall_risk": "high"})
    
    assert len(trace.steps) == 1
    assert trace.steps[0].component == "evidence_mapper"
    assert trace.final_result["overall_risk"] == "high"
```

### 2.3 Instrument Evidence Mapper

Modify file: `src/contract_risk_analysis/pipeline/build_evidence.py`

**Changes:**
- [ ] Add optional `trace_collector: Optional[TraceCollector]` parameter to `map_findings_to_evidence()`
- [ ] Record step for each finding mapping:
  - Component: `evidence_mapper`
  - Operation: `apply_mapping_rule`
  - Inputs: finding, rule matched
  - Outputs: node, state
  - Reasoning: Why this rule was chosen
- [ ] Record step for conflict resolution
- [ ] Record step for final evidence list

**Example:**
```python
def map_findings_to_evidence(
    findings: List[ReviewFinding],
    config: EvidenceMappingConfig,
    trace_collector: Optional[TraceCollector] = None
) -> List[RiskEvidence]:
    
    if trace_collector:
        trace_collector.record_step(
            component="evidence_mapper",
            operation="start_mapping",
            inputs={"num_findings": len(findings)},
            outputs={},
            reasoning=f"Starting to map {len(findings)} findings to BN nodes"
        )
    
    # ... existing logic ...
    
    for finding in findings:
        node, state = apply_mapping_rule(finding, config)
        
        if trace_collector:
            trace_collector.record_step(
                component="evidence_mapper",
                operation="map_finding",
                inputs={"finding": finding.model_dump()},
                outputs={"node": node, "state": state},
                reasoning=f"Applied rule: {finding.finding_key} -> {node}.{state}"
            )
    
    # ... rest of logic ...
```

**Tasks:**
- [ ] Modify function signature to accept optional TraceCollector
- [ ] Add trace recording at key points
- [ ] Ensure backward compatibility (works without trace_collector)
- [ ] Add unit tests for traced vs non-traced paths
- [ ] Verify no performance regression (>10%)

### 2.4 Instrument Inference Engine

Modify file: `src/contract_risk_analysis/bn/inference.py`

**Changes:**
- [ ] Add optional `trace_collector` parameter to `assess_risk()`
- [ ] Record step for evidence application
- [ ] Record step for each dimension score computation
- [ ] Record inputs/outputs for each weighted sum calculation
- [ ] Record final overall risk computation

**Example:**
```python
def assess_risk(
    evidence: List[RiskEvidence],
    trace_collector: Optional[TraceCollector] = None
) -> RiskReport:
    
    if trace_collector:
        trace_collector.record_step(
            component="inference_engine",
            operation="start_assessment",
            inputs={"evidence_count": len(evidence)},
            outputs={},
            reasoning="Starting risk assessment with weighted-sum scoring"
        )
    
    # ... existing logic ...
    
    # For each dimension
    for dimension, rules in dimension_risk_rules.items():
        score = compute_dimension_score(evidence, rules)
        
        if trace_collector:
            trace_collector.record_step(
                component="inference_engine",
                operation="compute_dimension_score",
                inputs={"dimension": dimension, "rules": rules},
                outputs={"score": score},
                reasoning=f"Computed {dimension} score: {score:.3f} using {len(rules)} weighted inputs"
            )
    
    # ... rest of logic ...
```

**Tasks:**
- [ ] Add trace recording to `assess_risk()`
- [ ] Record dimension score computations
- [ ] Record overall risk calculation with weights
- [ ] Record which evidence contributed to each dimension
- [ ] Add unit tests

### 2.5 Create Trace Storage Layer

Create file: `src/contract_risk_analysis/explainability/trace_store.py`

**Options:**
1. **SQLite for dev** - Simple, no setup
2. **PostgreSQL for prod** - Scalable, robust

**Implementation:**
```python
class TraceStore:
    def save(self, trace: ReasoningTrace) -> str:
        """Save trace and return trace_id"""
        pass
    
    def get(self, trace_id: str) -> Optional[ReasoningTrace]:
        """Retrieve trace by ID"""
        pass
    
    def query(
        self, 
        contract_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[ReasoningTrace]:
        """Query traces with filters"""
        pass
```

**Tasks:**
- [ ] Design database schema:
  ```sql
  CREATE TABLE traces (
      id UUID PRIMARY KEY,
      contract_id VARCHAR(255),
      created_at TIMESTAMP,
      trace_data JSONB,
      metadata JSONB
  );
  
  CREATE INDEX idx_traces_contract_id ON traces(contract_id);
  CREATE INDEX idx_traces_created_at ON traces(created_at);
  ```
- [ ] Implement SQLite backend for development
- [ ] Implement PostgreSQL backend for production
- [ ] Add connection pooling
- [ ] Add unit tests with test database
- [ ] Add integration tests

**Success Criteria:**
- [ ] Can save and retrieve traces
- [ ] Query by contract_id returns all traces for that contract
- [ ] Performance: Save <50ms, Retrieve <20ms

---

## Module 2: Attribution Engine (Weeks 7-10)

### 3.1 Design Attribution Schema

Create file: `src/contract_risk_analysis/explainability/attribution_schema.py`

```python
class EvidenceAttribution(BaseModel):
    """How much a single evidence contributed to a risk score"""
    evidence_id: str
    finding_key: str
    node_id: str
    state: str
    contribution_score: float  # -1.0 to 1.0, how much this pushed the score
    contribution_direction: Literal["increases_risk", "decreases_risk", "neutral"]
    confidence: float
    explanation: str

class DimensionAttribution(BaseModel):
    """Attribution for a single dimension"""
    dimension: str
    score: float
    total_attributions: List[EvidenceAttribution]
    top_contributors: List[EvidenceAttribution]  # Top 3
    contradictory_evidence: List[EvidenceAttribution]  # Evidence that disagrees

class FullAttribution(BaseModel):
    trace_id: str
    contract_id: str
    overall_risk: str
    dimension_attributions: List[DimensionAttribution]
    summary: str  # Human-readable summary
```

**Tasks:**
- [ ] Design schema for weighted-sum attribution
- [ ] Define contribution_score calculation method
- [ ] Review with team
- [ ] Create JSON schema

### 3.2 Implement Attribution Calculator

Create file: `src/contract_risk_analysis/explainability/attribution_engine.py`

**Algorithm for weighted-sum attribution:**

For each dimension score:
1. Get all evidence that contributed to this dimension
2. For each evidence, calculate what the score would be without that evidence (counterfactual)
3. Contribution = actual_score - counterfactual_score
4. Normalize contributions to sum to actual score

```python
class AttributionEngine:
    def calculate_attribution(
        self,
        trace: ReasoningTrace,
        target_node: Optional[str] = None
    ) -> FullAttribution:
        """
        Calculate which evidence contributed to which risk scores.
        
        For weighted-sum scoring:
        - Contribution = impact of including vs excluding evidence
        """
        pass  # TODO: Implement
    
    def _calculate_dimension_attribution(
        self,
        dimension: str,
        dimension_step: TraceStep,
        all_steps: List[TraceStep]
    ) -> DimensionAttribution:
        """Calculate attribution for a single dimension"""
        pass  # TODO: Implement
    
    def _compute_counterfactual_score(
        self,
        dimension: str,
        exclude_evidence: RiskEvidence,
        all_evidence: List[RiskEvidence]
    ) -> float:
        """Compute score if we exclude one piece of evidence"""
        pass  # TODO: Implement
```

**Tasks:**
- [ ] Implement contribution calculation
- [ ] Implement counterfactual scoring
- [ ] Handle cases where multiple evidence map to same node
- [ ] Generate human-readable explanations
- [ ] Unit tests with known attributions

**Test Example:**
```python
def test_attribution_calculation():
    # Setup: Create trace with known inputs
    # Evidence A contributes 0.3 to dimension X
    # Evidence B contributes 0.2 to dimension X
    # Dimension X final score = 0.5
    
    attribution = engine.calculate_attribution(trace)
    
    dim_x = next(d for d in attribution.dimension_attributions if d.dimension == "X")
    assert len(dim_x.total_attributions) == 2
    assert sum(a.contribution_score for a in dim_x.total_attributions) == pytest.approx(0.5)
```

### 3.3 Generate Human-Readable Explanations

Create file: `src/contract_risk_analysis/explainability/explanation_renderer.py`

```python
class ExplanationRenderer:
    def render_text(self, attribution: FullAttribution) -> str:
        """Generate human-readable text explanation"""
        lines = []
        lines.append(f"Risk Assessment Explanation for {attribution.contract_id}")
        lines.append(f"Overall Risk: {attribution.overall_risk.upper()}")
        lines.append("")
        
        for dim_attr in attribution.dimension_attributions:
            lines.append(f"\n{dim_attr.dimension} (Score: {dim_attr.score:.2f}):")
            lines.append("  Top contributing factors:")
            for contrib in dim_attr.top_contributors:
                lines.append(f"    - {contrib.explanation} (contribution: {contrib.contribution_score:+.2f})")
        
        return "\n".join(lines)
    
    def render_json(self, attribution: FullAttribution) -> Dict:
        """Generate structured JSON for API/UI"""
        return attribution.model_dump()
    
    def render_markdown(self, attribution: FullAttribution) -> str:
        """Generate markdown report"""
        pass  # TODO: Implement
```

**Tasks:**
- [ ] Implement text renderer
- [ ] Implement JSON renderer
- [ ] Implement markdown renderer for reports
- [ ] Add highlighting for high-risk contributors
- [ ] Add contradiction highlighting

---

## Module 3: API Integration (Weeks 11-14)

### 4.1 Update Core Pipeline to Return Traces

Modify: `src/contract_risk_analysis/pipeline/` orchestration

**Changes:**
- [ ] Create new orchestration function that:
  1. Creates TraceCollector
  2. Passes it through evidence mapping
  3. Passes it through inference
  4. Finalizes trace
  5. Saves trace to store
  6. Returns (RiskReport, trace_id)

```python
def analyze_with_tracing(
    contract_text: str,
    contract_id: str,
    trace_store: TraceStore
) -> Tuple[RiskReport, str]:
    """
    Analyze contract with full tracing.
    
    Returns:
        (risk_report, trace_id)
    """
    # Create trace collector
    collector = TraceCollector(contract_id)
    
    # Step 1: LLM Review (may not be traceable yet)
    findings = llm_review(contract_text)
    
    # Step 2: Evidence Mapping (with tracing)
    evidence = map_findings_to_evidence(findings, config, collector)
    
    # Step 3: Inference (with tracing)
    report = assess_risk(evidence, collector)
    
    # Step 4: Finalize and save trace
    trace = collector.finalize(report.model_dump())
    trace_id = trace_store.save(trace)
    
    return report, trace_id
```

### 4.2 Add Explainability Endpoints

Create file: `src/contract_risk_analysis/web/explainability_routes.py`

**New API Endpoints:**

```python
@app.get("/api/v1/traces/{trace_id}")
async def get_trace(trace_id: str) -> ReasoningTrace:
    """Get full reasoning trace"""
    trace = trace_store.get(trace_id)
    if not trace:
        raise HTTPException(404, "Trace not found")
    return trace

@app.get("/api/v1/traces/{trace_id}/attribution")
async def get_attribution(
    trace_id: str,
    target_node: Optional[str] = None
) -> FullAttribution:
    """Get attribution for a trace"""
    trace = trace_store.get(trace_id)
    if not trace:
        raise HTTPException(404, "Trace not found")
    
    attribution = attribution_engine.calculate_attribution(trace, target_node)
    return attribution

@app.get("/api/v1/traces/{trace_id}/explain")
async def explain_trace(
    trace_id: str,
    format: Literal["text", "json", "markdown"] = "text"
) -> str:
    """Get human-readable explanation"""
    trace = trace_store.get(trace_id)
    if not trace:
        raise HTTPException(404, "Trace not found")
    
    attribution = attribution_engine.calculate_attribution(trace)
    
    if format == "text":
        return explanation_renderer.render_text(attribution)
    elif format == "json":
        return explanation_renderer.render_json(attribution)
    else:
        return explanation_renderer.render_markdown(attribution)
```

**Tasks:**
- [ ] Add trace retrieval endpoint
- [ ] Add attribution endpoint
- [ ] Add explanation endpoint with format options
- [ ] Add OpenAPI documentation
- [ ] Add integration tests

### 4.3 Update Existing Analysis Endpoint

Modify: `src/contract_risk_analysis/web/server.py`

**Changes:**
- [ ] Update `/analyze` to return `trace_id` in response
- [ ] Make tracing optional (query param: `?trace=true`)
- [ ] Maintain backward compatibility

```python
class AnalysisResponse(BaseModel):
    report: RiskReport
    trace_id: Optional[str]  # New field
    processing_time_ms: float

@app.post("/api/v1/analyze")
async def analyze(
    request: AnalysisRequest,
    trace: bool = Query(False, description="Enable tracing")
) -> AnalysisResponse:
    if trace:
        report, trace_id = analyze_with_tracing(...)
    else:
        report = analyze_legacy(...)  # Existing logic
        trace_id = None
    
    return AnalysisResponse(
        report=report,
        trace_id=trace_id,
        processing_time_ms=...
    )
```

---

## Module 4: UI & Visualization (Weeks 13-16)

### 5.1 Create Trace Viewer (CLI)

Create file: `src/contract_risk_analysis/cli_trace_viewer.py`

```python
# Command: python -m contract_risk_analysis.cli_trace_viewer <trace_id>

def view_trace(trace_id: str, format: str = "pretty"):
    """Display trace in human-readable format"""
    trace = trace_store.get(trace_id)
    
    if format == "pretty":
        print_colored_trace(trace)
    elif format == "json":
        print(json.dumps(trace.model_dump(), indent=2))
    elif format == "steps":
        for step in trace.steps:
            print(f"{step.step_number}. [{step.component}] {step.operation}")
            print(f"   Reasoning: {step.reasoning}")
            print()
```

**Tasks:**
- [ ] Implement pretty-printing with colors
- [ ] Show step-by-step progression
- [ ] Highlight key decisions
- [ ] Show timing information
- [ ] Add filtering (show only specific component)

### 5.2 Update Streamlit Demo

Modify: `src/contract_risk_analysis/demo/streamlit_app.py`

**Add new sections:**

```python
# After showing risk report, add:
if st.button("Show Reasoning Trace"):
    trace = trace_store.get(report.trace_id)
    
    st.subheader("Analysis Steps")
    for step in trace.steps:
        with st.expander(f"Step {step.step_number}: {step.operation}"):
            st.write(f"**Component:** {step.component}")
            st.write(f"**Reasoning:** {step.reasoning}")
            st.json(step.inputs)
            st.json(step.outputs)
    
    st.subheader("Evidence Attribution")
    attribution = attribution_engine.calculate_attribution(trace)
    
    for dim_attr in attribution.dimension_attributions:
        st.write(f"**{dim_attr.dimension}** (score: {dim_attr.score:.2f})")
        
        # Bar chart of contributions
        contributors = dim_attr.total_attributions
        st.bar_chart({
            c.evidence_id: c.contribution_score 
            for c in contributors
        })
```

**Tasks:**
- [ ] Add "Show Trace" button to results page
- [ ] Display steps in expandable sections
- [ ] Show attribution charts
- [ ] Highlight high-risk factors
- [ ] Show contradictory evidence

---

## Testing & Validation (Weeks 15-16)

### 6.1 Unit Tests

Create: `tests/explainability/`

**Test Files:**
- `test_trace_collector.py` - Test trace recording
- `test_trace_store.py` - Test storage backends
- `test_attribution_engine.py` - Test attribution calculation
- `test_explanation_renderer.py` - Test rendering

**Coverage Target:** >80% for new code

**Tasks:**
- [ ] Write comprehensive unit tests
- [ ] Test edge cases (empty evidence, conflicting evidence)
- [ ] Test performance (trace overhead <10%)
- [ ] Mock external dependencies

### 6.2 Integration Tests

Create: `tests/integration/test_explainability.py`

**Test Scenarios:**
- [ ] End-to-end: Contract → Trace → Attribution → Explanation
- [ ] API tests: All new endpoints
- [ ] Database tests: Save/retrieve/query traces
- [ ] Backward compatibility: Old API still works

### 6.3 Validation Checklist

**Functional Validation:**
- [ ] Risk scores unchanged from baseline (compare 100 test contracts)
- [ ] Traces capture all inference steps
- [ ] Attribution sums correctly
- [ ] Explanations are human-readable

**Performance Validation:**
- [ ] Trace overhead <100ms per request
- [ ] Attribution calculation <50ms
- [ ] Database queries <20ms
- [ ] Memory usage <10% increase

**API Validation:**
- [ ] All endpoints return correct schemas
- [ ] Error handling works correctly
- [ ] OpenAPI documentation is accurate

---

## Deliverables Checklist

### Code Deliverables
- [ ] `src/contract_risk_analysis/explainability/` module
  - [ ] `trace_schema.py`
  - [ ] `trace_collector.py`
  - [ ] `trace_store.py` (SQLite + PostgreSQL)
  - [ ] `attribution_schema.py`
  - [ ] `attribution_engine.py`
  - [ ] `explanation_renderer.py`
- [ ] Instrumented `build_evidence.py`
- [ ] Instrumented `inference.py`
- [ ] New API routes in `explainability_routes.py`
- [ ] Updated `server.py` with trace endpoints
- [ ] CLI trace viewer
- [ ] Updated Streamlit app

### Database Deliverables
- [ ] Migration scripts for trace table
- [ ] Schema documentation
- [ ] Index definitions

### Test Deliverables
- [ ] Unit tests (>80% coverage)
- [ ] Integration tests
- [ ] Performance benchmarks
- [ ] Regression tests (risk scores unchanged)

### Documentation Deliverables
- [ ] API documentation (OpenAPI)
- [ ] Architecture diagram (explainability components)
- [ ] User guide: "How to read traces"
- [ ] Developer guide: "How to add tracing to new components"

---

## Success Criteria

### Must Have (Critical)
- [ ] Every risk assessment can produce a trace
- [ ] Traces stored and retrievable by ID
- [ ] Attribution shows which evidence contributed to each score
- [ ] Explanations are human-readable
- [ ] No functional changes to risk scores
- [ ] All tests pass

### Should Have (Important)
- [ ] Trace viewer in Streamlit UI
- [ ] Performance overhead <100ms
- [ ] API documentation complete
- [ ] CLI tool for viewing traces
- [ ] >80% test coverage

### Nice to Have (Optional)
- [ ] Counterfactual explanations
- [ ] Export traces to file
- [ ] Trace comparison (diff view)
- [ ] Performance profiling dashboard

---

## Phase 1 Completion Definition of Done

- [ ] All checklist items above completed
- [ ] Code review by senior engineer
- [ ] Integration tests pass
- [ ] Performance benchmarks meet targets
- [ ] Documentation updated
- [ ] Demo video/screenshots created
- [ ] Team demo session conducted
- [ ] Alpha release tagged: `v0.5.0-alpha`

---

## Common Pitfalls & How to Avoid Them

### Pitfall 1: Traces are too verbose
**Problem:** Traces become huge and unwieldy  
**Solution:** 
- Only record key decision points
- Summarize large inputs/outputs
- Use references instead of duplicating data

### Pitfall 2: Attribution is confusing
**Problem:** Users don't understand contribution scores  
**Solution:**
- Always provide human-readable explanations
- Use visualizations (bar charts)
- Show concrete examples in documentation

### Pitfall 3: Performance regression
**Problem:** Tracing slows down the system  
**Solution:**
- Make tracing optional
- Profile before and after
- Use async storage writes
- Cache attribution calculations

### Pitfall 4: Database bloat
**Problem:** Trace storage grows too fast  
**Solution:**
- Implement retention policies (90 days default)
- Compress old traces
- Archive to cold storage
- Only store traces for traced requests (not all)

---

## Next Steps

After Phase 1 is complete:
1. **Review** - Team retrospective on what worked/didn't
2. **Plan Phase 2** - Use `04-PHASE-2-CHECKLIST.md`
3. **Update Roadmap** - Adjust timeline if needed
4. **Celebrate** - Phase 1 is a major milestone!

---

**Last Updated:** 2026-04-23  
**Status:** Ready for Implementation
