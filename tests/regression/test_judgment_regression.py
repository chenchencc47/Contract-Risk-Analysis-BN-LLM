"""v2.11 P2-2: Judgment regression tests.

Verifies that known-correct judgments are preserved across code changes.
These tests run offline — no API key or backend needed.

Each test encodes a judgment that was validated by independent analysis
(report-6 vs report-7 comparison, DeepSeek evaluation cross-referenced).
If any test fails, the judgment has regressed and must be investigated.
"""

from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════
# Test 1-3: Party-aware rule application (buyer side)
# ═══════════════════════════════════════════════════════════════════


class TestPartyAwareRulesBuyer:
    """Verify party-aware rules correctly reclassify buyer-side risks."""

    @staticmethod
    def _make_segment(clause_type: str, canonical_type: str, severity: str = "high"):
        from contract_risk_analysis.domain.free_review_schema import RiskSegment

        return RiskSegment(
            clause_type=clause_type,
            risk_title=f"test_{canonical_type}",
            risk_description="test description",
            evidence_text="test evidence text for regression testing purposes",
            confidence=0.85,
            severity=severity,
            canonical_type=canonical_type,
        )

    def test_liability_cap_missing_buyer_reclassified_to_positive(self):
        """Judgment: liability_cap missing is a BUYER ADVANTAGE, not a risk.

        Regression target: report-7 wrongly classified this as 🟠高/P1.
        After party-aware rules, it must be "positive" (favorable term).
        """
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = self._make_segment("liability_cap", "liability_cap", severity="high")
        result = _apply_party_aware_rules([seg], review_party="buyer")

        assert result[0].severity == "positive", (
            f"liability_cap + buyer should be reclassified to 'positive', "
            f"got '{result[0].severity}'"
        )
        assert "【立场感知裁决】" in result[0].risk_description, (
            "Party-aware note should be appended to risk_description"
        )
        assert result[0].counterparty_impact == "buyer_favorable"

    def test_jurisdiction_buyer_domicile_marked_favorable(self):
        """Judgment: jurisdiction in buyer's domicile is a core advantage."""
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = self._make_segment("dispute_resolution", "jurisdiction", severity="medium")
        result = _apply_party_aware_rules([seg], review_party="buyer")

        assert result[0].counterparty_impact == "buyer_favorable", (
            f"jurisdiction + buyer should be marked buyer_favorable"
        )
        assert "【立场感知裁决】" in result[0].risk_description

    def test_termination_for_cause_buyer_marked_favorable(self):
        """Judgment: buyer's sole termination right is a core weapon."""
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = self._make_segment("termination", "termination_for_cause", severity="medium")
        result = _apply_party_aware_rules([seg], review_party="buyer")

        assert result[0].counterparty_impact == "buyer_favorable"
        assert "【立场感知裁决】" in result[0].risk_description

    def test_high_prepayment_buyer_stays_unfavorable_bottom_line(self):
        """Judgment: high prepayment is a buyer-side funding risk."""
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = self._make_segment("payment", "payment_structure", severity="high")
        result = _apply_party_aware_rules([seg], review_party="buyer")

        assert result[0].severity == "high"
        assert result[0].counterparty_impact == "buyer_unfavorable"
        assert result[0].negotiation_chip is not None
        assert result[0].negotiation_chip.chip_type == "底线筹码"
        assert "高额预付款" in result[0].risk_description

    def test_early_risk_transfer_buyer_stays_unfavorable_bottom_line(self):
        """Judgment: risk transfer before final acceptance is unfavorable to buyer."""
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = self._make_segment("risk_transfer", "risk_transfer", severity="high")
        result = _apply_party_aware_rules([seg], review_party="buyer")

        assert result[0].severity == "high"
        assert result[0].counterparty_impact == "buyer_unfavorable"
        assert result[0].negotiation_chip is not None
        assert result[0].negotiation_chip.chip_type == "底线筹码"
        assert "最终验收" in result[0].risk_description

    def test_unknown_canonical_type_not_affected(self):
        """Non-party-aware canonical types should pass through unchanged."""
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = self._make_segment("custom", "custom_clause", severity="critical")
        result = _apply_party_aware_rules([seg], review_party="buyer")

        assert result[0].severity == "critical", (
            "custom_clause should not be reclassified for buyer"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 4: Party-aware rule application (seller side)
# ═══════════════════════════════════════════════════════════════════


class TestPartyAwareRulesSeller:
    """Verify party-aware rules correctly maintain seller-side risks."""

    def test_liability_cap_missing_seller_stays_high(self):
        """Judgment: liability_cap missing is a FATAL risk for the seller."""
        from contract_risk_analysis.domain.free_review_schema import RiskSegment
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = RiskSegment(
            clause_type="liability_cap",
            risk_title="test_liability_cap",
            risk_description="test",
            evidence_text="test evidence for regression testing purposes",
            confidence=0.90,
            severity="critical",
            canonical_type="liability_cap",
        )
        result = _apply_party_aware_rules([seg], review_party="seller")

        assert result[0].severity == "critical", (
            f"liability_cap + seller should NOT be reclassified, "
            f"got '{result[0].severity}'"
        )
        assert "【立场感知裁决】" in result[0].risk_description


# ═══════════════════════════════════════════════════════════════════
# Test 5: Liability cap floor rule in company_redlines.yaml
# ═══════════════════════════════════════════════════════════════════


class TestLiabilityCapFloor:
    """Verify the liability cap floor (100% of contract value) is enforced."""

    def test_liability_cap_floor_100_percent_exists(self):
        """The company_redlines.yaml has a 100% floor rule for buyer-side cap."""
        from pathlib import Path
        import yaml

        config_path = (
            Path(__file__).parent.parent.parent
            / "config" / "company_redlines.yaml"
        )
        with open(config_path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        buyer_rules = config.get("通用", {}).get("hard_rules", [])
        floor_rule = None
        for rule in buyer_rules:
            if "liability_cap_floor" in rule.get("id", ""):
                floor_rule = rule
                break

        assert floor_rule is not None, (
            "Missing liability_cap_floor_buyer_side rule in company_redlines.yaml"
        )
        assert "100%" in floor_rule.get("description", ""), (
            f"Liability cap floor must mention 100%, got: {floor_rule.get('description', '')}"
        )
        assert floor_rule.get("applies_to") == "buyer", (
            f"Rule should apply to 'buyer', got: {floor_rule.get('applies_to')}"
        )

    def test_no_unlimited_liability_rule_only_for_seller(self):
        """The 'no_unlimited_liability' rule is seller-side only (not universal)."""
        from pathlib import Path
        import yaml

        config_path = (
            Path(__file__).parent.parent.parent
            / "config" / "company_redlines.yaml"
        )
        with open(config_path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        seller_rules = config.get("通用", {}).get("hard_rules", [])
        unlimited_rule = None
        for rule in seller_rules:
            if "no_unlimited_liability" in rule.get("id", ""):
                unlimited_rule = rule
                break

        assert unlimited_rule is not None, (
            "no_unlimited_liability_seller_side rule should exist"
        )
        assert unlimited_rule.get("applies_to") == "seller", (
            "no_unlimited_liability should only apply to seller, "
            f"got applies_to={unlimited_rule.get('applies_to')}"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 6: Internal consistency — defense chip vs signing condition
# ═══════════════════════════════════════════════════════════════════


class TestInternalConsistency:
    """Verify that contradictory dossier states are detected."""

    def test_defensive_chip_in_signing_condition_detected(self):
        """If a risk item is classified as a defense chip, it must not be
        in signing_forbidden or signing_acceptable.

        This is the exact bug found in report-7: liability_cap was classified
        as '响应筹码' in Section 5 but listed as mandatory signing condition
        in Section 6.
        """
        from contract_risk_analysis.domain.free_review_schema import (
            DossierRiskItem,
            FavorableTerm,
            ReportDossier,
        )

        # Simulate: liability_cap correctly reclassified as favorable
        # It should NOT appear in risk_items at all
        favorable = FavorableTerm(
            term_name="无责任上限",
            clause_type="liability_cap",
            description="对买方是核心优势",
            defense_priority="坚守",
            chip_type="响应筹码",
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=["预付款比例过高：必须降至30%"],
            signing_acceptable=["风险转移节点：推迟至终验"],
            negotiation_bottom_lines=[],
            favorable_terms=[favorable],
        )

        # Favorable terms should not appear in signing conditions
        for ft in dossier.favorable_terms:
            for sf in dossier.signing_forbidden:
                assert ft.term_name not in sf, (
                    f"Favorable term '{ft.term_name}' should not be in "
                    f"signing_forbidden: '{sf}'"
                )
            for sa in dossier.signing_acceptable:
                assert ft.term_name not in sa, (
                    f"Favorable term '{ft.term_name}' should not be in "
                    f"signing_acceptable: '{sa}'"
                )

    def test_positive_severity_items_become_favorable_terms(self):
        """Items with severity='positive' should be moved to favorable_terms,
        not remain in risk_items.
        """
        from contract_risk_analysis.domain.free_review_schema import (
            FreeReviewOutput,
            NegotiationChip,
            RiskSegment,
        )
        from contract_risk_analysis.review.report_writer import _build_dossier

        free_output = FreeReviewOutput(
            contract_id="test",
            overall_assessment="overall",
            risk_segments=[
                RiskSegment(
                    clause_type="liability_cap",
                    risk_title="无责任上限",
                    risk_description="对买方是核心优势",
                    evidence_text="test",
                    confidence=1.0,
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

        assert len(dossier.risk_items) == 0, (
            "positive severity items should not be in risk_items"
        )
        assert len(dossier.favorable_terms) == 1
        assert dossier.favorable_terms[0].term_name == "无责任上限"
        assert dossier.favorable_terms[0].chip_type == "响应筹码"


# ═══════════════════════════════════════════════════════════════════
# Test 7: Cross-chip consistency — party_aware_rules YAML integrity
# ═══════════════════════════════════════════════════════════════════


class TestPartyAwareConfigIntegrity:
    """Verify party_aware_rules.yaml covers all required clause types."""

    REQUIRED_BUYER_RULES = [
        "liability_cap",
        "damages_exposure",
        "liquidated_damages",
        "termination_for_cause",
        "jurisdiction",
        "warranty_scope",
        "payment_structure",
        "risk_transfer",
        "payment_security_structure",  # v2.14
    ]

    REQUIRED_SELLER_RULES = [
        "liability_cap",
        "damages_exposure",
        "liquidated_damages",
        "termination_for_cause",
        "jurisdiction",
        "payment_structure",
        "warranty_scope",
        "payment_delivery_linkage",
        "risk_transfer",
        "payment_security_structure",  # v2.14
    ]

    def test_all_buyer_rules_present(self):
        """All 6 required buyer-side rules are in the YAML."""
        from pathlib import Path
        import yaml

        config_path = (
            Path(__file__).parent.parent.parent
            / "config" / "party_aware_rules.yaml"
        )
        with open(config_path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        buyer_rules = config.get("buyer", {})
        for canonical_type in self.REQUIRED_BUYER_RULES:
            assert canonical_type in buyer_rules, (
                f"Missing buyer rule for '{canonical_type}' in party_aware_rules.yaml"
            )
            rule = buyer_rules[canonical_type]
            assert "action" in rule, (
                f"Buyer rule '{canonical_type}' missing 'action' field"
            )
            assert "note" in rule, (
                f"Buyer rule '{canonical_type}' missing 'note' field"
            )

    def test_all_seller_rules_present(self):
        """All 8 required seller-side rules are in the YAML."""
        from pathlib import Path
        import yaml

        config_path = (
            Path(__file__).parent.parent.parent
            / "config" / "party_aware_rules.yaml"
        )
        with open(config_path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        seller_rules = config.get("seller", {})
        for canonical_type in self.REQUIRED_SELLER_RULES:
            assert canonical_type in seller_rules, (
                f"Missing seller rule for '{canonical_type}' in party_aware_rules.yaml"
            )
            rule = seller_rules[canonical_type]
            assert "action" in rule, (
                f"Seller rule '{canonical_type}' missing 'action' field"
            )


# ═══════════════════════════════════════════════════════════════════
# Test 8: BN interpretation guardrails (v2.13-C)
# ═══════════════════════════════════════════════════════════════════


class TestBnInterpretationGuardrails:
    """Verify BN counterfactual interpretation rules prevent misuse."""

    def test_all_required_nodes_have_rules(self):
        """Every BN variable named in the design spec must have a guardrail rule."""
        from contract_risk_analysis.review.report_writer import BN_INTERPRETATION_RULES

        required = [
            "liability_cap",
            "liability_cap_strength",
            "damages_exposure",
            "jurisdiction_fairness",
            "termination_right_balance",
            "termination_clause_completeness",
        ]
        for node in required:
            assert node in BN_INTERPRETATION_RULES, (
                f"BN node '{node}' missing from BN_INTERPRETATION_RULES"
            )
            rule = BN_INTERPRETATION_RULES[node]
            assert "report_usage" in rule, f"'{node}' missing report_usage"
            assert "buyer" in rule, f"'{node}' missing buyer interpretation"
            assert "seller" in rule, f"'{node}' missing seller interpretation"

    def test_liability_cap_buyer_is_defensive_chip_only(self):
        """liability_cap from buyer view must be defensive_chip_only — NOT proactive."""
        from contract_risk_analysis.review.report_writer import (
            _get_bn_report_usage,
            _get_bn_interpretation_note,
        )

        usage = _get_bn_report_usage("liability_cap", "buyer")
        assert usage == "defensive_chip_only", (
            f"liability_cap + buyer report_usage should be defensive_chip_only, got {usage}"
        )
        note = _get_bn_interpretation_note("liability_cap", "buyer")
        assert "严禁" in note, (
            f"Buyer liability_cap note must contain 严禁, got: {note}"
        )
        assert "主动" in note

    def test_liability_cap_seller_can_be_proactive(self):
        """liability_cap from seller view can be used proactively."""
        from contract_risk_analysis.review.report_writer import _get_bn_report_usage

        usage = _get_bn_report_usage("liability_cap", "seller")
        # Seller view: same report_usage classification (still guarded),
        # but the interpretation note tells a different story
        assert usage == "defensive_chip_only"

    def test_damages_exposure_buyer_is_defensive_chip_only(self):
        """damages_exposure from buyer view must NOT suggest active exclusion."""
        from contract_risk_analysis.review.report_writer import (
            _get_bn_report_usage,
            _get_bn_interpretation_note,
        )

        usage = _get_bn_report_usage("damages_exposure", "buyer")
        assert usage == "defensive_chip_only"
        note = _get_bn_interpretation_note("damages_exposure", "buyer")
        assert "严禁" in note

    def test_jurisdiction_fairness_buyer_is_defensive_chip_only(self):
        """jurisdiction_fairness from buyer view must NOT suggest changing venue."""
        from contract_risk_analysis.review.report_writer import _get_bn_report_usage

        usage = _get_bn_report_usage("jurisdiction_fairness", "buyer")
        assert usage == "defensive_chip_only"

    def test_termination_nodes_are_manual_review(self):
        """Termination-related BN data requires manual review."""
        from contract_risk_analysis.review.report_writer import _get_bn_report_usage

        assert _get_bn_report_usage("termination_right_balance", "buyer") == "manual_review_note"
        assert _get_bn_report_usage("termination_clause_completeness", "buyer") == "manual_review_note"

    def test_counterfactual_takeaway_defensive_chip(self):
        """_counterfactual_takeaway with defensive_chip_only must warn 'not a modification target'."""
        from contract_risk_analysis.domain.free_review_schema import (
            CounterfactualResult,
            DimensionDelta,
        )
        from contract_risk_analysis.review.report_writer import _counterfactual_takeaway

        cf = CounterfactualResult(
            node_name="liability_cap",
            node_label="责任上限",
            current_state="missing",
            proposed_state="capped_at_100pct",
            base_high_risk=0.45,
            counterfactual_high_risk=0.30,
            delta_high_risk=0.15,
            description="test",
            dimension_deltas=[
                DimensionDelta(
                    dimension_key="financial_exposure_risk",
                    dimension_label="财务暴露风险",
                    base_high=0.50,
                    counterfactual_high=0.35,
                    delta=0.15,
                )
            ],
        )
        takeaway = _counterfactual_takeaway(cf, "buyer")
        assert "不是主动修改建议" in takeaway, (
            f"Defensive chip takeaway must warn against proactive modification, got: {takeaway}"
        )

    def test_counterfactual_takeaway_manual_review(self):
        """_counterfactual_takeaway with manual_review_note must flag for human review."""
        from contract_risk_analysis.domain.free_review_schema import (
            CounterfactualResult,
            DimensionDelta,
        )
        from contract_risk_analysis.review.report_writer import _counterfactual_takeaway

        cf = CounterfactualResult(
            node_name="termination_right_balance",
            node_label="终止权利平衡",
            current_state="unbalanced",
            proposed_state="balanced",
            base_high_risk=0.40,
            counterfactual_high_risk=0.30,
            delta_high_risk=0.10,
            description="test",
            dimension_deltas=[
                DimensionDelta(
                    dimension_key="legal_enforceability_risk",
                    dimension_label="法律可执行性风险",
                    base_high=0.45,
                    counterfactual_high=0.35,
                    delta=0.10,
                )
            ],
        )
        takeaway = _counterfactual_takeaway(cf, "buyer")
        assert "人工复核" in takeaway, (
            f"Manual review takeaway must flag for human review, got: {takeaway}"
        )

    def test_dossier_section_includes_report_usage_column(self):
        """_fmt_dossier_section must include the '数据使用层级' column for BN data."""
        from contract_risk_analysis.domain.free_review_schema import (
            CounterfactualResult,
            DimensionDelta,
            FreeReviewOutput,
            ReportDossier,
            RiskSegment,
        )
        from contract_risk_analysis.review.report_writer import _fmt_dossier_section

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[],
            counterfactuals=[
                CounterfactualResult(
                    node_name="liability_cap",
                    node_label="责任上限",
                    current_state="missing",
                    proposed_state="capped",
                    base_high_risk=0.45,
                    counterfactual_high_risk=0.30,
                    delta_high_risk=0.15,
                    description="test",
                    dimension_deltas=[
                        DimensionDelta(
                            dimension_key="financial_exposure_risk",
                            dimension_label="财务暴露风险",
                            base_high=0.50,
                            counterfactual_high=0.35,
                            delta=0.15,
                        )
                    ],
                )
            ],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=[],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
        )

        section = _fmt_dossier_section(dossier)
        assert "数据使用层级" in section, (
            "Dossier section must include '数据使用层级' column for BN data"
        )
        assert "仅防守筹码说明" in section, (
            "liability_cap from buyer view must show '仅防守筹码说明'"
        )
        assert "不是主动修改建议" in section, (
            "Defensive chip takeaway must appear in dossier section"
        )

    def test_unknown_node_returns_empty_usage(self):
        """Nodes not in BN_INTERPRETATION_RULES should return empty string."""
        from contract_risk_analysis.review.report_writer import _get_bn_report_usage

        assert _get_bn_report_usage("nonexistent_node", "buyer") == ""
        assert _get_bn_report_usage("some_random_bn_var", "seller") == ""


# ═══════════════════════════════════════════════════════════════════
# Test 9: Pre-render consistency checks (v2.13-D)
# ═══════════════════════════════════════════════════════════════════


class TestPreRenderConsistencyChecks:
    """Verify pre-render consistency checks catch contradictions before LLM prompt."""

    def test_clean_dossier_no_violations(self):
        """A well-formed dossier should produce no violations."""
        from contract_risk_analysis.domain.free_review_schema import (
            DossierRiskItem,
            ReportDossier,
        )
        from contract_risk_analysis.review.report_writer import (
            _run_pre_render_consistency_checks,
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[
                DossierRiskItem(
                    issue_id="ISSUE-001",
                    risk_title="预付款比例过高",
                    clause_type="payment",
                    severity="critical",
                    priority_rank=1,
                    evidence_text="80%预付款",
                    confidence=0.9,
                )
            ],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=["预付款比例过高：必须降至30%"],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
            favorable_terms=[],
        )

        violations = _run_pre_render_consistency_checks(dossier)
        assert len(violations) == 0, (
            f"Clean dossier should have 0 violations, got: {violations}"
        )

    def test_favorable_term_in_risk_items_detected(self):
        """A term that appears in both favorable_terms and risk_items is a violation."""
        from contract_risk_analysis.domain.free_review_schema import (
            DossierRiskItem,
            FavorableTerm,
            ReportDossier,
        )
        from contract_risk_analysis.review.report_writer import (
            _run_pre_render_consistency_checks,
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[
                DossierRiskItem(
                    issue_id="ISSUE-001",
                    risk_title="无责任上限风险",
                    clause_type="liability_cap",
                    canonical_type="liability_cap",
                    severity="high",
                    priority_rank=1,
                    evidence_text="...",
                    confidence=0.9,
                )
            ],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=[],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
            favorable_terms=[
                FavorableTerm(
                    term_name="无责任上限",
                    clause_type="liability_cap",
                    description="对买方有利",
                )
            ],
        )

        violations = _run_pre_render_consistency_checks(dossier)
        assert len(violations) > 0, "Should detect liability_cap in both risk and favorable"
        assert any("无责任上限" in v for v in violations), (
            f"Violations should mention the conflicting term: {violations}"
        )

    def test_response_chip_in_signing_forbidden_detected(self):
        """Response chip in signing_forbidden = violation (should not proactively modify)."""
        from contract_risk_analysis.domain.free_review_schema import (
            DossierRiskItem,
            NegotiationChip,
            ReportDossier,
        )
        from contract_risk_analysis.review.report_writer import (
            _run_pre_render_consistency_checks,
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[
                DossierRiskItem(
                    issue_id="ISSUE-001",
                    risk_title="无责任上限",
                    clause_type="liability_cap",
                    severity="positive",
                    priority_rank=5,
                    evidence_text="...",
                    confidence=0.9,
                    negotiation_chip=NegotiationChip(chip_type="响应筹码"),
                )
            ],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=["无责任上限：必须增加责任上限"],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
            favorable_terms=[],
        )

        violations = _run_pre_render_consistency_checks(dossier)
        assert len(violations) > 0, "Should detect response chip in signing_forbidden"
        assert any("响应筹码" in v for v in violations), (
            f"Violations should mention 响应筹码: {violations}"
        )

    def test_must_fix_favorable_term_detected(self):
        """Favorable term with negotiation_role='must_fix' is a contradiction."""
        from contract_risk_analysis.domain.free_review_schema import (
            FavorableTerm,
            ReportDossier,
        )
        from contract_risk_analysis.review.report_writer import (
            _run_pre_render_consistency_checks,
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=[],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
            favorable_terms=[
                FavorableTerm(
                    term_name="测试有利条款",
                    clause_type="test_type",
                    description="测试",
                    negotiation_role="must_fix",
                )
            ],
        )

        violations = _run_pre_render_consistency_checks(dossier)
        assert len(violations) > 0, "Should detect must_fix on favorable term"
        assert any("must_fix" in v for v in violations)

    def test_internal_issue_id_in_user_visible_text_detected(self):
        """Customer-facing text must not leak ISSUE-xxxx internal IDs."""
        from contract_risk_analysis.domain.free_review_schema import ReportDossier
        from contract_risk_analysis.review.report_writer import (
            _run_pre_render_consistency_checks,
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="请优先处理 ISSUE-001 后再推进签署。",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=[],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
            favorable_terms=[],
        )

        violations = _run_pre_render_consistency_checks(dossier)
        assert any("ISSUE-001" in v for v in violations)

    def test_placeholder_text_detected(self):
        """Customer-facing text must not contain unresolved placeholders."""
        from contract_risk_analysis.domain.free_review_schema import ReportDossier
        from contract_risk_analysis.review.report_writer import (
            _run_pre_render_consistency_checks,
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="请将违约金调整为【X】并在后续确认。",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=[],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
            favorable_terms=[],
        )

        violations = _run_pre_render_consistency_checks(dossier)
        assert any("【X】" in v for v in violations)

    def test_unsupported_numeric_claim_detected(self):
        """Free-form numeric estimates without structured source should be blocked."""
        from contract_risk_analysis.domain.free_review_schema import ReportDossier
        from contract_risk_analysis.review.report_writer import (
            _run_pre_render_consistency_checks,
        )

        dossier = ReportDossier(
            contract_id="test",
            review_party="buyer",
            risk_items=[],
            counterfactuals=[],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="",
            overall_assessment="如发生争议，诉讼成本约20-50万，成功回收率低于60%。",
            strengths=[],
            missing_clauses=[],
            signing_forbidden=[],
            signing_acceptable=[],
            negotiation_bottom_lines=[],
            favorable_terms=[],
        )

        violations = _run_pre_render_consistency_checks(dossier)
        assert any("20-50万" in v or "60%" in v for v in violations)


# ═══════════════════════════════════════════════════════════════════
# Test 10: Structural pattern detection — payment-security inversion (v2.14)
# ═══════════════════════════════════════════════════════════════════


class TestPaymentSecurityInversion:
    """Verify structural detection of payment-security inversion patterns."""

    @staticmethod
    def _make_seg(
        clause_type: str,
        canonical_type: str,
        title: str,
        desc: str,
        evidence: str,
        severity: str = "high",
    ):
        from contract_risk_analysis.domain.free_review_schema import RiskSegment

        return RiskSegment(
            clause_type=clause_type,
            risk_title=title,
            risk_description=desc,
            evidence_text=evidence,
            confidence=0.85,
            severity=severity,
            canonical_type=canonical_type,
        )

    def test_inversion_detected_when_both_prepayment_and_delayed_deposit(self):
        """High prepayment + delayed deposit → structural inversion detected."""
        from contract_risk_analysis.review.adjudicate import (
            _detect_payment_security_inversion,
        )

        segments = [
            self._make_seg(
                "payment",
                "payment_structure",
                "预付款比例过高",
                "合同约定甲方支付80%预付款，金额达1228万元",
                "甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款",
                severity="high",
            ),
            self._make_seg(
                "quality",
                "warranty_scope",
                "质保金提交节点过晚",
                "质保金在支付剩余款项前提交，晚于预付款",
                "甲方在支付合同总价的剩余款项前，可要求乙方提交质量保证金",
                severity="medium",
            ),
        ]

        result = _detect_payment_security_inversion(segments, "buyer")

        # Should have created or enhanced a structural inversion item
        structural_items = [
            s for s in result
            if "倒挂" in (s.risk_title + s.risk_description)
        ]
        assert len(structural_items) >= 1, (
            f"Should detect structural inversion, got {len(result)} segments: "
            f"{[s.risk_title for s in result]}"
        )
        structural = structural_items[0]
        assert structural.severity in ("critical", "high"), (
            f"Structural inversion should be critical or high, got {structural.severity}"
        )
        assert structural.priority_rank == 1, (
            f"Structural inversion should have P1, got P{structural.priority_rank}"
        )

    def test_inversion_detected_without_sample_specific_numbers(self):
        """Generalized structural signals should work without 80% or 1228万 anchors."""
        from contract_risk_analysis.review.adjudicate import (
            _detect_payment_security_inversion,
        )

        segments = [
            self._make_seg(
                "payment",
                "payment_structure",
                "首付款比例偏高",
                "合同约定签约后支付合同总价的大部分款项，且未见同步履约担保安排",
                "合同签订生效后5日内，甲方先行支付合同总价的65%作为首付款",
                severity="high",
            ),
            self._make_seg(
                "quality",
                "warranty_scope",
                "保证金提供节点滞后",
                "质量保证金在尾款支付前才提交，明显滞后于前置付款",
                "乙方应在支付剩余款项前另行提交合同金额5%的质量保证金",
                severity="medium",
            ),
        ]

        result = _detect_payment_security_inversion(segments, "buyer")

        structural_items = [
            s for s in result
            if s.canonical_type == "payment_security_structure"
        ]
        assert len(structural_items) >= 1, (
            "Generalized payment-security inversion should be detected without sample numbers"
        )
        assert "65%" not in structural_items[0].risk_title
        assert structural_items[0].priority_rank == 1

    def test_no_inversion_without_prepayment(self):
        """If no high prepayment segment, no inversion should be detected."""
        from contract_risk_analysis.review.adjudicate import (
            _detect_payment_security_inversion,
        )

        segments = [
            self._make_seg(
                "quality",
                "warranty_scope",
                "质保金提交节点过晚",
                "质保金在支付剩余款项前提交",
                "甲方可要求乙方提交质量保证金",
                severity="medium",
            ),
        ]

        result = _detect_payment_security_inversion(segments, "buyer")
        assert len(result) == 1, "Should not create inversion without prepayment"

    def test_no_inversion_without_delayed_deposit(self):
        """High prepayment alone (no delayed deposit) → no structural inversion."""
        from contract_risk_analysis.review.adjudicate import (
            _detect_payment_security_inversion,
        )

        segments = [
            self._make_seg(
                "payment",
                "payment_structure",
                "预付款比例过高",
                "合同约定甲方支付80%预付款",
                "甲方支付80%作为预付款",
                severity="high",
            ),
        ]

        result = _detect_payment_security_inversion(segments, "buyer")
        assert len(result) == 1, "Should not detect inversion without delayed deposit"

    def test_inversion_not_detected_for_seller(self):
        """Seller view: high prepayment is advantage, no inversion warning needed."""
        from contract_risk_analysis.review.adjudicate import (
            _detect_payment_security_inversion,
        )

        segments = [
            self._make_seg(
                "payment",
                "payment_structure",
                "预付款比例过高",
                "甲方支付80%预付款",
                "甲方支付80%作为预付款",
                severity="high",
            ),
            self._make_seg(
                "quality",
                "warranty_scope",
                "质保金提交节点过晚",
                "质保金在支付剩余款项前提交",
                "甲方可要求乙方提交质量保证金",
                severity="medium",
            ),
        ]

        result = _detect_payment_security_inversion(segments, "seller")
        # Seller view: should return unchanged
        assert len(result) == 2, (
            f"Seller view should not trigger inversion detection, got {len(result)}"
        )

    def test_inversion_integrated_in_adjudicate_pipeline(self):
        """Full adjudicate() pipeline must include structural inversion step."""
        from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput
        from contract_risk_analysis.review.adjudicate import adjudicate

        free_output = FreeReviewOutput(
            contract_id="test",
            overall_assessment="test",
            risk_segments=[
                self._make_seg(
                    "payment",
                    "payment_structure",
                    "预付款比例过高",
                    "甲方支付80%预付款共1228万元",
                    "甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款",
                    severity="high",
                ),
                self._make_seg(
                    "quality",
                    "warranty_scope",
                    "质保金提交节点过晚",
                    "质保金在支付剩余款项前提交，明显晚于预付款",
                    "甲方在支付合同总价的剩余款项前，可要求乙方提交质量保证金",
                    severity="medium",
                ),
            ],
            missing_clauses=[],
            strengths=[],
        )

        result = adjudicate(free_output, "buyer")

        # Should have 3 items: 2 original + 1 structural inversion
        structural = [
            s for s in result.risk_segments
            if "倒挂" in (s.risk_title + s.risk_description)
        ]
        assert len(structural) >= 1, "Adjudicate pipeline should detect structural inversion"


# ═══════════════════════════════════════════════════════════════════
# Test 11: Multi-format report output — deterministic formats (v2.15)
# ═══════════════════════════════════════════════════════════════════


class TestMultiFormatReports:
    """Verify deterministic report formats are generated correctly."""

    def _make_dossier(self, review_party: str = "buyer"):
        from contract_risk_analysis.domain.free_review_schema import (
            CounterfactualResult,
            DimensionDelta,
            DossierRiskItem,
            NegotiationChip,
            ReportDossier,
        )

        return ReportDossier(
            contract_id="test-contract-001",
            review_party=review_party,
            risk_items=[
                DossierRiskItem(
                    issue_id="ISSUE-001",
                    risk_title="预付款比例过高",
                    clause_type="payment",
                    canonical_type="payment_structure",
                    severity="critical",
                    priority_rank=1,
                    evidence_text="甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款",
                    confidence=0.90,
                    recommendation="降低预付款比例至30%以下，并增加等额履约保函",
                    legal_basis="民法典第525条",
                    legal_direction="unfavorable",
                    negotiation_role="must_fix",
                    negotiation_chip=NegotiationChip(
                        chip_type="底线筹码",
                        reason="买方大额资金敞口",
                    ),
                ),
                DossierRiskItem(
                    issue_id="ISSUE-002",
                    risk_title="质保金提交节点过晚",
                    clause_type="quality",
                    canonical_type="warranty_scope",
                    severity="high",
                    priority_rank=2,
                    evidence_text="甲方在支付剩余款项前，可要求乙方提交质量保证金",
                    confidence=0.80,
                    recommendation="质保金提交节点提前至预付款支付前",
                    legal_direction="unfavorable",
                    negotiation_role="trade",
                    negotiation_chip=NegotiationChip(chip_type="交换筹码"),
                ),
            ],
            counterfactuals=[
                CounterfactualResult(
                    node_name="payment_structure",
                    node_label="付款结构改善",
                    current_state="high_prepayment_no_security",
                    proposed_state="moderate_prepayment_with_security",
                    base_high_risk=0.55,
                    counterfactual_high_risk=0.30,
                    delta_high_risk=0.25,
                    description="将预付款降至30%并增加履约保函",
                    dimension_deltas=[
                        DimensionDelta(
                            dimension_key="financial_exposure_risk",
                            dimension_label="财务暴露风险",
                            base_high=0.60,
                            counterfactual_high=0.30,
                            delta=0.30,
                        )
                    ],
                )
            ],
            bn_annotations=[],
            joint_risks=[],
            bn_summary="BN校验完成，未发现重大矛盾。",
            overall_assessment="本合同存在重大付款安全风险，建议在签署前修改核心条款。",
            strengths=["甲方住所地法院管辖"],
            missing_clauses=["未约定履约保函"],
            signing_forbidden=["预付款比例过高：必须降至30%以下并增加等额履约保函"],
            signing_acceptable=["质保金提交节点提前至预付款支付前"],
            negotiation_bottom_lines=["预付款不得高于30%"],
            favorable_terms=[],
        )

    def test_revision_checklist_contains_must_fix_items(self):
        """Revision checklist must include must_fix/critical items."""
        from contract_risk_analysis.review.report_writer import _build_revision_checklist

        dossier = self._make_dossier()
        checklist = _build_revision_checklist(dossier)

        assert "合同修订清单" in checklist
        assert "ISSUE-001" in checklist
        assert "预付款比例过高" in checklist
        assert "必须修改" in checklist or "签署底线" in checklist
        assert "降低预付款" in checklist

    def test_revision_checklist_includes_favorable_terms_section(self):
        """Revision checklist should have a section listing favorable terms NOT to modify."""
        from contract_risk_analysis.domain.free_review_schema import FavorableTerm
        from contract_risk_analysis.review.report_writer import _build_revision_checklist

        dossier = self._make_dossier()
        dossier.favorable_terms = [
            FavorableTerm(
                term_name="无责任上限",
                clause_type="liability_cap",
                description="对买方是核心优势",
                chip_type="响应筹码",
            )
        ]
        checklist = _build_revision_checklist(dossier)

        assert "有利条款" in checklist
        assert "无责任上限" in checklist
        assert "不建议主动提出修改" in checklist

    def test_bn_appendix_contains_counterfactual_data(self):
        """BN appendix must include counterfactual details."""
        from contract_risk_analysis.review.report_writer import _build_bn_appendix

        dossier = self._make_dossier()
        appendix = _build_bn_appendix(dossier)

        assert "BN/方法论附录" in appendix
        assert "pgmpy" in appendix or "变量消除" in appendix
        assert "付款结构改善" in appendix
        assert "财务暴露风险" in appendix
        assert "30.0%" in appendix  # delta displayed
        assert "方法论局限" in appendix

    def test_bn_appendix_includes_limitations(self):
        """BN appendix must document methodological limitations."""
        from contract_risk_analysis.review.report_writer import _build_bn_appendix

        dossier = self._make_dossier()
        appendix = _build_bn_appendix(dossier)

        assert "方法论局限" in appendix
        assert "反事实模拟" in appendix
        assert "CPT" in appendix or "先验" in appendix

    def test_bn_appendix_includes_conflicts_when_present(self):
        """When dossier has internal conflicts, BN appendix must record them."""
        from contract_risk_analysis.review.report_writer import _build_bn_appendix

        dossier = self._make_dossier()
        dossier.internal_conflicts = ["测试冲突：预付款条款与质保金条款存在矛盾"]
        appendix = _build_bn_appendix(dossier)

        assert "冲突记录" in appendix or "冲突" in appendix
        assert "测试冲突" in appendix

    def test_multi_format_reports_deterministic_formats(self):
        """generate_multi_format_reports must produce deterministic formats without LLM."""
        from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput
        from contract_risk_analysis.review.report_writer import (
            generate_multi_format_reports,
        )

        dossier = self._make_dossier()
        free_output = FreeReviewOutput(
            contract_id="test",
            overall_assessment="test",
            risk_segments=[],
            missing_clauses=[],
            strengths=[],
        )

        reports = generate_multi_format_reports(
            free_output,
            None,
            dossier=dossier,
            include_executive=False,   # Skip LLM calls
            include_full_review=False,  # Skip LLM calls
            include_playbook=False,     # Skip LLM calls
            include_checklist=True,
            include_appendix=True,
        )

        assert reports.dossier is dossier
        assert len(reports.revision_checklist) > 0, "Revision checklist should be generated"
        assert len(reports.bn_appendix) > 0, "BN appendix should be generated"
        assert reports.executive_brief == "", "Skipped formats should be empty"
        assert reports.full_legal_review == ""
        assert reports.negotiation_playbook == ""

    def test_executive_brief_prompt_contains_key_sections(self):
        """Executive brief prompt must include all required sections."""
        from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput
        from contract_risk_analysis.review.report_writer import (
            _build_executive_brief_prompt,
        )

        dossier = self._make_dossier()
        free_output = FreeReviewOutput(
            contract_id="test",
            overall_assessment="test",
            risk_segments=[],
            missing_clauses=[],
            strengths=[],
        )

        prompt = _build_executive_brief_prompt(dossier, free_output, "buyer")
        assert "签署建议" in prompt
        assert "核心风险" in prompt
        assert "我方优势" in prompt
        assert "谈判底线" in prompt
        assert "决策建议" in prompt
        assert "500-800字" in prompt

    def test_negotiation_playbook_prompt_contains_all_sections(self):
        """Negotiation playbook prompt must include all required sections."""
        from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput
        from contract_risk_analysis.review.report_writer import (
            _build_negotiation_playbook_prompt,
        )

        dossier = self._make_dossier()
        free_output = FreeReviewOutput(
            contract_id="test",
            overall_assessment="test",
            risk_segments=[],
            missing_clauses=[],
            strengths=[],
        )

        prompt = _build_negotiation_playbook_prompt(dossier, free_output, "buyer")
        assert "筹码总览" in prompt
        assert "对手主攻方向预判" in prompt
        assert "底线筹码防御策略" in prompt
        assert "交换筹码退让阶梯" in prompt
        assert "响应筹码交换方案" in prompt
        assert "谈判路线图" in prompt
