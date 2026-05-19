import json
from pathlib import Path

from contract_risk_analysis import cli
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult


def test_main_reads_explicit_input_path_and_prints_report(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "custom_review_result.json"
    input_path.write_text(
        """
        {
          "contract_id": "nda-003",
          "findings": [
            {
              "clause_type": "termination",
              "status": "missing",
              "evidence_text": "No termination clause found.",
              "confidence": 0.91,
              "finding_key": "termination_clause_missing",
              "finding_label": "终止条款缺失"
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    cli.main([str(input_path)])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["contract_id"] == "nda-003"
    assert payload["overall_risk"] == "medium"
    assert payload["requires_manual_review"] is False
    assert payload["signing_recommendation"] == "有条件签署"
    assert payload["dimension_scores"]["legal_enforceability_risk"] == 0.4675
    assert payload["top_risks"][0]["title"] == "终止条款完整性"
    assert payload["top_risks"][0]["reason"] == "终止条款缺失"


def test_main_reviews_contract_text_and_prints_report(tmp_path: Path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "contract.txt"
    input_path.write_text("Termination is not described.", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "review_contract_text",
        lambda contract_text, contract_id, source_document=None: ReviewResult(
            contract_id=contract_id,
            review_type="nda",
            source_document=source_document,
            findings=[
                ReviewFinding(
                    clause_type="termination",
                    status="missing",
                    evidence_text="No termination clause found.",
                    confidence=0.91,
                    finding_key="termination_clause_missing",
                    finding_label="终止条款缺失",
                )
            ],
        ),
    )

    cli.main([
        "--contract-text-path",
        str(input_path),
        "--contract-id",
        "nda-text-001",
    ])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["contract_id"] == "nda-text-001"
    assert payload["overall_risk"] == "medium"
    assert payload["signing_recommendation"] == "有条件签署"
    assert payload["top_risks"][0]["reason"] == "终止条款缺失"


def test_main_dump_review_json_prints_review_result_before_report(tmp_path: Path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "contract.txt"
    input_path.write_text("Termination is not described.", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "review_contract_text",
        lambda contract_text, contract_id, source_document=None: ReviewResult(
            contract_id=contract_id,
            review_type="nda",
            source_document=source_document,
            findings=[
                ReviewFinding(
                    clause_type="termination",
                    status="missing",
                    evidence_text="No termination clause found.",
                    confidence=0.91,
                    finding_key="termination_clause_missing",
                    finding_label="终止条款缺失",
                )
            ],
        ),
    )

    cli.main([
        "--contract-text-path",
        str(input_path),
        "--contract-id",
        "nda-text-002",
        "--dump-review-json",
    ])

    output = capsys.readouterr().out.strip()
    report_start = output.rfind("\n{\n  \"contract_id\": \"nda-text-002\",")
    review_payload = json.loads(output[:report_start].strip())
    report_payload = json.loads(output[report_start + 1 :])

    assert review_payload["contract_id"] == "nda-text-002"
    assert review_payload["findings"][0]["finding_key"] == "termination_clause_missing"
    assert review_payload["findings"][0]["finding_label"] == "终止条款缺失"
    assert report_payload["signing_recommendation"] == "有条件签署"
    assert report_payload["top_risks"][0]["reason"] == "终止条款缺失"


def test_main_passes_allowed_priority_to_report_render(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "load_review_result",
        lambda _path: ReviewResult(
            contract_id="nda-rollout-cli",
            findings=[
                ReviewFinding(
                    clause_type="termination",
                    status="missing",
                    evidence_text="No termination clause found.",
                    confidence=0.91,
                    finding_key="termination_clause_missing",
                    finding_label="终止条款缺失",
                )
            ],
        ),
    )

    captured: dict[str, object] = {}

    def fake_render(review_result, allowed_priorities=None):
        captured["contract_id"] = review_result.contract_id
        captured["allowed_priorities"] = allowed_priorities
        return '{"ok": true}'

    monkeypatch.setattr(cli, "render_report_payload", fake_render)

    cli.main(["--allowed-priority", "P0"])

    output = capsys.readouterr().out.strip()
    assert output == '{"ok": true}'
    assert captured["contract_id"] == "nda-rollout-cli"
    assert captured["allowed_priorities"] == {"P0"}


def test_main_scores_golden_case(tmp_path: Path, capsys) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not:
  - id: wrong_cap
    forbidden: 不得主动增加责任上限
    wrong_patterns: ["主动增加责任上限"]
should_find_advantages: []
        """.strip(),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.md"
    report_path.write_text("本报告识别80%预付款风险。", encoding="utf-8")

    cli.main([
        "--score-golden-case",
        str(case_path),
        "--report",
        str(report_path),
    ])

    payload = json.loads(capsys.readouterr().out)
    assert payload["case_id"] == "demo_case"
    assert payload["score"] == 100.0
    assert payload["summary"]["must_find"] == "1/1"
    assert payload["summary"]["must_not"] == "1/1"


def test_main_scores_golden_case_batch(tmp_path: Path, capsys) -> None:
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

    cli.main([
        "--score-golden-case-batch",
        str(case_path),
        "--reports-dir",
        str(reports_dir),
    ])

    output = capsys.readouterr().out.strip()
    json_start = output.rfind("\n{\n")
    summary_text = output[:json_start].strip()
    payload = json.loads(output[json_start + 1 :])

    assert "Batch golden-case regression summary" in summary_text
    assert "Reports scanned: 2" in summary_text
    assert "Average score: 87.5" in summary_text
    assert payload["score_kind"] == "golden_case_batch_regression"
    assert payload["reports_scored"] == 2
    assert payload["best_report"]["report_name"] == "a.md"


def test_main_score_golden_case_batch_requires_reports_dir() -> None:
    try:
        cli.main(["--score-golden-case-batch", "case.yaml"])
    except SystemExit as exc:
        assert str(exc) == "--score-golden-case-batch requires --reports-dir"
    else:
        raise AssertionError("Expected SystemExit")


def test_main_lists_golden_patterns(tmp_path: Path, capsys) -> None:
    patterns_dir = tmp_path / "patterns"
    patterns_dir.mkdir()
    (patterns_dir / "demo.yaml").write_text(
        """
pattern_id: demo_pattern
pattern_name: 示例模式
status: candidate
source_cases: [demo_case]
applies_to:
  contract_types: [买卖合同]
  review_stances: [buyer]
        """.strip(),
        encoding="utf-8",
    )

    cli.main([
        "--list-golden-patterns",
        "--golden-patterns-dir",
        str(patterns_dir),
    ])

    payload = json.loads(capsys.readouterr().out)
    assert payload["patterns"][0]["pattern_id"] == "demo_pattern"
    assert payload["patterns"][0]["pattern_name"] == "示例模式"


def test_main_score_golden_case_requires_report() -> None:
    try:
        cli.main(["--score-golden-case", "case.yaml"])
    except SystemExit as exc:
        assert str(exc) == "--score-golden-case requires --report"
    else:
        raise AssertionError("Expected SystemExit")


def test_main_can_print_debug_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "load_review_result",
        lambda _path: ReviewResult(
            contract_id="nda-debug-cli",
            findings=[
                ReviewFinding(
                    clause_type="termination",
                    status="missing",
                    evidence_text="No termination clause found.",
                    confidence=0.91,
                    finding_key="termination_clause_missing",
                    finding_label="终止条款缺失",
                )
            ],
        ),
    )

    cli.main(["--debug-output"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_id"] == "nda-debug-cli"
    assert "evidence_items" in payload
    assert "node_observations" in payload
