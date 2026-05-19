from contract_risk_analysis.bn.bn_mapping import BnMappingService, _load_clause_type_hints
from contract_risk_analysis.bn.pgmpy_adapter import load_v2_config
from contract_risk_analysis.domain.free_review_schema import RiskSegment


def test_load_clause_type_hints_reads_yaml_config() -> None:
    hints = _load_clause_type_hints()

    assert hints["付款"] == ["payment_structure"]
    assert hints["热值"] == ["calorific_value_pricing"]


def test_bn_mapping_service_loads_clause_type_hints_on_init(monkeypatch) -> None:
    import contract_risk_analysis.bn.bn_mapping as bn_mapping

    monkeypatch.setattr(
        bn_mapping,
        "_load_clause_type_hints",
        lambda: {"自定义条款": ["payment_structure"]},
    )

    service = BnMappingService(
        mapping_config={"finding_key_rules": {}},
        v2_config=load_v2_config(),
    )
    segment = RiskSegment(
        clause_type="自定义条款",
        risk_title="自定义风险",
        risk_description="测试 YAML 在 service 初始化时加载。",
        evidence_text="测试证据",
        confidence=0.9,
        severity="high",
    )

    node_name, mapped_state = service._resolve_node_state(segment)

    assert node_name == "payment_structure"
    assert mapped_state is not None


def test_bn_mapping_service_preserves_representative_clause_type_mappings() -> None:
    service = BnMappingService(
        mapping_config={"finding_key_rules": {}},
        v2_config=load_v2_config(),
    )

    cases = [
        ("付款", "high", "payment_structure"),
        ("责任上限", "high", "liability_cap_strength"),
        ("交付", "medium", "delivery_terms"),
        ("热值", "high", "calorific_value_pricing"),
        ("原料验收", "medium", "raw_material_acceptance_std"),
        ("争议解决", "high", "dispute_resolution_clarity"),
        ("质保", "medium", "cuad_warranty_duration"),
    ]

    for clause_type, severity, expected_node in cases:
        segment = RiskSegment(
            clause_type=clause_type,
            risk_title=f"{clause_type}测试",
            risk_description="回归验证",
            evidence_text="测试证据",
            confidence=0.9,
            severity=severity,
        )
        node_name, mapped_state = service._resolve_node_state(segment)
        assert node_name == expected_node
        assert mapped_state is not None
