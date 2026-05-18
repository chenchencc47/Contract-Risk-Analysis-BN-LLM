"""F-1: LEDGAR 100-class taxonomy → BN node mapping."""
import json

mappings = [
    # (ledgar_en, zh_label, status, bn_node_name, contract_scope)
    # status: covered / new_universal / new_contract_specific / not_applicable

    # ── Already covered ──
    ('Adjustments', '价格调整条款', 'covered', 'price_adjustment_mechanism', 'all'),
    ('Agreements', '协议条款', 'covered', 'termination_clause_completeness', 'all'),
    ('Amendments', '合同修改条款', 'covered', 'termination_clause', 'all'),
    ('Applicable Laws', '适用法律条款', 'covered', 'governing_law_clause', 'all'),
    ('Approvals', '审批/验收条款', 'covered', 'acceptance_process_clarity', 'all'),
    ('Arbitration', '仲裁条款', 'covered', 'dispute_resolution_clause', 'all'),
    ('Assignments', '合同转让条款', 'covered', 'cuad_anti_assignment', 'all'),
    ('Assigns', '继受人条款', 'covered', 'cuad_anti_assignment', 'all'),
    ('Change In Control', '控制权变更', 'covered', 'cuad_change_of_control', 'all'),
    ('Closings', '交割/交付条款', 'covered', 'delivery_terms', 'all'),
    ('Confidentiality', '保密条款', 'covered', 'confidentiality_nli', 'all'),
    ('Consent To Jurisdiction', '管辖同意', 'covered', 'jurisdiction_fairness', 'all'),
    ('Costs', '费用承担', 'covered', 'payment_structure', 'all'),
    ('Duties', '义务条款', 'covered', 'termination_clause_completeness', 'all'),
    ('Enforcements', '执行/救济', 'covered', 'cuad_liquidated_damages', 'all'),
    ('Entire Agreements', '完整协议', 'covered', 'termination_clause_completeness', 'all'),
    ('Expenses', '费用条款', 'covered', 'payment_structure', 'all'),
    ('Fees', '服务费/报酬', 'covered', 'payment_structure', 'all'),
    ('Governing Laws', '管辖法律', 'covered', 'governing_law_clause', 'all'),
    ('Indemnifications', '赔偿条款', 'covered', 'damages_exposure', 'all'),
    ('Indemnity', '赔偿保证', 'covered', 'damages_exposure', 'all'),
    ('Insurances', '保险条款', 'covered', 'cuad_insurance', 'all'),
    ('Integration', '合同整合', 'covered', 'termination_clause_completeness', 'all'),
    ('Intellectual Property', '知识产权', 'covered', 'cuad_ip_ownership_assignment', 'all'),
    ('Jurisdictions', '管辖地', 'covered', 'jurisdiction_fairness', 'all'),
    ('Litigations', '诉讼/争议', 'covered', 'dispute_resolution_clause', 'all'),
    ('Modifications', '合同修改', 'covered', 'termination_clause', 'all'),
    ('Non-Disparagement', '不贬损', 'covered', 'cuad_non_disparagement', 'all'),
    ('Payments', '付款条款', 'covered', 'payment_structure', 'all'),
    ('Releases', '免责/解除', 'covered', 'damages_exposure', 'all'),
    ('Remedies', '救济措施', 'covered', 'cuad_liquidated_damages', 'all'),
    ('Sales', '销售条款', 'covered', 'payment_structure', 'all'),
    ('Specific Performance', '强制履行', 'covered', 'cuad_liquidated_damages', 'all'),
    ('Submission To Jurisdiction', '提交管辖', 'covered', 'jurisdiction_fairness', 'all'),
    ('Successors', '继承人/继受人', 'covered', 'cuad_anti_assignment', 'all'),
    ('Terminations', '终止条款', 'covered', 'termination_clause', 'all'),
    ('Venues', '审判地', 'covered', 'dispute_venue_fairness', 'all'),
    ('Waivers', '放弃权利', 'covered', 'cuad_no_waiver', 'all'),
    ('Warranties', '保证/质保', 'covered', 'cuad_warranty_duration', 'all'),

    # ── New universal nodes (should be in universal_core or text_triggers) ──
    ('Anti-Corruption Laws', '反腐败/商业贿赂', 'new_universal', 'cuad_anti_corruption', 'all'),
    ('Authority', '签约授权', 'new_universal', 'cuad_signing_authority', 'all'),
    ('Binding Effects', '合同约束力', 'new_universal', 'cuad_binding_effect', 'all'),
    ('Compliance With Laws', '合规条款', 'new_universal', 'cuad_compliance_with_laws', 'all'),
    ('Construction', '合同解释规则(不利解释原则)', 'new_universal', 'cuad_contra_proferentem', 'all'),
    ('Cooperation', '合作义务', 'new_universal', 'cuad_cooperation', 'all'),
    ('Disclosures', '信息披露/附件', 'new_universal', 'cuad_disclosure_schedule', 'all'),
    ('Enforceability', '可执行性', 'new_universal', 'cuad_enforceability', 'all'),
    ('Further Assurances', '进一步保证', 'new_universal', 'cuad_further_assurances', 'all'),
    ('Interests', '逾期利息', 'new_universal', 'cuad_interest_on_late_payment', 'all'),
    ('Interpretations', '合同解释规则', 'new_universal', 'cuad_interpretation_rules', 'all'),
    ('No Waivers', '不放弃权利', 'new_universal', 'cuad_no_waiver', 'all'),
    ('Notices', '通知条款', 'new_universal', 'cuad_notice', 'all'),
    ('Powers', '授权/权限', 'new_universal', 'cuad_powers', 'all'),
    ('Publicity', '公开宣传/新闻发布', 'new_universal', 'cuad_publicity', 'all'),
    ('Representations', '陈述与保证', 'new_universal', 'cuad_representations_warranties', 'all'),
    ('Sanctions', '制裁/出口管制', 'new_universal', 'cuad_sanctions', 'all'),
    ('Severability', '可分割性', 'new_universal', 'cuad_severability', 'all'),
    ('Survival', '条款存续', 'new_universal', 'cuad_survival', 'all'),
    ('Taxes', '税务条款', 'new_universal', 'cuad_taxes', 'all'),
    ('Terms', '合同期限', 'new_universal', 'cuad_contract_term', 'all'),

    # ── New contract-specific nodes ──
    ('Authorizations', '政府许可/审批', 'new_contract_specific', 'cuad_regulatory_approvals', '采购合同'),
    ('Books', '账簿/记录查阅', 'new_contract_specific', 'cuad_books_records', '租赁合同/服务合同'),
    ('Brokers', '中介/居间', 'new_contract_specific', 'cuad_brokers', '买卖合同'),
    ('Consents', '第三方同意', 'new_contract_specific', 'cuad_third_party_consents', '租赁合同'),
    ('Forfeitures', '没收/丧失权利', 'new_contract_specific', 'cuad_forfeiture', '租赁合同'),
    ('Liens', '留置权', 'new_contract_specific', 'cuad_liens', '采购合同'),
    ('Qualifications', '资格/资质', 'new_contract_specific', 'cuad_qualifications', '服务合同'),
    ('Records', '记录保存', 'new_contract_specific', 'cuad_record_keeping', 'all'),
    ('Solvency', '偿付能力声明', 'new_contract_specific', 'cuad_solvency', '采购合同'),
    ('Tax Withholdings', '税款代扣', 'new_contract_specific', 'cuad_tax_withholding', 'all'),
    ('Transactions With Affiliates', '关联交易', 'new_contract_specific', 'cuad_affiliate_transactions', 'all'),
    ('Use Of Proceeds', '资金用途限制', 'new_contract_specific', 'cuad_use_of_proceeds', '采购合同'),
    ('Vesting', '权利归属/成熟', 'new_contract_specific', 'cuad_vesting', '技术开发合同'),
    ('Withholdings', '代扣代缴', 'new_contract_specific', 'cuad_withholding', 'all'),

    # ── Not applicable (US law specific / employment / boilerplate) ──
    ('Base Salary', '基本薪酬', 'not_applicable', None, None),
    ('Benefits', '员工福利', 'not_applicable', None, None),
    ('Capitalization', '资本结构', 'not_applicable', None, None),
    ('Counterparts', '合同份数声明', 'not_applicable', None, None),
    ('Death', '当事人死亡', 'not_applicable', None, None),
    ('Defined Terms', '定义条款(通用)', 'not_applicable', None, None),
    ('Definitions', '定义条款(通用)', 'not_applicable', None, None),
    ('Disability', '残疾条款', 'not_applicable', None, None),
    ('Effective Dates', '生效日期', 'not_applicable', None, None),
    ('Effectiveness', '生效条件', 'not_applicable', None, None),
    ('Employment', '雇佣条款', 'not_applicable', None, None),
    ('Erisa', '美国雇员退休金(ERISA)', 'not_applicable', None, None),
    ('Existence', '公司存续声明', 'not_applicable', None, None),
    ('Financial Statements', '财务报表', 'not_applicable', None, None),
    ('General', '一般条款(泛称)', 'not_applicable', None, None),
    ('Headings', '章节标题', 'not_applicable', None, None),
    ('Miscellaneous', '杂项条款', 'not_applicable', None, None),
    ('No Conflicts', '无冲突声明', 'not_applicable', None, None),
    ('No Defaults', '无违约声明', 'not_applicable', None, None),
    ('Organizations', '公司组织', 'not_applicable', None, None),
    ('Participations', '参与权', 'not_applicable', None, None),
    ('Positions', '职位条款', 'not_applicable', None, None),
    ('Subsidiaries', '子公司', 'not_applicable', None, None),
    ('Titles', '职位/头衔', 'not_applicable', None, None),
    ('Vacations', '休假条款', 'not_applicable', None, None),
    ('Waiver Of Jury Trials', '放弃陪审团审判(美国特有)', 'not_applicable', None, None),
]

covered = sum(1 for m in mappings if m[2] == 'covered')
new_u = sum(1 for m in mappings if m[2] == 'new_universal')
new_cs = sum(1 for m in mappings if m[2] == 'new_contract_specific')
not_app = sum(1 for m in mappings if m[2] == 'not_applicable')

print(f'LEDGAR 100 classes → BN mapping:')
print(f'  Already covered:      {covered}')
print(f'  New universal:         {new_u}')
print(f'  New contract-specific: {new_cs}')
print(f'  Not applicable:        {not_app}')
print(f'  Total:                 {len(mappings)}')
print()
print('=== NEW UNIVERSAL NODES ({}) ==='.format(new_u))
for m in mappings:
    if m[2] == 'new_universal':
        print(f'  {m[3]}: {m[1]} (LEDGAR: {m[0]})')
print()
print('=== NEW CONTRACT-SPECIFIC NODES ({}) ==='.format(new_cs))
for m in mappings:
    if m[2] == 'new_contract_specific':
        print(f'  {m[3]}: {m[1]} → {m[4]} (LEDGAR: {m[0]})')

# Verify against existing BN node names
with open('config/bayesian_network_v2.json', encoding='utf-8') as f:
    bn = json.load(f)
existing = set(bn['nodes'])

# Check new nodes don't collide
new_nodes = [m[3] for m in mappings if m[2] in ('new_universal', 'new_contract_specific')]
collisions = [n for n in new_nodes if n in existing]
if collisions:
    print(f'\nWARNING: {len(collisions)} new node names collide with existing: {collisions}')
else:
    print(f'\nNo name collisions — all {len(new_nodes)} new nodes are safe to add')
