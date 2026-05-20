"""P1-3: Apply LEDGAR-calibrated CPTs to bayesian_network_v2.json."""
from datasets import load_from_disk
import json, numpy as np
from collections import Counter

# Load LEDGAR
ds = load_from_disk("dataset/ledgar")
label_names = ds["train"].features["label"].names
counts = Counter()
for split in ["train", "test", "validation"]:
    for sample in ds[split]:
        counts[label_names[sample["label"]]] += 1
total = sum(counts.values())
print(f"LEDGAR samples: {total}")

# Full mapping (ledgar_label, status, bn_node)
MAPPING = [
    ("Adjustments","covered","price_adjustment_mechanism"),
    ("Agreements","covered","termination_clause_completeness"),
    ("Amendments","covered","termination_clause"),
    ("Applicable Laws","covered","governing_law_clause"),
    ("Approvals","covered","acceptance_process_clarity"),
    ("Arbitration","covered","dispute_resolution_clause"),
    ("Assignments","covered","cuad_anti_assignment"),
    ("Assigns","covered","cuad_anti_assignment"),
    ("Change In Control","covered","cuad_change_of_control"),
    ("Closings","covered","delivery_terms"),
    ("Confidentiality","covered","confidentiality_nli"),
    ("Consent To Jurisdiction","covered","jurisdiction_fairness"),
    ("Costs","covered","payment_structure"),
    ("Duties","covered","termination_clause_completeness"),
    ("Enforcements","covered","cuad_liquidated_damages"),
    ("Entire Agreements","covered","termination_clause_completeness"),
    ("Expenses","covered","payment_structure"),
    ("Fees","covered","payment_structure"),
    ("Governing Laws","covered","governing_law_clause"),
    ("Indemnifications","covered","damages_exposure"),
    ("Indemnity","covered","damages_exposure"),
    ("Insurances","covered","cuad_insurance"),
    ("Integration","covered","termination_clause_completeness"),
    ("Intellectual Property","covered","cuad_ip_ownership_assignment"),
    ("Jurisdictions","covered","jurisdiction_fairness"),
    ("Litigations","covered","dispute_resolution_clause"),
    ("Modifications","covered","termination_clause"),
    ("Non-Disparagement","covered","cuad_non_disparagement"),
    ("Payments","covered","payment_structure"),
    ("Releases","covered","damages_exposure"),
    ("Remedies","covered","cuad_liquidated_damages"),
    ("Sales","covered","payment_structure"),
    ("Specific Performance","covered","cuad_liquidated_damages"),
    ("Submission To Jurisdiction","covered","jurisdiction_fairness"),
    ("Successors","covered","cuad_anti_assignment"),
    ("Terminations","covered","termination_clause"),
    ("Venues","covered","dispute_venue_fairness"),
    ("Waivers","covered","cuad_no_waiver"),
    ("Warranties","covered","cuad_warranty_duration"),
    ("Anti-Corruption Laws","new_universal","cuad_anti_corruption"),
    ("Authority","new_universal","cuad_signing_authority"),
    ("Binding Effects","new_universal","cuad_binding_effect"),
    ("Compliance With Laws","new_universal","cuad_compliance_with_laws"),
    ("Construction","new_universal","cuad_contra_proferentem"),
    ("Cooperation","new_universal","cuad_cooperation"),
    ("Disclosures","new_universal","cuad_disclosure_schedule"),
    ("Enforceability","new_universal","cuad_enforceability"),
    ("Further Assurances","new_universal","cuad_further_assurances"),
    ("Interests","new_universal","cuad_interest_on_late_payment"),
    ("Interpretations","new_universal","cuad_interpretation_rules"),
    ("No Waivers","new_universal","cuad_no_waiver"),
    ("Notices","new_universal","cuad_notice"),
    ("Powers","new_universal","cuad_powers"),
    ("Publicity","new_universal","cuad_publicity"),
    ("Representations","new_universal","cuad_representations_warranties"),
    ("Sanctions","new_universal","cuad_sanctions"),
    ("Severability","new_universal","cuad_severability"),
    ("Survival","new_universal","cuad_survival"),
    ("Taxes","new_universal","cuad_taxes"),
    ("Terms","new_universal","cuad_contract_term"),
    ("Authorizations","new_contract_specific","cuad_regulatory_approvals"),
    ("Books","new_contract_specific","cuad_books_records"),
    ("Brokers","new_contract_specific","cuad_brokers"),
    ("Consents","new_contract_specific","cuad_third_party_consents"),
    ("Forfeitures","new_contract_specific","cuad_forfeiture"),
    ("Liens","new_contract_specific","cuad_liens"),
    ("Qualifications","new_contract_specific","cuad_qualifications"),
    ("Records","new_contract_specific","cuad_record_keeping"),
    ("Solvency","new_contract_specific","cuad_solvency"),
    ("Tax Withholdings","new_contract_specific","cuad_tax_withholding"),
    ("Transactions With Affiliates","new_contract_specific","cuad_affiliate_transactions"),
    ("Use Of Proceeds","new_contract_specific","cuad_use_of_proceeds"),
    ("Vesting","new_contract_specific","cuad_vesting"),
    ("Withholdings","new_contract_specific","cuad_withholding"),
]

with open("config/bayesian_network_v2.json", "r", encoding="utf-8") as f:
    bn = json.load(f)

# Aggregate LEDGAR freq per BN node
bn_freq = {}
for ledgar_label, status, bn_node in MAPPING:
    bn_freq[bn_node] = bn_freq.get(bn_node, 0.0) + counts[ledgar_label] / total

# Calibration anchors: covered nodes with unique CUAD CPT present values
anchor_nodes = {
    "acceptance_process_clarity", "cuad_anti_assignment", "cuad_change_of_control",
    "cuad_insurance", "cuad_ip_ownership_assignment", "cuad_liquidated_damages",
    "cuad_non_disparagement", "cuad_warranty_duration", "dispute_resolution_clause",
    "governing_law_clause", "jurisdiction_fairness", "termination_clause",
    "termination_clause_completeness",
}
X, Y = [], []
for bn_node in anchor_nodes:
    if bn_node in bn_freq and bn_node in bn["nodes"]:
        p = bn["nodes"][bn_node]["cpt"].get("present")
        if p is not None:
            X.append(bn_freq[bn_node])
            Y.append(p)

a, b = np.polyfit(X, Y, 1)
print(f"Linear fit: P(present) = {a:.4f} * ledgar_freq + {b:.4f}")
print(f"Anchors: {len(X)}")

# Apply to 35 target nodes
updated = 0
for ledgar_label, status, bn_node in MAPPING:
    if status not in ("new_universal", "new_contract_specific"):
        continue
    if bn_node not in bn_freq or bn_node not in bn["nodes"]:
        continue

    new_p = max(0.02, min(0.70, a * bn_freq[bn_node] + b))
    new_p = round(new_p, 6)
    states = bn["nodes"][bn_node].get("states", [])

    if "present" in states and "missing" in states:
        new_cpt = {
            "present": new_p,
            "missing": round(1.0 - new_p - 0.03, 6),
            "unknown": 0.03,
        }
    elif "favorable" in states and "unfavorable" in states:
        rem = 1.0 - new_p
        new_cpt = {
            "favorable": new_p,
            "neutral": round(rem * 0.6, 6),
            "unfavorable": round(rem * 0.4, 6),
        }
    else:
        continue

    bn["nodes"][bn_node]["cpt"] = new_cpt
    bn["nodes"][bn_node]["cpt_source"] = (
        "expert_estimated (LEDGAR frequency calibrated, 2026-05-20)"
    )
    updated += 1

with open("config/bayesian_network_v2.json", "w", encoding="utf-8") as f:
    json.dump(bn, f, ensure_ascii=False, indent=2)

print(f"Updated {updated} nodes.")

# Show range
items = [
    (bn_node, bn["nodes"][bn_node]["cpt"], bn_freq.get(bn_node, 0))
    for _, status, bn_node in MAPPING
    if status in ("new_universal", "new_contract_specific")
    and bn_node in bn["nodes"]
]
items.sort(key=lambda x: x[2], reverse=True)
print(f"\nHighest: {items[0][0]} (freq={items[0][2]:.6f}) -> {items[0][1]}")
print(f"Lowest:  {items[-1][0]} (freq={items[-1][2]:.6f}) -> {items[-1][1]}")
