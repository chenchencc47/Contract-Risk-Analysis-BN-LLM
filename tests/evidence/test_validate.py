from contract_risk_analysis.evidence.validate import (
    assess_evidence_quality,
    resolve_effective_state,
)
from contract_risk_analysis.review.verification import should_verify


def test_good_evidence_passes_all_checks() -> None:
    eq = assess_evidence_quality(
        finding_key="termination_clause_present",
        clause_type="termination",
        status="present",
        evidence_text="乙方逾期交货超过15日，甲方有权解除合同并要求乙方退还已付款项及支付合同总额10%的违约金",
        raw_confidence=0.95,
    )
    assert eq.is_quality_ok
    assert eq.adjusted_confidence == 0.95


def test_empty_evidence_with_present_is_flagged() -> None:
    eq = assess_evidence_quality(
        finding_key="liability_cap_present",
        clause_type="liability_cap",
        status="present",
        evidence_text="",
        raw_confidence=0.9,
    )
    assert not eq.is_quality_ok
    assert eq.adjusted_confidence < 0.5
    assert eq.should_be_unknown


def test_missing_status_with_explanation_is_allowed() -> None:
    eq = assess_evidence_quality(
        finding_key="termination_clause_missing",
        clause_type="termination",
        status="missing",
        evidence_text="未发现明确终止条款",
        raw_confidence=0.93,
    )
    assert eq.is_quality_ok
    assert resolve_effective_state("missing", eq) == "missing"


def test_generic_text_is_flagged() -> None:
    eq = assess_evidence_quality(
        finding_key="dispute_resolution_present",
        clause_type="dispute_resolution",
        status="present",
        evidence_text="该合同存在争议解决条款，约定了仲裁和诉讼相关事项",
        raw_confidence=0.88,
    )
    assert not eq.is_quality_ok
    assert "LLM生成" in "".join(eq.flags) or eq.adjusted_confidence < 0.6


def test_resolve_effective_state_returns_unknown_for_low_confidence() -> None:
    eq = assess_evidence_quality(
        finding_key="governing_law_present",
        clause_type="governing_law",
        status="present",
        evidence_text="",
        raw_confidence=0.3,
    )
    assert resolve_effective_state("present", eq) == "unknown"


def test_resolve_effective_state_preserves_present() -> None:
    eq = assess_evidence_quality(
        finding_key="termination_clause_present",
        clause_type="termination",
        status="present",
        evidence_text="甲方有权在乙方逾期超过15日时解除本合同",
        raw_confidence=0.97,
    )
    assert resolve_effective_state("present", eq) == "present"


def test_should_verify_triggers_for_low_quality() -> None:
    eq = assess_evidence_quality(
        finding_key="test",
        clause_type="termination",
        status="present",
        evidence_text="",
        raw_confidence=0.9,
    )
    assert should_verify(eq)


def test_should_verify_skips_good_quality() -> None:
    eq = assess_evidence_quality(
        finding_key="test",
        clause_type="termination",
        status="present",
        evidence_text="甲方有权在乙方逾期超过15日时解除本合同并要求退还已付款项",
        raw_confidence=0.95,
    )
    assert not should_verify(eq)
