"""F-2: Validate BN node coverage against Chinese contract templates.

Reads chinese_contract_templates (10K samples) and cross-references clause
presence against BN nodes. Outputs per-contract-type coverage statistics
that can be used to refine contract_type_routing.yaml.

Usage:
    python scripts/validate_bn_coverage.py
    python scripts/validate_bn_coverage.py --min-frequency 0.05
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from datasets import load_from_disk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BN_CONFIG = PROJECT_ROOT / "config" / "bayesian_network_v2.json"
ROUTING_CONFIG = PROJECT_ROOT / "config" / "contract_type_routing.yaml"

# ── Contract type keywords (from contract_type_routing.yaml) ──
CONTRACT_TYPE_KW = {
    "销售合同": ["购销", "买卖", "供货", "发货", "收货", "质保金"],
    "采购合同": ["采购", "原料", "供应商", "批次结算", "第三方检测"],
    "技术开发合同": ["技术开发", "软件开发", "系统开发", "定制开发", "委托开发",
                      "源代码", "软件", "系统", "算法", "接口", "API", "部署", "试运行"],
    "服务合同": ["服务", "咨询", "外包", "维护", "运营", "培训", "支持", "专家", "顾问", "劳务", "人力"],
    "租赁合同": ["租赁", "出租", "承租", "租金", "租期", "押金", "腾房", "转租", "装修", "房屋"],
    "保密协议": ["保密", "机密", "商业秘密", "专有信息", "披露", "信息接收", "NDA", "返还", "存续"],
}

# ── Keyword → BN node mapping (node-level signal detection) ──
NODE_KEYWORDS = {
    # universal_core (original)
    "payment_structure": ["付款", "支付", "预付款", "首付", "尾款", "结算", "押金", "保证金"],
    "delivery_terms": ["交货", "交付", "发货", "收货", "运输", "运费"],
    "acceptance_process_clarity": ["验收", "初验", "终验", "验收合格", "检验"],
    "liability_cap_strength": ["责任上限", "赔偿上限", "责任限制", "赔偿限额"],
    "damages_exposure": ["赔偿", "损失", "损害赔偿", "间接损失"],
    "termination_clause_completeness": ["终止", "解除", "解约"],
    "termination_right_balance": ["解除权", "任意解除", "单方解除"],
    "dispute_resolution_clarity": ["争议解决", "争议处理", "协商不成"],
    "jurisdiction_fairness": ["管辖", "法院", "仲裁"],
    "governing_law_clarity": ["适用法律", "中华人民共和国", "民法典"],
    "force_majeure_completeness": ["不可抗力", "天灾", "战争"],
    # new universal (LEDGAR)
    "cuad_anti_corruption": ["商业贿赂", "反腐败", "行贿", "廉洁", "利益输送"],
    "cuad_signing_authority": ["授权", "有权签署", "法定代表人", "授权代表"],
    "cuad_binding_effect": ["约束力", "法律约束", "生效"],
    "cuad_compliance_with_laws": ["合规", "法律法规", "遵守法律"],
    "cuad_contra_proferentem": ["不利解释", "格式条款", "提供格式条款一方", "加重对方责任", "限制对方主要权利"],
    "cuad_cooperation": ["配合", "协助", "合作"],
    "cuad_disclosure_schedule": ["附件", "披露", "清单", "明细"],
    "cuad_enforceability": ["可执行", "强制执行", "有效"],
    "cuad_further_assurances": ["进一步保证", "补充协议", "必要文件", "签署或促使签署"],
    "cuad_interest_on_late_payment": ["逾期利息", "滞纳金", "延期付款利息", "迟延利息"],
    "cuad_interpretation_rules": ["合同解释", "标题仅供参考", "条款独立性", "解释规则"],
    "cuad_no_waiver": ["不视为放弃", "未行使不构成", "权利保留", "不构成弃权", "未行使权利"],
    "cuad_notice": ["通知", "送达", "书面通知", "联系方式", "地址"],
    "cuad_powers": ["权限", "授权范围", "代理权限"],
    "cuad_publicity": ["宣传", "新闻发布", "公开", "媒体"],
    "cuad_representations_warranties": ["陈述", "保证", "声明与保证", "承诺"],
    "cuad_sanctions": ["制裁", "出口管制", "贸易制裁"],
    "cuad_severability": ["可分割", "部分无效", "条款独立性", "部分条款无效", "不影响其他条款"],
    "cuad_survival": ["继续有效", "存续", "合同终止后", "终止后继续有效"],
    "cuad_taxes": ["税费", "税金", "税务", "增值税", "所得税"],
    "cuad_contract_term": ["合同期限", "有效期", "合同期", "期限"],
    # contract-specific
    "cuad_regulatory_approvals": ["审批", "许可", "备案", "核准", "资质"],
    "cuad_books_records": ["账簿", "记录", "账册", "查阅"],
    "cuad_brokers": ["中介", "居间", "经纪", "代理费"],
    "cuad_third_party_consents": ["第三方同意", "业主同意", "债权人同意"],
    "cuad_forfeiture": ["没收", "丧失", "不予退还", "抵扣", "押金不退", "保证金不退", "定金不退"],
    "cuad_liens": ["留置", "质押", "抵押"],
    "cuad_qualifications": ["资质", "资格", "执业", "持证"],
    "cuad_record_keeping": ["记录保存", "存档", "保管期限"],
    "cuad_solvency": ["偿付能力", "资不抵债", "破产"],
    "cuad_tax_withholding": ["代扣", "代缴", "扣缴"],
    "cuad_use_of_proceeds": ["资金用途", "专款专用", "挪用"],
    "cuad_vesting": ["归属", "成熟", "行权"],
    "cuad_withholding": ["代扣", "预扣", "扣除"],
    "cuad_affiliate_transactions": ["关联方", "关联交易", "子公司"],
    # existing contract-specific
    "risk_transfer_point": ["风险转移", "毁损灭失", "风险承担"],
    "cuad_warranty_duration": ["质保期", "保修期", "质量保证期"],
    "cuad_insurance": ["保险", "投保", "保险公司"],
    "confidentiality_nli": ["保密", "机密", "商业秘密"],
    "cuad_source_code_escrow": ["源代码", "源码", "托管"],
    "cuad_ip_ownership_assignment": ["知识产权", "著作权", "专利权", "商标"],
    "cuad_liquidated_damages": ["违约金", "罚金", "罚款"],
    "cuad_anti_assignment": ["转让", "转租", "不得转让"],
    "cuad_non_compete": ["竞业", "不得从事", "竞争"],
    "cuad_audit_rights": ["审计", "核查", "检查权"],
    "cuad_termination_for_convenience": ["任意终止", "提前终止", "随时解除"],
}

def classify_contract_type(title: str, content: str) -> list[str]:
    """Classify a contract template into one or more contract types."""
    text = (title + " " + (content or "")).lower()
    matched = []
    for ctype, keywords in CONTRACT_TYPE_KW.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score >= 2:  # at least 2 keyword matches
            matched.append(ctype)
    return matched if matched else ["其他"]


def detect_node_signals(text: str) -> dict[str, bool]:
    """Check which BN nodes have keyword signals in the contract text."""
    text_lower = text.lower()
    signals = {}
    for node, keywords in NODE_KEYWORDS.items():
        signals[node] = any(kw.lower() in text_lower for kw in keywords)
    return signals


def main(min_frequency: float = 0.02):
    print(f"Loading templates...")
    ds = load_from_disk(str(PROJECT_ROOT / "dataset" / "chinese_contract_templates"))
    print(f"Loaded {len(ds)} samples\n")

    # ── Pass 1: Classify and count signals ──
    type_node_counts: dict[str, Counter] = defaultdict(Counter)
    type_total: Counter = Counter()

    for sample in ds:
        title = sample.get("title", "")
        content = sample.get("content", "") or ""
        text = title + " " + content
        if len(text) < 50:
            continue

        types = classify_contract_type(title, content)
        signals = detect_node_signals(text)

        for ctype in types:
            type_total[ctype] += 1
            for node, present in signals.items():
                if present:
                    type_node_counts[ctype][node] += 1

    # ── Pass 2: Print coverage report ──
    for ctype in sorted(type_total.keys(), key=lambda t: -type_total[t]):
        total = type_total[ctype]
        if total < 10:
            continue
        print(f"=== {ctype} ({total} samples) ===")

        # Universal nodes with low coverage — candidates for downgrade
        low_cov = []
        # Contract-specific nodes with high coverage — candidates for promotion
        high_cov = []

        for node, count in sorted(type_node_counts[ctype].items()):
            freq = count / total
            if freq >= 0.30:
                marker = "███" if freq >= 0.60 else ("██" if freq >= 0.45 else "█")
                print(f"  {marker} {node}: {freq:.0%} ({count}/{total})")

                # Check if this is a contract-specific node appearing frequently
                # in a type it wasn't assigned to
                # (manual review needed)

        print()

    # ── Pass 3: Flag anomalies ──
    print("=== ANOMALIES ===")
    print()

    # Universal nodes that don't appear in any type
    universal_nodes = [n for n in NODE_KEYWORDS if n.startswith("cuad_")]
    for node in universal_nodes:
        max_freq = max(
            (type_node_counts[ctype].get(node, 0) / max(type_total[ctype], 1))
            for ctype in type_total if type_total[ctype] >= 10
        )
        if max_freq < min_frequency:
            print(f"  LOW: {node} max frequency {max_freq:.1%} across all types")

    # Suggest missing keywords
    for node in ["cuad_contra_proferentem", "cuad_further_assurances", "cuad_no_waiver",
                  "cuad_survival", "cuad_binding_effect", "cuad_enforceability",
                  "cuad_representations_warranties", "cuad_powers", "cuad_interpretation_rules"]:
        max_freq = max(
            (type_node_counts[ctype].get(node, 0) / max(type_total[ctype], 1))
            for ctype in type_total if type_total[ctype] >= 10
        )
        if max_freq < 0.05:
            print(f"  ADD_KEYWORDS: {node} max={max_freq:.1%} — consider adding more Chinese keywords to NODE_KEYWORDS")


if __name__ == "__main__":
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--min-frequency" else 0.02
    main(threshold)
