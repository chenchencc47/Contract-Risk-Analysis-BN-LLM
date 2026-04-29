import json
from pathlib import Path

from contract_risk_analysis import benchmark_runner


def test_benchmark_runner_compares_full_and_p0(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "review.json"
    input_path.write_text(
        json.dumps(
            {
                "contract_id": "nda-bench-001",
                "findings": [
                    {
                        "clause_type": "termination",
                        "status": "missing",
                        "evidence_text": "No termination clause found.",
                        "confidence": 0.91,
                        "finding_key": "termination_clause_missing",
                        "finding_label": "终止条款缺失",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    benchmark_runner.main([str(input_path)])

    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_id"] == "nda-bench-001"
    assert "full" in payload
    assert "p0" in payload
