from pathlib import Path

from contract_risk_analysis.cli import load_review_result


def test_load_review_result_populates_optional_schema_fields(tmp_path: Path) -> None:
    input_path = tmp_path / "review_result.json"
    input_path.write_text(
        """
        {
          "contract_id": "nda-002",
          "review_type": "nda",
          "source_document": "sample-contract.pdf",
          "findings": [
            {
              "clause_type": "termination",
              "status": "missing",
              "evidence_text": "No termination clause found.",
              "confidence": 0.91,
              "hypothesis": "Agreement contains a termination clause.",
              "risk_factor": "termination_risk"
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    review_result = load_review_result(input_path)

    assert review_result.contract_id == "nda-002"
    assert review_result.review_type == "nda"
    assert review_result.source_document == "sample-contract.pdf"
    assert review_result.findings[0].hypothesis == "Agreement contains a termination clause."
    assert review_result.findings[0].risk_factor == "termination_risk"
