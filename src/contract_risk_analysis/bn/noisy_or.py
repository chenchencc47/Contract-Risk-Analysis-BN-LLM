"""Noisy-OR / Noisy-MAX CPT generator for risk aggregation nodes (P4.4).

Reduces overall_contract_risk CPT from O(K^M) = 3^5 = 243 rows
to O(K*M) = 15 parameters via independent causal influence model.
"""

from __future__ import annotations

from itertools import product


def _risk_level_score(level: str) -> float:
    """Map a node state to a numeric risk score.

    Handles multiple state naming conventions:
      - Risk levels: low=0.0, medium=0.5, high=1.0
      - Binary presence: present=0.0, missing=1.0
      - Binary fairness: balanced=0.0, counterparty_favorable=1.0
      - Binary quality: acceptable=0.0, unfavorable=1.0
      - Severity levels: acceptable=0.0, moderate=0.4, missing=0.8, severe=1.0
      - NLI: entailment=0.0, neutral=0.5, contradiction=1.0
      - Exposure: low=0.0, medium=0.5, high=1.0
      - Unknown/ambiguous: 0.5 (neutral)
    """
    mapping: dict[str, float] = {
        "low": 0.0, "medium": 0.5, "high": 1.0,
        "present": 0.0, "missing": 1.0,
        "balanced": 0.0, "counterparty_favorable": 1.0,
        "acceptable": 0.0, "unfavorable": 1.0,
        "moderate": 0.4, "severe": 1.0,
        "entailment": 0.0, "neutral": 0.5, "contradiction": 1.0,
        "favorable": 0.0, "neutral": 0.5, "unfavorable": 1.0,
        "broad": 0.0, "narrow": 0.7,
        "unknown": 0.5, "ambiguous": 0.5,
    }
    return mapping.get(level, 0.5)


def _score_to_distribution(score: float, thresholds: tuple[float, float] = (0.7, 0.35)) -> dict[str, float]:
    """Convert a weighted risk score to a probability distribution over {low, medium, high}."""
    high_t, med_t = thresholds
    if score >= high_t:
        return {"low": 0.05, "medium": 0.15, "high": 0.80}
    elif score >= med_t:
        return {"low": 0.15, "medium": 0.70, "high": 0.15}
    else:
        return {"low": 0.80, "medium": 0.15, "high": 0.05}


def generate_noisy_max_cpt(
    parent_weights: dict[str, float],
    parent_states_map: dict[str, list[str]],
    child_states: list[str] | None = None,
    thresholds: tuple[float, float] = (0.7, 0.35),
) -> dict[str, dict[str, float]]:
    """Generate full CPT from noisy-max parameters.

    Args:
        parent_weights: Dict mapping parent_node_name → weight (positive float).
        parent_states_map: Dict mapping parent_node_name → list of its states.
        child_states: States of the child node (default: low/medium/high).
        thresholds: (high_threshold, medium_threshold) for score→level conversion.

    Returns:
        CPT dict in the v2 config format: {"parent1state|parent2state|...": {"low": p, ...}}
    """
    if child_states is None:
        child_states = ["low", "medium", "high"]

    parent_names = list(parent_weights.keys())
    parent_state_lists = [parent_states_map[p] for p in parent_names]
    total_weight = sum(parent_weights.values()) or 1.0

    cpt: dict[str, dict[str, float]] = {}

    for combo in product(*parent_state_lists):
        # Compute weighted score
        weighted_sum = sum(
            parent_weights[p_name] * _risk_level_score(combo[i])
            for i, p_name in enumerate(parent_names)
        )
        score = weighted_sum / total_weight

        key = "|".join(combo)
        cpt[key] = _score_to_distribution(score, thresholds)

    return cpt


def compute_default_dimension_weights() -> dict[str, float]:
    """Default weights for risk dimensions (from original config)."""
    return {
        "legal_enforceability_risk": 0.20,
        "financial_exposure_risk": 0.30,
        "performance_delivery_risk": 0.15,
        "dispute_resolution_risk": 0.20,
        "clause_balance_risk": 0.15,
    }


def validate_cpt(cpt: dict[str, dict[str, float]], expected_keys: int) -> list[str]:
    """Validate a generated CPT.

    Returns list of issues (empty if valid).
    """
    issues: list[str] = []
    if len(cpt) != expected_keys:
        issues.append(f"Expected {expected_keys} CPT rows, got {len(cpt)}")

    for key, dist in cpt.items():
        total = sum(dist.values())
        if abs(total - 1.0) > 0.02:
            issues.append(f"Row '{key}': probabilities sum to {total:.4f} (expected ~1.0)")

    return issues
