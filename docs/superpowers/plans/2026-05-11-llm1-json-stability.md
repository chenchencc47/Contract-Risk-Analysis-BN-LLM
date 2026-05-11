# LLM₁ JSON Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/v2/review` resilient to one malformed LLM₁ JSON response and unify `negotiation_chip` as a structured object across parsing, adjudication, rendering, tests, and API output.

**Architecture:** Keep the existing free-review pipeline intact, but tighten the contract at the LLM₁ boundary. Introduce a dedicated `NegotiationChip` model, normalize legacy string input only at the parse boundary, and ensure all downstream code consumes objects instead of free-form strings.

**Tech Stack:** Python 3.11, FastAPI, dataclasses, pytest, OpenAI-compatible chat completions

---

## File map

- Modify: `src/contract_risk_analysis/domain/free_review_schema.py`
  - Add the `NegotiationChip` dataclass.
  - Update `RiskSegment.negotiation_chip` and `DossierRiskItem.negotiation_chip` to use `NegotiationChip | None`.
- Modify: `src/contract_risk_analysis/review/ai_review.py`
  - Change `_free_review_schema()` so `negotiation_chip` is a nullable object.
  - Add parse helpers that normalize `dict | str | None` into `NegotiationChip | None`.
  - Keep the single retry for malformed JSON.
- Modify: `src/contract_risk_analysis/review/adjudicate.py`
  - Replace string assignment for `seg.negotiation_chip` with `NegotiationChip` construction.
- Modify: `src/contract_risk_analysis/review/report_writer.py`
  - Replace string contains logic with explicit object-field reads.
  - Render structured chip data into text only at the output layer.
- Modify: `backend/routers/review.py`
  - Keep `asdict(...)`-based output so `negotiation_chip` is emitted as an object.
  - Add one API-level regression assertion through tests rather than hand-written formatting.
- Modify: `tests/review/test_ai_review.py`
  - Add parsing tests for object, `None`, legacy string downgrade, invalid object shape, and malformed JSON retry.
- Modify: `tests/regression/test_judgment_regression.py`
  - Update dossier fixtures that currently pass `negotiation_chip` as a string.
- Create if needed: `tests/review/test_report_writer_negotiation_chip.py`
  - Add focused rendering tests if `tests/review/test_ai_review.py` would become overloaded.

## Task 1: Introduce the structured chip model

**Files:**
- Modify: `src/contract_risk_analysis/domain/free_review_schema.py`
- Test: `tests/review/test_ai_review.py`

- [ ] **Step 1: Write the failing type-oriented test**

```python
from contract_risk_analysis.domain.free_review_schema import NegotiationChip, RiskSegment


def test_risk_segment_accepts_structured_negotiation_chip() -> None:
    segment = RiskSegment(
        clause_type="payment",
        risk_title="预付款比例过高",
        risk_description="test",
        evidence_text="甲方应支付80%预付款",
        confidence=0.9,
        severity="high",
        negotiation_chip=NegotiationChip(
            chip_type="交换筹码",
            location="第九条 付款方式",
            reason="预付款比例是卖方极想保留的条件",
            counterparty_attack="卖方会主张行业惯例需要高预付款",
            strategy="将预付款降到50%并交换交付条件",
        ),
    )

    assert segment.negotiation_chip is not None
    assert segment.negotiation_chip.chip_type == "交换筹码"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py::test_risk_segment_accepts_structured_negotiation_chip -v`
Expected: FAIL with `ImportError` or `TypeError` because `NegotiationChip` does not exist yet.

- [ ] **Step 3: Add the minimal data model**

```python
@dataclass
class NegotiationChip:
    chip_type: str | None = None
    location: str | None = None
    reason: str | None = None
    counterparty_attack: str | None = None
    strategy: str | None = None
```

And update the two fields:

```python
negotiation_chip: NegotiationChip | None = None
```

in both `RiskSegment` and `DossierRiskItem`.

- [ ] **Step 4: Re-run the test to verify it passes**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py::test_risk_segment_accepts_structured_negotiation_chip -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/domain/free_review_schema.py tests/review/test_ai_review.py
git commit -m "refactor: add structured negotiation chip model"
```

## Task 2: Parse structured chips at the LLM₁ boundary

**Files:**
- Modify: `src/contract_risk_analysis/review/ai_review.py`
- Test: `tests/review/test_ai_review.py`

- [ ] **Step 1: Write the failing parser tests**

```python
from contract_risk_analysis.review.ai_review import _parse_free_review_payload


def test_parse_free_review_payload_builds_structured_chip() -> None:
    payload = {
        "contract_id": "c1",
        "overall_assessment": "summary",
        "risk_segments": [
            {
                "clause_type": "payment",
                "risk_title": "预付款比例过高",
                "risk_description": "risk",
                "evidence_text": "80%预付款",
                "confidence": 0.95,
                "severity": "critical",
                "negotiation_chip": {
                    "chip_type": "交换筹码",
                    "location": "第九条",
                    "reason": "卖方极想保留",
                    "counterparty_attack": "行业惯例",
                    "strategy": "降到50%",
                },
            }
        ],
        "missing_clauses": [],
        "strengths": [],
    }

    result = _parse_free_review_payload(payload)

    assert result.risk_segments[0].negotiation_chip is not None
    assert result.risk_segments[0].negotiation_chip.location == "第九条"


def test_parse_free_review_payload_downgrades_legacy_chip_string() -> None:
    payload = {
        "contract_id": "c1",
        "overall_assessment": "summary",
        "risk_segments": [
            {
                "clause_type": "payment",
                "risk_title": "预付款比例过高",
                "risk_description": "risk",
                "evidence_text": "80%预付款",
                "confidence": 0.95,
                "severity": "critical",
                "negotiation_chip": "响应筹码",
            }
        ],
        "missing_clauses": [],
        "strengths": [],
    }

    result = _parse_free_review_payload(payload)

    assert result.risk_segments[0].negotiation_chip is not None
    assert result.risk_segments[0].negotiation_chip.chip_type == "响应筹码"
    assert result.risk_segments[0].negotiation_chip.reason == "响应筹码"


def test_parse_free_review_payload_rejects_invalid_chip_shape() -> None:
    payload = {
        "contract_id": "c1",
        "overall_assessment": "summary",
        "risk_segments": [
            {
                "clause_type": "payment",
                "risk_title": "预付款比例过高",
                "risk_description": "risk",
                "evidence_text": "80%预付款",
                "confidence": 0.95,
                "severity": "critical",
                "negotiation_chip": ["not", "valid"],
            }
        ],
        "missing_clauses": [],
        "strengths": [],
    }

    with pytest.raises(ValueError, match="negotiation_chip"):
        _parse_free_review_payload(payload)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py -k "structured_chip or downgrades_legacy_chip_string or invalid_chip_shape" -v`
Expected: FAIL because the parser still passes raw values straight into `RiskSegment(**item)`.

- [ ] **Step 3: Write the minimal parser implementation**

Add a dedicated helper in `ai_review.py`:

```python
def _parse_negotiation_chip(value: object) -> NegotiationChip | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return NegotiationChip(
            chip_type=value.get("chip_type"),
            location=value.get("location"),
            reason=value.get("reason"),
            counterparty_attack=value.get("counterparty_attack"),
            strategy=value.get("strategy"),
        )
    if isinstance(value, str):
        chip_type = value if value in {"底线筹码", "交换筹码", "响应筹码"} else None
        return NegotiationChip(
            chip_type=chip_type,
            reason=value,
        )
    raise ValueError("negotiation_chip 必须是对象、字符串或 null。")
```

Then change `_parse_free_review_payload()` to normalize each segment before constructing `RiskSegment`:

```python
normalized = dict(item)
normalized["negotiation_chip"] = _parse_negotiation_chip(item.get("negotiation_chip"))
segments.append(RiskSegment(**normalized))
```

- [ ] **Step 4: Update the LLM schema and prompt contract**

Replace the old nullable string schema entry with a nullable object schema:

```python
"negotiation_chip": {
    "anyOf": [
        {
            "type": "object",
            "properties": {
                "chip_type": _nullable_string(),
                "location": _nullable_string(),
                "reason": _nullable_string(),
                "counterparty_attack": _nullable_string(),
                "strategy": _nullable_string(),
            },
            "required": [
                "chip_type",
                "location",
                "reason",
                "counterparty_attack",
                "strategy",
            ],
            "additionalProperties": False,
        },
        {"type": "null"},
    ]
}
```

And replace the prompt description with a concrete object contract:

```python
"  - negotiation_chip: （可选）对象，包含 chip_type、location、reason、counterparty_attack、strategy\n"
```

- [ ] **Step 5: Re-run the tests to verify they pass**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py -k "structured_chip or downgrades_legacy_chip_string or invalid_chip_shape" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/contract_risk_analysis/review/ai_review.py tests/review/test_ai_review.py
git commit -m "fix: normalize negotiation chip at free review boundary"
```

## Task 3: Keep malformed JSON retry covered while tightening parsing

**Files:**
- Modify: `tests/review/test_ai_review.py`
- Modify if needed: `src/contract_risk_analysis/review/ai_review.py`
- Test: `tests/review/test_ai_review.py`

- [ ] **Step 1: Expand the retry regression to the structured world**

Use the existing retry test shape, but make the successful retry response include a structured chip:

```python
client = _DummyClient([
    '{"contract_id":"c1","overall_assessment":"x","risk_segments":[{"clause_type":"payment"',
    '{"contract_id":"c1","overall_assessment":"x","risk_segments":[{"clause_type":"payment","risk_title":"ok","risk_description":"ok","evidence_text":"ok","confidence":0.9,"severity":"high","negotiation_chip":{"chip_type":"交换筹码","location":"第九条","reason":"卖方极想保留","counterparty_attack":"行业惯例","strategy":"换取交付让步"}}],"missing_clauses":[],"strengths":[]}',
])
```

Assert:

```python
assert result.risk_segments[0].negotiation_chip is not None
assert result.risk_segments[0].negotiation_chip.strategy == "换取交付让步"
assert client.calls == 2
```

- [ ] **Step 2: Run the retry tests to verify current behavior**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py -k "retries_once_after_invalid_json or raises_after_second_invalid_json" -v`
Expected: If the new parser rejects the retried payload incorrectly, FAIL; otherwise PASS.

- [ ] **Step 3: Make the smallest fix needed**

If the retry test fails because the structured payload is rejected, adjust only `_parse_negotiation_chip(...)` or `_parse_free_review_payload(...)`. Keep the retry loop itself unchanged:

```python
except ValueError as exc:
    if "JSON 解析失败" not in str(exc) or attempt == 1:
        raise
```

- [ ] **Step 4: Re-run the retry tests**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py -k "retries_once_after_invalid_json or raises_after_second_invalid_json" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/ai_review.py tests/review/test_ai_review.py
git commit -m "test: cover malformed json retry with structured chips"
```

## Task 4: Convert adjudication writes to structured chips

**Files:**
- Modify: `src/contract_risk_analysis/review/adjudicate.py`
- Test: `tests/review/test_ai_review.py` or `tests/review/test_adjudicate.py` if created

- [ ] **Step 1: Write the failing adjudication test**

```python
from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, RiskSegment
from contract_risk_analysis.review.adjudicate import adjudicate


def test_adjudicate_assigns_structured_chip_from_party_rule() -> None:
    output = FreeReviewOutput(
        contract_id="c1",
        overall_assessment="summary",
        risk_segments=[
            RiskSegment(
                clause_type="liability_cap",
                risk_title="无责任上限",
                risk_description="desc",
                evidence_text="evidence",
                confidence=0.9,
                severity="high",
                canonical_type="liability_cap",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    result = adjudicate(output, review_party="buyer")

    chip = result.risk_segments[0].negotiation_chip
    assert chip is not None
    assert chip.chip_type in {"底线筹码", "交换筹码", "响应筹码"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review -k "assigns_structured_chip_from_party_rule" -v`
Expected: FAIL because `adjudicate.py` still writes a bare string.

- [ ] **Step 3: Write the minimal adjudication implementation**

Replace the current assignment:

```python
if chip and not seg.negotiation_chip:
    seg.negotiation_chip = chip
```

with:

```python
if chip and not seg.negotiation_chip:
    seg.negotiation_chip = NegotiationChip(
        chip_type=chip,
        reason=note or chip,
    )
```

Add the needed import:

```python
from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, NegotiationChip
```

- [ ] **Step 4: Re-run the test to verify it passes**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review -k "assigns_structured_chip_from_party_rule" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/adjudicate.py tests/review
git commit -m "refactor: emit structured chips from adjudication"
```

## Task 5: Remove string-based chip logic from report writing

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py`
- Modify: `tests/regression/test_judgment_regression.py`
- Create if needed: `tests/review/test_report_writer_negotiation_chip.py`

- [ ] **Step 1: Write the failing rendering tests**

```python
from contract_risk_analysis.domain.free_review_schema import DossierRiskItem, NegotiationChip


def test_positive_chip_maps_to_favorable_term_type() -> None:
    risk = DossierRiskItem(
        issue_id="ISSUE-test-001",
        risk_title="无责任上限",
        clause_type="liability_cap",
        severity="positive",
        priority_rank=5,
        evidence_text="test",
        confidence=1.0,
        negotiation_chip=NegotiationChip(
            chip_type="响应筹码",
            location="责任条款",
            reason="对买方有利",
            counterparty_attack="卖方将主张无限责任过重",
            strategy="以责任范围调整交换付款让步",
        ),
    )

    assert risk.negotiation_chip is not None
    assert risk.negotiation_chip.chip_type == "响应筹码"
```

And add a dossier formatting regression:

```python
def test_dossier_detail_renders_structured_chip_fields() -> None:
    ...
    assert "筹码类型：交换筹码" in section
    assert "换取交付让步" in section
```

- [ ] **Step 2: Run the rendering tests to verify they fail**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/regression/test_judgment_regression.py -v`
Expected: FAIL because the regression fixture still passes strings and `report_writer.py` still assumes string operations.

- [ ] **Step 3: Write the minimal report writer implementation**

Replace string contains logic with explicit field access. For example, replace:

```python
chip = item.negotiation_chip or ""
is_defensive = any(kw in chip for kw in _defensive_chip_keywords)
```

with:

```python
chip = item.negotiation_chip
chip_type = chip.chip_type if chip else ""
is_defensive = chip_type in {"响应筹码", "底线筹码"}
```

Replace favorable-term extraction:

```python
chip_type=item.negotiation_chip or "",
```

with:

```python
chip_type=item.negotiation_chip.chip_type if item.negotiation_chip else "",
```

Replace dossier detail rendering:

```python
if item.negotiation_chip:
    lines.append(f"- 筹码类型：{item.negotiation_chip.chip_type or '未标注'}")
    if item.negotiation_chip.reason:
        lines.append(f"- 筹码原因：{item.negotiation_chip.reason}")
    if item.negotiation_chip.strategy:
        lines.append(f"- 应对策略：{item.negotiation_chip.strategy}")
```

- [ ] **Step 4: Update the regression fixtures**

Replace string fixtures like:

```python
negotiation_chip="响应筹码",
```

with:

```python
negotiation_chip=NegotiationChip(
    chip_type="响应筹码",
    reason="响应筹码",
),
```

- [ ] **Step 5: Re-run the rendering tests**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/regression/test_judgment_regression.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/contract_risk_analysis/review/report_writer.py tests/regression/test_judgment_regression.py tests/review
git commit -m "refactor: render structured negotiation chips"
```

## Task 6: Verify API output and full review behavior

**Files:**
- Modify if needed: `backend/routers/review.py`
- Test: `tests/review/test_ai_review.py`
- Test: live `/api/v2/review` request

- [ ] **Step 1: Write the API-shape regression test**

If a lightweight router/unit test exists, assert that `asdict(...)` emits nested chip fields:

```python
def test_fact_sheet_emits_structured_negotiation_chip() -> None:
    item = DossierRiskItem(
        issue_id="ISSUE-1",
        risk_title="预付款比例过高",
        clause_type="payment",
        severity="high",
        priority_rank=1,
        evidence_text="80%预付款",
        confidence=0.9,
        negotiation_chip=NegotiationChip(
            chip_type="交换筹码",
            location="第九条",
            reason="卖方想保留",
            counterparty_attack="行业惯例",
            strategy="降到50%",
        ),
    )
    payload = asdict(item)
    assert payload["negotiation_chip"]["chip_type"] == "交换筹码"
```

- [ ] **Step 2: Run the targeted tests**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py tests/regression/test_judgment_regression.py -q`
Expected: PASS

- [ ] **Step 3: Confirm router output does not need custom serialization**

Inspect `backend/routers/review.py` and keep this code unchanged if tests are green:

```python
"risk_segments": [asdict(s) for s in free_output.risk_segments],
```

and:

```python
"negotiation_chip": item.negotiation_chip,
```

Only change the router if serialization tests prove it is necessary.

- [ ] **Step 4: Run live API verification**

Run:

```bash
"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" - <<'PY'
import requests
contract = '''买卖合同
甲方（买方）：北京测试科技有限公司
乙方（卖方）：上海设备制造有限公司
第一条 合同标的：乙方向甲方出售水质监测设备一套。
第二条 合同金额：本合同总价款为人民币1535万元整。
第三条 交付：甲方收货地点为北京市辖区范围内。甲方经核对产品数量无误及对产品质量进行初验收并签字确认后，视为乙方已交付。
第九条 付款方式：甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款。
第十三条 争议解决：因本合同引起的争议，向甲方住所地人民法院提起诉讼。'''
resp = requests.post(
    'http://localhost:9527/api/v2/review',
    json={'contract_text': contract, 'contract_id': 'plan-api-check', 'review_party': 'buyer'},
    timeout=600,
)
body = resp.json()
print(resp.status_code)
print(type(body['free_review']['risk_segments'][0].get('negotiation_chip')).__name__)
print(body['free_review']['risk_segments'][0].get('negotiation_chip'))
print(body['fact_sheet']['risk_items'][0].get('negotiation_chip'))
PY
```

Expected:
- First line: `200`
- Second line: `dict` or `NoneType`
- Printed chip payloads show nested keys like `chip_type`, `reason`, `strategy`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/review.py tests/review/test_ai_review.py tests/regression/test_judgment_regression.py src/contract_risk_analysis/review/report_writer.py src/contract_risk_analysis/review/adjudicate.py src/contract_risk_analysis/review/ai_review.py src/contract_risk_analysis/domain/free_review_schema.py
git commit -m "fix: stabilize free review chip contract"
```

## Task 7: Run the final verification suite

**Files:**
- No new files
- Test: `tests/review/test_ai_review.py`
- Test: `tests/regression/test_judgment_regression.py`
- Test: live `/api/v2/review`

- [ ] **Step 1: Run the focused unit and regression suite**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/review/test_ai_review.py tests/regression/test_judgment_regression.py -q`
Expected: PASS

- [ ] **Step 2: Run the broader project smoke suite if it already passes on this branch**

Run: `"E:/myProgram/BN-Contract-Risk-Analysis/.venv/Scripts/python.exe" -m pytest tests/ -q`
Expected: PASS, or known pre-existing unrelated failures only. If unrelated failures exist, record them explicitly before stopping.

- [ ] **Step 3: Run the live API smoke check again**

Run the same verification script from Task 6 Step 4.
Expected: `200` response with structured or null `negotiation_chip` fields.

- [ ] **Step 4: Review git diff before handoff**

Run: `git diff -- src/contract_risk_analysis/domain/free_review_schema.py src/contract_risk_analysis/review/ai_review.py src/contract_risk_analysis/review/adjudicate.py src/contract_risk_analysis/review/report_writer.py backend/routers/review.py tests/review/test_ai_review.py tests/regression/test_judgment_regression.py`
Expected: Only the planned contract, parser, renderer, and test changes.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/domain/free_review_schema.py src/contract_risk_analysis/review/ai_review.py src/contract_risk_analysis/review/adjudicate.py src/contract_risk_analysis/review/report_writer.py backend/routers/review.py tests/review/test_ai_review.py tests/regression/test_judgment_regression.py
git commit -m "test: verify structured negotiation chip pipeline"
```
