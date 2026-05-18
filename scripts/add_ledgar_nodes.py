"""F-1b: Add 35 new BN nodes to bayesian_network_v2.json."""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "bayesian_network_v2.json"

with open(CONFIG_PATH, encoding="utf-8") as f:
    bn = json.load(f)

# ── New universal nodes (contract_fact: present/missing/unknown) ──
UNIVERSAL_FACT = [
    ("cuad_anti_corruption", "反腐败/商业贿赂"),
    ("cuad_signing_authority", "签约授权"),
    ("cuad_compliance_with_laws", "合规条款"),
    ("cuad_cooperation", "合作义务"),
    ("cuad_disclosure_schedule", "信息披露/附件"),
    ("cuad_further_assurances", "进一步保证"),
    ("cuad_contract_term", "合同期限"),
    ("cuad_notice", "通知条款"),
    ("cuad_publicity", "公开宣传/新闻发布"),
    ("cuad_sanctions", "制裁/出口管制"),
    ("cuad_taxes", "税务条款"),
]

# ── New universal nodes (legal_semantics: favorable/neutral/unfavorable) ──
UNIVERSAL_SEMANTICS = [
    ("cuad_binding_effect", "合同约束力"),
    ("cuad_contra_proferentem", "合同解释规则(不利解释原则)"),
    ("cuad_enforceability", "可执行性"),
    ("cuad_interest_on_late_payment", "逾期利息"),
    ("cuad_interpretation_rules", "合同解释规则"),
    ("cuad_no_waiver", "不放弃权利"),
    ("cuad_powers", "授权/权限"),
    ("cuad_representations_warranties", "陈述与保证"),
    ("cuad_severability", "可分割性"),
    ("cuad_survival", "条款存续"),
]

# ── New contract-specific nodes (contract_fact) ──
SPECIFIC_FACT = [
    ("cuad_regulatory_approvals", "政府许可/审批"),
    ("cuad_books_records", "账簿/记录查阅"),
    ("cuad_brokers", "中介/居间"),
    ("cuad_third_party_consents", "第三方同意"),
    ("cuad_qualifications", "资格/资质"),
    ("cuad_record_keeping", "记录保存"),
    ("cuad_solvency", "偿付能力声明"),
    ("cuad_tax_withholding", "税款代扣"),
    ("cuad_use_of_proceeds", "资金用途限制"),
]

# ── New contract-specific nodes (legal_semantics) ──
SPECIFIC_SEMANTICS = [
    ("cuad_forfeiture", "没收/丧失权利"),
    ("cuad_liens", "留置权"),
    ("cuad_affiliate_transactions", "关联交易"),
    ("cuad_vesting", "权利归属/成熟"),
    ("cuad_withholding", "代扣代缴"),
]

added = 0
for node_name, label in UNIVERSAL_FACT:
    bn["nodes"][node_name] = {
        "layer": "contract_fact",
        "label": label,
        "states": ["present", "missing", "unknown"],
        "parents": [],
        "cpt": {"present": 0.65, "missing": 0.30, "unknown": 0.05},
        "cpt_source": "expert_estimated (LEDGAR taxonomy mapping, 2026-05-18)",
    }
    added += 1

for node_name, label in UNIVERSAL_SEMANTICS:
    bn["nodes"][node_name] = {
        "layer": "legal_semantics",
        "label": label,
        "states": ["favorable", "neutral", "unfavorable"],
        "parents": [],
        "cpt": {"favorable": 0.50, "neutral": 0.30, "unfavorable": 0.20},
        "cpt_source": "expert_estimated (LEDGAR taxonomy mapping, 2026-05-18)",
    }
    added += 1

for node_name, label in SPECIFIC_FACT:
    bn["nodes"][node_name] = {
        "layer": "contract_fact",
        "label": label,
        "states": ["present", "missing", "unknown"],
        "parents": [],
        "cpt": {"present": 0.55, "missing": 0.40, "unknown": 0.05},
        "cpt_source": "expert_estimated (LEDGAR taxonomy mapping, 2026-05-18)",
    }
    added += 1

for node_name, label in SPECIFIC_SEMANTICS:
    bn["nodes"][node_name] = {
        "layer": "legal_semantics",
        "label": label,
        "states": ["favorable", "neutral", "unfavorable"],
        "parents": [],
        "cpt": {"favorable": 0.50, "neutral": 0.30, "unfavorable": 0.20},
        "cpt_source": "expert_estimated (LEDGAR taxonomy mapping, 2026-05-18)",
    }
    added += 1

# Update node count in description
old_count = bn["description"].split("with")[1].split("nodes")[0].strip()
bn["description"] = bn["description"].replace(
    f"with {old_count} nodes", f"with {55 + added} nodes"
)

with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(bn, f, ensure_ascii=False, indent=2)

print(f"Added {added} nodes to bayesian_network_v2.json (55 → {55 + added})")
print(f"  universal contract_fact: {len(UNIVERSAL_FACT)}")
print(f"  universal legal_semantics: {len(UNIVERSAL_SEMANTICS)}")
print(f"  contract-specific fact: {len(SPECIFIC_FACT)}")
print(f"  contract-specific semantics: {len(SPECIFIC_SEMANTICS)}")
print("All CPTs marked expert_estimated")
