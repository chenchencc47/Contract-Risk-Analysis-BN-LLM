# 04 - Phase 2: Bayesian Inference Engine Checklist

**Phase Goal:** Replace weighted-sum scoring with true Bayesian probabilistic inference  
**Duration:** 4 months  
**Prerequisite:** Phase 1 complete (explainability infrastructure)  
**Priority:** HIGH (core technical improvement)

---

## Overview

Phase 2 transforms the current weighted-sum heuristic into a true probabilistic reasoning system. This is the core technical evolution of the project.

### What Changes

**Current (Weighted-Sum):**
```python
score = Σ(evidence_weight[i] * state_value[i])
risk_level = threshold(score)
```

**Target (Bayesian):**
```python
P(risk_level | evidence) = inference(evidence, network_structure, CPTs)
# Returns full probability distribution, not single value
```

### Key Deliverables

1. **Bayesian Network Library** - Structure, inference algorithms, CPTs
2. **Inference Engine** - Belief propagation, variable elimination
3. **CPT Learning** - Parameter estimation from data
4. **Uncertainty Quantification** - Confidence intervals, entropy
5. **Backward Compatibility** - Feature flags, gradual rollout

### Why This Matters

- **Proper Uncertainty:** Weighted sums can't represent "60% high, 40% medium"
- **Explainability:** Bayesian updates are interpretable
- **Mathematical Rigor:** Probabilistic reasoning has solid foundations
- **Future Extensibility:** Easy to add new nodes, relationships

---

## Pre-Phase: Preparation (Week 1-2)

### 1.1 Learning & Research

Before writing code, ensure team understands:

- [ ] **Bayesian Networks primer** - Nodes, edges, CPTs, d-separation
- [ ] **Inference algorithms** - Variable elimination, belief propagation
- [ ] **pgmpy library** - If using, review documentation
- [ ] **Current system deep dive** - Understand every line of weighted-sum code

**Resources:**
- Book: "Probabilistic Graphical Models" (Koller & Friedman) - Chapters 1-10
- Online: pgmpy documentation and tutorials
- Course: Coursera "Probabilistic Graphical Models"

### 1.2 Technical Decisions

**Decision 1: Build vs. Use Library**

Option A: Use `pgmpy` (recommended for speed)
- Pros: Mature, tested, many algorithms
- Cons: Dependency, less control, may not fit our use case perfectly

Option B: Build custom inference (recommended for learning)
- Pros: Full control, optimized for our network size (~20 nodes)
- Cons: Time-consuming, risk of bugs

Option C: Hybrid (recommended for production)
- Use pgmpy for development and testing
- Build custom optimized version later if needed
- Abstract interface allows swapping implementations

**Decision 2: Inference Algorithm**

For our network size (~20 nodes, ~5 parents max):
- **Exact:** Variable elimination - fast, accurate
- **Approximate:** Loopy belief propagation - if network grows
- **Sampling:** Gibbs sampling - for complex queries

**Recommendation:** Start with variable elimination, add others later.

### 1.3 Repository Setup

- [ ] Create feature branch: `feature/phase2-bayesian-inference`
- [ ] Add dependencies:
  ```
  pgmpy>=0.1.24
  networkx>=3.0
  numpy>=1.24.0
  scipy>=1.10.0
  ```
- [ ] Install and verify: `pip install -r requirements.txt`
- [ ] Run Phase 1 tests to ensure baseline is stable

---

## Module 1: Bayesian Network Core (Weeks 3-6)

### 2.1 Define Network Structure

Create file: `src/contract_risk_analysis/bn/probabilistic/network.py`

**Task:** Convert current config to proper BN structure

```python
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
import networkx as nx

@dataclass
class BNNode:
    id: str
    states: List[str]  # e.g., ["low", "medium", "high"]
    parents: List[str]  # Parent node IDs
    cpd: Optional[ConditionalProbabilityTable] = None
    
@dataclass
class ConditionalProbabilityTable:
    """
    CPT for a node.
    For node with states [A, B, C] and parents with [2, 3] states:
    - Table shape: (3, 2, 3) = (num_states, *parent_state_counts)
    - Each column sums to 1.0
    """
    node_id: str
    states: List[str]
    parent_ids: List[str]
    parent_states: List[List[str]]  # States for each parent
    probabilities: np.ndarray  # The actual CPT values
    
    def validate(self) -> bool:
        """Ensure CPT is valid (all columns sum to 1)"""
        pass  # TODO

class BayesianNetwork:
    """
    Represents the contract risk Bayesian network.
    """
    def __init__(self):
        self.nodes: Dict[str, BNNode] = {}
        self.graph = nx.DiGraph()
        
    def add_node(self, node: BNNode) -> None:
        """Add a node to the network"""
        pass  # TODO
        
    def add_edge(self, parent: str, child: str) -> None:
        """Add directed edge (must not create cycles)"""
        pass  # TODO
        
    def get_ancestors(self, node_id: str) -> Set[str]:
        """Get all ancestors of a node"""
        pass  # TODO
        
    def get_descendants(self, node_id: str) -> Set[str]:
        """Get all descendants of a node"""
        pass  # TODO
        
    def validate_structure(self) -> Tuple[bool, List[str]]:
        """
        Validate network structure:
        - No cycles
        - All parent references valid
        - CPTs defined for all nodes
        Returns: (is_valid, list_of_errors)
        """
        pass  # TODO
        
    def to_dict(self) -> Dict:
        """Serialize to dictionary"""
        pass  # TODO
        
    @classmethod
    def from_dict(cls, data: Dict) -> "BayesianNetwork":
        """Deserialize from dictionary"""
        pass  # TODO
```

**Tasks:**
- [ ] Implement BNNode and CPT data classes
- [ ] Implement BayesianNetwork class with graph operations
- [ ] Add structure validation (cycle detection)
- [ ] Add serialization/deserialization
- [ ] Create network from current `bayesian_network.json`
- [ ] Unit tests for all operations

### 2.2 Convert Current Config

**Task:** Write migration script from weighted-sum config to BN config

Create: `scripts/migrate_config_to_bn.py`

```python
"""
Migrate from weighted-sum config to proper Bayesian network config.

Current config has:
- dimension_risk_rules (weighted sums)
- CPTs (but not used in weighted-sum mode)

Target config needs:
- Complete CPTs for all nodes
- Proper parent-child relationships
- All probabilities sum to 1.0
"""

def migrate_config(input_path: str, output_path: str):
    # Load current config
    with open(input_path) as f:
        old_config = json.load(f)
    
    # Create BN structure from dimension rules
    bn = BayesianNetwork()
    
    # Add evidence nodes (leaf nodes)
    for node_def in old_config["nodes"]:
        if node_def["id"] not in ["overall_contract_risk"] + [d["dimension"] for d in old_config["dimension_risk_rules"]]:
            node = BNNode(
                id=node_def["id"],
                states=node_def["states"],
                parents=[]  # Evidence nodes have no parents (or learned from data)
            )
            bn.add_node(node)
    
    # Add dimension nodes
    for dim_rule in old_config["dimension_risk_rules"]:
        dim_id = dim_rule["dimension"]
        weighted_inputs = dim_rule["weighted_inputs"]
        
        # Create dimension node with evidence nodes as parents
        node = BNNode(
            id=dim_id,
            states=["low", "medium", "high"],  # Or from config
            parents=[inp["node"] for inp in weighted_inputs]
        )
        bn.add_node(node)
        
        # Add edges from evidence to dimension
        for inp in weighted_inputs:
            bn.add_edge(inp["node"], dim_id)
    
    # Add overall risk node
    overall_node = BNNode(
        id="overall_contract_risk",
        states=["low", "medium", "high"],
        parents=[d["dimension"] for d in old_config["dimension_risk_rules"]]
    )
    bn.add_node(overall_node)
    
    for dim_rule in old_config["dimension_risk_rules"]:
        bn.add_edge(dim_rule["dimension"], "overall_contract_risk")
    
    # Generate initial CPTs from weighted-sum rules
    # (This is a heuristic - real CPTs should be learned from data)
    generate_cpts_from_weights(bn, old_config)
    
    # Save new config
    with open(output_path, 'w') as f:
        json.dump(bn.to_dict(), f, indent=2)

def generate_cpts_from_weights(bn: BayesianNetwork, config: Dict):
    """
    Generate initial CPTs using weighted-sum as heuristic.
    
    This is a starting point - real CPTs should be learned from data.
    """
    for node_id, node in bn.nodes.items():
        if not node.parents:
            # Evidence node - uniform prior or from data
            node.cpd = generate_uniform_cpt(node)
        else:
            # Dimension or overall node - use weighted sum heuristic
            node.cpd = generate_cpt_from_weights(node, config)
```

**Tasks:**
- [ ] Write migration script
- [ ] Generate initial CPTs from weighted-sum rules
- [ ] Run on current config
- [ ] Validate output (all CPTs sum to 1)
- [ ] Document heuristic used

### 2.3 Implement Variable Elimination

Create file: `src/contract_risk_analysis/bn/probabilistic/inference.py`

**Algorithm:** Variable Elimination for exact inference

```python
class VariableEliminationInference:
    """
    Exact inference using variable elimination.
    
    Suitable for small networks (<30 nodes).
    Time complexity: O(n * exp(w)) where w = treewidth
    """
    
    def __init__(self, network: BayesianNetwork):
        self.network = network
        
    def query(
        self,
        target_nodes: List[str],
        evidence: Dict[str, str],  # node_id -> observed_state
        elimination_order: Optional[List[str]] = None
    ) -> InferenceResult:
        """
        Query P(target_nodes | evidence)
        
        Returns marginal distributions for each target.
        """
        # Step 1: Validate inputs
        self._validate_query(target_nodes, evidence)
        
        # Step 2: Determine elimination order
        if elimination_order is None:
            elimination_order = self._get_elimination_order(target_nodes, evidence)
        
        # Step 3: Initialize factors from CPTs
        factors = self._initialize_factors(evidence)
        
        # Step 4: Eliminate variables one by one
        for var in elimination_order:
            factors = self._eliminate_variable(var, factors)
        
        # Step 5: Normalize and return
        result = self._compute_marginals(factors, target_nodes)
        return result
    
    def _initialize_factors(
        self, 
        evidence: Dict[str, str]
    ) -> List[Factor]:
        """
        Create initial factors from CPTs.
        
        For observed evidence, reduce factor to match observation.
        """
        factors = []
        for node_id, node in self.network.nodes.items():
            factor = Factor.from_cpt(node.cpd)
            
            # If this node is observed, reduce the factor
            if node_id in evidence:
                observed_state = evidence[node_id]
                factor = factor.reduce(node_id, observed_state)
            
            factors.append(factor)
        
        return factors
    
    def _eliminate_variable(
        self, 
        var: str, 
        factors: List[Factor]
    ) -> List[Factor]:
        """
        Eliminate a variable by:
        1. Multiplying all factors containing the variable
        2. Summing out (marginalizing) the variable
        """
        # Find factors containing this variable
        relevant_factors = [f for f in factors if var in f.variables]
        other_factors = [f for f in factors if var not in f.variables]
        
        # Multiply relevant factors
        product = Factor.multiply_all(relevant_factors)
        
        # Sum out the variable
        new_factor = product.sum_out(var)
        
        # Return new list of factors
        if new_factor.variables:
            return other_factors + [new_factor]
        else:
            return other_factors
    
    def _get_elimination_order(
        self,
        target_nodes: List[str],
        evidence: Dict[str, str]
    ) -> List[str]:
        """
        Determine elimination order using min-degree heuristic.
        
        Eliminate variables that are not targets and not evidence.
        """
        # Nodes to eliminate = all nodes - targets - evidence
        eliminate_candidates = set(self.network.nodes.keys())
        eliminate_candidates -= set(target_nodes)
        eliminate_candidates -= set(evidence.keys())
        
        # Use min-degree heuristic
        order = []
        remaining = eliminate_candidates.copy()
        
        while remaining:
            # Find variable with minimum degree in current graph
            min_degree_var = min(
                remaining,
                key=lambda v: self._get_degree(v, remaining)
            )
            order.append(min_degree_var)
            remaining.remove(min_degree_var)
        
        return order

@dataclass
class Factor:
    """
    A factor in the factor graph.
    
    Represents a function over a set of variables.
    """
    variables: List[str]
    table: np.ndarray  # Multi-dimensional array
    
    @classmethod
    def from_cpt(cls, cpt: ConditionalProbabilityTable) -> "Factor":
        """Create factor from CPT"""
        variables = cpt.parent_ids + [cpt.node_id]
        return Factor(variables=variables, table=cpt.probabilities)
    
    def reduce(self, variable: str, state: str) -> "Factor":
        """Reduce factor by observing a variable's state"""
        pass  # TODO
    
    def sum_out(self, variable: str) -> "Factor":
        """Sum out (marginalize) a variable"""
        pass  # TODO
    
    @staticmethod
    def multiply_all(factors: List["Factor"]) -> "Factor":
        """Multiply multiple factors together"""
        pass  # TODO
```

**Tasks:**
- [ ] Implement Factor class with multiply and sum_out
- [ ] Implement variable elimination algorithm
- [ ] Add min-degree heuristic for elimination order
- [ ] Handle evidence reduction
- [ ] Unit tests with simple networks
- [ ] Unit tests with contract risk network

**Test Cases:**
```python
def test_simple_inference():
    """Test on simple network: A -> B"""
    # P(A=0) = 0.3, P(A=1) = 0.7
    # P(B=0|A=0) = 0.8, P(B=1|A=0) = 0.2
    # P(B=0|A=1) = 0.4, P(B=1|A=1) = 0.6
    
    bn = create_simple_bn()
    inference = VariableEliminationInference(bn)
    
    # Query P(B) without evidence
    result = inference.query(target_nodes=["B"], evidence={})
    # Expected: P(B=0) = 0.3*0.8 + 0.7*0.4 = 0.52
    assert abs(result.marginals["B"]["0"] - 0.52) < 0.001
    
    # Query P(B | A=0)
    result = inference.query(target_nodes=["B"], evidence={"A": "0"})
    # Expected: P(B=0|A=0) = 0.8
    assert abs(result.marginals["B"]["0"] - 0.8) < 0.001

def test_contract_risk_inference():
    """Test on actual contract risk network"""
    bn = load_contract_risk_bn()
    inference = VariableEliminationInference(bn)
    
    # Test with some evidence
    evidence = {
        "termination_clause_completeness": "missing",
        "liability_cap_strength": "severe"
    }
    
    result = inference.query(
        target_nodes=["overall_contract_risk"],
        evidence=evidence
    )
    
    # Verify result is a valid probability distribution
    overall = result.marginals["overall_contract_risk"]
    assert abs(sum(overall.values()) - 1.0) < 0.001
    assert all(p >= 0 for p in overall.values())
```

---

## Module 2: Evidence Handling (Weeks 7-8)

### 3.1 Soft Evidence Support

**Problem:** LLM findings have uncertainty. Current system ignores this.

**Solution:** Support "soft evidence" - probability distribution over states

```python
@dataclass
class SoftEvidence:
    """
    Evidence with uncertainty.
    
    Instead of "termination_clause = missing",
    we have "P(termination_clause = missing) = 0.85"
    """
    node_id: str
    state_probabilities: Dict[str, float]  # state -> probability
    
    def validate(self) -> bool:
        """Ensure probabilities sum to 1.0"""
        return abs(sum(self.state_probabilities.values()) - 1.0) < 0.001

def convert_findings_to_soft_evidence(
    findings: List[ReviewFinding],
    config: EvidenceMappingConfig
) -> List[SoftEvidence]:
    """
    Convert LLM findings to soft evidence with uncertainty.
    
    Uses finding confidence to create probability distribution.
    """
    evidence_list = []
    
    for finding in findings:
        # Map finding to node and primary state
        node_id, primary_state = apply_mapping_rule(finding, config)
        
        # Create probability distribution based on confidence
        confidence = finding.confidence  # e.g., 0.85
        
        # Primary state gets confidence, others share remainder
        states = get_node_states(node_id)
        num_other_states = len(states) - 1
        
        state_probs = {}
        for state in states:
            if state == primary_state:
                state_probs[state] = confidence
            else:
                state_probs[state] = (1 - confidence) / num_other_states
        
        evidence_list.append(SoftEvidence(
            node_id=node_id,
            state_probabilities=state_probs
        ))
    
    return evidence_list
```

**Tasks:**
- [ ] Implement SoftEvidence class
- [ ] Convert hard evidence to soft evidence
- [ ] Modify inference to handle soft evidence
- [ ] Update Phase 1 evidence mapper to output soft evidence
- [ ] Unit tests

### 3.2 Evidence Combination

**Problem:** Multiple findings might affect same node

**Solution:** Combine evidence using Bayesian updating or Dempster-Shafer

```python
def combine_evidence(
    evidence_list: List[SoftEvidence]
) -> Dict[str, SoftEvidence]:
    """
    Combine multiple pieces of evidence targeting the same node.
    
    For node N with evidence E1, E2:
    P(N | E1, E2) ∝ P(E1 | N) * P(E2 | N) * P(N)
    
    Assuming independence of evidence given node state.
    """
    # Group by node
    by_node = defaultdict(list)
    for ev in evidence_list:
        by_node[ev.node_id].append(ev)
    
    combined = {}
    for node_id, ev_list in by_node.items():
        if len(ev_list) == 1:
            combined[node_id] = ev_list[0]
        else:
            # Combine using product of likelihoods
            states = get_node_states(node_id)
            combined_probs = {}
            
            for state in states:
                # P(state | E1, E2) ∝ P(E1 | state) * P(E2 | state)
                prob = 1.0
                for ev in ev_list:
                    prob *= ev.state_probabilities[state]
                combined_probs[state] = prob
            
            # Normalize
            total = sum(combined_probs.values())
            combined_probs = {s: p/total for s, p in combined_probs.items()}
            
            combined[node_id] = SoftEvidence(
                node_id=node_id,
                state_probabilities=combined_probs
            )
    
    return combined
```

**Tasks:**
- [ ] Implement evidence combination
- [ ] Handle conflicting evidence (low agreement)
- [ ] Add confidence scores to combined evidence
- [ ] Unit tests with conflicting evidence

---

## Module 3: CPT Learning (Weeks 9-12)

### 4.1 Maximum Likelihood Estimation

**Task:** Learn CPTs from labeled contract data

```python
class CPTLearner:
    """
    Learn CPTs from labeled training data.
    """
    
    def __init__(self, network: BayesianNetwork):
        self.network = network
        
    def learn_from_data(
        self,
        training_data: List[Dict[str, str]],  # List of complete assignments
        method: Literal["mle", "bayesian"] = "mle",
        prior: Optional[Dict] = None
    ) -> BayesianNetwork:
        """
        Learn CPTs from complete data.
        
        Args:
            training_data: List of complete node assignments
            method: "mle" for maximum likelihood, "bayesian" for Bayesian with prior
            prior: For Bayesian learning, prior counts (pseudocounts)
        
        Returns:
            Network with learned CPTs
        """
        for node_id, node in self.network.nodes.items():
            node.cpd = self._learn_cpt_for_node(
                node_id=node_id,
                training_data=training_data,
                method=method,
                prior=prior
            )
        
        return self.network
    
    def _learn_cpt_for_node(
        self,
        node_id: str,
        training_data: List[Dict[str, str]],
        method: str,
        prior: Optional[Dict]
    ) -> ConditionalProbabilityTable:
        """Learn CPT for a single node"""
        node = self.network.nodes[node_id]
        states = node.states
        parents = node.parents
        
        if not parents:
            # No parents - learn marginal distribution
            counts = defaultdict(int)
            for sample in training_data:
                counts[sample[node_id]] += 1
            
            total = len(training_data)
            probs = np.array([counts[s] / total for s in states])
            
            return ConditionalProbabilityTable(
                node_id=node_id,
                states=states,
                parent_ids=[],
                parent_states=[],
                probabilities=probs
            )
        else:
            # Has parents - learn conditional distribution
            parent_states_list = [
                self.network.nodes[p].states for p in parents
            ]
            
            # Shape: (num_states, *parent_state_counts)
            shape = [len(states)] + [len(ps) for ps in parent_states_list]
            counts = np.zeros(shape)
            
            # Count occurrences
            for sample in training_data:
                node_state_idx = states.index(sample[node_id])
                parent_indices = [
                    self.network.nodes[p].states.index(sample[p])
                    for p in parents
                ]
                counts[(node_state_idx, *parent_indices)] += 1
            
            # Add prior pseudocounts (Laplace smoothing)
            if method == "bayesian" and prior:
                # Add pseudocounts
                pass  # TODO
            else:
                # MLE with Laplace smoothing (add-1)
                counts += 1
            
            # Normalize
            totals = counts.sum(axis=0, keepdims=True)
            probs = counts / totals
            
            return ConditionalProbabilityTable(
                node_id=node_id,
                states=states,
                parent_ids=parents,
                parent_states=parent_states_list,
                probabilities=probs
            )
```

**Tasks:**
- [ ] Implement MLE for CPTs
- [ ] Add Laplace smoothing (handling zeros)
- [ ] Implement Bayesian learning with priors
- [ ] Handle missing data (optional)
- [ ] Unit tests

### 4.2 Training Data Format

Create: `docs/training_data_format.md`

```yaml
# Training data format (JSON Lines)

Each line is a JSON object with complete assignment to all nodes:

{
  "contract_id": "nda_001",
  "contract_type": "nda",
  "annotator": "legal_expert_1",
  "timestamp": "2026-01-15T10:30:00Z",
  
  # Evidence nodes (from expert review)
  "termination_clause_completeness": "missing",
  "liability_cap_strength": "severe",
  "governing_law_clarity": "clear",
  # ... all evidence nodes
  
  # Dimension nodes (computed or annotated)
  "legal_enforceability_risk": "high",
  "financial_exposure_risk": "high",
  # ... all dimension nodes
  
  # Target node
  "overall_contract_risk": "high"
}
```

**Tasks:**
- [ ] Define training data schema
- [ ] Create validation script
- [ ] Create sample training data
- [ ] Document collection process

### 4.3 Training Pipeline

Create file: `src/contract_risk_analysis/bn/training/pipeline.py`

```python
def train_bn_model(
    training_data_path: str,
    network_structure_path: str,
    output_model_path: str,
    validation_split: float = 0.2
) -> TrainingResult:
    """
    Complete training pipeline.
    
    1. Load network structure
    2. Load and validate training data
    3. Split into train/validation
    4. Learn CPTs
    5. Validate on holdout set
    6. Save model
    """
    # Load structure
    bn = BayesianNetwork.from_json(network_structure_path)
    
    # Load data
    data = load_training_data(training_data_path)
    
    # Split
    train_data, val_data = train_test_split(data, test_size=validation_split)
    
    # Learn
    learner = CPTLearner(bn)
    trained_bn = learner.learn_from_data(train_data, method="mle")
    
    # Validate
    metrics = validate_model(trained_bn, val_data)
    
    # Save
    model_package = ModelPackage(
        network=trained_bn,
        training_metadata={
            "num_samples": len(train_data),
            "validation_accuracy": metrics.accuracy,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
    model_package.save(output_model_path)
    
    return TrainingResult(
        model_path=output_model_path,
        metrics=metrics,
        num_parameters=count_parameters(trained_bn)
    )
```

**Tasks:**
- [ ] Implement training pipeline
- [ ] Add validation metrics
- [ ] Create model versioning
- [ ] Add experiment tracking (optional)
- [ ] CLI tool for training

---

## Module 4: Uncertainty Quantification (Weeks 13-14)

### 5.1 Entropy and Confidence Metrics

```python
class UncertaintyQuantifier:
    """
    Quantify uncertainty in inference results.
    """
    
    def compute_entropy(
        self, 
        distribution: Dict[str, float]
    ) -> float:
        """
        Compute Shannon entropy.
        
        H(X) = -Σ P(x) * log2(P(x))
        
        Higher entropy = more uncertainty
        """
        entropy = 0.0
        for prob in distribution.values():
            if prob > 0:
                entropy -= prob * np.log2(prob)
        return entropy
    
    def compute_confidence(
        self,
        distribution: Dict[str, float]
    ) -> float:
        """
        Compute confidence as probability of most likely state.
        
        confidence = max(P(x))
        """
        return max(distribution.values())
    
    def compute_credible_interval(
        self,
        distribution: Dict[str, float],
        confidence_level: float = 0.95
    ) -> Tuple[List[str], float]:
        """
        Compute credible interval (highest posterior density).
        
        Returns states that contain confidence_level probability mass.
        """
        # Sort states by probability (descending)
        sorted_states = sorted(
            distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Accumulate until we reach confidence level
        cumulative = 0.0
        interval_states = []
        for state, prob in sorted_states:
            interval_states.append(state)
            cumulative += prob
            if cumulative >= confidence_level:
                break
        
        return interval_states, cumulative
    
    def compute_calibration_error(
        self,
        predictions: List[Dict[str, float]],
        actuals: List[str]
    ) -> float:
        """
        Compute expected calibration error.
        
        ECE = Σ |accuracy(bin) - confidence(bin)| * P(bin)
        
        Lower is better (0 = perfectly calibrated).
        """
        # Bin predictions by confidence
        bins = defaultdict(lambda: {"correct": 0, "total": 0, "conf_sum": 0})
        
        for pred, actual in zip(predictions, actuals):
            # Get predicted class and confidence
            predicted = max(pred, key=pred.get)
            confidence = pred[predicted]
            
            # Assign to bin (e.g., 10 bins)
            bin_idx = min(int(confidence * 10), 9)
            
            bins[bin_idx]["total"] += 1
            bins[bin_idx]["conf_sum"] += confidence
            if predicted == actual:
                bins[bin_idx]["correct"] += 1
        
        # Compute ECE
        ece = 0.0
        total_samples = len(predictions)
        
        for bin_idx, stats in bins.items():
            if stats["total"] > 0:
                accuracy = stats["correct"] / stats["total"]
                avg_confidence = stats["conf_sum"] / stats["total"]
                bin_weight = stats["total"] / total_samples
                
                ece += abs(accuracy - avg_confidence) * bin_weight
        
        return ece
```

**Tasks:**
- [ ] Implement uncertainty metrics
- [ ] Add to inference result
- [ ] Create calibration plots
- [ ] Unit tests

### 5.2 Uncertainty Reporting

Update: `src/contract_risk_analysis/bn/inference.py` (result class)

```python
class ProbabilisticRiskReport(BaseModel):
    """
    Risk report with full probability distributions.
    """
    contract_id: str
    
    # Overall risk distribution
    overall_risk_distribution: Dict[str, float]
    overall_risk_entropy: float
    overall_risk_confidence: float
    
    # Dimension distributions
    dimension_distributions: Dict[str, Dict[str, float]]
    dimension_entropies: Dict[str, float]
    
    # Interpretation
    most_likely_risk: str
    credible_interval_95: List[str]  # States covering 95% probability
    
    # Recommendations
    signing_recommendation: str
    recommendation_confidence: float
    manual_review_items: List[str]
    
    # Trace
    trace_id: str
```

**Tasks:**
- [ ] Update report schema
- [ ] Compute uncertainty for each dimension
- [ ] Generate recommendations based on uncertainty
- [ ] Update UI to show distributions (not just single value)

---

## Module 5: Integration & Rollout (Weeks 15-16)

### 6.1 Feature Flag System

Create file: `src/contract_risk_analysis/config/feature_flags.py`

```python
class FeatureFlags:
    """
    Control rollout of Bayesian inference.
    """
    
    USE_BAYESIAN_INFERENCE: bool = False
    BAYESIAN_ROLLOUT_PERCENTAGE: float = 0.0  # 0-100
    ENABLE_SOFT_EVIDENCE: bool = False
    ENABLE_CPT_LEARNING: bool = False
    
    @classmethod
    def should_use_bayesian(cls, contract_id: str) -> bool:
        """
        Determine if this contract should use Bayesian inference.
        
        Uses consistent hashing for gradual rollout.
        """
        if not cls.USE_BAYESIAN_INFERENCE:
            return False
        
        if cls.BAYESIAN_ROLLOUT_PERCENTAGE >= 100:
            return True
        
        # Use hash of contract_id for deterministic assignment
        hash_val = int(hashlib.md5(contract_id.encode()).hexdigest(), 16)
        assignment = (hash_val % 10000) / 100  # 0-100
        
        return assignment < cls.BAYESIAN_ROLLOUT_PERCENTAGE
```

**Tasks:**
- [ ] Implement feature flags
- [ ] Add environment variable support
- [ ] Create gradual rollout mechanism
- [ ] Add monitoring for flag usage

### 6.2 Backward Compatible API

Update: `src/contract_risk_analysis/bn/inference.py`

```python
def assess_risk(
    evidence: List[RiskEvidence],
    trace_collector: Optional[TraceCollector] = None,
    use_bayesian: Optional[bool] = None  # New parameter
) -> RiskReport:
    """
    Assess contract risk.
    
    Args:
        evidence: List of risk evidence
        trace_collector: Optional trace collector
        use_bayesian: If None, use feature flag. If True/False, override.
    """
    # Determine inference mode
    if use_bayesian is None:
        use_bayesian = FeatureFlags.USE_BAYESIAN_INFERENCE
    
    if use_bayesian:
        return _assess_risk_bayesian(evidence, trace_collector)
    else:
        return _assess_risk_weighted_sum(evidence, trace_collector)

def _assess_risk_bayesian(
    evidence: List[RiskEvidence],
    trace_collector: Optional[TraceCollector]
) -> RiskReport:
    """New Bayesian implementation"""
    # Convert to soft evidence
    soft_evidence = convert_to_soft_evidence(evidence)
    
    # Load BN
    bn = load_bayesian_network()
    
    # Run inference
    inference = VariableEliminationInference(bn)
    result = inference.query(
        target_nodes=["overall_contract_risk"],
        evidence=soft_evidence
    )
    
    # Quantify uncertainty
    uncertainty = UncertaintyQuantifier()
    
    # Build probabilistic report
    report = ProbabilisticRiskReport(
        overall_risk_distribution=result.marginals["overall_contract_risk"],
        overall_risk_entropy=uncertainty.compute_entropy(
            result.marginals["overall_contract_risk"]
        ),
        # ... other fields
    )
    
    return report

def _assess_risk_weighted_sum(
    evidence: List[RiskEvidence],
    trace_collector: Optional[TraceCollector]
) -> RiskReport:
    """Legacy weighted-sum implementation"""
    # ... existing code from Phase 1 ...
    pass
```

**Tasks:**
- [ ] Create unified API
- [ ] Maintain backward compatibility
- [ ] Add mode selection logic
- [ ] Unit tests for both modes

### 6.3 Migration & Rollout Plan

**Week 15: Internal Testing**
- [ ] Deploy to staging environment
- [ ] Run on 100 test contracts
- [ ] Compare Bayesian vs weighted-sum outputs
- [ ] Fix any discrepancies
- [ ] Document differences

**Week 16: Gradual Rollout**
- [ ] Day 1: 5% of traffic uses Bayesian
- [ ] Monitor: Latency, accuracy, error rates
- [ ] Day 3: 25% of traffic
- [ ] Monitor: Same metrics
- [ ] Day 5: 50% of traffic
- [ ] Monitor: Same metrics + calibration
- [ ] Day 7: 100% of traffic (if metrics look good)

**Rollback Plan:**
```python
# If issues detected, instantly rollback:
FeatureFlags.USE_BAYESIAN_INFERENCE = False
# All new requests use weighted-sum
```

---

## Testing & Validation

### 7.1 Correctness Tests

Create: `tests/bn/probabilistic/test_inference_correctness.py`

```python
"""
Test that inference produces correct probabilities.

Compare against:
1. Manual calculations for simple networks
2. Reference implementation (pgmpy)
3. Known analytical results
"""

def test_inference_matches_pgmpy():
    """Compare our implementation to pgmpy reference"""
    # Create network
    bn = create_test_network()
    
    # Our implementation
    our_inference = VariableEliminationInference(bn)
    our_result = our_inference.query(...)
    
    # pgmpy reference
    from pgmpy.models import BayesianNetwork
    from pgmpy.inference import VariableElimination
    
    pgmpy_bn = convert_to_pgmpy(bn)
    pgmpy_inference = VariableElimination(pgmpy_bn)
    pgmpy_result = pgmpy_inference.query(...)
    
    # Compare
    for node in our_result.marginals:
        for state in our_result.marginals[node]:
            our_prob = our_result.marginals[node][state]
            pgmpy_prob = pgmpy_result[node].get_value(**{node: state})
            assert abs(our_prob - pgmpy_prob) < 0.001

def test_probabilities_sum_to_one():
    """All marginal distributions must sum to 1"""
    pass

def test_evidence_reduces_entropy():
    """Adding evidence should reduce (or maintain) uncertainty"""
    pass

def test_symmetry_independence():
    """Independent nodes should have correct marginals"""
    pass
```

### 7.2 Performance Tests

```python
def test_inference_latency():
    """Bayesian inference should be <200ms for 20-node network"""
    bn = load_contract_risk_bn()
    inference = VariableEliminationInference(bn)
    
    start = time.time()
    result = inference.query(...)
    elapsed = time.time() - start
    
    assert elapsed < 0.2  # 200ms

def test_inference_throughput():
    """Should handle 10 requests/second"""
    pass

def test_memory_usage():
    """Memory should be <500MB for typical usage"""
    pass
```

### 7.3 Regression Tests

```python
def test_backward_compatibility():
    """Weighted-sum mode produces same results as before"""
    # Run 100 contracts through weighted-sum mode
    # Compare to baseline results
    # Should be identical
    pass
```

---

## Deliverables Checklist

### Code Deliverables
- [ ] `src/contract_risk_analysis/bn/probabilistic/` module
  - [ ] `network.py` - BN structure
  - [ ] `inference.py` - Variable elimination
  - [ ] `evidence.py` - Soft evidence handling
  - [ ] `uncertainty.py` - Uncertainty metrics
- [ ] `src/contract_risk_analysis/bn/training/` module
  - [ ] `learner.py` - CPT learning
  - [ ] `pipeline.py` - Training pipeline
- [ ] `src/contract_risk_analysis/config/feature_flags.py`
- [ ] Migration script: `scripts/migrate_config_to_bn.py`
- [ ] CLI: `python -m contract_risk_analysis.bn.train`

### Model Deliverables
- [ ] `config/bayesian_network_probabilistic.json` - New BN config
- [ ] `models/baseline_cpts.json` - Initial CPTs from weighted-sum
- [ ] `models/trained_v1/` - Trained model (after Phase 3)

### Test Deliverables
- [ ] Unit tests for all inference operations
- [ ] Correctness tests vs pgmpy
- [ ] Performance benchmarks
- [ ] Regression tests

### Documentation Deliverables
- [ ] `docs/bayesian_inference.md` - How inference works
- [ ] `docs/cpt_learning.md` - How to train models
- [ ] `docs/migration_guide.md` - How to migrate from weighted-sum
- [ ] API documentation updates

---

## Success Criteria

### Must Have
- [ ] True Bayesian inference working (not weighted-sum)
- [ ] Variable elimination implemented and tested
- [ ] Soft evidence supported
- [ ] Backward compatibility maintained
- [ ] All tests pass
- [ ] Performance <200ms per inference

### Should Have
- [ ] CPT learning from data
- [ ] Uncertainty quantification (entropy, confidence)
- [ ] Feature flag system for gradual rollout
- [ ] Comparison to pgmpy reference
- [ ] >80% test coverage

### Nice to Have
- [ ] Loopy belief propagation (for larger networks)
- [ ] Automatic CPT learning pipeline
- [ ] Model versioning system
- [ ] Calibration metrics

---

## Phase 2 Completion Definition of Done

- [ ] All checklist items complete
- [ ] Code review by senior engineer + data scientist
- [ ] Inference validated against reference implementation
- [ ] Performance benchmarks meet targets
- [ ] Gradual rollout to 100% complete
- [ ] Documentation updated
- [ ] Team training on Bayesian inference
- [ ] Beta release tagged: `v0.8.0-beta`

---

## Next Steps

After Phase 2:
1. **Evaluate** - Compare Bayesian vs weighted-sum accuracy
2. **Train Models** - Use Phase 3 to build training dataset
3. **Iterate** - Improve CPTs based on real data
4. **Scale** - Handle larger contract volumes

---

**Last Updated:** 2026-04-23  
**Prerequisites:** Phase 1 complete  
**Status:** Ready for Planning
