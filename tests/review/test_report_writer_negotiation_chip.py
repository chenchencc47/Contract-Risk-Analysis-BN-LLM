from contract_risk_analysis.domain.free_review_schema import (
    DossierRiskItem,
    FreeReviewOutput,
    NegotiationChip,
    RiskSegment,
)
from contract_risk_analysis.review.report_writer import (
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

    assert "筹码类型：交换筹码" in dossier_text
    assert "筹码理由：对方极度想保留该安排" in dossier_text
    assert "筹码策略：可作为换取付款节点后移的交换条件" in dossier_text
    assert "NegotiationChip(" not in dossier_text

    assert "筹码分析：交换筹码" in llm_text
    assert "理由：对方极度想保留该安排" in llm_text
    assert "策略：可作为换取付款节点后移的交换条件" in llm_text
    assert "NegotiationChip(" not in llm_text


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
