"""Phase A P4: Report stability verification.

Verifies that the same contract produces stable dossier fields across
repeated pipeline runs. This is the core trustworthiness guarantee.

Usage:
    pytest tests/stability/test_report_stability.py -v -s

Note: This test requires a running backend (API at localhost:9527) and
a valid DeepSeek API key. It is designed for manual verification, not CI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


# ── Test configuration ────────────────────────────────────────────

# Contract text to use for stability testing
_SAMPLE_CONTRACT = """买卖合同

甲方（买方）：北京测试科技有限公司
乙方（卖方）：上海设备制造有限公司

第一条 合同标的
乙方向甲方出售水质监测设备一套，具体规格型号见附件一。

第二条 合同金额
本合同总价款为人民币1535万元整。

第三条 交付
1. 交货地点：甲方指定的北京市辖区范围内。
2. 甲方经核对产品数量无误及对产品质量进行初验收并签字确认后，视为乙方已交付。

第六条 质量保证
1. 质保期为36个月，自最终验收合格之日起计算。
2. 质保期内乙方免费提供维修服务。
3. 外观验收不免除乙方内在质量保证责任。

第七条 安装调试
乙方负责在交货后90日内完成安装调试。

第九条 付款方式
1. 甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款。
2. 剩余15%在最终验收合格后支付。
3. 质保金为合同金额的5%，以支票形式提交。

第十条 违约责任
1. 乙方逾期交货的，每延期一天，应向甲方支付合同总价款万分之五的违约金。
2. 由此给甲方造成损失的，乙方应承担赔偿责任。

第十一条 合同解除
乙方逾期交货超过15天，甲方有权单方解除合同并要求赔偿。

第十三条 争议解决
因本合同引起的争议，双方协商不成的，向甲方住所地人民法院提起诉讼。
"""

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ── Stability data structures ─────────────────────────────────────


@dataclass
class DossierSnapshot:
    """Extracted stable fields from one pipeline run's response."""
    run_index: int
    risk_count: int
    issue_ids: list[str]
    severities: dict[str, str]  # issue_id → severity
    priorities: dict[str, int]  # issue_id → priority_rank
    bn_counterfactual_count: int
    signing_forbidden_count: int
    manual_review_count: int


@dataclass
class StabilityReport:
    """Aggregated stability analysis across N runs."""
    total_runs: int
    snapshots: list[DossierSnapshot] = field(default_factory=list)

    @property
    def risk_count_stable(self) -> bool:
        if len(self.snapshots) < 2:
            return True
        first = self.snapshots[0].risk_count
        return all(s.risk_count == first for s in self.snapshots)

    @property
    def issue_ids_stable(self) -> bool:
        if len(self.snapshots) < 2:
            return True
        first = set(self.snapshots[0].severities.keys())
        return all(set(s.severities.keys()) == first for s in self.snapshots)

    @property
    def severities_stable(self) -> bool:
        if len(self.snapshots) < 2:
            return True
        ref = self.snapshots[0].severities
        # Allow different issue_ids across runs, but same issue_id must have same severity
        for snap in self.snapshots[1:]:
            for iid, sev in snap.severities.items():
                if iid in ref and ref[iid] != sev:
                    return False
        return True

    @property
    def priorities_stable(self) -> bool:
        if len(self.snapshots) < 2:
            return True
        ref = self.snapshots[0].priorities
        for snap in self.snapshots[1:]:
            for iid, pri in snap.priorities.items():
                if iid in ref and ref[iid] != pri:
                    return False
        return True

    def summary(self) -> str:
        lines = [
            f"=== 稳定性验证报告（{self.total_runs} runs）===",
            f"风险项数量稳定：{'✓' if self.risk_count_stable else '✗'} "
            f"({[s.risk_count for s in self.snapshots]})",
            f"Issue ID 集合稳定：{'✓' if self.issue_ids_stable else '✗'}",
            f"严重度一致：{'✓' if self.severities_stable else '✗'}",
            f"优先级一致：{'✓' if self.priorities_stable else '✗'}",
            f"BN 反事实数量：{[s.bn_counterfactual_count for s in self.snapshots]}",
            f"签署底线数量：{[s.signing_forbidden_count for s in self.snapshots]}",
            f"人工复核数量：{[s.manual_review_count for s in self.snapshots]}",
            "",
            "通过条件：风险项数量+ID集合+严重度+优先级全部稳定",
            f"总体结果：{'PASS' if self._all_stable() else 'FAIL — 存在漂移'}",
        ]
        return "\n".join(lines)

    def _all_stable(self) -> bool:
        return (
            self.risk_count_stable
            and self.issue_ids_stable
            and self.severities_stable
            and self.priorities_stable
        )


# ── API helper ─────────────────────────────────────────────────────


def _call_v2_api(contract_text: str, review_party: str = "buyer") -> dict[str, Any]:
    """Call the v2 review API and return the parsed response."""
    import requests
    resp = requests.post(
        "http://localhost:9527/api/v2/review",
        json={
            "contract_text": contract_text,
            "contract_id": "stability-test",
            "review_party": review_party,
        },
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()


def _extract_snapshot(response: dict[str, Any], run_index: int) -> DossierSnapshot:
    """Extract stable dossier fields from an API response."""
    free = response.get("free_review", {})
    consistency = response.get("consistency", {})
    segments = free.get("risk_segments", [])

    severities: dict[str, int] = {}
    priorities: dict[str, int] = {}
    issue_ids: list[str] = []

    for i, seg in enumerate(segments):
        iid = f"ISSUE-{i + 1:03d}"
        issue_ids.append(iid)
        severities[iid] = seg.get("severity", "unknown")
        priorities[iid] = seg.get("priority_rank", 99)

    return DossierSnapshot(
        run_index=run_index,
        risk_count=len(segments),
        issue_ids=issue_ids,
        severities=severities,
        priorities=priorities,
        bn_counterfactual_count=len(consistency.get("counterfactuals", [])),
        signing_forbidden_count=sum(
            1 for s in segments
            if s.get("severity") == "critical" and s.get("priority_rank") == 1
        ),
        manual_review_count=0,  # Will be populated from dossier in future
    )


# ── Narrative guardrail check ─────────────────────────────────────


def check_narrative_guardrail(narrative: str, dossier_risk_titles: set[str]) -> list[str]:
    """Check that the narrative doesn't introduce risks not in the dossier.

    Returns a list of violations (risk titles found in narrative but not in dossier).
    This is a best-effort heuristic — it checks for risk-like patterns in the narrative.
    """
    violations: list[str] = []
    # Simple check: look for lines that look like risk descriptions
    # that aren't in the dossier
    import re
    # Find potential risk mentions (lines with risk indicators)
    risk_indicators = re.findall(
        r'(?:风险|致命|高风险|中风险|低风险)[：:]\s*(.+?)(?:\n|$)',
        narrative,
    )
    for indicator in risk_indicators:
        indicator = indicator.strip()
        # Check if this appears in any dossier risk title
        found = any(
            indicator[:20] in title or title[:20] in indicator
            for title in dossier_risk_titles
        )
        if not found and len(indicator) > 10:
            violations.append(indicator)

    return violations


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="Requires DEEPSEEK_API_KEY and running backend",
)
class TestReportStability:
    """Stability tests requiring a live backend and API key."""

    @pytest.mark.parametrize("run_index", range(3))
    def test_single_run_completes(self, run_index: int):
        """Each individual run completes without error."""
        response = _call_v2_api(_SAMPLE_CONTRACT)
        assert response.get("generation_mode") in ("v2_combined", "combined_phase_a")
        assert response.get("free_review", {}).get("segments_count", 0) > 0

    def test_stability_3_runs(self):
        """Core stability test: 3 runs, compare dossier fields."""
        snapshots: list[DossierSnapshot] = []
        for i in range(3):
            response = _call_v2_api(_SAMPLE_CONTRACT)
            snapshots.append(_extract_snapshot(response, i))

        report = StabilityReport(total_runs=3, snapshots=snapshots)
        print("\n" + report.summary())

        assert report._all_stable(), (
            f"Stability check failed!\n{report.summary()}"
        )

    def test_narrative_guardrail(self):
        """Narrative report must not introduce risks not in the dossier."""
        response = _call_v2_api(_SAMPLE_CONTRACT)
        narrative = response.get("report", {}).get("narrative_report", "")
        if not narrative:
            pytest.skip("No narrative report in response")

        segments = response.get("free_review", {}).get("risk_segments", [])
        dossier_titles = {s.get("risk_title", "") for s in segments}

        violations = check_narrative_guardrail(narrative, dossier_titles)
        if violations:
            print(f"\nNarrative guardrail violations: {violations}")
        assert len(violations) == 0, (
            f"Narrative introduced {len(violations)} risks not in dossier: {violations}"
        )


# ── Offline unit tests (no API needed) ────────────────────────────


class TestAdjudicationStability:
    """Unit tests for the adjudication layer's deterministic behavior."""

    def test_deduplication_deterministic(self):
        """Same input should produce same deduplication result every time."""
        from contract_risk_analysis.domain.free_review_schema import (
            FreeReviewOutput,
            RiskSegment,
        )
        from contract_risk_analysis.review.adjudicate import adjudicate

        segments = [
            RiskSegment(
                clause_type="payment", risk_title="预付款比例过高",
                risk_description="预付款80%风险极高",
                evidence_text="甲方于本合同签订后10日内向乙方支付合同金额的80%",
                confidence=0.95, severity="critical", canonical_type="payment",
            ),
            RiskSegment(
                clause_type="payment", risk_title="预付款比例80%过高",
                risk_description="预付款比例太高",
                evidence_text="甲方于本合同签订后10日内向乙方支付合同金额的80%",
                confidence=0.85, severity="critical", canonical_type="payment",
            ),
            RiskSegment(
                clause_type="delivery", risk_title="交付地点不明确",
                risk_description="仅约定北京市辖区",
                evidence_text="甲方收货地点：甲方指定的北京市辖区范围内",
                confidence=0.90, severity="high", canonical_type="delivery",
            ),
        ]

        free = FreeReviewOutput(
            contract_id="test",
            overall_assessment="test",
            risk_segments=segments,
            missing_clauses=[],
            strengths=[],
        )

        # Run adjudication 5 times, check same result
        results = []
        for _ in range(5):
            # Fresh copy each time
            fresh = FreeReviewOutput(
                contract_id="test",
                overall_assessment="test",
                risk_segments=[
                    RiskSegment(
                        clause_type=s.clause_type, risk_title=s.risk_title,
                        risk_description=s.risk_description,
                        evidence_text=s.evidence_text,
                        confidence=s.confidence, severity=s.severity,
                        canonical_type=s.canonical_type,
                    )
                    for s in segments
                ],
                missing_clauses=[],
                strengths=[],
            )
            adj = adjudicate(fresh)
            results.append(len(adj.risk_segments))

        # All runs should produce the same count
        assert len(set(results)) == 1, f"Inconsistent dedup: {results}"
        # The two payment items should be merged → 2 total
        assert results[0] == 2, f"Expected 2 items after dedup, got {results[0]}"


# ── V-3: Mapping stability tests (no API needed) ────────────────────


class TestMappingStability:
    """V-3: Verify synonymous clause_type inputs map to same canonical type / BN node."""

    SYNONYM_PAIRS = [
        # (input, expected_canonical)
        ("payment", "payment"),
        ("Payment", "payment"),
        ("付款", "payment"),
        ("delivery", "delivery"),
        ("Delivery", "delivery"),
        ("交货", "delivery"),
        ("termination", "termination"),
        ("解除", "termination"),
        ("liability", "liability_cap"),
        ("责任上限", "liability_cap"),
        ("liquidated_damages", "liquidated_damages"),
        ("违约金", "liquidated_damages"),
        ("warranty", "warranty"),
        ("质保", "warranty"),
        ("dispute_resolution", "dispute_resolution"),
        ("争议", "dispute_resolution"),
        ("confidentiality", "confidentiality"),
        ("保密", "confidentiality"),
        ("ip_ownership", "ip_ownership"),
        ("知识产权", "ip_ownership"),
        ("governing_law", "governing_law"),
        ("适用法律", "governing_law"),
    ]

    def test_canonicalize_synonyms(self):
        """All synonyms in a group map to the same canonical type."""
        from contract_risk_analysis.review.canonicalize import canonicalize_clause_type

        # Group by expected canonical
        groups: dict[str, list[str]] = {}
        for input_val, expected in self.SYNONYM_PAIRS:
            groups.setdefault(expected, []).append(input_val)

        for canonical, inputs in groups.items():
            for inp in inputs:
                result = canonicalize_clause_type(inp)
                assert result == canonical, (
                    f"'{inp}' → '{result}', expected '{canonical}'"
                )

    def test_canonicalize_deterministic(self):
        """Same input always produces same canonical type (5 runs)."""
        from contract_risk_analysis.review.canonicalize import canonicalize_clause_type

        for _ in range(5):
            assert canonicalize_clause_type("payment") == "payment"
            assert canonicalize_clause_type("delivery") == "delivery"

    def test_unknown_type_returns_none(self):
        """Completely unknown clause_type returns None, not a wrong match."""
        from contract_risk_analysis.review.canonicalize import canonicalize_clause_type

        assert canonicalize_clause_type("xyz_unknown_12345") is None


# ── V-2: Narrative guardrail (offline unit test) ────────────────────


class TestNarrativeGuardrail:
    """V-2: Narrative must not introduce risks not in the dossier."""

    def test_guardrail_detects_new_risk(self):
        """Guardrail catches a risk mentioned in narrative but not in dossier."""
        narrative = """
        ## 风险总览
        风险：预付款比例过高 - 80%的预付款存在重大资金风险。
        风险：违约金过高可能导致法院调减。
        """
        dossier_titles = {"预付款比例过高"}
        violations = check_narrative_guardrail(narrative, dossier_titles)
        # "违约金过高" is in narrative but not in dossier → violation
        assert len(violations) > 0, "Should detect narrative-only risk"

    def test_guardrail_passes_clean_narrative(self):
        """Guardrail passes when all risks are in the dossier."""
        narrative = """
        ## 风险总览
        风险：预付款比例过高 - 80%的预付款存在重大资金风险。
        """
        dossier_titles = {"预付款比例过高"}
        violations = check_narrative_guardrail(narrative, dossier_titles)
        assert len(violations) == 0, f"Expected 0 violations, got {violations}"


# ── V-4: Conflict escalation test (offline unit test) ──────────────


class TestConflictEscalation:
    """V-4: System must flag manual_review instead of hiding uncertainty."""

    def test_bn_contradiction_flags_manual_review(self):
        """When BN contradicts LLM severity, dossier flags manual_review."""
        from contract_risk_analysis.domain.free_review_schema import (
            ConsistencyReport,
            FreeReviewOutput,
            RiskSegment,
            ValidationAnnotation,
        )
        from contract_risk_analysis.review.report_writer import _build_dossier

        seg = RiskSegment(
            clause_type="liability",
            risk_title="无责任上限",
            risk_description="合同未设责任上限",
            evidence_text="由此给甲方造成损失的，乙方应承担赔偿责任。",
            confidence=0.9,
            severity="critical",
            suggested_bn_nodes=["liability_cap_strength"],
        )

        free = FreeReviewOutput(
            contract_id="test",
            overall_assessment="test",
            risk_segments=[seg],
            missing_clauses=[],
            strengths=[],
        )

        # BN contradictory annotation
        consistency = ConsistencyReport(
            contract_id="test",
            annotations=[
                ValidationAnnotation(
                    annotation_type="contradiction",
                    severity="warning",
                    message="BN P(high)=0.08, LLM severity=critical — possible overestimate",
                    llm_clause_type="liability",
                )
            ],
            counterfactuals=[],
            bn_posteriors={"liability_cap_strength": {"high": 0.08, "low": 0.92}},
            bn_summary="test",
        )

        dossier = _build_dossier(free, consistency, "buyer")
        # Should flag for manual review
        flagged = [item for item in dossier.risk_items if item.manual_review]
        assert len(flagged) > 0, "Contradiction should trigger manual_review flag"

    def test_low_evidence_flags_concern(self):
        """Critical severity without BN coverage gets downgraded to high."""
        from contract_risk_analysis.domain.free_review_schema import (
            FreeReviewOutput,
            RiskSegment,
        )
        from contract_risk_analysis.review.report_writer import _build_dossier

        seg = RiskSegment(
            clause_type="unknown_type",
            risk_title="罕见风险",
            risk_description="一个罕见的合同风险",
            evidence_text="短证据",
            confidence=0.5,
            severity="critical",
            suggested_bn_nodes=[],  # No BN coverage
        )

        free = FreeReviewOutput(
            contract_id="test",
            overall_assessment="test",
            risk_segments=[seg],
            missing_clauses=[],
            strengths=[],
        )

        dossier = _build_dossier(free, None, "buyer")
        item = dossier.risk_items[0]
        # critical without BN coverage → downgraded to high
        assert item.severity == "high", (
            f"Critical without BN coverage should be downgraded to high, got {item.severity}"
        )
