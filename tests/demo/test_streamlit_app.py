import json

import pytest

import contract_risk_analysis.demo.streamlit_app as streamlit_app
from contract_risk_analysis.demo.streamlit_app import _recalculate_report, _review_result_from_json_text, apply_overrides, build_demo_view_model
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult


class _DummyExpander:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyUploadedFile:
    def __init__(self, payload_text: str, name: str = "uploaded.json") -> None:
        self._payload_text = payload_text
        self.name = name

    def getvalue(self) -> bytes:
        return self._payload_text.encode("utf-8")


class _DummySidebar:
    def __init__(self, payload_text: str = "") -> None:
        self._payload_text = payload_text
        self.errors: list[str] = []

    def header(self, *_args, **_kwargs) -> None:
        return None

    def file_uploader(self, label, *_args, **_kwargs):
        if "JSON" in label and self._payload_text:
            return _DummyUploadedFile(self._payload_text)
        return None

    def success(self, *_args, **_kwargs) -> None:
        return None

    def info(self, *_args, **_kwargs) -> None:
        return None

    def error(self, message: str) -> None:
        self.errors.append(message)

    def radio(self, *_args, **_kwargs):
        return "结构化审查结果 JSON" if self._payload_text else "合同文本 AI 审查"

    def text_input(self, *_args, **_kwargs):
        return "nda-text-001"

    def text_area(self, *_args, **_kwargs):
        return "Termination is not described."

    def button(self, *_args, **_kwargs):
        return True

    def selectbox(self, _label, options, index=0, **_kwargs):
        return options[index]

    def slider(self, _label, _min_value, _max_value, value, _step, **_kwargs):
        return value


class _StopCalled(Exception):
    pass


class _DummyColumn:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def test_build_demo_view_model_returns_findings_evidence_and_report() -> None:
    review_result = ReviewResult(
        contract_id="nda-006",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No termination clause found.",
                confidence=0.91,
            ),
            ReviewFinding(
                clause_type="liability_cap",
                status="acceptable",
                evidence_text="Liability cap is limited.",
                confidence=0.77,
            ),
        ],
    )

    view_model = build_demo_view_model(review_result)

    assert view_model["contract_id"] == "nda-006"
    assert len(view_model["findings"]) == 2
    assert view_model["evidence"]["termination_clause"] == "missing"
    assert view_model["evidence"]["liability_cap"] == "acceptable"
    assert view_model["report"]["overall_risk"] == "medium"
    assert view_model["report"]["requires_manual_review"] is False
    assert json.loads(view_model["report_json"])["contract_id"] == "nda-006"


def test_review_result_from_json_text_rejects_payload_without_findings() -> None:
    with pytest.raises(ValueError, match="findings"):
        _review_result_from_json_text('{"contract_id": "nda-001", "overall_risk": "high"}')


def test_main_shows_error_when_uploaded_json_has_no_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    sidebar = _DummySidebar('{"contract_id": "nda-001", "overall_risk": "high"}')

    monkeypatch.setattr(streamlit_app.st, "set_page_config", lambda **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "expander", lambda *_args, **_kwargs: _DummyExpander())
    monkeypatch.setattr(streamlit_app.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "sidebar", sidebar)
    monkeypatch.setattr(streamlit_app.st, "stop", lambda: (_ for _ in ()).throw(_StopCalled()))

    with pytest.raises(_StopCalled):
        streamlit_app.main()

    assert sidebar.errors
    assert "findings" in sidebar.errors[0]


def test_main_renders_ai_review_result(monkeypatch: pytest.MonkeyPatch) -> None:
    sidebar = _DummySidebar()
    json_calls: list[object] = []

    monkeypatch.setattr(streamlit_app.st, "set_page_config", lambda **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "expander", lambda *_args, **_kwargs: _DummyExpander())
    monkeypatch.setattr(streamlit_app.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "sidebar", sidebar)
    monkeypatch.setattr(streamlit_app.st, "columns", lambda *_args, **_kwargs: (_DummyColumn(), _DummyColumn()))
    monkeypatch.setattr(streamlit_app.st, "subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "json", lambda value, **_kwargs: json_calls.append(value))
    monkeypatch.setattr(streamlit_app.st, "code", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app, "review_contract_text", lambda contract_text, contract_id, source_document=None: ReviewResult(
        contract_id=contract_id,
        review_type="nda",
        source_document=source_document,
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No termination clause found.",
                confidence=0.91,
            )
        ],
    ))

    streamlit_app.main()

    assert any(isinstance(item, list) for item in json_calls)
    assert any(isinstance(item, dict) and item.get("termination_clause") == "missing" for item in json_calls)


def test_main_accepts_markdown_upload_for_ai_review(monkeypatch: pytest.MonkeyPatch) -> None:
    sidebar = _DummySidebar()
    json_calls: list[object] = []

    def file_uploader(label, *_args, **_kwargs):
        if "TXT / MD" in label:
            return _DummyUploadedFile("# NDA\n\nTermination is not described.", name="contract.md")
        return None

    sidebar.file_uploader = file_uploader

    monkeypatch.setattr(streamlit_app.st, "set_page_config", lambda **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "expander", lambda *_args, **_kwargs: _DummyExpander())
    monkeypatch.setattr(streamlit_app.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "sidebar", sidebar)
    monkeypatch.setattr(streamlit_app.st, "columns", lambda *_args, **_kwargs: (_DummyColumn(), _DummyColumn()))
    monkeypatch.setattr(streamlit_app.st, "subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app.st, "json", lambda value, **_kwargs: json_calls.append(value))
    monkeypatch.setattr(streamlit_app.st, "code", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(streamlit_app, "review_contract_text", lambda contract_text, contract_id, source_document=None: ReviewResult(
        contract_id=contract_id,
        review_type="nda",
        source_document=source_document,
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No termination clause found.",
                confidence=0.91,
            )
        ],
    ))

    streamlit_app.main()

    assert any(isinstance(item, list) for item in json_calls)


def test_apply_overrides_replaces_node_states_and_key_cpt_values() -> None:
    base_view_model = {
        "evidence": {
            "termination_clause": "missing",
            "liability_cap": "acceptable",
            "confidentiality_nli": "entailment",
        },
        "network_config": {
            "cpts": {
                "termination_risk": {"missing": 0.85, "present": 0.2},
                "liability_risk": {"unfavorable": 0.8, "acceptable": 0.1},
                "confidentiality_risk": {"contradiction": 0.8, "entailment": 0.15, "neutral": 0.45},
                "overall_legal_risk": {"high|low|low": {"high": 0.2, "medium": 0.55, "low": 0.25}},
            }
        },
    }

    overridden = apply_overrides(
        base_view_model,
        node_overrides={"termination_clause": "present"},
        cpt_overrides={"termination_risk.present": 0.35},
    )

    assert overridden["evidence"]["termination_clause"] == "present"
    assert overridden["network_config"]["cpts"]["termination_risk"]["present"] == 0.35



def test_build_demo_view_model_keeps_supporting_evidence_for_rich_bn_flow() -> None:
    review_result = ReviewResult(
        contract_id="nda-007",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No express termination clause found.",
                confidence=0.94,
                finding_key="termination_clause_missing",
                finding_label="终止条款缺失",
            )
        ],
    )

    view_model = build_demo_view_model(review_result)

    assert view_model["evidence"]["termination_clause_completeness"] == "missing"
    assert view_model["supporting_findings_by_node"]["termination_clause_completeness"] == ["终止条款缺失"]
    assert view_model["supporting_evidence_by_node"]["termination_clause_completeness"] == ["No express termination clause found."]
    assert "signing_recommendation" in view_model["report"]



def test_recalculate_report_preserves_supporting_evidence_context() -> None:
    view_model = {
        "contract_id": "nda-008",
        "evidence": {"termination_clause_completeness": "missing"},
        "triggered_findings": ["termination_clause_missing:missing"],
        "supporting_findings_by_node": {"termination_clause_completeness": ["终止条款缺失"]},
        "supporting_evidence_by_node": {"termination_clause_completeness": ["No express termination clause found."]},
        "network_config": streamlit_app.load_network_config(),
        "report": {},
        "report_json": "",
    }

    recalculated = _recalculate_report(view_model)

    assert recalculated["report"]["top_risks"]
    assert recalculated["report"]["top_risks"][0]["reason"] == "终止条款缺失"
    assert recalculated["report"]["top_risks"][0]["evidence"] == ["No express termination clause found."]


def test_build_demo_view_model_exposes_node_observations() -> None:
    review_result = ReviewResult(
        contract_id="nda-009",
        findings=[
            ReviewFinding(
                clause_type="termination",
                status="missing",
                evidence_text="No express termination clause found.",
                confidence=0.94,
                finding_key="termination_clause_missing",
                finding_label="终止条款缺失",
            )
        ],
    )

    view_model = build_demo_view_model(review_result)

    assert "node_observations" in view_model
    assert view_model["node_observations"]
    assert view_model["node_observations"][0]["node_name"] == "termination_clause_completeness"
