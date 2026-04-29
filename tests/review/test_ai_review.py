import pytest

from contract_risk_analysis.domain.review_schema import ReviewResult
from contract_risk_analysis.review.ai_review import _completion_to_payload, _parse_review_result_payload


class _DummyMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _DummyChoice:
    def __init__(self, content: str) -> None:
        self.message = _DummyMessage(content)


class _DummyCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_DummyChoice(content)]


def test_parse_review_result_payload_returns_review_result() -> None:
    payload = {
        "contract_id": "nda-ai-001",
        "review_type": "nda",
        "source_document": "inline-text",
        "findings": [
            {
                "clause_type": "termination",
                "status": "missing",
                "evidence_text": "No termination clause found.",
                "confidence": 0.91,
            }
        ],
    }

    review_result = _parse_review_result_payload(payload)

    assert isinstance(review_result, ReviewResult)
    assert review_result.contract_id == "nda-ai-001"
    assert review_result.findings[0].clause_type == "termination"


def test_parse_review_result_payload_accepts_fine_grained_finding_fields() -> None:
    payload = {
        "contract_id": "nda-ai-002",
        "review_type": "sales_contract",
        "source_document": "contract.md",
        "findings": [
            {
                "clause_type": "termination",
                "status": "missing",
                "evidence_text": "No termination clause found.",
                "confidence": 0.91,
                "finding_key": "termination_clause_missing",
                "finding_label": "终止条款缺失",
                "counterparty_favorability": "buyer_favorable",
            }
        ],
    }

    review_result = _parse_review_result_payload(payload)

    finding = review_result.findings[0]
    assert finding.finding_key == "termination_clause_missing"
    assert finding.finding_label == "终止条款缺失"
    assert finding.counterparty_favorability == "buyer_favorable"


def test_parse_review_result_payload_rejects_missing_findings() -> None:
    with pytest.raises(ValueError, match="findings"):
        _parse_review_result_payload({"contract_id": "nda-ai-001"})


def test_completion_to_payload_reads_json_from_message_content() -> None:
    completion = _DummyCompletion('{"contract_id": "nda-ai-001", "findings": []}')

    payload = _completion_to_payload(completion)

    assert payload["contract_id"] == "nda-ai-001"
