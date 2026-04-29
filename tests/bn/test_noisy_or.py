from contract_risk_analysis.bn.noisy_or import (
    _risk_level_score,
    generate_noisy_max_cpt,
    compute_default_dimension_weights,
    validate_cpt,
)


def test_risk_level_score_handles_binary_states() -> None:
    assert _risk_level_score("present") == 0.0
    assert _risk_level_score("missing") == 1.0
    assert _risk_level_score("balanced") == 0.0
    assert _risk_level_score("counterparty_favorable") == 1.0


def test_risk_level_score_handles_risk_levels() -> None:
    assert _risk_level_score("low") == 0.0
    assert _risk_level_score("medium") == 0.5
    assert _risk_level_score("high") == 1.0


def test_risk_level_score_handles_unknown() -> None:
    assert _risk_level_score("unknown") == 0.5
    assert _risk_level_score("ambiguous") == 0.5


def test_generate_noisy_max_cpt_all_low() -> None:
    weights = {"a": 0.5, "b": 0.5}
    states = {"a": ["low", "high"], "b": ["low", "high"]}
    cpt = generate_noisy_max_cpt(weights, states)
    # All low -> should score 0 -> low risk
    entry = cpt["low|low"]
    assert entry["low"] > entry["high"]
    assert entry["low"] > entry["medium"]


def test_generate_noisy_max_cpt_all_high() -> None:
    weights = {"a": 0.5, "b": 0.5}
    states = {"a": ["low", "high"], "b": ["low", "high"]}
    cpt = generate_noisy_max_cpt(weights, states)
    entry = cpt["high|high"]
    assert entry["high"] > entry["low"]
    assert entry["high"] > entry["medium"]


def test_generate_noisy_max_cpt_returns_correct_count() -> None:
    weights = {"x": 0.5, "y": 0.3, "z": 0.2}
    states = {"x": ["low", "medium", "high"], "y": ["low", "medium", "high"], "z": ["low", "medium", "high"]}
    cpt = generate_noisy_max_cpt(weights, states)
    assert len(cpt) == 27  # 3^3


def test_generate_noisy_max_cpt_with_binary_parents() -> None:
    weights = {"semantic_node": 0.6, "risk_dim": 0.4}
    states = {
        "semantic_node": ["present", "missing"],
        "risk_dim": ["low", "medium", "high"],
    }
    cpt = generate_noisy_max_cpt(weights, states)
    assert len(cpt) == 6  # 2 * 3
    # missing + high -> score = (0.6*1.0 + 0.4*1.0) / 1.0 = 1.0 -> high risk
    entry = cpt["missing|high"]
    assert entry["high"] > 0.5


def test_default_dimension_weights_sum() -> None:
    weights = compute_default_dimension_weights()
    assert abs(sum(weights.values()) - 1.0) < 0.01


def test_validate_cpt_passes_for_valid_cpt() -> None:
    weights = {"a": 0.5, "b": 0.5}
    states = {"a": ["low", "high"], "b": ["low", "high"]}
    cpt = generate_noisy_max_cpt(weights, states)
    issues = validate_cpt(cpt, 4)
    assert len(issues) == 0


def test_validate_cpt_detects_row_count_mismatch() -> None:
    weights = {"a": 0.5, "b": 0.5}
    states = {"a": ["low", "high"], "b": ["low", "high"]}
    cpt = generate_noisy_max_cpt(weights, states)
    issues = validate_cpt(cpt, 3)
    assert len(issues) > 0
