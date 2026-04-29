import contract_risk_analysis.demo.report_page as report_page
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult
from tests.demo.test_streamlit_app import _DummyColumn, _DummyExpander, _DummySidebar


class _DummyReportSidebar(_DummySidebar):
    def __init__(self, text_payload: str = "") -> None:
        super().__init__()
        self._text_payload = text_payload

    def file_uploader(self, label, *_args, **_kwargs):
        if "TXT / MD" in label and self._text_payload:
            from tests.demo.test_streamlit_app import _DummyUploadedFile

            return _DummyUploadedFile(self._text_payload, name="contract.md")
        return None

    def text_area(self, *_args, **_kwargs):
        return self._text_payload or "# NDA\n\nTermination is not described."


class _DummyMetricRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    def __call__(self, label, value, delta=None):
        self.calls.append((label, value, delta))


def test_main_renders_report_page(monkeypatch) -> None:
    sidebar = _DummyReportSidebar("# NDA\n\nTermination is not described.")
    json_calls: list[object] = []
    markdown_calls: list[str] = []
    metric_recorder = _DummyMetricRecorder()

    monkeypatch.setattr(report_page.st, "set_page_config", lambda **_kwargs: None)
    monkeypatch.setattr(report_page.st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "expander", lambda *_args, **_kwargs: _DummyExpander())
    monkeypatch.setattr(report_page.st, "markdown", lambda value, **_kwargs: markdown_calls.append(value))
    monkeypatch.setattr(report_page.st, "sidebar", sidebar)
    monkeypatch.setattr(report_page.st, "columns", lambda count, **_kwargs: tuple(_DummyColumn() for _ in range(count)))
    monkeypatch.setattr(report_page.st, "metric", metric_recorder)
    monkeypatch.setattr(report_page.st, "subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "json", lambda value, **_kwargs: json_calls.append(value))
    monkeypatch.setattr(report_page.st, "code", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "table", lambda value, **_kwargs: json_calls.append(value))
    monkeypatch.setattr(report_page, "review_contract_text", lambda contract_text, contract_id, source_document=None: ReviewResult(
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

    report_page.main()

    assert any(call[0] == "总体风险" for call in metric_recorder.calls)
    assert any("风险摘要" in value for value in markdown_calls)
    assert any("整改建议" in value for value in markdown_calls)
    assert any(isinstance(item, list) for item in json_calls)
    assert any(isinstance(item, dict) and item.get("termination_clause") == "missing" for item in json_calls)


def test_main_renders_bn_driven_sections_from_report(monkeypatch) -> None:
    sidebar = _DummyReportSidebar("# NDA\n\nTermination is not described.")
    markdown_calls: list[str] = []
    metric_recorder = _DummyMetricRecorder()

    monkeypatch.setattr(report_page.st, "set_page_config", lambda **_kwargs: None)
    monkeypatch.setattr(report_page.st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "expander", lambda *_args, **_kwargs: _DummyExpander())
    monkeypatch.setattr(report_page.st, "markdown", lambda value, **_kwargs: markdown_calls.append(value))
    monkeypatch.setattr(report_page.st, "sidebar", sidebar)
    monkeypatch.setattr(report_page.st, "columns", lambda count, **_kwargs: tuple(_DummyColumn() for _ in range(count)))
    monkeypatch.setattr(report_page.st, "metric", metric_recorder)
    monkeypatch.setattr(report_page.st, "subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "code", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page, "review_contract_text", lambda contract_text, contract_id, source_document=None: ReviewResult(
        contract_id=contract_id,
        review_type="nda",
        source_document=source_document,
        findings=[],
    ))
    monkeypatch.setattr(report_page, "build_demo_view_model", lambda _review_result: {
        "contract_id": "nda-report-001",
        "findings": [],
        "evidence": {"termination_clause_completeness": "missing"},
        "triggered_findings": [],
        "report": {
            "contract_id": "nda-report-001",
            "overall_risk": "high",
            "requires_manual_review": True,
            "summary_reasons": ["终止条款缺失"],
            "signing_recommendation": "暂不建议直接签署",
            "dimension_scores": {
                "legal_enforceability_risk": 0.81,
                "financial_exposure_risk": 0.22,
            },
            "dimension_summaries": {
                "legal_enforceability_risk": "合同在终止机制或适用法律上存在明显缺口，法律执行路径不稳定。",
                "financial_exposure_risk": "财务责任暴露整体可控。",
            },
            "top_risks": [
                {
                    "title": "终止条款完整性",
                    "dimension": "legal_enforceability_risk",
                    "risk_level": "high",
                    "reason": "终止条款缺失",
                    "evidence": ["No termination clause found."],
                    "recommendation": "补充终止条件、通知周期和解除后责任。",
                }
            ],
            "manual_review_items": ["请人工复核：终止条款完整性——补充终止条件、通知周期和解除后责任。"],
        },
        "report_json": "{}",
    })

    report_page.main()

    assert any(call[0] == "签署建议" and call[1] == "暂不建议直接签署" for call in metric_recorder.calls)
    assert any("维度风险" in value for value in markdown_calls)
    assert any("法律可执行性风险" in value for value in markdown_calls)
    assert any("人工复核项" in value for value in markdown_calls)
    assert any("暂不建议直接签署" in value for value in markdown_calls)


def test_main_prefers_issue_reports_when_present(monkeypatch) -> None:
    sidebar = _DummyReportSidebar("# NDA\n\nTermination is not described.")
    markdown_calls: list[str] = []
    metric_recorder = _DummyMetricRecorder()

    monkeypatch.setattr(report_page.st, "set_page_config", lambda **_kwargs: None)
    monkeypatch.setattr(report_page.st, "title", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "expander", lambda *_args, **_kwargs: _DummyExpander())
    monkeypatch.setattr(report_page.st, "markdown", lambda value, **_kwargs: markdown_calls.append(value))
    monkeypatch.setattr(report_page.st, "sidebar", sidebar)
    monkeypatch.setattr(report_page.st, "columns", lambda count, **_kwargs: tuple(_DummyColumn() for _ in range(count)))
    monkeypatch.setattr(report_page.st, "metric", metric_recorder)
    monkeypatch.setattr(report_page.st, "subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "code", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page.st, "table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(report_page, "review_contract_text", lambda contract_text, contract_id, source_document=None: ReviewResult(
        contract_id=contract_id,
        review_type="nda",
        source_document=source_document,
        findings=[],
    ))
    monkeypatch.setattr(report_page, "build_demo_view_model", lambda _review_result: {
        "contract_id": "nda-report-002",
        "findings": [],
        "evidence": {"termination_clause_completeness": "missing"},
        "triggered_findings": [],
        "report": {
            "contract_id": "nda-report-002",
            "overall_risk": "medium",
            "requires_manual_review": False,
            "summary_reasons": ["终止条款缺失"],
            "signing_recommendation": "有条件签署",
            "dimension_scores": {"legal_enforceability_risk": 0.62},
            "dimension_summaries": {"legal_enforceability_risk": "存在终止机制缺口。"},
            "top_risks": [],
            "manual_review_items": [],
            "polished": {
                "issue_reports": [
                    {
                        "issue_id": "issue_001",
                        "title": "终止条款缺失",
                        "risk_level": "medium",
                        "problem_analysis": "合同缺少终止机制。",
                        "original_clause": "No express termination clause found.",
                        "legal_basis": "终止机制应明确。",
                        "best_practice": "约定通知期和终止后责任。",
                        "suggested_revision": "任一方可提前30日书面通知终止合同。",
                        "revision_reason": "平衡双方退出机制。"
                    }
                ]
            },
        },
        "report_json": "{}",
    })

    report_page.main()

    assert any("问题分析" in value for value in markdown_calls)
    assert any("建议修改为" in value for value in markdown_calls)
