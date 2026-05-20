# 01 - Strategic Roadmap

**Goal:** Transform BN-Contract-Risk-Analysis from demo → high-explainability, evaluable, probabilistic contract risk reasoning system

**Current State:** Weighted-sum scoring with BN-like structure but no true probabilistic inference  
**Target State:** Full Bayesian reasoning with uncertainty quantification, explainable traces, validated metrics

**Timeline:** 12 months (3 phases × 4 months each)  
**Risk Level:** Medium (significant architectural changes)

---

## Executive Summary

This roadmap outlines a phased approach to evolve the current contract risk analysis system from a heuristic scoring prototype into a production-grade probabilistic reasoning engine. Each phase builds on the previous, ensuring backward compatibility and incremental validation.

### Strategic Pillars

1. **Explainability First:** Every decision must be traceable and justifiable
2. **Evaluability by Design:** Metrics and benchmarks are built, not bolted on
3. **True Probability:** Replace heuristics with principled Bayesian inference
4. **Production Ready:** Deployment, monitoring, and operational concerns addressed

---

## Phase Overview

| Phase | Duration | Focus | Deliverable | Success Criteria |
|-------|----------|-------|-------------|------------------|
| **Phase 1** | Months 1-4 | Explainability Infrastructure | Reasoning traces, attribution visualization | 100% decision traceability, <100ms trace overhead |
| **Phase 2** | Months 5-8 | Bayesian Inference Engine | True probabilistic reasoning, CPT learning | KL divergence <0.1 vs expert judgments |
| **Phase 3** | Months 9-12 | Evaluation & Validation | Benchmark dataset, automated metrics | F1 >0.85, calibration error <0.05 |

---

## Phase 1: Explainability Infrastructure (Months 1-4)

### Goal
Make every risk assessment decision transparent, traceable, and debuggable without sacrificing performance.

### Key Deliverables

#### 1.1 Reasoning Trace System
- [ ] Implement trace capture at each inference step
- [ ] Store evidence-to-node mapping decisions
- [ ] Record scoring computation paths
- [ ] Export traces in structured format (JSON/Protobuf)
- [ ] Trace viewer UI for visual inspection

#### 1.2 Attribution Engine
- [ ] Identify which evidence contributed to each risk score
- [ ] Calculate contribution weights for each finding
- [ ] Highlight contradictory evidence
- [ ] Generate human-readable explanation strings
- [ ] API endpoint: `/explain/{report_id}`

#### 1.3 Gap Analysis & Documentation
- [ ] Audit current codebase for explainability gaps
- [ ] Document current weighted-sum logic
- [ ] Create explainability requirements matrix
- [ ] Define trace schema v1.0

### Milestone: Alpha Release (End Month 4)
**Criteria:**
- [ ] All risk assessments include reasoning traces
- [ ] Traces can be exported and visualized
- [ ] Attribution shows which evidence drove each score
- [ ] Documentation explains trace format
- [ ] Demo updated to show traces in UI

### Dependencies
- Internal: None (builds on existing code)
- External: None

---

## Phase 2: Bayesian Inference Engine (Months 5-8)

### Goal
Replace weighted-sum scoring with true Bayesian probabilistic inference while maintaining explainability.

### Key Deliverables

#### 2.1 Probabilistic Inference Core
- [ ] Implement belief propagation algorithm
- [ ] Support exact inference for current BN size (~20 nodes)
- [ ] Handle evidence with uncertainty (soft evidence)
- [ ] Marginal probability computation
- [ ] Conditional probability queries

#### 2.2 CPT Learning & Parameter Estimation
- [ ] Implement maximum likelihood estimation from labeled data
- [ ] Bayesian parameter learning with priors
- [ ] Structure learning for optimal network topology
- [ ] Parameter sensitivity analysis
- [ ] Versioning for CPT updates

#### 2.3 Uncertainty Quantification
- [ ] Output full probability distributions (not just point estimates)
- [ ] Confidence intervals for risk scores
- [ ] Entropy-based uncertainty metrics
- [ ] Visualization: probability bars, distribution plots
- [ ] API: `GET /risk/{contract_id}/distribution`

#### 2.4 Backward Compatibility
- [ ] Legacy mode for weighted-sum scoring
- [ ] Migration path for existing configs
- [ ] Feature flags for inference mode
- [ ] Performance parity: <2x latency increase

### Milestone: Beta Release (End Month 8)
**Criteria:**
- [ ] True Bayesian inference operational
- [ ] CPTs learned from training data
- [ ] Probability distributions exposed in API
- [ ] Backward compatible with Phase 1 traces
- [ ] Documentation covers inference algorithms
- [ ] Unit tests cover probabilistic correctness

### Dependencies
- Internal: Phase 1 complete (traces help validate inference)
- External: Labeled contract dataset (can start with synthetic)

---

## Phase 3: Evaluation & Validation (Months 9-12)

### Goal
Establish rigorous evaluation framework to validate accuracy, calibration, and utility of risk assessments.

### Key Deliverables

#### 3.1 Benchmark Dataset
- [ ] Curate 500+ contract-risk pairs with ground truth labels
- [ ] Expert legal annotators for risk judgments
- [ ] Inter-annotator agreement >0.8 (Cohen's kappa)
- [ ] Stratified by contract type (NDA, SLA, MSA, etc.)
- [ ] Public/private split for validation
- [ ] Data license and privacy compliance

#### 3.2 Evaluation Metrics Suite
- [ ] Classification: Precision, Recall, F1, ROC-AUC
- [ ] Calibration: Brier score, reliability diagrams, calibration error
- [ ] Probabilistic: Log-likelihood, KL divergence
- [ ] Decision utility: Cost-sensitive accuracy
- [ ] Regression: MAE, RMSE for risk scores

#### 3.3 Automated Evaluation Pipeline
- [ ] Continuous integration tests for model performance
- [ ] Regression detection on benchmark dataset
- [ ] Statistical significance testing
- [ ] Performance dashboards
- [ ] Alerting for metric degradation

#### 3.4 Human Evaluation Protocol
- [ ] Side-by-side comparison with expert assessments
- [ ] User study protocol (IRB approval if needed)
- [ ] Utility scoring for risk warnings
- [ ] Qualitative feedback collection
- [ ] Expert panel review quarterly

### Milestone: Production Release (End Month 12)
**Criteria:**
- [ ] F1 score >0.85 on benchmark
- [ ] Calibration error <0.05
- [ ] Human expert agreement >0.85
- [ ] Evaluation pipeline runs automatically on PR
- [ ] Documentation includes evaluation results
- [ ] Benchmark dataset versioned and documented

### Dependencies
- Internal: Phase 2 complete (need inference engine to evaluate)
- External: Legal experts for annotation (6-8 week lead time)

---

## Timeline Visualization

```
Month:  1   2   3   4   5   6   7   8   9   10  11  12
        |--- Phase 1: Explainability ---|
                        |--- Phase 2: Bayesian Inference ---|
                                            |--- Phase 3: Evaluation ---|
        
Milestones:
M1 (M4):  ████████ ALPHA - Tracing operational
M2 (M8):  ████████ BETA  - Bayesian inference live
M3 (M12): ████████ PROD  - Validated, benchmarked

Key Activities:
- M1-M2:  Trace system design & implementation
- M3:     Attribution engine
- M4:     Alpha release & review
- M5-M6:  Inference algorithm implementation
- M6-M7:  CPT learning from data
- M7-M8:  Uncertainty quantification
- M8:     Beta release & dogfooding
- M9:     Benchmark dataset curation
- M10:    Evaluation metrics implementation
- M11:    Human evaluation study
- M12:    Production release & documentation
```

---

## Resource Allocation

### Team Structure

| Role | Phase 1 | Phase 2 | Phase 3 | Notes |
|------|---------|---------|---------|-------|
| **Senior Engineer** | 1.0 FTE | 1.0 FTE | 0.5 FTE | Architecture, core algorithms |
| **Backend Engineer** | 0.5 FTE | 1.0 FTE | 0.5 FTE | API, pipeline, integration |
| **Data Scientist** | 0.25 FTE | 0.75 FTE | 1.0 FTE | Bayesian methods, evaluation |
| **Frontend/DevOps** | 0.25 FTE | 0.25 FTE | 0.25 FTE | Trace UI, deployment |
| **Legal Expert** | 0.1 FTE | 0.1 FTE | 0.5 FTE | Annotation, validation |

### Total Effort: ~15 person-months

---

## Risk Management

### Critical Path Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Bayesian inference too slow | Medium | High | Start with exact, migrate to approximate (MCMC, variational) |
| Insufficient training data | Medium | High | Synthetic data generation, active learning, transfer learning |
| Expert annotation bottleneck | High | Medium | Start early (M8), use multiple annotators, inter-annotator agreement checks |
| Backward compatibility breaks | Low | High | Feature flags, extensive testing, gradual rollout |

### Contingency Plans

**If Phase 1 takes longer than 4 months:**
- Reduce Phase 2 scope (skip structure learning, keep fixed CPTs)
- Parallelize Phase 2 & 3 (start dataset curation during inference dev)

**If Bayesian inference is computationally infeasible:**
- Use hybrid approach: probabilistic for uncertainty, weighted-sum for speed
- Investigate approximate inference (loopy belief propagation, sampling)

**If benchmark dataset is delayed:**
- Use synthetic data for initial validation
- Partner with legal firms for data sharing agreements

---

## Success Metrics Dashboard

### Phase 1 (Explainability)
- [ ] Trace coverage: 100% of inferences
- [ ] Trace overhead: <100ms per request
- [ ] Attribution accuracy: >95% (manual spot-checks)
- [ ] Documentation completeness: All public APIs documented

### Phase 2 (Bayesian Inference)
- [ ] Inference accuracy: KL divergence <0.1 vs expert judgments
- [ ] Inference latency: P95 <500ms for 20-node network
- [ ] Uncertainty calibration: Reliability diagram within ±0.05
- [ ] Backward compatibility: 100% of existing tests pass

### Phase 3 (Evaluation)
- [ ] Classification: F1 >0.85, Precision >0.85, Recall >0.85
- [ ] Calibration: Brier score <0.15, Calibration error <0.05
- [ ] Dataset: 500+ labeled contracts, κ >0.8 inter-annotator agreement
- [ ] Human evaluation: Expert agreement >0.85, utility score >4/5

---

## Dependencies & External Factors

### Technical Dependencies
- Python 3.9+ (current)
- PyTorch/NumPy for probabilistic computation (add in Phase 2)
- FastAPI (current)
- PostgreSQL or similar for trace storage (add in Phase 1)

### External Dependencies
- Moonshot/Kimi API (current) - monitor rate limits, pricing
- Legal expert availability for annotation (Phase 3)
- Compute resources for inference (Phase 2+)

### Regulatory/Compliance
- Contract data privacy (GDPR, CCPA if applicable)
- Model explainability requirements (if regulated industry)
- Data retention policies for traces and benchmarks

---

## Communication Plan

### Internal Updates
- **Weekly:** Standup during active implementation
- **Bi-weekly:** Demo of completed features
- **Monthly:** Phase milestone review
- **Quarterly:** Strategic alignment check

### External Communication
- **Alpha (M4):** Internal team only, gather feedback
- **Beta (M8):** Limited external access, case studies
- **Production (M12):** Public announcement, documentation

### Documentation Updates
- Each phase completion triggers documentation review
- Architecture Decision Records (ADRs) for major choices
- Changelog maintained with each release

---

## Appendix: Definition of Done

### Phase 1 Definition of Done
- [ ] All checklist items in `03-PHASE-1-CHECKLIST.md` complete
- [ ] Code review by at least one senior engineer
- [ ] All new code has >80% test coverage
- [ ] Documentation updated (API docs, README, architecture diagrams)
- [ ] Alpha release tagged in git (`v0.5.0-alpha`)
- [ ] Demo video/screenshots showing trace functionality

### Phase 2 Definition of Done
- [ ] All checklist items in `04-PHASE-2-CHECKLIST.md` complete
- [ ] Probabilistic inference validated against known test cases
- [ ] Performance benchmarks show <2x latency vs weighted-sum
- [ ] Backward compatibility tests pass
- [ ] Beta release tagged (`v0.8.0-beta`)
- [ ] Technical blog post or paper draft (optional)

### Phase 3 Definition of Done
- [ ] All checklist items in `05-PHASE-3-CHECKLIST.md` complete
- [ ] Benchmark dataset publicly documented
- [ ] Evaluation metrics meet or exceed targets
- [ ] Human evaluation study complete with IRB approval
- [ ] Production release tagged (`v1.0.0`)
- [ ] Final architecture documentation published

---

**Last Updated:** 2026-04-23  
**Next Review:** End of Phase 1 (Month 4)
