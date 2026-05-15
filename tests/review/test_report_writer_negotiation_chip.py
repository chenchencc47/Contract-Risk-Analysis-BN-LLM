from contract_risk_analysis.domain.free_review_schema import (
    DossierRiskItem,
    FreeReviewOutput,
    NegotiationChip,
    QuantitativeContext,
    RiskSegment,
)
from contract_risk_analysis.review.report_writer import (
    _build_combined_prompt,
    _build_dossier,
    _fmt_dossier_section,
    _fmt_llm_analysis,
)


def test_positive_item_maps_structured_chip_to_favorable_term() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="liability_cap",
                risk_title="无责任上限",
                risk_description="对买方是核心优势",
                evidence_text="责任上限未约定",
                confidence=0.95,
                severity="positive",
                recommendation="对买方是核心优势",
                negotiation_chip=NegotiationChip(
                    chip_type="响应筹码",
                    reason="对买方是核心优势",
                ),
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    dossier = _build_dossier(free_output, None, "buyer")

    assert len(dossier.favorable_terms) == 1
    assert dossier.favorable_terms[0].chip_type == "响应筹码"
    assert dossier.favorable_terms[0].review_stance == "buyer"
    assert dossier.favorable_terms[0].legal_direction == "favorable"
    assert dossier.favorable_terms[0].negotiation_role == "respond"


def test_formatters_render_structured_chip_fields_not_object_repr() -> None:
    chip = NegotiationChip(
        chip_type="交换筹码",
        reason="对方极度想保留该安排",
        strategy="可作为换取付款节点后移的交换条件",
    )
    dossier_item = DossierRiskItem(
        issue_id="ISSUE-test-001",
        risk_title="预付款比例过高",
        clause_type="payment_structure",
        severity="high",
        priority_rank=2,
        evidence_text="预付款90%",
        confidence=0.9,
        negotiation_chip=chip,
    )

    dossier_text = _fmt_dossier_section(
        type("StubDossier", (), {
            "contract_id": "test-contract",
            "review_party": "buyer",
            "risk_items": [dossier_item],
            "favorable_terms": [],
            "counterfactuals": [],
            "manual_review_items": [],
            "internal_conflicts": [],
            "overall_assessment": "overall",
            "bn_annotations": [],
            "joint_risks": [],
            "signing_forbidden": [],
            "signing_acceptable": [],
            "negotiation_bottom_lines": [],
            "strengths": [],
            "missing_clauses": [],
        })()
    )

    llm_text = _fmt_llm_analysis(
        FreeReviewOutput(
            contract_id="test-contract",
            overall_assessment="overall",
            risk_segments=[
                RiskSegment(
                    clause_type="payment_structure",
                    risk_title="预付款比例过高",
                    risk_description="该比例导致现金流压力过大",
                    evidence_text="预付款90%",
                    confidence=0.9,
                    severity="high",
                    negotiation_chip=chip,
                )
            ],
            missing_clauses=[],
            strengths=[],
        )
    )

    assert "| ISSUE-test-001 | 预付款比例过高 | payment_structure | — | — | 🟠高 | P2 | — | 否 |" in dossier_text
    assert "- 法律方向：unknown（已冻结，不得自行反向推断）" in dossier_text
    assert "- 谈判角色：monitor（已冻结，渲染时必须遵守）" in dossier_text
    assert "筹码类型：交换筹码" in dossier_text
    assert "筹码理由：对方极度想保留该安排" in dossier_text
    assert "筹码策略：可作为换取付款节点后移的交换条件" in dossier_text
    assert "NegotiationChip(" not in dossier_text

    assert "筹码分析：交换筹码" in llm_text
    assert "理由：对方极度想保留该安排" in llm_text
    assert "策略：可作为换取付款节点后移的交换条件" in llm_text
    assert "NegotiationChip(" not in llm_text


def test_dossier_risk_item_gets_legal_direction_fields() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="对买方不利",
                evidence_text="合同签订后支付50%首付款",
                confidence=0.91,
                severity="high",
                canonical_type="payment_structure",
                counterparty_impact="buyer_unfavorable",
                negotiation_chip=NegotiationChip(chip_type="底线筹码"),
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    dossier = _build_dossier(free_output, None, "buyer")

    assert len(dossier.risk_items) == 1
    item = dossier.risk_items[0]
    assert item.affected_party == "review_party"
    assert item.review_stance == "buyer"
    assert item.legal_direction == "unfavorable"
    assert item.negotiation_role == "must_fix"


def test_defensive_chip_consistency_uses_chip_type_field() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="jurisdiction",
                risk_title="争议管辖在买方住所地",
                risk_description="对买方有利",
                evidence_text="争议由买方所在地法院管辖",
                confidence=0.88,
                severity="high",
                priority_rank=1,
                recommendation="保留现有约定",
                negotiation_chip=NegotiationChip(
                    chip_type="底线筹码",
                    reason="这是核心程序优势",
                ),
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    dossier = _build_dossier(free_output, None, "buyer")

    assert len(dossier.manual_review_items) == 1
    assert any("筹码分类为「底线筹码」" in msg for msg in dossier.internal_conflicts)


def test_build_dossier_preserves_quantitative_context() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    quantitative_context = QuantitativeContext(
        contract_amount=15_350_000,
        amount_source_text="合同总价为人民币1535万元",
        quantification_allowed=True,
        exchange_rate_hints=["每降低10个百分点≈人民币1,535,000元"],
    )

    dossier = _build_dossier(
        free_output,
        None,
        "buyer",
        quantitative_context=quantitative_context,
    )

    assert dossier.quantitative_context is not None
    assert dossier.quantitative_context.contract_amount == 15_350_000
    assert dossier.quantitative_context.exchange_rate_hints == [
        "每降低10个百分点≈人民币1,535,000元"
    ]


def test_dossier_section_renders_quantitative_context() -> None:
    quantitative_context = QuantitativeContext(
        contract_amount=15_350_000,
        amount_source_text="合同总价为人民币1535万元",
        quantification_allowed=True,
        exchange_rate_hints=["每降低10个百分点≈人民币1,535,000元"],
    )
    dossier_text = _fmt_dossier_section(
        type("StubDossier", (), {
            "contract_id": "test-contract",
            "review_party": "buyer",
            "risk_items": [],
            "favorable_terms": [],
            "counterfactuals": [],
            "manual_review_items": [],
            "internal_conflicts": [],
            "overall_assessment": "overall",
            "bn_annotations": [],
            "joint_risks": [],
            "signing_forbidden": [],
            "signing_acceptable": [],
            "negotiation_bottom_lines": [],
            "strengths": [],
            "missing_clauses": [],
            "quantitative_context": quantitative_context,
        })()
    )

    assert "### 定量锚点（系统确定性抽取——第三/四/五章涉及金额时必须遵守）" in dossier_text
    assert "- 合同总价：人民币15,350,000元（来源：合同总价为人民币1535万元）" in dossier_text
    assert "- 金额换算许可：是" in dossier_text
    assert "每降低10个百分点≈人民币1,535,000元" in dossier_text


def test_combined_prompt_forbids_amount_conversion_without_total_price() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    quantitative_context = QuantitativeContext(
        contract_amount=None,
        quantification_allowed=False,
        warnings=["缺少合同总价，禁止把百分比换算成金额"],
    )
    dossier = _build_dossier(
        free_output,
        None,
        "buyer",
        quantitative_context=quantitative_context,
    )

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "金额换算许可：否" in prompt
    assert "缺少合同总价，禁止把百分比换算成金额" in prompt
    assert "第三/四/五章只允许写百分比/天数，不得补写任何金额" in prompt
    assert "合同总价未识别，暂不进行金额换算" in prompt



def test_combined_prompt_keeps_internal_renderer_notes_out_of_customer_required_sections() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    dossier = _build_dossier(free_output, None, "buyer")

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "## 渲染器备注（强制执行，不可跳过）" not in prompt
    assert "客户版报告不得暴露内部编号、渲染器问责或系统自检过程" in prompt


def test_combined_prompt_includes_report_17_consistency_repairs() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    dossier = _build_dossier(free_output, None, "buyer")

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "每个攻击方向的小标题必须直接概括其后正文真正攻击的对象和诉求" in prompt
    assert "禁止复用其他报告里的固定攻击标签" in prompt
    assert "如果正文主要攻击管辖、责任上限、验收或付款结构，标题必须如实反映该对象" in prompt
    assert "如果第六章对某付款/风险条款设置了“在缺少某项保护条件时不得超过X%/不得接受某节点”的签署底线" in prompt
    assert "必须同步写明使该退让成立的保护前提" in prompt
    assert "按本合同实际数字/节点填写" in prompt
    assert "更低比例、更晚风险转移、更强担保或更明确标准" in prompt
    assert "所有BN百分比都表示高风险概率改善幅度或比较结果" in prompt
    assert "直接金钱估值、收益金额或可兑现对价" in prompt
    assert "必须写成“主问题+补充子问题”的层次结构" in prompt


def test_combined_prompt_includes_non_hardcoding_guardrails() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    dossier = _build_dossier(free_output, None, "buyer")

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "禁止把某一份合同中的固定比例、固定金额、固定期限、固定城市或固定行业惯例写成通用答案" in prompt
    assert "所有具体数字、期限、金额、地点、节点都只能按本合同实际数字/节点填写" in prompt
    assert "不得照搬其他报告中的现成退让阶梯、三板斧标签或固定攻击标题" in prompt
    assert "客户版不得出现 ISSUE-、渲染器备注、内部一致性警告、TODO、TBD" in prompt


def test_consistency_checks_flag_external_eval_mentions_in_customer_text() -> None:
    from contract_risk_analysis.domain.free_review_schema import ReportDossier
    from contract_risk_analysis.review.report_writer import _run_pre_render_consistency_checks

    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="参考 DeepSeek 评价，本合同风险偏高。",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        favorable_terms=[],
        manual_review_items=[],
        internal_conflicts=[],
    )

    violations = _run_pre_render_consistency_checks(dossier)
    assert any("外部评价" in msg for msg in violations)


def test_consistency_checks_flag_freeform_numeric_estimates() -> None:
    from contract_risk_analysis.domain.free_review_schema import ReportDossier
    from contract_risk_analysis.review.report_writer import _run_pre_render_consistency_checks

    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="追回预付款的诉讼成本约20-50万元，成功回收率低于60%。",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        favorable_terms=[],
        manual_review_items=[],
        internal_conflicts=[],
    )

    violations = _run_pre_render_consistency_checks(dossier)
    assert any("无来源数字" in msg for msg in violations)


def test_combined_prompt_includes_chapter_4_terminology_ban() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    dossier = _build_dossier(free_output, None, "buyer")

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "第四章用语规范" in prompt
    assert "P(high)" in prompt  # the banned term must appear in the ban table
    assert "高风险概率" in prompt  # the replacement must appear
    assert "条款改善效果预估" in prompt
    assert "风险改善量化评估" in prompt
    assert "法律分析判断" in prompt


def test_combined_prompt_includes_signing_guardrail_number_discipline() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    dossier = _build_dossier(free_output, None, "buyer")

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "签署底线数字纪律（强制执行）" in prompt
    assert "严禁" in prompt
    assert "自行补写 Dossier 中未出现的具体数字" in prompt
    assert "方向+条件的形式" in prompt
    assert "每一段攻击话术必须至少引用当前合同的一个具体条款号和一个本合同独有的百分比或金额" in prompt
    assert "第五章数字自检" in prompt
