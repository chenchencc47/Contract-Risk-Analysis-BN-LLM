from pathlib import Path

from contract_risk_analysis.evaluation import golden_score
from contract_risk_analysis.evaluation.golden_score import (
    auto_score_report_text,
    format_batch_golden_summary,
    load_golden_cases,
    load_golden_patterns,
    score_golden_case,
    score_reports_against_case_batch,
    summarize_patterns,
)


def test_load_golden_cases():
    cases = load_golden_cases("tests/fixtures/golden_cases")

    case_ids = {case["case_id"] for case in cases}

    assert "sales_purchase_contract_001" in case_ids
    assert "sales_contract_001" in case_ids


def test_score_golden_case_hits_must_find_and_should_find():
    case = {
        "case_id": "demo",
        "must_find": [
            {
                "id": "prepayment",
                "expected": "识别预付款",
                "evidence_keywords": ["80%", "预付款"],
            }
        ],
        "must_not": [],
        "should_find_advantages": [
            {
                "id": "forum",
                "expected": "识别管辖优势",
                "evidence_keywords": ["甲方住所地", "管辖"],
            }
        ],
    }
    report = "本合同约定80%预付款。争议由甲方住所地法院管辖。"

    score = score_golden_case(case, report)

    assert score.score == 100.0
    assert score.must_find[0].passed is True
    assert score.should_find_advantages[0].passed is True


def test_score_golden_case_detects_forbidden_pattern():
    case = {
        "case_id": "demo",
        "must_find": [],
        "must_not": [
            {
                "id": "wrong_liability_cap",
                "forbidden": "不得主动增加责任上限",
                "wrong_patterns": ["甲方应主动增加责任上限"],
            }
        ],
        "should_find_advantages": [],
    }
    report = "报告建议甲方应主动增加责任上限。"

    score = score_golden_case(case, report)

    assert score.score == 0.0
    assert score.must_not[0].passed is False
    assert score.must_not[0].matched_keywords == ["甲方应主动增加责任上限"]


def test_load_and_summarize_golden_patterns():
    patterns = load_golden_patterns("tests/fixtures/golden_patterns")

    rows = summarize_patterns(patterns)
    pattern_ids = {row["pattern_id"] for row in rows}

    assert "high_prepayment_without_security" in pattern_ids
    assert "liability_cap_by_party_stance" in pattern_ids


def test_auto_score_report_text_exposes_regression_semantics():
    report = "本合同约定80%预付款。争议由甲方住所地法院管辖。"

    score = auto_score_report_text(
        report,
        cases_dir="tests/fixtures/golden_cases",
    )

    assert score is not None
    assert score["score_kind"] == "golden_case_regression"
    assert score["score_label"] == "Golden Case 回归匹配分"
    assert "回归" in score["regression_note"]
    assert "不是任何合同都通用的质量总分" in score["regression_note"]


def test_score_reports_against_case_batch_aggregates_directory_scores(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not: []
should_find_advantages:
  - id: forum
    expected: 识别管辖优势
    evidence_keywords: ["甲方住所地", "管辖"]
        """.strip(),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "a.md").write_text(
        "本合同约定80%预付款。争议由甲方住所地法院管辖。",
        encoding="utf-8",
    )
    (reports_dir / "b.md").write_text(
        "本合同约定80%预付款。",
        encoding="utf-8",
    )
    (reports_dir / "notes.txt").write_text("ignore", encoding="utf-8")

    batch = score_reports_against_case_batch(case_path, reports_dir)

    assert batch.score_kind == "golden_case_batch_regression"
    assert batch.reports_scanned == 2
    assert batch.reports_scored == 2
    assert batch.average_score == 87.5
    assert batch.best_report == {"report_name": "a.md", "score": 100.0}
    assert batch.worst_report == {"report_name": "b.md", "score": 75.0}
    assert [item.report_name for item in batch.results] == ["a.md", "b.md"]
    assert batch.results[0].must_find_passed == 1
    assert batch.results[0].advantages_passed == 1


def test_score_reports_against_case_batch_returns_empty_batch_for_empty_directory(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text("case_id: demo_case\nmust_find: []\nmust_not: []\n", encoding="utf-8")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    batch = score_reports_against_case_batch(case_path, reports_dir)

    assert batch.reports_scanned == 0
    assert batch.reports_scored == 0
    assert batch.average_score is None
    assert batch.best_report is None
    assert batch.worst_report is None
    assert batch.results == []
    assert batch.failed_reports == []


def test_score_reports_against_case_batch_records_read_failures_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not: []
should_find_advantages: []
        """.strip(),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "ok.md").write_text("本合同约定80%预付款。", encoding="utf-8")
    (reports_dir / "broken.md").write_text("损坏报告", encoding="utf-8")

    original_read = golden_score._read_report_text

    def fake_read(report_path: Path) -> str:
        if report_path.name == "broken.md":
            raise UnicodeDecodeError("utf-8", b"x", 0, 1, "boom")
        return original_read(report_path)

    monkeypatch.setattr(golden_score, "_read_report_text", fake_read)

    batch = score_reports_against_case_batch(case_path, reports_dir)

    assert batch.reports_scanned == 2
    assert batch.reports_scored == 1
    assert len(batch.failed_reports) == 1
    assert batch.failed_reports[0]["report_name"] == "broken.md"
    assert "UnicodeDecodeError" in batch.failed_reports[0]["error"]


def test_format_batch_golden_summary_includes_core_fields(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not: []
should_find_advantages:
  - id: forum
    expected: 识别管辖优势
    evidence_keywords: ["甲方住所地", "管辖"]
        """.strip(),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "a.md").write_text(
        "本合同约定80%预付款。争议由甲方住所地法院管辖。",
        encoding="utf-8",
    )
    (reports_dir / "b.md").write_text("本合同约定80%预付款。", encoding="utf-8")

    batch = score_reports_against_case_batch(case_path, reports_dir)
    summary = format_batch_golden_summary(batch)

    assert "Batch golden-case regression summary" in summary
    assert "Reports scanned: 2" in summary
    assert "Reports scored: 2" in summary
    assert "Average score: 87.5" in summary
    assert "1. a.md — 100.0" in summary
    assert "Lowest report:" in summary


# ═══════════════════════════════════════════════════════════════════
# v2.16-D: Pattern → Production Rule alignment tests
# ═══════════════════════════════════════════════════════════════════


def test_all_patterns_aligned_to_production_rules():
    """Every golden pattern must have production rule coverage."""
    from contract_risk_analysis.evaluation.golden_score import (
        check_pattern_production_alignment,
        PATTERN_PRODUCTION_COVERAGE,
        load_golden_patterns,
    )

    patterns = load_golden_patterns("tests/fixtures/golden_patterns")
    report = check_pattern_production_alignment()

    assert report.patterns_checked == len(patterns), (
        f"Should check all {len(patterns)} patterns"
    )
    assert report.patterns_aligned == len(patterns), (
        f"All {len(patterns)} patterns should be aligned. "
        f"Unaligned: {[d['pattern_id'] for d in report.details if not d['aligned']]}"
    )
    assert report.all_aligned, "All patterns must be aligned to production rules"

    # Every pattern in the directory must have a PATTERN_PRODUCTION_COVERAGE entry
    for p in patterns:
        pid = p.get("pattern_id")
        assert pid in PATTERN_PRODUCTION_COVERAGE, (
            f"Pattern '{pid}' has no entry in PATTERN_PRODUCTION_COVERAGE. "
            f"Add an entry or mark it as aligned=False with a note."
        )


def test_pattern_alignment_report_exportable():
    """Alignment report must be exportable to dict for CLI/JSON output."""
    from contract_risk_analysis.evaluation.golden_score import (
        check_pattern_production_alignment,
    )

    report = check_pattern_production_alignment()
    d = report.to_dict()

    assert "patterns_checked" in d
    assert "patterns_aligned" in d
    assert "patterns_unaligned" in d
    assert "all_aligned" in d
    assert "details" in d
    assert isinstance(d["details"], list)
    assert len(d["details"]) == d["patterns_checked"]


def test_key_patterns_have_coverage_details():
    """Each aligned pattern must list at least one coverage layer."""
    from contract_risk_analysis.evaluation.golden_score import (
        check_pattern_production_alignment,
    )

    report = check_pattern_production_alignment()
    for detail in report.details:
        if detail["aligned"]:
            assert len(detail["coverage"]) >= 1, (
                f"Pattern '{detail['pattern_id']}' is marked aligned "
                f"but has no coverage details"
            )


# ═══════════════════════════════════════════════════════════════════
# v2.16-E: LLM-as-judge scaffolding tests
# ═══════════════════════════════════════════════════════════════════


def test_llm_judge_dimensions_sum_to_100():
    """All scoring dimensions must sum to exactly 100."""
    from contract_risk_analysis.evaluation.golden_score import (
        LLM_JUDGE_SCORING_DIMENSIONS,
    )

    total = sum(d["max_score"] for d in LLM_JUDGE_SCORING_DIMENSIONS.values())
    assert total == 100, f"Scoring dimensions must sum to 100, got {total}"


def test_llm_judge_dimensions_have_required_fields():
    """Each scoring dimension must have label, max_score, description, scoring_guidance."""
    from contract_risk_analysis.evaluation.golden_score import (
        LLM_JUDGE_SCORING_DIMENSIONS,
    )

    required_fields = {"label", "max_score", "description", "scoring_guidance"}
    for key, dim in LLM_JUDGE_SCORING_DIMENSIONS.items():
        missing = required_fields - set(dim.keys())
        assert not missing, (
            f"Dimension '{key}' missing required fields: {missing}"
        )


def test_llm_judge_prompt_includes_golden_case_criteria():
    """Judge prompt must reference golden case criteria when provided."""
    from contract_risk_analysis.evaluation.golden_score import build_llm_judge_prompt

    golden_case = {
        "case_id": "test",
        "must_find": [
            {"id": "prepayment", "expected": "识别80%预付款", "evidence_keywords": ["80%", "预付款"]},
        ],
        "must_not": [
            {"id": "wrong_cap", "forbidden": "不得主动增加责任上限"},
        ],
        "should_find_advantages": [
            {"id": "forum", "expected": "识别管辖优势"},
        ],
    }

    prompt = build_llm_judge_prompt("测试报告内容", golden_case=golden_case)

    assert "must_find" in prompt
    assert "must_not" in prompt
    assert "should_find_advantages" in prompt
    assert "prepayment" in prompt
    assert "wrong_cap" in prompt
    assert "forum" in prompt


def test_llm_judge_prompt_constrains_to_golden_standards():
    """Judge prompt must explicitly forbid self-defined scoring criteria."""
    from contract_risk_analysis.evaluation.golden_score import build_llm_judge_prompt

    prompt = build_llm_judge_prompt("测试报告")

    assert "不得自由制定评分标准" in prompt
    assert "JSON" in prompt
    assert "total_score" in prompt
    assert "overall_assessment" in prompt


def test_llm_judge_prompt_without_golden_case():
    """Judge prompt should work without golden case (generic evaluation)."""
    from contract_risk_analysis.evaluation.golden_score import build_llm_judge_prompt

    prompt = build_llm_judge_prompt("测试报告内容")
    # Should still include basic scoring framework
    assert "核心风险识别" in prompt
    assert "立场正确性" in prompt
    assert "BN使用合理性" in prompt
