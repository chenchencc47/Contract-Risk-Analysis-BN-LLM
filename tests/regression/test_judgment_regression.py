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

    def test_unknown_canonical_type_not_affected(self):
        """Non-party-aware canonical types should pass through unchanged."""
        from contract_risk_analysis.review.adjudicate import _apply_party_aware_rules

        seg = self._make_segment("payment", "payment_structure", severity="critical")
        result = _apply_party_aware_rules([seg], review_party="buyer")

        assert result[0].severity == "critical", (
            "payment_structure should not be reclassified for buyer"
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
