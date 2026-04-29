import asyncio
import json

import contract_risk_analysis.web.server as server
from contract_risk_analysis.domain.review_schema import LegalIssueReport, ReviewFinding, ReviewResult
from contract_risk_analysis.review.report_writer import PolishedReport


class _DummyRequest:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def json(self):
        return self._payload


def test_api_review_passes_allowed_priorities_to_build_evidence(monkeypatch):
    monkeypatch.setattr(
        server,
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

    captured: dict[str, object] = {}

    def fake_build_evidence(review_result, allowed_priorities=None):
        captured["contract_id"] = review_result.contract_id
        captured["allowed_priorities"] = allowed_priorities
        from contract_risk_analysis.pipeline.build_evidence import build_evidence as real_build_evidence

        return real_build_evidence(review_result, allowed_priorities=allowed_priorities)

    monkeypatch.setattr(server, "build_evidence", fake_build_evidence)
    monkeypatch.setattr(server, "polish_report", lambda _report: (_ for _ in ()).throw(RuntimeError("skip polish")))

    response = asyncio.run(
        server.api_review(
            _DummyRequest(
                {
                    "contract_text": "Termination is not described.",
                    "contract_id": "nda-web-001",
                    "allowed_priorities": ["P0"],
                }
            )
        )
    )

    payload = json.loads(response.body.decode("utf-8"))
    assert payload["contract_id"] == "nda-web-001"
    assert captured["allowed_priorities"] == {"P0"}


def test_api_review_can_return_debug_payload(monkeypatch):
    monkeypatch.setattr(
        server,
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
    monkeypatch.setattr(server, "polish_report", lambda _report: (_ for _ in ()).throw(RuntimeError("skip polish")))

    response = asyncio.run(
        server.api_review(
            _DummyRequest(
                {
                    "contract_text": "Termination is not described.",
                    "contract_id": "nda-web-002",
                    "include_debug": True,
                }
            )
        )
    )

    payload = json.loads(response.body.decode("utf-8"))
    assert payload["contract_id"] == "nda-web-002"
    assert "debug" in payload
    assert "evidence_items" in payload["debug"]
    assert "node_observations" in payload["debug"]


def test_api_review_includes_polished_issue_reports(monkeypatch):
    monkeypatch.setattr(
        server,
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

    def fake_polish_report(report):
        return PolishedReport(
            executive_summary="整体中风险。",
            dimension_insights={"legal_enforceability_risk": "存在终止条款缺失问题。"},
            signing_advice="建议补齐关键条款后签署。",
            action_plan=["补充终止条款"],
            cross_dimension_notes=[],
            issue_reports=[
                LegalIssueReport(
                    issue_id="issue_001",
                    title="终止条款缺失",
                    risk_level="medium",
                    problem_analysis="合同缺少终止机制。",
                    original_clause="No express termination clause found.",
                    legal_basis="根据合同法一般原则，终止机制应明确。",
                    best_practice="通常约定提前通知与终止后义务。",
                    suggested_revision="任一方可提前30日书面通知终止合同。",
                    revision_reason="平衡双方退出机制。",
                )
            ],
        )

    monkeypatch.setattr(server, "polish_report", fake_polish_report)

    response = asyncio.run(
        server.api_review(
            _DummyRequest(
                {
                    "contract_text": "Termination is not described.",
                    "contract_id": "nda-web-003",
                }
            )
        )
    )

    payload = json.loads(response.body.decode("utf-8"))
    assert payload["contract_id"] == "nda-web-003"
    polished = payload["report"]["polished"]
    assert polished["issue_reports"][0]["title"] == "终止条款缺失"
