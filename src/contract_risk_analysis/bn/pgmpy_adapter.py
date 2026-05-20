"""True Bayesian Network adapter using pgmpy.

Builds a pgmpy BayesianNetwork from bayesian_network_v2.json, injects
observed evidence, runs variable elimination, and returns posterior
distributions for risk nodes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import product
from pathlib import Path

import numpy as np

from pgmpy.inference import VariableElimination
from pgmpy.models import BayesianNetwork as _BayesianNetworkBase

try:
    from pgmpy.models import DiscreteBayesianNetwork as BayesianNetwork
except ImportError:
    BayesianNetwork = _BayesianNetworkBase
from pgmpy.factors.discrete import TabularCPD, DiscreteFactor


V2_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "bayesian_network_v2.json"


def _infer_unknown_entry(
    combo: tuple[str, ...], parents: list[str], cpt_data: dict,
    child_states: list[str],
) -> dict[str, float] | float | None:
    """Infer CPT entry when parent state is 'unknown'.

    Uses uniform distribution over child states as a safe default,
    or the average of known parent states for this node.
    """
    # If any parent is unknown, use uniform prior over child states
    # For binary child with float CPT: return 0.5 (even chance)
    sample_value = next(iter(cpt_data.values()), None)
    if isinstance(sample_value, (int, float)):
        return 0.5
    if isinstance(sample_value, dict) and child_states:
        uniform = 1.0 / len(child_states)
        return {s: round(uniform, 6) for s in child_states}
    return None


def _noisy_or_infer_entry(
    parent_combo: tuple[str, ...], parents: list[str], config: dict
) -> dict[str, float] | None:
    """Infer missing CPT entry for overall_contract_risk via noisy-max model."""
    if "dimension_labels" not in config:
        return None
    from contract_risk_analysis.bn.noisy_or import (
        compute_default_dimension_weights,
        generate_noisy_max_cpt,
    )
    dim_weights = compute_default_dimension_weights()
    parent_states = {p: config["nodes"][p]["states"] for p in parents}
    full_cpt = generate_noisy_max_cpt(dim_weights, parent_states)
    key = "|".join(parent_combo)
    return full_cpt.get(key)


@lru_cache(maxsize=1)
def load_v2_config() -> dict:
    return json.loads(V2_CONFIG_PATH.read_text(encoding="utf-8"))


def _safe_cpt_lookup(cpt_data: dict, state: str, all_states: list[str], default: float = 0.05) -> float:
    """Look up CPT probability for a state, returning small default for missing entries."""
    if state in cpt_data:
        return float(cpt_data[state])
    if state in ("unknown", "ambiguous"):
        return default
    return 0.0


def _parse_cpt_entry(value, child_states: list[str]) -> list[float]:
    """Parse a single CPT entry into a probability vector over child states.

    Handles two formats:
      - float → P(first_state|parent) = value. If 2 states, rest goes to second.
                If 3+ states, treats float as P(first), distributes P(unknown)=0.03,
                and remainder to second state.
      - dict → explicit probabilities keyed by state name
    """
    if isinstance(value, (int, float)):
        v = float(value)
        num_states = len(child_states)
        if num_states == 2:
            return [v, round(1.0 - v, 6)]
        # Handle 3+ states with 'unknown': P(first) = v, P(unknown)=small, rest to others
        if "unknown" in child_states:
            unknown_idx = child_states.index("unknown")
            result = [0.0] * num_states
            result[0] = round(v * 0.97, 6)
            result[unknown_idx] = 0.03
            # Distribute remainder among non-first, non-unknown states
            remainder = round(1.0 - result[0] - result[unknown_idx], 6)
            other_indices = [i for i in range(num_states) if i not in (0, unknown_idx)]
            if other_indices:
                for i in other_indices:
                    result[i] = round(remainder / len(other_indices), 6)
            return result
        # No unknown: proportional distribution
        result = [0.0] * num_states
        result[0] = v
        remainder = round(1.0 - v, 6)
        for i in range(1, num_states):
            result[i] = round(remainder / (num_states - 1), 6)
        return result
    if isinstance(value, dict):
        return [float(value.get(s, 0.0)) for s in child_states]
    if isinstance(value, list):
        return [float(v) for v in value]
    raise TypeError(f"Unexpected CPT value type: {type(value)}")


def _generate_aggregate_cpt(
    parents: list[str],
    child_states: list[str],
    config: dict,
    threshold: float = 0.3,
) -> dict[str, list[float]]:
    """Generate a CPT for a CUAD aggregate node by counting missing parents.

    Instead of enumerating all parent state combinations (which explodes
    with many parents), this uses a counting-based approach:
    - Count how many parent CUAD nodes are in "missing" state
    - If missing_fraction >= threshold → "unfavorable"
    - If missing_fraction >= threshold/2 → "neutral"
    - Otherwise → "favorable"

    Returns a dict in the format expected by the CPT enumeration loop:
    {key_parts: [prob_s1, prob_s2, prob_s3]}
    """
    n_parents = len(parents)
    if n_parents == 0:
        return {"": [0.34, 0.33, 0.33]}

    cpt_data: dict[str, list[float]] = {}
    # Enumerate all parent combinations (small for ~5 parents each with 2-3 states)
    from itertools import product
    parent_states_list = [config["nodes"][p]["states"] for p in parents]

    for combo in product(*parent_states_list):
        key_parts = "|".join(combo)
        # Count "bad" states
        bad_count = 0
        total_non_unknown = 0
        for state in combo:
            if state == "unknown":
                continue
            total_non_unknown += 1
            if state in ("missing", "unfavorable", "severe", "counterparty_favorable", "contradiction"):
                bad_count += 1

        if total_non_unknown == 0:
            missing_frac = 0.0
        else:
            missing_frac = bad_count / total_non_unknown

        # Map fraction to distribution
        if missing_frac >= threshold:
            # Unfavorable
            cpt_data[key_parts] = [0.05, 0.15, 0.80]
        elif missing_frac >= threshold / 2:
            # Neutral
            cpt_data[key_parts] = [0.15, 0.70, 0.15]
        else:
            # Favorable
            cpt_data[key_parts] = [0.80, 0.15, 0.05]

    return cpt_data


def _build_cpd(node_name: str, node_config: dict, config: dict) -> TabularCPD:
    """Build a pgmpy TabularCPD for a single node from v2 config."""
    child_states = node_config["states"]
    parents = node_config.get("parents", [])
    cpt_data = node_config["cpt"]

    # Handle noisy-or marker: replace with generated CPT
    if isinstance(cpt_data, dict) and cpt_data.get("_noisy_or"):
        from contract_risk_analysis.bn.noisy_or import generate_noisy_max_cpt
        # Use node-specific weights if provided, else default dimension weights
        custom_weights = node_config.get("noisy_or_weights")
        if custom_weights:
            weights = {str(k): float(v) for k, v in custom_weights.items()}
        else:
            from contract_risk_analysis.bn.noisy_or import compute_default_dimension_weights
            weights = compute_default_dimension_weights()
        # Only pass parent states for parents that exist in the config
        parent_states = {}
        for p in parents:
            if p in config["nodes"]:
                parent_states[p] = config["nodes"][p]["states"]
                if p not in weights:
                    weights[p] = 0.2  # default weight for unspecified parents
        # Filter weights to only include actual parents
        weights = {p: w for p, w in weights.items() if p in parent_states}
        cpt_data = generate_noisy_max_cpt(weights, parent_states)

    # Handle aggregate marker: counting-based aggregation of many CUAD parents
    if isinstance(cpt_data, dict) and cpt_data.get("_aggregate"):
        cpt_data = _generate_aggregate_cpt(
            parents=parents,
            child_states=child_states,
            config=config,
            threshold=cpt_data.get("unfavorable_threshold", 0.3),
        )

    if not parents:
        probs = [_safe_cpt_lookup(cpt_data, s, child_states, 0.05) for s in child_states]
        total = sum(probs)
        probs = [p / total for p in probs] if total > 0 else [1.0 / len(child_states)] * len(child_states)
        return TabularCPD(
            variable=node_name,
            variable_card=len(child_states),
            values=np.array([[p] for p in probs]),
            state_names={node_name: child_states},
        )

    parent_states_list = [config["nodes"][p]["states"] for p in parents]
    evidence_card = [len(states) for states in parent_states_list]

    # Build pgmpy-ordered CPT columns
    # pgmpy column order: last parent varies fastest, then second-to-last, etc.
    num_columns = 1
    for card in evidence_card:
        num_columns *= card

    cpt_matrix = []
    for si in range(len(child_states)):
        cpt_matrix.append([0.0] * num_columns)

    # Enumerate all parent state combinations in pgmpy order
    for col_idx, combo in enumerate(product(*parent_states_list)):
        key_parts = "|".join(combo)
        cpt_value = cpt_data.get(key_parts)
        if cpt_value is None:
            # P4.4: Auto-generate via noisy-OR for overall_contract_risk
            if node_name == "overall_contract_risk" and len(parents) >= 3:
                cpt_value = _noisy_or_infer_entry(combo, parents, config)
            # Auto-fill missing combos for unknown parent states
            if cpt_value is None and "unknown" in combo:
                cpt_value = _infer_unknown_entry(combo, parents, cpt_data, child_states)
            if cpt_value is None:
                raise ValueError(
                    f"Missing CPT entry for '{node_name}' with parents "
                    f"{parents} and state combo '{key_parts}'"
                )
        probs = _parse_cpt_entry(cpt_value, child_states)
        total = sum(probs)
        for si, prob in enumerate(probs):
            cpt_matrix[si][col_idx] = prob / total if total > 0 else 1.0 / len(child_states)

    return TabularCPD(
        variable=node_name,
        variable_card=len(child_states),
        values=np.array(cpt_matrix),
        evidence=parents if parents else None,
        evidence_card=evidence_card if parents else None,
        state_names={node_name: child_states, **{p: config["nodes"][p]["states"] for p in parents}},
    )


def build_model(config: dict | None = None) -> BayesianNetwork:
    """Build a pgmpy BayesianNetwork from the v2 config."""
    if config is None:
        config = load_v2_config()
    edges = [tuple(edge) for edge in config["edges"]]
    model = BayesianNetwork(edges)
    for node_name in model.nodes():
        node_config = config["nodes"][node_name]
        cpd = _build_cpd(node_name, node_config, config)
        model.add_cpds(cpd)
    model.check_model()
    return model


@dataclass(frozen=True)
class NodePosterior:
    node_name: str
    state_distribution: dict[str, float]  # state → probability
    most_likely_state: str
    most_likely_probability: float


@dataclass(frozen=True)
class BnInferenceResult:
    posteriors: dict[str, NodePosterior]
    overall_risk_distribution: dict[str, float]
    overall_risk_level: str
    dimension_distributions: dict[str, dict[str, float]]


def _discrete_factor_to_distribution(factor: DiscreteFactor, variable: str) -> dict[str, float]:
    """Extract a single-variable distribution from a pgmpy factor."""
    values = factor.values
    states = factor.state_names[variable]
    if len(values.shape) == 1:
        return {s: float(values[i]) for i, s in enumerate(states)}
    # For multi-dimensional factors, marginalize to single variable
    # values shape is (var1_card, var2_card, ...) — find the axis for our variable
    var_idx = list(factor.variables).index(variable)
    result = {}
    for i, s in enumerate(states):
        # Sum over all other dimensions to get marginal
        slices = [slice(None)] * len(factor.variables)
        slices[var_idx] = i
        val = float(values[tuple(slices)].sum())
        result[s] = val
    # Normalize
    total = sum(result.values())
    if total > 0:
        result = {k: v / total for k, v in result.items()}
    return result


def run_inference(
    model: BayesianNetwork | None = None,
    evidence: dict[str, str] | None = None,
    config: dict | None = None,
) -> BnInferenceResult:
    """Run variable elimination with observed evidence and return posteriors.

    Args:
        model: Pre-built BayesianNetwork (optional, built from config if None).
        evidence: Dict mapping node_name → observed_state.
        config: v2 config dict (optional, loaded if None).

    Returns:
        BnInferenceResult with posterior distributions for all risk/decision nodes.
    """
    if config is None:
        config = load_v2_config()
    if model is None:
        model = build_model(config)

    inference = VariableElimination(model)

    # Validate evidence states
    model_nodes = set(model.nodes())
    clean_evidence: dict[str, str] = {}
    if evidence:
        for node_name, state in evidence.items():
            if node_name not in config["nodes"] or node_name not in model_nodes:
                continue
            allowed = config["nodes"][node_name]["states"]
            if state not in allowed:
                continue
            clean_evidence[node_name] = state

    risk_dimensions = ["legal_enforceability_risk", "financial_exposure_risk",
                       "performance_delivery_risk", "dispute_resolution_risk",
                       "clause_balance_risk"]
    decision_node = "overall_contract_risk"

    # Compute posteriors
    posteriors: dict[str, NodePosterior] = {}

    # Query overall contract risk
    try:
        overall_factor = inference.query(
            variables=[decision_node],
            evidence=clean_evidence if clean_evidence else None,
        )
        overall_dist = _discrete_factor_to_distribution(overall_factor, decision_node)
    except Exception:
        overall_dist = {"low": 0.33, "medium": 0.34, "high": 0.33}

    # Determine overall risk level from distribution
    overall_level = max(overall_dist, key=overall_dist.get)

    posteriors[decision_node] = NodePosterior(
        node_name=decision_node,
        state_distribution=overall_dist,
        most_likely_state=overall_level,
        most_likely_probability=overall_dist[overall_level],
    )

    # Query each risk dimension
    dimension_distributions: dict[str, dict[str, float]] = {}
    for dim in risk_dimensions:
        try:
            factor = inference.query(
                variables=[dim],
                evidence=clean_evidence if clean_evidence else None,
            )
            dist = _discrete_factor_to_distribution(factor, dim)
        except Exception:
            dist = {"low": 0.34, "medium": 0.33, "high": 0.33}
        dimension_distributions[dim] = dist
        best_state = max(dist, key=dist.get)
        posteriors[dim] = NodePosterior(
            node_name=dim,
            state_distribution=dist,
            most_likely_state=best_state,
            most_likely_probability=dist[best_state],
        )

    return BnInferenceResult(
        posteriors=posteriors,
        overall_risk_distribution=overall_dist,
        overall_risk_level=overall_level,
        dimension_distributions=dimension_distributions,
    )


def _node_precision_floor(node_name: str, config: dict) -> float:
    """Minimum meaningful delta for *node_name* given its CPT source.

    Sampling resolution:
      - cuad_empirical / cuad_aggregate_counting:  1 / 510 contracts → 0.002
      - contractnli_empirical:                      1 / 607 contracts → 0.003
      - expert_estimated:           human-judgment granularity → 0.01
      - noisy_max / missing source: conservative fallback → 0.01
    """
    node_cfg = config.get("nodes", {}).get(node_name, {})
    source = node_cfg.get("cpt_source", "")

    if "cuad_empirical" in source or "cuad_aggregate" in source:
        return 0.002
    if "contractnli_empirical" in source:
        return 0.003
    if "expert_estimated" in source:
        return 0.01
    # noisy_max_* nodes, missing cpt_source, and genuinely unknown
    return 0.01


_RELATIVE_DELTA_THRESHOLD = 0.05
_MIN_COUNTERFACTUALS = 3


def run_sensitivity_analysis(
    model: BayesianNetwork | None = None,
    evidence: dict[str, str] | None = None,
    target_node: str = "overall_contract_risk",
    dimension_targets: list[str] | None = None,
    config: dict | None = None,
) -> list[dict]:
    """Compute how much each evidence node change would affect the target posterior.

    For each evidence node, flip its state to the "best" state and measure
    the resulting change in the target node's high-risk probability.

    If dimension_targets is provided, also computes per-dimension deltas for
    each evidence node on its associated dimension nodes.

    Returns list of {node_name, current_state, best_state, delta_high_risk,
    dimension_deltas} sorted by delta descending.
    """
    if config is None:
        config = load_v2_config()
    if model is None:
        model = build_model(config)

    inference = VariableElimination(model)
    clean_evidence = dict(evidence or {})

    # Filter out evidence for nodes not in the model graph (orphan nodes)
    model_nodes = set(model.nodes())
    filtered = {k: v for k, v in clean_evidence.items() if k in model_nodes}
    if len(filtered) < len(clean_evidence):
        import logging
        logging.getLogger(__name__).debug(
            "Filtered %d evidence nodes not in graph: %s",
            len(clean_evidence) - len(filtered),
            sorted(set(clean_evidence) - model_nodes),
        )
    clean_evidence = filtered

    # Build node-to-dimension map for per-dimension delta computation
    node_to_dims = _build_node_to_dimension_map(config)

    # Get baseline high-risk probability for overall target
    base_factor = inference.query(
        variables=[target_node],
        evidence=clean_evidence if clean_evidence else None,
    )
    base_dist = _discrete_factor_to_distribution(base_factor, target_node)
    base_high = base_dist.get("high", 0.0)

    # Pre-compute dimension baselines if requested
    dim_baselines: dict[str, float] = {}
    if dimension_targets:
        for dim_node in dimension_targets:
            try:
                dim_factor = inference.query(
                    variables=[dim_node],
                    evidence=clean_evidence if clean_evidence else None,
                )
                dim_dist = _discrete_factor_to_distribution(dim_factor, dim_node)
                dim_baselines[dim_node] = dim_dist.get("high", 0.0)
            except Exception:
                dim_baselines[dim_node] = 0.0

    # Identify which state is "best" for each evidence node.
    # Hardcoded map for known nodes; auto-discovery fills the rest.
    favorable_states: dict[str, str] = {
        "termination_clause": "present",
        "liability_cap": "acceptable",
        "confidentiality_nli": "entailment",
        "governing_law_clause": "present",
        "dispute_resolution_clause": "present",
        "termination_clause_completeness": "present",
        "termination_right_balance": "balanced",
        "liability_cap_strength": "acceptable",
        "damages_exposure": "low",
        "governing_law_clarity": "present",
        "dispute_resolution_clarity": "present",
        "jurisdiction_fairness": "balanced",
        "acceptance_process_clarity": "present",
        "confidentiality_scope_reasonableness": "entailment",
        # Sales-contract-specific nodes (P0: ensure comprehensive coverage)
        "payment_structure": "balanced",
        "delivery_terms": "present",
        "risk_transfer_point": "favorable",
        "dispute_venue_fairness": "balanced",
        "force_majeure_completeness": "present",
        "warranty_scope": "broad",
        "dispute_resolution_completeness": "present",
    }

    # Auto-discover all evidence-layer nodes from config (CUAD + sales + existing)
    fact_semantics_nodes: list[str] = []
    for node_name, node_cfg in config["nodes"].items():
        layer = node_cfg.get("layer", "")
        if layer in ("contract_fact", "legal_semantics"):
            fact_semantics_nodes.append(node_name)
            # Auto-infer favorable state for nodes not in the hardcoded map
            if node_name not in favorable_states:
                states = node_cfg.get("states", [])
                # Extended candidate list for broader coverage (P0 fix)
                for fav in ("present", "balanced", "acceptable", "favorable",
                            "entailment", "broad", "low", "sufficient",
                            "strong", "reasonable", "clear", "complete",
                            "adequate", "exists", "yes",
                            "specific", "precise", "explicit"):
                    if fav in states:
                        favorable_states[node_name] = fav
                        break
                # Fallback: use the last state (typically the "good" one)
                if node_name not in favorable_states and states:
                    favorable_states[node_name] = states[-1]

    results: list[dict] = []
    for node_name in fact_semantics_nodes:
        current_state = clean_evidence.get(node_name)
        best_state = favorable_states.get(node_name)
        if best_state is None or best_state == current_state:
            continue

        # Run counterfactual: what if this node were in the best state?
        counterfactual = dict(clean_evidence)
        counterfactual[node_name] = best_state
        try:
            cf_factor = inference.query(
                variables=[target_node],
                evidence=counterfactual,
            )
            cf_dist = _discrete_factor_to_distribution(cf_factor, target_node)
        except Exception:
            continue
        cf_high = cf_dist.get("high", 0.0)
        delta = round(base_high - cf_high, 6)

        if delta > 0:
            # Compute dimension-level deltas
            dim_deltas: list[dict] = []
            affected_dims = node_to_dims.get(node_name, [])
            for dim_node in affected_dims:
                if dim_node not in dim_baselines:
                    continue
                try:
                    dim_cf_factor = inference.query(
                        variables=[dim_node],
                        evidence=counterfactual,
                    )
                    dim_cf_dist = _discrete_factor_to_distribution(dim_cf_factor, dim_node)
                    dim_cf_high = dim_cf_dist.get("high", 0.0)
                    dim_base = dim_baselines[dim_node]
                    dim_delta = round(dim_base - dim_cf_high, 6)
                    if dim_delta > 0.001:
                        dim_deltas.append({
                            "dimension_key": dim_node,
                            "dimension_label": DIMENSION_LABELS.get(dim_node, dim_node),
                            "base_high": round(dim_base, 4),
                            "counterfactual_high": round(dim_cf_high, 4),
                            "delta": dim_delta,
                        })
                except Exception:
                    continue

            results.append({
                "node_name": node_name,
                "current_state": current_state or "unassessed",
                "best_state": best_state,
                "delta_high_risk": delta,
                "base_high_risk": round(base_high, 4),
                "counterfactual_high_risk": round(cf_high, 4),
                "dimension_deltas": dim_deltas,
                "observed": current_state is not None,
            })

    results.sort(key=lambda r: r["delta_high_risk"], reverse=True)

    # ── threshold filtering with minimum guarantee ──
    significant: list[dict] = []
    for r in results:
        node_name = r["node_name"]
        floor = _node_precision_floor(node_name, config)
        if r["delta_high_risk"] < floor:
            continue
        # Relative threshold: delta must be at least 5 % of baseline
        # (avoids flagging 3%→2.8% as "significant")
        base = r["base_high_risk"]
        if base > 0.01 and (r["delta_high_risk"] / base) < _RELATIVE_DELTA_THRESHOLD:
            continue
        significant.append(r)

    if len(significant) >= _MIN_COUNTERFACTUALS:
        return significant
    # Fallback: fewer than 3 items passed thresholds — return top 3 by raw delta
    return results[:_MIN_COUNTERFACTUALS]


# Re-exported from constants for backward compatibility
from contract_risk_analysis.constants import (
    DIMENSION_LABELS,
    DIMENSION_NODES,
    NODE_LABELS,
    RISK_LABELS,
)


def _build_node_to_dimension_map(config: dict) -> dict[str, list[str]]:
    """Build a mapping from evidence node → affected dimension node(s).

    Traces edges from contract_fact/legal_semantics nodes to risk_dimension nodes
    through aggregate nodes. Returns {node_name: [dimension_node_name, ...]}.
    """
    edges: list[tuple[str, str]] = config.get("edges", [])
    nodes: dict[str, dict] = config.get("nodes", {})

    # Build adjacency: parent → child, child → parent
    children: dict[str, list[str]] = {}
    parents: dict[str, list[str]] = {}
    for parent, child in edges:
        children.setdefault(parent, []).append(child)
        parents.setdefault(child, []).append(parent)

    dim_set = set(DIMENSION_NODES)
    evidence_to_dims: dict[str, list[str]] = {}

    for node_name, node_cfg in nodes.items():
        layer = node_cfg.get("layer", "")
        if layer not in ("contract_fact", "legal_semantics"):
            continue
        if node_name.startswith("cuad_agg_"):
            continue

        # BFS from this node to find reachable dimension nodes
        visited: set[str] = set()
        queue = children.get(node_name, []).copy()
        reachable_dims: list[str] = []
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if current in dim_set:
                reachable_dims.append(current)
            else:
                queue.extend(children.get(current, []))

        if reachable_dims:
            evidence_to_dims[node_name] = reachable_dims

    return evidence_to_dims


@dataclass(frozen=True)
class JointRiskResult:
    """Joint probability of two risk dimensions both being 'high'."""
    dim_a: str
    dim_b: str
    dim_a_label: str
    dim_b_label: str
    p_a_high: float          # P(A=high)
    p_b_high: float          # P(B=high)
    p_joint_high: float      # P(A=high ∩ B=high)
    multiplier: float        # P(A∩B) / (P(A) * P(B)) — >1 = multiplicative
    description: str


def query_joint_probability(
    dim_pairs: list[tuple[str, str]],
    evidence: dict[str, str] | None = None,
    model: BayesianNetwork | None = None,
    config: dict | None = None,
) -> list[JointRiskResult]:
    """Compute P(A=high ∩ B=high) for each dimension pair.

    The multiplier indicates whether the two dimensions interact
    multiplicatively (>1), independently (=1), or negatively (<1).

    Args:
        dim_pairs: List of (dim_a, dim_b) tuples to query.
        evidence: BN evidence dict.
        model: Pre-built model (optional).
        config: BN config (optional).

    Returns:
        List of JointRiskResult sorted by multiplier descending.
    """
    if config is None:
        config = load_v2_config()
    if model is None:
        model = build_model(config)

    inference = VariableElimination(model)
    clean_evidence = {k: v for k, v in (evidence or {}).items() if k in set(model.nodes())}

    # First get marginal P(high) for each unique dimension
    unique_dims: set[str] = set()
    for a, b in dim_pairs:
        unique_dims.add(a)
        unique_dims.add(b)

    marginals: dict[str, float] = {}
    for dim in unique_dims:
        try:
            factor = inference.query(
                variables=[dim],
                evidence=clean_evidence if clean_evidence else None,
            )
            dist = _discrete_factor_to_distribution(factor, dim)
            marginals[dim] = dist.get("high", 0.0)
        except Exception:
            marginals[dim] = 0.0

    results: list[JointRiskResult] = []
    for dim_a, dim_b in dim_pairs:
        p_a = marginals.get(dim_a, 0.0)
        p_b = marginals.get(dim_b, 0.0)
        try:
            joint_factor = inference.query(
                variables=[dim_a, dim_b],
                evidence=clean_evidence if clean_evidence else None,
            )
            # Extract P(dim_a=high, dim_b=high)
            dim_a_idx = list(joint_factor.variables).index(dim_a)
            dim_b_idx = list(joint_factor.variables).index(dim_b)
            values = joint_factor.values
            # Find indices of 'high' state in each dimension
            high_idx_a = joint_factor.state_names[dim_a].index("high")
            high_idx_b = joint_factor.state_names[dim_b].index("high")
            # Build slice to extract the joint probability
            slices = [slice(None)] * len(joint_factor.variables)
            slices[dim_a_idx] = high_idx_a
            slices[dim_b_idx] = high_idx_b
            p_joint = float(values[tuple(slices)])
        except Exception:
            p_joint = 0.0

        # Multiplier: >1 = synergistic, =1 = independent, <1 = antagonistic
        independent = p_a * p_b
        multiplier = round(p_joint / independent, 2) if independent > 0 else 1.0

        dim_a_label = DIMENSION_LABELS.get(dim_a, dim_a)
        dim_b_label = DIMENSION_LABELS.get(dim_b, dim_b)

        if multiplier > 1.3:
            desc = f"「{dim_a_label}」与「{dim_b_label}」存在乘数效应：联合高风险概率 {p_joint:.1%}，乘数因子 {multiplier}x。两个风险维度相互放大，需同步处理。"
        elif multiplier > 0.9:
            desc = f"「{dim_a_label}」与「{dim_b_label}」基本独立：联合高风险概率 {p_joint:.1%}。"
        else:
            desc = f"「{dim_a_label}」与「{dim_b_label}」存在负相关：联合高风险概率 {p_joint:.1%}。改善一个维度可能降低另一维度风险。"

        results.append(JointRiskResult(
            dim_a=dim_a, dim_b=dim_b,
            dim_a_label=dim_a_label, dim_b_label=dim_b_label,
            p_a_high=round(p_a, 4), p_b_high=round(p_b, 4),
            p_joint_high=round(p_joint, 4),
            multiplier=multiplier,
            description=desc,
        ))

    results.sort(key=lambda r: -r.multiplier)
    return results
