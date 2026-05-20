"""P1-3: LEDGAR-assisted CPT calibration.

Uses LEDGAR 80K clause classifications to calibrate prior P(present)
for 35 BN nodes that currently have expert_estimated CPTs.

Method:
1. Covered nodes (have both LEDGAR labels and CUAD CPTs) serve as calibration anchors
2. Linear regression: P(present) ~ LEDGAR_frequency
3. Apply to 35 new nodes to estimate data-driven P(present)
"""
from datasets import load_from_disk
import json
import numpy as np
from collections import Counter

# ── Load LEDGAR ──
ds = load_from_disk("dataset/ledgar")
label_names = ds["train"].features["label"].names

counts = Counter()
for split in ["train", "test", "validation"]:
    for sample in ds[split]:
        counts[label_names[sample["label"]]] += 1
total = sum(counts.values())

# ── LEDGAR → BN mapping ──
MAPPING = {
    # covered (calibration anchors)
    "Adjustments": ("covered", "price_adjustment_mechanism"),
    "Agreements": ("covered", "termination_clause_completeness"),
    "Amendments": ("covered", "termination_clause"),
    "Applicable Laws": ("covered", "governing_law_clause"),
    "Approvals": ("covered", "acceptance_process_clarity"),
    "Arbitration": ("covered", "dispute_resolution_clause"),
    "Assignments": ("covered", "cuad_anti_assignment"),
    "Assigns": ("covered", "cuad_anti_assignment"),
    "Change In Control": ("covered", "cuad_change_of_control"),
    "Closings": ("covered", "delivery_terms"),
    "Confidentiality": ("covered", "confidentiality_nli"),
    "Consent To Jurisdiction": ("covered", "jurisdiction_fairness"),
    "Costs": ("covered", "payment_structure"),
    "Duties": ("covered", "termination_clause_completeness"),
    "Enforcements": ("covered", "cuad_liquidated_damages"),
    "Entire Agreements": ("covered", "termination_clause_completeness"),
    "Expenses": ("covered", "payment_structure"),
    "Fees": ("covered", "payment_structure"),
    "Governing Laws": ("covered", "governing_law_clause"),
    "Indemnifications": ("covered", "damages_exposure"),
    "Indemnity": ("covered", "damages_exposure"),
    "Insurances": ("covered", "cuad_insurance"),
    "Integration": ("covered", "termination_clause_completeness"),
    "Intellectual Property": ("covered", "cuad_ip_ownership_assignment"),
    "Jurisdictions": ("covered", "jurisdiction_fairness"),
    "Litigations": ("covered", "dispute_resolution_clause"),
    "Modifications": ("covered", "termination_clause"),
    "Non-Disparagement": ("covered", "cuad_non_disparagement"),
    "Payments": ("covered", "payment_structure"),
    "Releases": ("covered", "damages_exposure"),
    "Remedies": ("covered", "cuad_liquidated_damages"),
    "Sales": ("covered", "payment_structure"),
    "Specific Performance": ("covered", "cuad_liquidated_damages"),
    "Submission To Jurisdiction": ("covered", "jurisdiction_fairness"),
    "Successors": ("covered", "cuad_anti_assignment"),
    "Terminations": ("covered", "termination_clause"),
    "Venues": ("covered", "dispute_venue_fairness"),
    "Waivers": ("covered", "cuad_no_waiver"),
    "Warranties": ("covered", "cuad_warranty_duration"),
    # new_universal (targets)
    "Anti-Corruption Laws": ("new_universal", "cuad_anti_corruption"),
    "Authority": ("new_universal", "cuad_signing_authority"),
    "Binding Effects": ("new_universal", "cuad_binding_effect"),
    "Compliance With Laws": ("new_universal", "cuad_compliance_with_laws"),
    "Construction": ("new_universal", "cuad_contra_proferentem"),
    "Cooperation": ("new_universal", "cuad_cooperation"),
    "Disclosures": ("new_universal", "cuad_disclosure_schedule"),
    "Enforceability": ("new_universal", "cuad_enforceability"),
    "Further Assurances": ("new_universal", "cuad_further_assurances"),
    "Interests": ("new_universal", "cuad_interest_on_late_payment"),
    "Interpretations": ("new_universal", "cuad_interpretation_rules"),
    "No Waivers": ("new_universal", "cuad_no_waiver"),
    "Notices": ("new_universal", "cuad_notice"),
    "Powers": ("new_universal", "cuad_powers"),
    "Publicity": ("new_universal", "cuad_publicity"),
    "Representations": ("new_universal", "cuad_representations_warranties"),
    "Sanctions": ("new_universal", "cuad_sanctions"),
    "Severability": ("new_universal", "cuad_severability"),
    "Survival": ("new_universal", "cuad_survival"),
    "Taxes": ("new_universal", "cuad_taxes"),
    "Terms": ("new_universal", "cuad_contract_term"),
    # new_contract_specific
    "Authorizations": ("new_contract_specific", "cuad_regulatory_approvals"),
    "Books": ("new_contract_specific", "cuad_books_records"),
    "Brokers": ("new_contract_specific", "cuad_brokers"),
    "Consents": ("new_contract_specific", "cuad_third_party_consents"),
    "Forfeitures": ("new_contract_specific", "cuad_forfeiture"),
    "Liens": ("new_contract_specific", "cuad_liens"),
    "Qualifications": ("new_contract_specific", "cuad_qualifications"),
    "Records": ("new_contract_specific", "cuad_record_keeping"),
    "Solvency": ("new_contract_specific", "cuad_solvency"),
    "Tax Withholdings": ("new_contract_specific", "cuad_tax_withholding"),
    "Transactions With Affiliates": ("new_contract_specific", "cuad_affiliate_transactions"),
    "Use Of Proceeds": ("new_contract_specific", "cuad_use_of_proceeds"),
    "Vesting": ("new_contract_specific", "cuad_vesting"),
    "Withholdings": ("new_contract_specific", "cuad_withholding"),
}

# ── Build calibration anchors ──
with open("config/bayesian_network_v2.json", "r", encoding="utf-8") as f:
    bn = json.load(f)

# Aggregate LEDGAR frequencies per BN node (some labels map to same node)
bn_ledgar_freq: dict[str, float] = {}
for ledgar_label, (status, bn_node) in MAPPING.items():
    freq = counts[ledgar_label] / total
    bn_ledgar_freq[bn_node] = bn_ledgar_freq.get(bn_node, 0.0) + freq

# Extract calibration points (covered nodes with CUAD CPT)
X, Y = [], []
anchors = []
for bn_node, ledgar_freq in sorted(bn_ledgar_freq.items()):
    node_cfg = bn["nodes"].get(bn_node, {})
    cpt = node_cfg.get("cpt", {})
    p_present = cpt.get("present")
    if p_present is not None and bn_node in {
        "price_adjustment_mechanism", "termination_clause_completeness",
        "termination_clause", "governing_law_clause", "acceptance_process_clarity",
        "dispute_resolution_clause", "cuad_anti_assignment", "cuad_change_of_control",
        "delivery_terms", "jurisdiction_fairness", "payment_structure",
        "cuad_liquidated_damages", "damages_exposure", "cuad_insurance",
        "cuad_ip_ownership_assignment", "cuad_non_disparagement",
        "cuad_warranty_duration", "dispute_venue_fairness", "cuad_no_waiver",
    }:
        X.append(ledgar_freq)
        Y.append(p_present)
        anchors.append((bn_node, ledgar_freq, p_present))

print(f"Calibration anchors: {len(anchors)}")
print(f'{"BN Node":<38} {"LEDGAR freq":>12} {"CUAD P(present)":>15}')
print("-" * 68)
for bn_node, lf, pp in anchors:
    print(f"{bn_node:<38} {lf:>12.6f} {pp:>15.6f}")

# Linear regression
a, b = np.polyfit(X, Y, 1)
predicted = [a * x + b for x in X]
residuals = [abs(p - y) for p, y in zip(predicted, Y)]
print(f"\nLinear fit: P(present) = {a:.4f} * ledgar_freq + {b:.4f}")
print(f"Mean absolute residual: {np.mean(residuals):.4f}")
print(f"Max residual: {np.max(residuals):.4f}")

# ── Apply to 35 target nodes ──
print(f"\n{'='*80}")
print("Calibrated CPTs for 35 LEDGAR-mapped nodes:")
print(f"{'BN Node':<38} {'LEDGAR freq':>12} {'Old P(pres)':>11} {'New P(pres)':>11} {'Change':>8}")
print("-" * 85)

updates = {}
for ledgar_label, (status, bn_node) in MAPPING.items():
    if status not in ("new_universal", "new_contract_specific"):
        continue
    if bn_node not in bn_ledgar_freq:
        continue
    ledgar_freq = bn_ledgar_freq[bn_node]
    new_p = max(0.02, min(0.70, a * ledgar_freq + b))  # clamp to [0.02, 0.70]
    new_p = round(new_p, 6)

    old_cpt = bn["nodes"][bn_node].get("cpt", {})
    old_p = old_cpt.get("present", "N/A") if isinstance(old_cpt, dict) else "N/A"

    change = ""
    if isinstance(old_p, (int, float)):
        change = f"{new_p - old_p:+.4f}"

    print(f"{bn_node:<38} {ledgar_freq:>12.6f} {str(old_p):>11} {new_p:>11.6f} {change:>8}")
    updates[bn_node] = new_p

print(f"\n{len(updates)} nodes to update.")
