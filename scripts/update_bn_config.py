"""Update BN config: add CUAD aggregate nodes (P0.1)."""
import json
from collections import defaultdict

with open('config/bayesian_network_v2.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

CUAD_NODE_DEFS = {
    "Termination For Convenience": ("cuad_termination_for_convenience", "legal_enforceability_risk"),
    "Notice Period To Terminate Renewal": ("cuad_notice_period_to_terminate", "legal_enforceability_risk"),
    "Governing Law": ("cuad_governing_law", "legal_enforceability_risk"),
    "Third Party Beneficiary": ("cuad_third_party_beneficiary", "legal_enforceability_risk"),
    "Audit Rights": ("cuad_audit_rights", "legal_enforceability_risk"),
    "Uncapped Liability": ("cuad_uncapped_liability", "financial_exposure_risk"),
    "Cap On Liability": ("cuad_cap_on_liability", "financial_exposure_risk"),
    "Liquidated Damages": ("cuad_liquidated_damages", "financial_exposure_risk"),
    "Insurance": ("cuad_insurance", "financial_exposure_risk"),
    "Warranty Duration": ("cuad_warranty_duration", "financial_exposure_risk"),
    "Revenue/Profit Sharing": ("cuad_revenue_profit_sharing", "financial_exposure_risk"),
    "Minimum Commitment": ("cuad_minimum_commitment", "financial_exposure_risk"),
    "Volume Restriction": ("cuad_volume_restriction", "financial_exposure_risk"),
    "Post-Termination Services": ("cuad_post_termination_services", "performance_delivery_risk"),
    "Source Code Escrow": ("cuad_source_code_escrow", "performance_delivery_risk"),
    "Covenant Not To Sue": ("cuad_covenant_not_to_sue", "dispute_resolution_risk"),
    "No-Solicit Of Customers": ("cuad_no_solicit_of_customers", "dispute_resolution_risk"),
    "No-Solicit Of Employees": ("cuad_no_solicit_of_employees", "dispute_resolution_risk"),
    "Non-Disparagement": ("cuad_non_disparagement", "dispute_resolution_risk"),
    "Anti-Assignment": ("cuad_anti_assignment", "clause_balance_risk"),
    "Change Of Control": ("cuad_change_of_control", "clause_balance_risk"),
    "Non-Compete": ("cuad_non_compete", "clause_balance_risk"),
    "Exclusivity": ("cuad_exclusivity", "clause_balance_risk"),
    "Most Favored Nation": ("cuad_most_favored_nation", "clause_balance_risk"),
    "Ip Ownership Assignment": ("cuad_ip_ownership_assignment", "clause_balance_risk"),
    "Joint Ip Ownership": ("cuad_joint_ip_ownership", "clause_balance_risk"),
    "License Grant": ("cuad_license_grant", "clause_balance_risk"),
    "Non-Transferable License": ("cuad_non_transferable_license", "clause_balance_risk"),
    "Rofr/Rofo/Rofn": ("cuad_rofr_rofo_rofn", "clause_balance_risk"),
    "Price Restrictions": ("cuad_price_restrictions", "clause_balance_risk"),
}

# Remove old CUAD edges to risk dimensions and old aggregate nodes
dim_names = ["legal_enforceability_risk", "financial_exposure_risk",
             "performance_delivery_risk", "dispute_resolution_risk", "clause_balance_risk"]

config["edges"] = [e for e in config["edges"]
    if not (e[0].startswith("cuad_") and e[1] in dim_names)]

old_aggs = [f"cuad_agg_{d}" for d in dim_names]
for agg in old_aggs:
    config["nodes"].pop(agg, None)
config["edges"] = [e for e in config["edges"]
    if e[0] not in old_aggs and e[1] not in old_aggs]

# Clean dimension parents of CUAD nodes
for dim in dim_names:
    node = config["nodes"].get(dim)
    if not node:
        continue
    node["parents"] = [p for p in node.get("parents", []) if not p.startswith("cuad_")]
    w = node.get("noisy_or_weights", {})
    node["noisy_or_weights"] = {k: v for k, v in w.items() if not k.startswith("cuad_")}

# Group CUAD nodes by dimension
cuad_by_dim = defaultdict(list)
for cat_name, (node_name, dim) in CUAD_NODE_DEFS.items():
    if node_name in config["nodes"]:
        cuad_by_dim[dim].append(node_name)

# Split large groups
FINANCIAL_A = [n for n in cuad_by_dim["financial_exposure_risk"]
    if n in ["cuad_uncapped_liability", "cuad_cap_on_liability", "cuad_liquidated_damages",
             "cuad_insurance", "cuad_warranty_duration"]]
FINANCIAL_B = [n for n in cuad_by_dim["financial_exposure_risk"]
    if n in ["cuad_revenue_profit_sharing", "cuad_minimum_commitment", "cuad_volume_restriction"]]

BALANCE_A = [n for n in cuad_by_dim["clause_balance_risk"]
    if n in ["cuad_anti_assignment", "cuad_change_of_control", "cuad_non_compete",
             "cuad_exclusivity", "cuad_most_favored_nation", "cuad_rofr_rofo_rofn"]]
BALANCE_B = [n for n in cuad_by_dim["clause_balance_risk"]
    if n in ["cuad_ip_ownership_assignment", "cuad_joint_ip_ownership",
             "cuad_license_grant", "cuad_non_transferable_license", "cuad_price_restrictions"]]

AGGREGATES = [
    ("cuad_agg_legal", "legal_enforceability_risk",
     cuad_by_dim["legal_enforceability_risk"], 0.15),
    ("cuad_agg_financial_a", "financial_exposure_risk", FINANCIAL_A, 0.10),
    ("cuad_agg_financial_b", "financial_exposure_risk", FINANCIAL_B, 0.08),
    ("cuad_agg_performance", "performance_delivery_risk",
     cuad_by_dim["performance_delivery_risk"], 0.15),
    ("cuad_agg_dispute", "dispute_resolution_risk",
     cuad_by_dim["dispute_resolution_risk"], 0.15),
    ("cuad_agg_balance_a", "clause_balance_risk", BALANCE_A, 0.10),
    ("cuad_agg_balance_b", "clause_balance_risk", BALANCE_B, 0.08),
]

edges_added = 0
for agg_name, target_dim, cuad_nodes, weight in AGGREGATES:
    if not cuad_nodes:
        continue
    config["nodes"][agg_name] = {
        "layer": "legal_semantics",
        "label": f"CUAD Aggregate ({target_dim})",
        "states": ["favorable", "neutral", "unfavorable"],
        "parents": cuad_nodes,
        "cpt_source": "cuad_aggregate_counting",
        "cpt": {"_aggregate": True, "unfavorable_threshold": 0.3},
    }
    for cn in cuad_nodes:
        e = [cn, agg_name]
        if e not in config["edges"]:
            config["edges"].append(e)
            edges_added += 1
    e2 = [agg_name, target_dim]
    if e2 not in config["edges"]:
        config["edges"].append(e2)
        edges_added += 1
    dim_node = config["nodes"][target_dim]
    if agg_name not in dim_node.get("parents", []):
        dim_node.setdefault("parents", []).append(agg_name)
    dim_node.setdefault("noisy_or_weights", {})[agg_name] = weight

print(f"Created {len(AGGREGATES)} aggregate nodes, added {edges_added} edges")
for agg_name, _, cuad_nodes, _ in AGGREGATES:
    if not cuad_nodes: continue
    combos = 3 ** len(cuad_nodes)
    flag = "LARGE" if combos > 10000 else "OK"
    print(f"  {agg_name}: {len(cuad_nodes)} parents -> {combos} entries [{flag}]")

with open('config/bayesian_network_v2.json', 'w', encoding='utf-8') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
print(f"Done: {len(config['nodes'])} nodes, {len(config['edges'])} edges")
