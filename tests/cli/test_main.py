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
