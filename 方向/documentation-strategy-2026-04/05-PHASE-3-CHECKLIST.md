# 05 - Phase 3: Evaluation & Validation Checklist

**Phase Goal:** Establish rigorous evaluation framework with benchmarks, metrics, and validation  
**Duration:** 4 months  
**Prerequisite:** Phase 2 complete (Bayesian inference engine)  
**Priority:** HIGH (required for production deployment)

---

## Overview

Phase 3 transforms the system from "it works" to "we know it works and how well." This phase is about building trust through measurement.

### Why Evaluation Matters

Without rigorous evaluation:
- We can't know if Bayesian is better than weighted-sum
- We can't detect when the system degrades
- We can't convince stakeholders to trust the system
- We can't improve systematically

### Key Deliverables

1. **Benchmark Dataset** - 500+ labeled contracts with ground truth
2. **Metrics Suite** - Classification, calibration, probabilistic metrics
3. **Evaluation Pipeline** - Automated testing on every change
4. **Human Validation** - Expert comparison study
5. **Continuous Monitoring** - Production metrics and alerting

---

## Pre-Phase: Planning (Week 1-2)

### 1.1 Define Success Metrics

Before collecting data, define what "good" means:

**Classification Metrics:**
```python
metrics = {
    "accuracy": "Overall correctness",
    "precision": "Of predicted high-risk, how many are actually high-risk?",
    "recall": "Of actual high-risk, how many did we catch?",
    "f1": "Harmonic mean of precision and recall",
    "roc_auc": "Ability to discriminate risk levels",
    "confusion_matrix": "Detailed breakdown by class"
}
```

**Calibration Metrics:**
```python
metrics = {
    "expected_calibration_error": "Average |confidence - accuracy|",
    "maximum_calibration_error": "Worst bin error",
    "brier_score": "Mean squared error of probabilities",
    "reliability_diagram": "Visual calibration plot"
}
```

**Probabilistic Metrics:**
```python
metrics = {
    "log_likelihood": "How likely is the data given our model?",
    "kl_divergence": "Distance from expert judgments",
    "entropy": "Average uncertainty (lower is more confident)"
}
```

**Decision Metrics:**
```python
metrics = {
    "decision_accuracy": "Correct signing recommendations",
    "cost_sensitive_accuracy": "Weighted by business impact",
    "false_negative_rate": "Missed high-risk contracts (critical!)"
}
```

### 1.2 Choose Baselines

What are we comparing against?

1. **Weighted-Sum (Current)** - Is Bayesian actually better?
2. **Random Baseline** - Sanity check (should be much worse)
3. **Majority Class** - Always predict most common class
4. **Human Expert** - Gold standard (expensive but necessary)

### 1.3 Legal/Compliance Review

- [ ] **Data Privacy** - Do contracts contain PII? Need anonymization?
- [ ] **Data License** - Can we use contracts for training/evaluation?
- [ ] **IRB Approval** - If doing human subjects research (expert studies)
- [ ] **Export Controls** - Any restrictions on model/data sharing?

---

## Module 1: Benchmark Dataset (Weeks 3-8)

### 2.1 Dataset Specification

Create: `docs/benchmark_dataset_spec.md`

```yaml
Benchmark Dataset Specification v1.0

Size: 500 contracts minimum (target: 1000)
Stratification:
  - Contract types: NDA (30%), SLA (25%), MSA (20%), Employment (15%), Other (10%)
  - Risk distribution: Low (40%), Medium (35%), High (20%), Critical (5%)
  - Jurisdictions: US (50%), EU (30%), Asia (15%), Other (5%)
  - Industries: Tech (40%), Finance (25%), Healthcare (20%), Other (15%)

Required Fields per Contract:
  - contract_id: Unique identifier
  - contract_text: Full text (anonymized)
  - contract_type: Category
  - metadata: Length, jurisdiction, industry, date
  
  # Ground truth annotations (from legal experts)
  - expert_annotations: List of {expert_id, risk_level, confidence, timestamp}
  - consensus_risk: Majority vote (or expert panel consensus)
  - agreement_score: Inter-annotator agreement (Cohen's kappa)
  
  # Annotation metadata
  - annotation_time_minutes: How long expert spent
  - difficulty_rating: Expert-rated 1-5
  - notes: Any special considerations
```

### 2.2 Data Collection Pipeline

Create: `src/contract_risk_analysis/evaluation/data_collection.py`

```python
class ContractDatasetBuilder:
    """
    Build and manage benchmark dataset.
    """
    
    def __init__(self, storage_path: str):
        self.storage = ContractStorage(storage_path)
        
    def add_contract(
        self,
        contract_text: str,
        metadata: ContractMetadata,
        source: str  # Where contract came from
    ) -> str:
        """
        Add a contract to the dataset.
        
        Steps:
        1. Anonymize (remove PII)
        2. Validate format
        3. Assign ID
        4. Store
        """
        # Anonymization
        anonymized_text = self._anonymize(contract_text)
        
        # Validation
        self._validate_contract(anonymized_text)
        
        # Create entry
        contract_id = str(uuid.uuid4())
        entry = ContractEntry(
            id=contract_id,
            text=anonymized_text,
            metadata=metadata,
            source=source,
            added_at=datetime.utcnow(),
            annotations=[]
        )
        
        # Store
        self.storage.save(entry)
        
        return contract_id
    
    def _anonymize(self, text: str) -> str:
        """
        Remove personally identifiable information.
        
        Techniques:
        - Named entity recognition (remove names, companies)
        - Pattern matching (emails, phone numbers, SSNs)
        - Manual review for edge cases
        """
        # Use spaCy NER
        doc = nlp(text)
        
        anonymized = text
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG", "GPE"]:
                anonymized = anonymized.replace(ent.text, f"[{ent.label_}]")
        
        # Pattern matching
        anonymized = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', anonymized)
        
        return anonymized
    
    def get_annotation_task(self, expert_id: str) -> Optional[AnnotationTask]:
        """
        Get next contract for expert to annotate.
        
        Prioritizes:
        1. Contracts with few annotations
        2. Diverse contract types
        3. High-confidence requirements first
        """
        # Find contracts needing annotation
        candidates = self.storage.get_unannotated(expert_id)
        
        # Prioritize by stratification needs
        stratification_needs = self._get_stratification_needs()
        
        # Score candidates
        best_candidate = max(
            candidates,
            key=lambda c: self._annotation_priority(c, stratification_needs)
        )
        
        return AnnotationTask(
            contract_id=best_candidate.id,
            contract_text=best_candidate.text,
            metadata=best_candidate.metadata
        )
    
    def submit_annotation(
        self,
        contract_id: str,
        expert_id: str,
        annotation: ExpertAnnotation
    ) -> None:
        """Submit expert annotation"""
        contract = self.storage.get(contract_id)
        contract.annotations.append(annotation)
        self.storage.save(contract)
        
        # Update consensus
        self._update_consensus(contract_id)
```

### 2.3 Expert Annotation Interface

Create: `src/contract_risk_analysis/evaluation/annotation_ui.py`

Simple Streamlit interface for experts:

```python
# annotation_app.py
import streamlit as st

st.title("Contract Risk Annotation")

# Expert login
expert_id = st.text_input("Expert ID")
if not expert_id:
    st.stop()

# Get next task
task = dataset_builder.get_annotation_task(expert_id)

st.subheader("Contract")
st.text_area("Contract Text", task.contract_text, height=400)

st.subheader("Your Assessment")

# Risk level
col1, col2 = st.columns(2)
with col1:
    risk_level = st.selectbox(
        "Risk Level",
        ["low", "medium", "high", "critical"]
    )

with col2:
    confidence = st.slider(
        "Confidence",
        0.0, 1.0, 0.8
    )

# Detailed assessment
st.subheader("Detailed Assessment")

legal_enforceability = st.selectbox(
    "Legal Enforceability Risk",
    ["low", "medium", "high", "critical"]
)

financial_exposure = st.selectbox(
    "Financial Exposure Risk",
    ["low", "medium", "high", "critical"]
)

# ... other dimensions

signing_recommendation = st.radio(
    "Signing Recommendation",
    ["approve", "approve_with_changes", "reject", "needs_review"]
)

# Notes
notes = st.text_area("Notes", placeholder="Any special considerations...")

# Submit
if st.button("Submit Annotation"):
    annotation = ExpertAnnotation(
        expert_id=expert_id,
        risk_level=risk_level,
        confidence=confidence,
        dimensions={
            "legal_enforceability": legal_enforceability,
            "financial_exposure": financial_exposure,
            # ...
        },
        signing_recommendation=signing_recommendation,
        notes=notes,
        timestamp=datetime.utcnow(),
        time_spent_minutes=...  # Track time
    )
    
    dataset_builder.submit_annotation(task.contract_id, expert_id, annotation)
    st.success("Annotation submitted! Loading next contract...")
    st.experimental_rerun()
```

### 2.4 Inter-Annotator Agreement

```python
class AgreementCalculator:
    """
    Calculate inter-annotator agreement.
    """
    
    def cohens_kappa(self, annotations1, annotations2):
        """
        Cohen's kappa for two annotators.
        
        κ = (p_o - p_e) / (1 - p_e)
        
        where:
        - p_o = observed agreement
        - p_e = expected agreement (by chance)
        
        Interpretation:
        - κ < 0.2: Poor
        - 0.2-0.4: Fair
        - 0.4-0.6: Moderate
        - 0.6-0.8: Good
        - >0.8: Excellent
        """
        from sklearn.metrics import cohen_kappa_score
        
        return cohen_kappa_score(annotations1, annotations2)
    
    def fleiss_kappa(self, all_annotations):
        """
        Fleiss' kappa for multiple annotators.
        """
        # Implementation for multiple annotators
        pass
    
    def krippendorffs_alpha(self, all_annotations):
        """
        Krippendorff's alpha (more general, handles missing data).
        """
        pass
```

**Tasks:**
- [ ] Implement agreement metrics
- [ ] Compute agreement per contract type
- [ ] Identify problematic contracts (low agreement)
- [ ] Set minimum agreement threshold (κ > 0.6)

### 2.5 Dataset Statistics & Quality

```python
def generate_dataset_report(dataset_path: str) -> DatasetReport:
    """Generate comprehensive dataset quality report"""
    
    contracts = load_all_contracts(dataset_path)
    
    report = {
        "total_contracts": len(contracts),
        "stratification": {
            "by_type": Counter(c.metadata.contract_type for c in contracts),
            "by_risk": Counter(c.consensus_risk for c in contracts),
            "by_jurisdiction": Counter(c.metadata.jurisdiction for c in contracts),
        },
        "annotations": {
            "total_annotations": sum(len(c.annotations) for c in contracts),
            "avg_annotations_per_contract": mean(len(c.annotations) for c in contracts),
            "unique_experts": len(set(a.expert_id for c in contracts for a in c.annotations)),
        },
        "agreement": {
            "mean_kappa": mean(agreements),
            "min_kappa": min(agreements),
            "contracts_below_threshold": count_low_agreement,
        },
        "quality_flags": {
            "contracts_needing_more_annotations": [...],
            "contracts_with_low_agreement": [...],
            "potential_duplicates": [...],
        }
    }
    
    return report
```

**Success Criteria:**
- [ ] 500+ contracts annotated
- [ ] 3+ experts per contract
- [ ] Mean κ > 0.6
- [ ] Stratification balanced

---

## Module 2: Evaluation Metrics Suite (Weeks 7-10)

### 3.1 Classification Metrics

Create: `src/contract_risk_analysis/evaluation/metrics/classification.py`

```python
class ClassificationMetrics:
    """
    Standard classification metrics for risk levels.
    """
    
    def __init__(self, predictions: List[str], ground_truth: List[str]):
        self.predictions = predictions
        self.ground_truth = ground_truth
        self.labels = ["low", "medium", "high", "critical"]
        
    def accuracy(self) -> float:
        """Overall accuracy"""
        correct = sum(p == g for p, g in zip(self.predictions, self.ground_truth))
        return correct / len(self.predictions)
    
    def precision_recall_f1(self) -> Dict[str, Dict[str, float]]:
        """
        Per-class precision, recall, F1.
        """
        from sklearn.metrics import classification_report
        
        report = classification_report(
            self.ground_truth,
            self.predictions,
            target_names=self.labels,
            output_dict=True
        )
        
        return report
    
    def confusion_matrix(self) -> np.ndarray:
        """Confusion matrix"""
        from sklearn.metrics import confusion_matrix
        
        return confusion_matrix(
            self.ground_truth,
            self.predictions,
            labels=self.labels
        )
    
    def macro_metrics(self) -> Dict[str, float]:
        """Macro-averaged metrics (treats all classes equally)"""
        per_class = self.precision_recall_f1()
        
        return {
            "macro_precision": mean(per_class[label]["precision"] for label in self.labels),
            "macro_recall": mean(per_class[label]["recall"] for label in self.labels),
            "macro_f1": mean(per_class[label]["f1-score"] for label in self.labels),
        }
    
    def weighted_metrics(self) -> Dict[str, float]:
        """Weighted metrics (by class frequency)"""
        per_class = self.precision_recall_f1()
        
        # Get support (number of samples) for each class
        supports = {label: per_class[label]["support"] for label in self.labels}
        total = sum(supports.values())
        
        return {
            "weighted_precision": sum(
                per_class[label]["precision"] * supports[label] / total
                for label in self.labels
            ),
            # ... similar for recall, f1
        }
```

### 3.2 Calibration Metrics

Create: `src/contract_risk_analysis/evaluation/metrics/calibration.py`

```python
class CalibrationMetrics:
    """
    Metrics for probabilistic calibration.
    
    A well-calibrated model has:
    - When it says "80% confident", it's right 80% of the time
    """
    
    def __init__(
        self,
        probabilities: List[Dict[str, float]],  # Predicted distributions
        ground_truth: List[str]  # Actual outcomes
    ):
        self.probs = probabilities
        self.truth = ground_truth
        
    def expected_calibration_error(self, n_bins: int = 10) -> float:
        """
        Expected Calibration Error (ECE).
        
        ECE = Σ (bin_size / total) * |accuracy(bin) - confidence(bin)|
        """
        # Get confidence (max probability) and predicted class for each sample
        confidences = []
        predictions = []
        
        for prob_dist in self.probs:
            pred_class = max(prob_dist, key=prob_dist.get)
            confidence = prob_dist[pred_class]
            confidences.append(confidence)
            predictions.append(pred_class)
        
        # Create bins
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        
        for i in range(n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            
            # Find samples in this bin
            in_bin = [
                (conf, pred, truth)
                for conf, pred, truth in zip(confidences, predictions, self.truth)
                if bin_lower <= conf < bin_upper
            ]
            
            if not in_bin:
                continue
            
            # Calculate accuracy and average confidence for bin
            bin_size = len(in_bin)
            bin_accuracy = sum(1 for _, pred, truth in in_bin if pred == truth) / bin_size
            bin_confidence = sum(conf for conf, _, _ in in_bin) / bin_size
            
            # Weight by bin size
            ece += (bin_size / len(self.probs)) * abs(bin_accuracy - bin_confidence)
        
        return ece
    
    def maximum_calibration_error(self, n_bins: int = 10) -> float:
        """Maximum calibration error across all bins"""
        # Similar to ECE but take max instead of weighted average
        pass
    
    def brier_score(self) -> float:
        """
        Brier score (mean squared error of probabilities).
        
        Brier = (1/N) Σ (p_i - o_i)^2
        
        where:
        - p_i = predicted probability of observed class
        - o_i = 1 if class observed, 0 otherwise
        
        Lower is better (0 = perfect, 0.25 = random for binary).
        """
        brier = 0.0
        
        for prob_dist, truth in zip(self.probs, self.truth):
            # Get predicted probability for true class
            prob_true = prob_dist.get(truth, 0)
            
            # Brier contribution
            # (p - 1)^2 for true class + Σ p^2 for other classes
            score = (prob_true - 1) ** 2
            for cls, prob in prob_dist.items():
                if cls != truth:
                    score += prob ** 2
            
            brier += score
        
        return brier / len(self.probs)
    
    def reliability_diagram(self, n_bins: int = 10) -> Dict:
        """
        Data for reliability diagram.
        
        Shows calibration curve: predicted confidence vs actual accuracy.
        """
        # Similar to ECE calculation but return per-bin data
        pass
```

### 3.3 Probabilistic Metrics

Create: `src/contract_risk_analysis/evaluation/metrics/probabilistic.py`

```python
class ProbabilisticMetrics:
    """
    Metrics specific to probabilistic predictions.
    """
    
    def __init__(
        self,
        predicted_distributions: List[Dict[str, float]],
        ground_truth: List[str]
    ):
        self.dists = predicted_distributions
        self.truth = ground_truth
    
    def log_likelihood(self) -> float:
        """
        Average log-likelihood of ground truth under predicted distribution.
        
        LL = (1/N) Σ log(P(truth_i | evidence_i))
        
        Higher is better.
        """
        log_likelihoods = []
        
        for dist, truth in zip(self.dists, self.truth):
            prob = dist.get(truth, 1e-10)  # Avoid log(0)
            log_likelihoods.append(np.log(prob))
        
        return np.mean(log_likelihoods)
    
    def kl_divergence_from_expert(
        self,
        expert_distributions: List[Dict[str, float]]
    ) -> float:
        """
        KL divergence from expert judgments.
        
        KL(P_expert || P_model) = Σ P_expert(x) * log(P_expert(x) / P_model(x))
        
        Lower is better (0 = perfect match).
        """
        kls = []
        
        for expert_dist, model_dist in zip(expert_distributions, self.dists):
            kl = 0.0
            for cls in expert_dist:
                p_expert = expert_dist[cls]
                p_model = model_dist.get(cls, 1e-10)
                kl += p_expert * np.log(p_expert / p_model)
            kls.append(kl)
        
        return np.mean(kls)
    
    def average_entropy(self) -> float:
        """Average entropy of predicted distributions"""
        entropies = []
        
        for dist in self.dists:
            entropy = 0.0
            for prob in dist.values():
                if prob > 0:
                    entropy -= prob * np.log2(prob)
            entropies.append(entropy)
        
        return np.mean(entropies)
```

### 3.4 Decision Metrics

```python
class DecisionMetrics:
    """
    Metrics for decision-making quality.
    
    Different from classification because decisions have costs.
    """
    
    def __init__(
        self,
        decisions: List[str],  # "approve", "reject", "review"
        ground_truth_risk: List[str],
        cost_matrix: Optional[Dict] = None
    ):
        self.decisions = decisions
        self.truth = ground_truth_risk
        
        # Cost matrix: cost[decision][true_risk]
        # Example: Rejecting a low-risk contract costs opportunity
        self.costs = cost_matrix or self._default_cost_matrix()
    
    def _default_cost_matrix(self):
        return {
            "approve": {"low": 0, "medium": 1, "high": 5, "critical": 10},
            "reject": {"low": 2, "medium": 1, "high": 0, "critical": 0},
            "review": {"low": 1, "medium": 1, "high": 1, "critical": 1},
        }
    
    def expected_cost(self) -> float:
        """Average cost of decisions"""
        total_cost = 0.0
        
        for decision, truth in zip(self.decisions, self.truth):
            total_cost += self.costs[decision][truth]
        
        return total_cost / len(self.decisions)
    
    def false_negative_rate(self) -> float:
        """
        Rate of approving high/critical risk contracts.
        
        Most critical metric for risk assessment!
        """
        high_risk_contracts = [t for t in self.truth if t in ["high", "critical"]]
        false_negatives = sum(
            1 for d, t in zip(self.decisions, self.truth)
            if d == "approve" and t in ["high", "critical"]
        )
        
        return false_negatives / len(high_risk_contracts) if high_risk_contracts else 0
    
    def cost_sensitive_accuracy(self) -> float:
        """Accuracy weighted by cost of mistakes"""
        pass
```

### 3.5 Metrics Aggregator

Create: `src/contract_risk_analysis/evaluation/metrics/aggregator.py`

```python
class MetricsAggregator:
    """
    Compute and aggregate all metrics.
    """
    
    def evaluate_model(
        self,
        model: RiskAssessmentModel,
        dataset: BenchmarkDataset,
        output_path: Optional[str] = None
    ) -> EvaluationReport:
        """
        Run full evaluation.
        """
        # Run model on dataset
        results = []
        for contract in dataset:
            prediction = model.predict(contract)
            results.append({
                "contract_id": contract.id,
                "predicted_risk": prediction.risk_level,
                "predicted_distribution": prediction.distribution,
                "ground_truth": contract.consensus_risk,
                "inference_time_ms": prediction.time_ms,
            })
        
        # Extract arrays
        predictions = [r["predicted_risk"] for r in results]
        ground_truth = [r["ground_truth"] for r in results]
        distributions = [r["predicted_distribution"] for r in results]
        
        # Compute all metrics
        report = EvaluationReport(
            classification=ClassificationMetrics(predictions, ground_truth),
            calibration=CalibrationMetrics(distributions, ground_truth),
            probabilistic=ProbabilisticMetrics(distributions, ground_truth),
            decision=DecisionMetrics(predictions, ground_truth),
            raw_results=results
        )
        
        # Save if requested
        if output_path:
            report.save(output_path)
        
        return report
    
    def compare_models(
        self,
        models: Dict[str, RiskAssessmentModel],
        dataset: BenchmarkDataset
    ) -> ComparisonReport:
        """
        Compare multiple models side-by-side.
        """
        reports = {
            name: self.evaluate_model(model, dataset)
            for name, model in models.items()
        }
        
        return ComparisonReport(reports=reports)
```

---

## Module 3: Evaluation Pipeline (Weeks 9-12)

### 4.1 Automated Evaluation

Create: `src/contract_risk_analysis/evaluation/pipeline.py`

```python
class EvaluationPipeline:
    """
    Automated evaluation on benchmark dataset.
    """
    
    def __init__(
        self,
        benchmark_path: str,
        output_dir: str
    ):
        self.benchmark = BenchmarkDataset(benchmark_path)
        self.output_dir = output_dir
        self.metrics = MetricsAggregator()
    
    def evaluate(
        self,
        model: RiskAssessmentModel,
        model_name: str,
        model_version: str
    ) -> EvaluationReport:
        """
        Run complete evaluation.
        """
        timestamp = datetime.utcnow().isoformat()
        
        # Run evaluation
        report = self.metrics.evaluate_model(
            model,
            self.benchmark,
            output_path=f"{self.output_dir}/{model_name}_{model_version}_{timestamp}.json"
        )
        
        # Generate visualizations
        self._generate_plots(report, model_name, model_version)
        
        # Check against thresholds
        passed = self._check_thresholds(report)
        
        return report, passed
    
    def _generate_plots(
        self,
        report: EvaluationReport,
        model_name: str,
        model_version: str
    ):
        """Generate evaluation plots"""
        import matplotlib.pyplot as plt
        
        # Confusion matrix
        plt.figure(figsize=(8, 6))
        cm = report.classification.confusion_matrix()
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
        plt.title(f'Confusion Matrix - {model_name}')
        plt.savefig(f'{self.output_dir}/confusion_matrix_{model_name}.png')
        plt.close()
        
        # Reliability diagram
        plt.figure(figsize=(8, 6))
        rel_data = report.calibration.reliability_diagram()
        plt.plot(rel_data["confidence"], rel_data["accuracy"], 'o-')
        plt.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')
        plt.xlabel('Confidence')
        plt.ylabel('Accuracy')
        plt.title(f'Reliability Diagram - {model_name}')
        plt.legend()
        plt.savefig(f'{self.output_dir}/reliability_{model_name}.png')
        plt.close()
        
        # ROC curves (one per class)
        # ...
    
    def _check_thresholds(self, report: EvaluationReport) -> bool:
        """
        Check if model meets quality thresholds.
        """
        thresholds = {
            "accuracy": 0.80,
            "macro_f1": 0.75,
            "calibration_ece": 0.10,
            "false_negative_rate": 0.05,
        }
        
        checks = {
            "accuracy": report.classification.accuracy() >= thresholds["accuracy"],
            "macro_f1": report.classification.macro_metrics()["macro_f1"] >= thresholds["macro_f1"],
            "calibration_ece": report.calibration.expected_calibration_error() <= thresholds["calibration_ece"],
            "false_negative_rate": report.decision.false_negative_rate() <= thresholds["false_negative_rate"],
        }
        
        return all(checks.values())
```

### 4.2 CI/CD Integration

Create: `.github/workflows/evaluation.yml`

```yaml
name: Evaluation

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run unit tests
      run: pytest tests/ -v
    
    - name: Run evaluation on benchmark
      run: |
        python -m contract_risk_analysis.evaluation.run \
          --model-path models/current \
          --benchmark data/benchmark_v1.json \
          --output results/
    
    - name: Check thresholds
      run: |
        python -m contract_risk_analysis.evaluation.check_thresholds \
          --results results/latest.json \
          --thresholds config/evaluation_thresholds.json
    
    - name: Upload results
      uses: actions/upload-artifact@v3
      with:
        name: evaluation-results
        path: results/
    
    - name: Comment PR
      if: github.event_name == 'pull_request'
      uses: actions/github-script@v6
      with:
        script: |
          const fs = require('fs');
          const results = JSON.parse(fs.readFileSync('results/latest.json'));
          
          const body = `## Evaluation Results
          
          - **Accuracy**: ${results.classification.accuracy.toFixed(3)}
          - **Macro F1**: ${results.classification.macro_f1.toFixed(3)}
          - **Calibration ECE**: ${results.calibration.ece.toFixed(3)}
          - **False Negative Rate**: ${results.decision.false_negative_rate.toFixed(3)}
          
          ${results.passed ? '✅ All thresholds passed' : '❌ Some thresholds failed'}
          `;
          
          github.rest.issues.createComment({
            issue_number: context.issue.number,
            owner: context.repo.owner,
            repo: context.repo.repo,
            body: body
          });
```

### 4.3 Regression Testing

```python
class RegressionTester:
    """
    Detect performance regressions.
    """
    
    def __init__(self, baseline_path: str):
        self.baseline = EvaluationReport.load(baseline_path)
    
    def check_regression(
        self,
        new_report: EvaluationReport,
        tolerance: float = 0.05
    ) -> RegressionResult:
        """
        Check if new model regresses from baseline.
        
        Args:
            tolerance: Acceptable decrease (e.g., 0.05 = 5% decrease ok)
        """
        regressions = []
        
        # Check key metrics
        metric_pairs = [
            ("accuracy", self.baseline.classification.accuracy(), new_report.classification.accuracy()),
            ("macro_f1", self.baseline.classification.macro_metrics()["macro_f1"], new_report.classification.macro_metrics()["macro_f1"]),
            ("calibration_ece", self.baseline.calibration.expected_calibration_error(), new_report.calibration.expected_calibration_error()),
        ]
        
        for name, baseline, new in metric_pairs:
            # For ECE, lower is better
            if name == "calibration_ece":
                if new > baseline * (1 + tolerance):
                    regressions.append({
                        "metric": name,
                        "baseline": baseline,
                        "new": new,
                        "change": (new - baseline) / baseline
                    })
            else:
                if new < baseline * (1 - tolerance):
                    regressions.append({
                        "metric": name,
                        "baseline": baseline,
                        "new": new,
                        "change": (baseline - new) / baseline
                    })
        
        return RegressionResult(
            has_regression=len(regressions) > 0,
            regressions=regressions
        )
```

---

## Module 4: Human Evaluation (Weeks 11-14)

### 5.1 Expert Comparison Study

**Protocol:**

1. **Select contracts:** 50 contracts from benchmark (stratified by risk)
2. **System predictions:** Run both weighted-sum and Bayesian on all 50
3. **Expert review:** Legal experts review contracts + predictions
4. **Comparison:** Score which predictions are better

```python
class ExpertComparisonStudy:
    """
    Run side-by-side comparison with expert judgments.
    """
    
    def __init__(self, contracts: List[ContractEntry]):
        self.contracts = contracts
    
    def run_comparison(
        self,
        model_a: RiskAssessmentModel,
        model_b: RiskAssessmentModel,
        experts: List[str]
    ) -> ComparisonStudyResult:
        """
        Run comparison study.
        """
        results = []
        
        for contract in self.contracts:
            # Get predictions from both models
            pred_a = model_a.predict(contract)
            pred_b = model_b.predict(contract)
            
            # Present to experts (blinded)
            for expert_id in experts:
                comparison = self._get_expert_comparison(
                    expert_id,
                    contract,
                    pred_a,
                    pred_b
                )
                results.append(comparison)
        
        # Aggregate results
        return self._aggregate_comparisons(results)
    
    def _get_expert_comparison(
        self,
        expert_id: str,
        contract: ContractEntry,
        pred_a: Prediction,
        pred_b: Prediction
    ) -> ExpertComparison:
        """
        Present predictions to expert and get judgment.
        
        Blinded: Expert doesn't know which is A or B.
        """
        # Randomize order
        order = random.choice([("A", pred_a, pred_b), ("B", pred_b, pred_a)])
        
        # Present via UI
        judgment = annotation_ui.present_comparison(
            expert_id=expert_id,
            contract=contract,
            prediction_1=order[1],
            prediction_2=order[2]
        )
        
        # Map back to original labels
        winner = order[0] if judgment.preferred == 1 else ("B" if order[0] == "A" else "A")
        
        return ExpertComparison(
            expert_id=expert_id,
            contract_id=contract.id,
            model_a_wins=(winner == "A"),
            reason=judgment.reason,
            confidence=judgment.confidence
        )
```

### 5.2 Utility Scoring

```python
class UtilityScorer:
    """
    Score predictions by decision utility.
    
    Ask experts: "How useful is this prediction for making signing decisions?"
    """
    
    def score_utility(
        self,
        prediction: Prediction,
        expert_id: str
    ) -> UtilityScore:
        """
        Get utility score from expert.
        
        Dimensions:
        - Accuracy (1-5): Is the risk level correct?
        - Calibration (1-5): Do probabilities match confidence?
        - Actionability (1-5): Can I act on this information?
        - Explainability (1-5): Do I understand why?
        """
        scores = annotation_ui.score_utility(
            expert_id=expert_id,
            prediction=prediction
        )
        
        return UtilityScore(
            accuracy=scores.accuracy,
            calibration=scores.calibration,
            actionability=scores.actionability,
            explainability=scores.explainability,
            overall=mean([scores.accuracy, scores.calibration, 
                         scores.actionability, scores.explainability])
        )
```

---

## Module 5: Production Monitoring (Weeks 13-16)

### 6.1 Production Metrics

```python
class ProductionMonitor:
    """
    Monitor model performance in production.
    """
    
    def __init__(self, metrics_client):
        self.metrics = metrics_client
    
    def log_prediction(
        self,
        contract_id: str,
        prediction: Prediction,
        latency_ms: float
    ):
        """Log each prediction for monitoring"""
        # Log to metrics system (Prometheus, DataDog, etc.)
        self.metrics.gauge(
            "risk_prediction_confidence",
            prediction.confidence,
            tags={"contract_id": contract_id}
        )
        
        self.metrics.histogram(
            "risk_prediction_latency_ms",
            latency_ms
        )
        
        self.metrics.counter(
            "risk_predictions_total",
            tags={"risk_level": prediction.risk_level}
        )
    
    def check_drift(
        self,
        window_hours: int = 24
    ) -> DriftReport:
        """
        Check for distribution drift.
        
        Compare recent predictions to training distribution.
        """
        recent = self.metrics.get_predictions(last_n_hours=window_hours)
        baseline = self.load_baseline_distribution()
        
        # Check if risk distribution changed
        recent_dist = Counter(p.risk_level for p in recent)
        baseline_dist = Counter(p.risk_level for p in baseline)
        
        # Chi-squared test
        chi2, p_value = chisquare(
            [recent_dist[r] for r in ["low", "medium", "high", "critical"]],
            [baseline_dist[r] for r in ["low", "medium", "high", "critical"]]
        )
        
        return DriftReport(
            has_drift=p_value < 0.05,
            chi2=chi2,
            p_value=p_value,
            recent_distribution=recent_dist,
            baseline_distribution=baseline_dist
        )
```

### 6.2 Alerting

```python
class EvaluationAlerter:
    """
    Send alerts for evaluation issues.
    """
    
    def check_and_alert(self, report: EvaluationReport):
        """Check metrics and send alerts if needed"""
        
        # Critical: False negative rate
        if report.decision.false_negative_rate() > 0.10:
            self.send_alert(
                level="CRITICAL",
                message=f"False negative rate {report.decision.false_negative_rate():.2%} exceeds 10%",
                details=report.to_dict()
            )
        
        # Warning: Calibration degradation
        if report.calibration.expected_calibration_error() > 0.15:
            self.send_alert(
                level="WARNING",
                message=f"Calibration ECE {report.calibration.expected_calibration_ece():.3f} exceeds 0.15",
                details=report.to_dict()
            )
        
        # Info: Performance summary
        self.send_alert(
            level="INFO",
            message=f"Evaluation complete. Accuracy: {report.classification.accuracy():.2%}",
            details={"summary": report.summary()}
        )
```

---

## Deliverables Checklist

### Data Deliverables
- [ ] `data/benchmark_v1.jsonl` - 500+ labeled contracts
- [ ] `data/benchmark_v1_report.pdf` - Dataset statistics and quality report
- [ ] Data collection protocol documentation
- [ ] Expert annotation guidelines

### Code Deliverables
- [ ] `src/contract_risk_analysis/evaluation/` module
  - [ ] `metrics/` - All metric implementations
  - [ ] `data_collection.py` - Dataset builder
  - [ ] `annotation_ui.py` - Expert interface
  - [ ] `pipeline.py` - Automated evaluation
- [ ] `scripts/train_test_split.py` - Data splitting
- [ ] `scripts/run_evaluation.py` - CLI evaluation tool
- [ ] `.github/workflows/evaluation.yml` - CI integration

### Documentation Deliverables
- [ ] `docs/benchmark_dataset.md` - Dataset description
- [ ] `docs/evaluation_metrics.md` - Metric definitions
- [ ] `docs/human_evaluation_protocol.md` - Study design
- [ ] `docs/monitoring.md` - Production monitoring setup

### Results Deliverables
- [ ] Baseline evaluation (weighted-sum)
- [ ] Bayesian model evaluation
- [ ] Comparison report
- [ ] Human evaluation study results

---

## Success Criteria

### Must Have
- [ ] 500+ contract benchmark dataset
- [ ] All metrics implemented and tested
- [ ] Evaluation runs automatically in CI
- [ ] Threshold checking in place
- [ ] F1 >0.85 on benchmark

### Should Have
- [ ] Calibration error <0.05
- [ ] Human expert agreement >0.85
- [ ] False negative rate <0.05
- [ ] Production monitoring dashboard
- [ ] Regression detection working

### Nice to Have
- [ ] 1000+ contract dataset
- [ ] Multi-year longitudinal study
- [ ] Active learning pipeline
- [ ] Automated model retraining

---

## Phase 3 Completion Definition of Done

- [ ] All checklist items complete
- [ ] Benchmark dataset published
- [ ] All metrics meet targets
- [ ] Human evaluation study complete
- [ ] CI/CD pipeline operational
- [ ] Production monitoring active
- [ ] Documentation complete
- [ ] Production release tagged: `v1.0.0`

---

## Next Steps After Phase 3

1. **Maintain** - Continue monitoring and improving
2. **Expand** - More contract types, jurisdictions
3. **Scale** - Handle larger volumes
4. **Research** - Publish findings, contribute to field

---

**Last Updated:** 2026-04-23  
**Prerequisites:** Phase 2 complete  
**Status:** Ready for Planning
