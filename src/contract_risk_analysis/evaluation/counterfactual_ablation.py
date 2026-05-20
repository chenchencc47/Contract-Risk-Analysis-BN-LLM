"""P3-3: Counterfactual ablation — validate 110 BN node flip directions.

For each contract_fact / legal_semantics node, flips between its
favorable and unfavorable state and checks whether P(high) moves in
the expected direction (unfavorable → higher risk).

Finds nodes whose CPT direction may be wrong (favorable state guessed
incorrectly, or edge polarity reversed).
"""
import json
from collections import defaultdict
from contract_risk_analysis.bn.pgmpy_adapter import (
    load_v2_config,
    build_model,
)
from pgmpy.inference import VariableElimination


def _discrete_factor_to_distribution(factor, var_name):
    """Extract {state: probability} from a pgmpy DiscreteFactor."""
    states = factor.state_names[var_name]
    values = factor.values
    # Flatten if needed
    if hasattr(values, "flatten"):
        values = values.flatten()
    return {s: float(v) for s, v in zip(states, values)}


def run_ablation():
    config = load_v2_config()
    model = build_model(config)
    inference = VariableElimination(model)
    nodes_cfg = config["nodes"]

    # ── Favorable state map (same logic as run_sensitivity_analysis) ──
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
        "payment_structure": "balanced",
        "delivery_terms": "present",
        "risk_transfer_point": "favorable",
        "dispute_venue_fairness": "balanced",
        "force_majeure_completeness": "present",
        "warranty_scope": "broad",
        "dispute_resolution_completeness": "present",
    }

    # Auto-discover for remaining nodes
    for node_name, node_cfg in nodes_cfg.items():
        layer = node_cfg.get("layer", "")
        if layer not in ("contract_fact", "legal_semantics"):
            continue
        if node_name in favorable_states:
            continue
        states = node_cfg.get("states", [])
        for fav in (
            "present", "balanced", "acceptable", "favorable",
            "entailment", "broad", "low", "sufficient",
            "strong", "reasonable", "clear", "complete",
            "adequate", "exists", "yes",
            "specific", "precise", "explicit",
        ):
            if fav in states:
                favorable_states[node_name] = fav
                break
        if node_name not in favorable_states and states:
            favorable_states[node_name] = states[-1]

    # ── Unfavorable state map ──
    unfavorable_candidates = [
        "unfavorable", "missing", "contradiction",
        "counterparty_favorable", "severe", "high",
        "narrow", "inadequate", "weak", "unreasonable",
        "absent", "vague", "none", "restrictive",
    ]

    def find_unfavorable(node_name, states, favorable):
        """Find the worst state for this node."""
        # First: explicit 'unfavorable' or 'missing'
        for cand in unfavorable_candidates:
            if cand in states and cand != favorable:
                return cand
        # Second: any state that's not favorable and not 'unknown'/'neutral'
        for s in states:
            if s != favorable and s not in ("unknown", "neutral"):
                return s
        # Last resort: any non-favorable state
        for s in states:
            if s != favorable:
                return s
        return None

    # ── Run ablation ──
    results = []
    direction_correct = 0
    direction_wrong = 0
    skipped = 0

    fact_semantics_nodes = [
        n for n, cfg in nodes_cfg.items()
        if cfg.get("layer") in ("contract_fact", "legal_semantics")
    ]

    print(f"Ablating {len(fact_semantics_nodes)} nodes...")
    print()

    for node_name in sorted(fact_semantics_nodes):
        favorable = favorable_states.get(node_name)
        if favorable is None:
            skipped += 1
            continue

        states = nodes_cfg[node_name].get("states", [])
        unfavorable = find_unfavorable(node_name, states, favorable)
        if unfavorable is None:
            skipped += 1
            continue

        # Run inference with ONLY this node set
        try:
            evidence_fav = {node_name: favorable}
            result_fav = inference.query(
                variables=["overall_contract_risk"],
                evidence=evidence_fav,
            )
            dist_fav = _discrete_factor_to_distribution(
                result_fav, "overall_contract_risk"
            )
            p_high_fav = dist_fav.get("high", 0.0)

            evidence_unfav = {node_name: unfavorable}
            result_unfav = inference.query(
                variables=["overall_contract_risk"],
                evidence=evidence_unfav,
            )
            dist_unfav = _discrete_factor_to_distribution(
                result_unfav, "overall_contract_risk"
            )
            p_high_unfav = dist_unfav.get("high", 0.0)
        except Exception as e:
            skipped += 1
            continue

        delta = round(p_high_unfav - p_high_fav, 6)
        correct = delta > 0  # unfavorable should INCREASE P(high)

        if correct:
            direction_correct += 1
        else:
            direction_wrong += 1

        results.append({
            "node_name": node_name,
            "favorable": favorable,
            "unfavorable": unfavorable,
            "p_high_fav": round(p_high_fav, 6),
            "p_high_unfav": round(p_high_unfav, 6),
            "delta": delta,
            "direction_correct": correct,
            "favorable_source": (
                "hand_specified" if node_name in {
                    "termination_clause", "liability_cap", "confidentiality_nli",
                    "governing_law_clause", "dispute_resolution_clause",
                    "termination_clause_completeness", "termination_right_balance",
                    "liability_cap_strength", "damages_exposure",
                    "governing_law_clarity", "dispute_resolution_clarity",
                    "jurisdiction_fairness", "acceptance_process_clarity",
                    "confidentiality_scope_reasonableness",
                    "payment_structure", "delivery_terms", "risk_transfer_point",
                    "dispute_venue_fairness", "force_majeure_completeness",
                    "warranty_scope", "dispute_resolution_completeness",
                } else "auto_discovered"
            ),
        })

    # ── Print report ──
    total = direction_correct + direction_wrong
    print(f"Results: {total} nodes evaluated, {skipped} skipped")
    print(f"  Direction correct:  {direction_correct}/{total} ({direction_correct/total*100:.1f}%)")
    print(f"  Direction VIOLATION: {direction_wrong}/{total} ({direction_wrong/total*100:.1f}%)")
    print()

    if direction_wrong > 0:
        print("=== DIRECTION VIOLATIONS ===")
        for r in results:
            if not r["direction_correct"]:
                print(f"  {r['node_name']}:")
                print(f"    favorable={r['favorable']} → P(high)={r['p_high_fav']:.4f}")
                print(f"    unfavorable={r['unfavorable']} → P(high)={r['p_high_unfav']:.4f}")
                print(f"    delta={r['delta']:.4f} (should be >0)")
                print(f"    source={r['favorable_source']}")

    # ── Summary by source ──
    hand = [r for r in results if r["favorable_source"] == "hand_specified"]
    auto = [r for r in results if r["favorable_source"] == "auto_discovered"]
    hand_wrong = sum(1 for r in hand if not r["direction_correct"])
    auto_wrong = sum(1 for r in auto if not r["direction_correct"])
    print(f"\nBy favorable state source:")
    print(f"  Hand-specified: {len(hand)} nodes, {hand_wrong} violations")
    print(f"  Auto-discovered: {len(auto)} nodes, {auto_wrong} violations")

    # ── Show auto-discovered nodes with tiny delta (suspicious) ──
    print(f"\n=== Auto-discovered nodes with |delta| < 0.01 (low confidence) ===")
    low_conf = [r for r in auto if abs(r["delta"]) < 0.01]
    low_conf.sort(key=lambda r: r["delta"])
    for r in low_conf:
        flag = "VIOLATION" if not r["direction_correct"] else "OK"
        print(f"  {r['node_name']:<40} fav={r['favorable']:<15} unfav={r['unfavorable']:<20} delta={r['delta']:>8.4f} {flag}")

    return results


if __name__ == "__main__":
    run_ablation()
