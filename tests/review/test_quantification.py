from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, RiskSegment
from contract_risk_analysis.review.quantification import build_quantitative_context


def test_build_quantitative_context_extracts_contract_amount_and_payment_anchor() -> None:
    contract_text = (
        "合同总价为人民币1535万元。"
        "甲方于合同签订后10日内支付合同金额的80%作为预付款。"
    )
    free_output = FreeReviewOutput(
        contract_id="sales-001",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高，造成重大资金敞口。",
                evidence_text="甲方于合同签订后10日内支付合同金额的80%作为预付款。",
                confidence=0.95,
                severity="high",
                canonical_type="payment_structure",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    ctx = build_quantitative_context(contract_text, free_output)

    assert ctx.contract_amount == 15_350_000
    assert ctx.quantification_allowed is True
    assert ctx.payment_anchors[0].percentage == 80
    assert ctx.payment_anchors[0].amount == 12_280_000
    assert "每降低10个百分点≈人民币1,535,000元" in ctx.exchange_rate_hints


def test_build_quantitative_context_refuses_money_quantification_without_total_price() -> None:
    contract_text = "甲方于合同签订后10日内支付合同金额的80%作为预付款。"
    free_output = FreeReviewOutput(
        contract_id="sales-002",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高。",
                evidence_text="甲方于合同签订后10日内支付合同金额的80%作为预付款。",
                confidence=0.90,
                severity="high",
                canonical_type="payment_structure",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    ctx = build_quantitative_context(contract_text, free_output)

    assert ctx.contract_amount is None
    assert ctx.quantification_allowed is False
    assert ctx.payment_anchors[0].percentage == 80
    assert ctx.payment_anchors[0].amount is None
    assert "缺少合同总价，禁止把百分比换算成金额" in ctx.warnings


def test_build_quantitative_context_extracts_table_style_total_price() -> None:
    contract_text = (
        "货物名称：终端设备。单价153,500元，数量100台，总价15,350,000元。"
        "甲方于本合同签订后10日内支付合同金额的80%作为预付款。"
    )
    free_output = FreeReviewOutput(
        contract_id="sales-003",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高。",
                evidence_text="甲方于本合同签订后10日内支付合同金额的80%作为预付款。",
                confidence=0.95,
                severity="high",
                canonical_type="payment_structure",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    ctx = build_quantitative_context(contract_text, free_output)

    assert ctx.contract_amount == 15_350_000
    assert ctx.payment_anchors[0].amount == 12_280_000



def test_build_quantitative_context_extracts_spaced_total_price() -> None:
    contract_text = (
        "合同货物总价 人民币 15,350,000 元。"
        "甲方于本合同签订后10日内支付合同金额的80%作为预付款。"
    )
    free_output = FreeReviewOutput(
        contract_id="sales-004",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高。",
                evidence_text="甲方于本合同签订后10日内支付合同金额的80%作为预付款。",
                confidence=0.95,
                severity="high",
                canonical_type="payment_structure",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    ctx = build_quantitative_context(contract_text, free_output)

    assert ctx.contract_amount == 15_350_000


def test_build_quantitative_context_extracts_ocr_spaced_total_price_and_payment_anchor() -> None:
    contract_text = (
        "1. 合 同 的 总 金 额 为 人 民 币 : ¥_15350000.00 _ 元。"
        "2. 甲 方 于 本 合 同 签 订 后 _10 日 内 向 乙 方 支 付 合 同 金 额 的 _80 %"
        "作 为 预 付 款 , 即 人 民 币 : ¥_12280000 _ 元。"
    )
    free_output = FreeReviewOutput(
        contract_id="sales-005",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高且无担保",
                risk_description="预付款比例过高，造成重大资金敞口。",
                evidence_text="甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款，即人民币：¥12280000元。",
                confidence=0.95,
                severity="high",
                canonical_type="payment",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    ctx = build_quantitative_context(contract_text, free_output)

    assert ctx.contract_amount == 15_350_000
    assert ctx.amount_source_text == "总金额为人民币:¥15350000.00元"
    assert ctx.payment_anchors[0].percentage == 80
    assert ctx.payment_anchors[0].amount == 12_280_000
