"""Add LEDGAR nodes to BN with intermediate aggregate nodes to avoid CPT explosion.

Strategy: create sub-aggregate nodes to keep each aggregate ≤ 7 parents (3^7=2187 combos).
"""
import json, copy

# ── Sub-aggregate definitions ──
SUB_AGGREGATES = {
    "ledgar_agg_legal_a": {
        "parents": [
            "cuad_anti_corruption", "cuad_compliance_with_laws", "cuad_sanctions",
            "cuad_regulatory_approvals", "cuad_signing_authority", "cuad_powers",
            "cuad_binding_effect",
        ],
        "target": "cuad_agg_legal",
    },
    "ledgar_agg_legal_b": {
        "parents": [
            "cuad_contra_proferentem", "cuad_enforceability", "cuad_severability",
            "cuad_interpretation_rules", "cuad_no_waiver", "cuad_survival",
            "cuad_contract_term",
        ],
        "target": "cuad_agg_legal",
    },
    "ledgar_agg_financial": {
        "parents": [
            "cuad_taxes", "cuad_tax_withholding", "cuad_withholding",
            "cuad_interest_on_late_payment",
        ],
        "target": "cuad_agg_financial_a",
    },
    "ledgar_agg_dispute": {
        "parents": [
            "cuad_notice", "cuad_disclosure_schedule",
            "cuad_representations_warranties", "cuad_forfeiture",
            "cuad_liens", "cuad_third_party_consents",
        ],
        "target": "cuad_agg_dispute",
    },
    "ledgar_agg_balance": {
        "parents": [
            "cuad_affiliate_transactions", "cuad_brokers", "cuad_publicity",
        ],
        "target": "cuad_agg_balance_a",
    },
}

# ── Remaining direct connections (small parent sets) ──
DIRECT_EDGES = {
    "cuad_further_assurances": "cuad_agg_performance",
    "cuad_cooperation": "cuad_agg_performance",
    "cuad_books_records": "cuad_agg_performance",
    "cuad_record_keeping": "cuad_agg_performance",
    "cuad_qualifications": "cuad_agg_performance",
    "cuad_use_of_proceeds": "cuad_agg_financial_b",
    "cuad_solvency": "cuad_agg_financial_b",
    "cuad_vesting": "cuad_agg_balance_b",
}

with open("config/bayesian_network_v2.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# ── 1. Create sub-aggregate nodes ──
for agg_name, spec in SUB_AGGREGATES.items():
    config["nodes"][agg_name] = {
        "layer": "legal_semantics",
        "label": agg_name,
        "states": ["favorable", "neutral", "unfavorable"],
        "parents": list(spec["parents"]),
        "cpt": {"_aggregate": True, "unfavorable_threshold": 0.3},
        "cpt_source": "noisy_max_generated",
    }

# ── 2. Add edges: leaf → sub-aggregate, sub-aggregate → main aggregate ──
existing_edges = {tuple(e) for e in config["edges"]}
new_edges = []

for agg_name, spec in SUB_AGGREGATES.items():
    for parent in spec["parents"]:
        edge = [parent, agg_name]
        if tuple(edge) not in existing_edges:
            new_edges.append(edge)
            existing_edges.add(tuple(edge))
    # sub-aggregate → main aggregate
    edge = [agg_name, spec["target"]]
    if tuple(edge) not in existing_edges:
        new_edges.append(edge)
        existing_edges.add(tuple(edge))

for node_name, agg_name in DIRECT_EDGES.items():
    edge = [node_name, agg_name]
    if tuple(edge) not in existing_edges:
        new_edges.append(edge)
        existing_edges.add(tuple(edge))

config["edges"].extend(new_edges)

# ── 3. Update main aggregate parents ──
for agg_name, spec in SUB_AGGREGATES.items():
    target = spec["target"]
    existing_parents = config["nodes"][target].get("parents", [])
    if agg_name not in existing_parents:
        config["nodes"][target]["parents"] = existing_parents + [agg_name]

for node_name, agg_name in DIRECT_EDGES.items():
    existing_parents = config["nodes"][agg_name].get("parents", [])
    if node_name not in existing_parents:
        config["nodes"][agg_name]["parents"] = existing_parents + [node_name]

# ── 4. Verify parent counts ──
print("Aggregate parent counts:")
for agg_name in list(SUB_AGGREGATES.keys()) + [
    "cuad_agg_legal", "cuad_agg_financial_a", "cuad_agg_financial_b",
    "cuad_agg_dispute", "cuad_agg_balance_a", "cuad_agg_balance_b",
    "cuad_agg_performance",
]:
    parents = config["nodes"][agg_name].get("parents", [])
    n = len(parents)
    combos = 3 ** n if n > 0 else 0
    flag = "OK" if combos < 100000 else "TOO BIG"
    print(f"  {agg_name}: {n} parents -> 3^{n}={combos:,} {flag}")

with open("config/bayesian_network_v2.json", "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print(f"\nTotal edges: {len(config['edges'])}, nodes: {len(config['nodes'])}")
print("Done.")
