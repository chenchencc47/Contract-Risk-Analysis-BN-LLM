from contract_risk_analysis.pipeline.node_schema import load_node_schema, load_priority_nodes


def test_load_node_schema_returns_nodes() -> None:
    schema = load_node_schema()

    assert "nodes" in schema
    assert schema["nodes"]


def test_load_priority_nodes_returns_p0_nodes() -> None:
    p0_nodes = load_priority_nodes("P0")

    assert "termination_clause_existence" in p0_nodes
    assert "overall_contract_risk" in p0_nodes
    assert "termination_clause" in p0_nodes
