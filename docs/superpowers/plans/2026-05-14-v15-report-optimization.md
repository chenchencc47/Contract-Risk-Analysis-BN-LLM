# v15 Report Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the next buy-side report beat `contract-review-买卖合同-15.md` on the two biggest validated gaps: deterministic business-impact quantification and deterministic concession/exchange ratios, while keeping the existing stance and BN guardrails intact.

**Architecture:** Keep the current v2 pipeline (`LLM₁ → adjudication/BN → Dossier → LLM₂`) and add one narrow quantitative layer between `free_output` and `ReportDossier`. That layer extracts contract-value anchors only when the contract text itself supports them, threads them into the Dossier, and makes Chapter 3/4/5 consume those anchors verbatim instead of inventing numbers. Strengthen the pre-render lint so unsupported money/range claims are rejected unless they can be traced to contract evidence, BN output, or the new deterministic quantitative context.

**Tech Stack:** Python, FastAPI, pytest

---

## File Structure

### New production file

- `src/contract_risk_analysis/review/quantification.py`
  - Owns deterministic extraction of contract amount, payment percentages, milestone amounts, and exchange-rate hints like “每10个百分点≈153.5万元”.
  - Keeps quantification logic out of the already-large `report_writer.py`.

### Existing files to modify

- `src/contract_risk_analysis/domain/free_review_schema.py`
  - Add frozen quantitative-context dataclasses and attach them to `ReportDossier`.

- `backend/routers/review.py:127-408`
  - Build quantitative context from `contract_text` and `free_output`, pass it into `_build_dossier()`, and expose it in `fact_sheet` for inspection.

- `src/contract_risk_analysis/review/report_writer.py:977-1151`
  - Keep current renderer rules, but add explicit quantitative-use rules to `_combined_system_prompt()` and `_counterfactual_takeaway()` consumers.

- `src/contract_risk_analysis/review/report_writer.py:1154-1377`
  - Accept and preserve deterministic quantitative context inside `_build_dossier()`.

- `src/contract_risk_analysis/review/report_writer.py:1380-1518`
  - Upgrade `_run_pre_render_consistency_checks()` from phrase-based numeric lint to source-aware numeric lint.

- `src/contract_risk_analysis/review/report_writer.py:1521-1758`
  - Add a Dossier section for quantitative anchors and prefilled exchange-rate hints.

- `src/contract_risk_analysis/review/report_writer.py:1875-2107`
  - Force Chapter 3/4/5 to use deterministic quantitative anchors when present, and to explicitly refuse amount-level quantification when absent.

- `src/contract_risk_analysis/review/ai_review.py:466-569`
  - Strengthen LLM₁ instructions so `commercial_impact` and `strategy` preserve visible percentages/amounts/days from the contract, without schema changes.

### Test files

- Create: `tests/review/test_quantification.py`
  - Unit tests for deterministic amount/percentage extraction and exchange-rate hint generation.

- Modify: `tests/review/test_report_writer_negotiation_chip.py`
  - Dossier formatting, prompt, and lint regression tests for the new quantitative layer.

- Modify: `tests/review/test_ai_review.py`
  - Prompt-level tests for the strengthened LLM₁ quantitative instructions.

- Modify: `tests/regression/test_judgment_regression.py`
  - End-to-end dossier/regression coverage proving the new quantitative layer does not break existing stance guardrails.

- Modify: `worklist/PROGRESS.md`
  - Record the completed implementation after tests pass.

### No frontend changes in this plan

The user’s requested improvement is report quality, not UI. Existing frontend already shows the report faithfully, and project memory says report content must remain complete.

---

### Task 1 (P0): Add deterministic quantitative-context extraction

**Files:**
- Create: `src/contract_risk_analysis/review/quantification.py`
- Modify: `src/contract_risk_analysis/domain/free_review_schema.py:16-318`
- Test: `tests/review/test_quantification.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/review/test_quantification.py` with these tests:

```python
from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, RiskSegment
from contract_risk_analysis.review.quantification import build_quantitative_context


def test_build_quantitative_context_extracts_contract_amount_and_payment_anchor() -> None:
    contract_text = (
        "合同总价为人民币1535万元。"
        "甲方于合同签订后10日内支付合同金额的80%作为预付款。"
    )
    free_output = FreeReviewOutput(
        contract_id="sales-001",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高，造成重大资金敞口。",
                evidence_text="甲方于合同签订后10日内支付合同金额的80%作为预付款。",
                confidence=0.95,
                severity="high",
                canonical_type="payment_structure",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    ctx = build_quantitative_context(contract_text, free_output)

    assert ctx.contract_amount == 15_350_000
    assert ctx.quantification_allowed is True
    assert ctx.payment_anchors[0].percentage == 80
    assert ctx.payment_anchors[0].amount == 12_280_000
    assert "每降低10个百分点≈人民币1,535,000元" in ctx.exchange_rate_hints


def test_build_quantitative_context_refuses_money_quantification_without_total_price() -> None:
    contract_text = "甲方于合同签订后10日内支付合同金额的80%作为预付款。"
    free_output = FreeReviewOutput(
        contract_id="sales-002",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高。",
                evidence_text="甲方于合同签订后10日内支付合同金额的80%作为预付款。",
                confidence=0.90,
                severity="high",
                canonical_type="payment_structure",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    ctx = build_quantitative_context(contract_text, free_output)

    assert ctx.contract_amount is None
    assert ctx.quantification_allowed is False
    assert ctx.payment_anchors[0].percentage == 80
    assert ctx.payment_anchors[0].amount is None
    assert "缺少合同总价，禁止把百分比换算成金额" in ctx.warnings
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_quantification.py -q
```

Expected: FAIL because `review/quantification.py` and the new quantitative dataclasses do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

In `src/contract_risk_analysis/domain/free_review_schema.py`, add these dataclasses near the other frozen report-side models:

```python
@dataclass(frozen=True)
class QuantitativeAnchor:
    label: str
    percentage: float | None = None
    amount: float | None = None
    days: int | None = None
    source_text: str = ""
    formula: str = ""


@dataclass(frozen=True)
class QuantitativeContext:
    contract_amount: float | None = None
    currency_label: str = "人民币"
    amount_source_text: str = ""
    quantification_allowed: bool = False
    payment_anchors: list[QuantitativeAnchor] = field(default_factory=list)
    exchange_rate_hints: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

And extend `ReportDossier` with:

```python
quantitative_context: QuantitativeContext | None = None
```

Create `src/contract_risk_analysis/review/quantification.py` with:

```python
from __future__ import annotations

import re

from contract_risk_analysis.domain.free_review_schema import (
    FreeReviewOutput,
    QuantitativeAnchor,
    QuantitativeContext,
)

_AMOUNT_PATTERNS = [
    re.compile(r"合同总价(?:为|：|:)?人民币?\s*([0-9]+(?:\.[0-9]+)?)万元"),
    re.compile(r"合同总价(?:为|：|:)?人民币?\s*([0-9][0-9,]*(?:\.[0-9]+)?)元"),
]
_PERCENT_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)%")


def _parse_contract_amount(contract_text: str) -> tuple[float | None, str]:
    for pattern in _AMOUNT_PATTERNS:
        match = pattern.search(contract_text)
        if not match:
            continue
        raw = match.group(1).replace(",", "")
        if "万元" in match.group(0):
            return float(raw) * 10_000, match.group(0)
        return float(raw), match.group(0)
    return None, ""


def _fmt_money(value: float) -> str:
    return f"人民币{value:,.0f}元"


def build_quantitative_context(contract_text: str, free_output: FreeReviewOutput) -> QuantitativeContext:
    contract_amount, source_text = _parse_contract_amount(contract_text)
    anchors: list[QuantitativeAnchor] = []
    warnings: list[str] = []
    hints: list[str] = []

    for seg in free_output.risk_segments:
        if (seg.canonical_type or seg.clause_type) != "payment_structure":
            continue
        match = _PERCENT_PATTERN.search(f"{seg.evidence_text} {seg.risk_description}")
        if not match:
            continue
        percentage = float(match.group(1))
        amount = round(contract_amount * percentage / 100, 2) if contract_amount is not None else None
        anchors.append(
            QuantitativeAnchor(
                label=seg.risk_title,
                percentage=percentage,
                amount=amount,
                source_text=seg.evidence_text,
                formula=(
                    f"{_fmt_money(contract_amount)} × {percentage:.0f}%"
                    if contract_amount is not None else ""
                ),
            )
        )

    if contract_amount is not None:
        hints.append(f"每降低10个百分点≈{_fmt_money(contract_amount * 0.10)}")
    elif anchors:
        warnings.append("缺少合同总价，禁止把百分比换算成金额")

    return QuantitativeContext(
        contract_amount=contract_amount,
        amount_source_text=source_text,
        quantification_allowed=contract_amount is not None,
        payment_anchors=anchors,
        exchange_rate_hints=hints,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_quantification.py -q
```

Expected: PASS for the two new tests.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/domain/free_review_schema.py src/contract_risk_analysis/review/quantification.py tests/review/test_quantification.py
git commit -m "feat: add deterministic report quantification context"
```

---

### Task 2 (P0): Thread quantitative context into the Dossier and response fact sheet

**Files:**
- Modify: `backend/routers/review.py:127-408`
- Modify: `src/contract_risk_analysis/review/report_writer.py:1154-1377`
- Modify: `tests/review/test_report_writer_negotiation_chip.py`
- Modify: `tests/regression/test_judgment_regression.py`

- [ ] **Step 1: Write the failing tests**

Add this test to `tests/review/test_report_writer_negotiation_chip.py`:

```python
from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, QuantitativeContext
from contract_risk_analysis.review.report_writer import _build_dossier


def test_build_dossier_preserves_quantitative_context() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    quantitative_context = QuantitativeContext(
        contract_amount=15_350_000,
        amount_source_text="合同总价为人民币1535万元",
        quantification_allowed=True,
        exchange_rate_hints=["每降低10个百分点≈人民币1,535,000元"],
    )

    dossier = _build_dossier(
        free_output,
        None,
        "buyer",
        quantitative_context=quantitative_context,
    )

    assert dossier.quantitative_context is not None
    assert dossier.quantitative_context.contract_amount == 15_350_000
    assert dossier.quantitative_context.exchange_rate_hints == [
        "每降低10个百分点≈人民币1,535,000元"
    ]
```

Add this regression test to `tests/regression/test_judgment_regression.py`:

```python
def test_quantitative_context_does_not_change_liability_cap_guardrails():
    from contract_risk_analysis.domain.free_review_schema import (
        FreeReviewOutput,
        QuantitativeContext,
        RiskSegment,
    )
    from contract_risk_analysis.review.report_writer import _build_dossier

    free_output = FreeReviewOutput(
        contract_id="test",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="liability_cap",
                risk_title="无责任上限",
                risk_description="对买方是优势。",
                evidence_text="合同未设置责任上限。",
                confidence=0.9,
                severity="positive",
                canonical_type="liability_cap",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    dossier = _build_dossier(
        free_output,
        None,
        "buyer",
        quantitative_context=QuantitativeContext(contract_amount=15_350_000, quantification_allowed=True),
    )

    assert len(dossier.risk_items) == 0
    assert len(dossier.favorable_terms) == 1
    assert dossier.favorable_terms[0].term_name == "无责任上限"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py tests/regression/test_judgment_regression.py -q
```

Expected: FAIL because `_build_dossier()` does not yet accept `quantitative_context`.

- [ ] **Step 3: Write the minimal implementation**

Change `_build_dossier()` in `src/contract_risk_analysis/review/report_writer.py` from:

```python
def _build_dossier(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None,
    review_party: str = "buyer",
) -> ReportDossier:
```

to:

```python
def _build_dossier(
    free_output: FreeReviewOutput,
    consistency: ConsistencyReport | None,
    review_party: str = "buyer",
    quantitative_context: QuantitativeContext | None = None,
) -> ReportDossier:
```

And in the return value add:

```python
quantitative_context=quantitative_context,
```

In `backend/routers/review.py`, build and pass the context before `_build_dossier()`:

```python
from contract_risk_analysis.review.quantification import build_quantitative_context
from contract_risk_analysis.review.report_writer import _build_dossier

quantitative_context = build_quantitative_context(contract_text, free_output)
dossier = _build_dossier(
    free_output,
    consistency,
    review_party,
    quantitative_context=quantitative_context,
)
```

Also expose it in `fact_sheet`:

```python
"quantitative_context": asdict(dossier.quantitative_context) if dossier.quantitative_context else None,
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py tests/regression/test_judgment_regression.py -q
```

Expected: PASS, and existing stance/guardrail tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/review.py src/contract_risk_analysis/review/report_writer.py tests/review/test_report_writer_negotiation_chip.py tests/regression/test_judgment_regression.py
git commit -m "feat: thread report quantification through dossier"
```

---

### Task 3 (P0): Make Chapter 3/4/5 consume deterministic quantitative anchors

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py:977-1151`
- Modify: `src/contract_risk_analysis/review/report_writer.py:1521-1758`
- Modify: `src/contract_risk_analysis/review/report_writer.py:1875-2107`
- Modify: `tests/review/test_report_writer_negotiation_chip.py`
- Modify: `tests/review/test_report_writer.py`

- [ ] **Step 1: Write the failing tests**

Add this test to `tests/review/test_report_writer_negotiation_chip.py`:

```python
from contract_risk_analysis.domain.free_review_schema import QuantitativeContext, ReportDossier
from contract_risk_analysis.review.report_writer import _fmt_dossier_section


def test_dossier_section_includes_quantitative_strategy_anchors() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        favorable_terms=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="overall",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        quantitative_context=QuantitativeContext(
            contract_amount=15_350_000,
            amount_source_text="合同总价为人民币1535万元",
            quantification_allowed=True,
            exchange_rate_hints=["每降低10个百分点≈人民币1,535,000元"],
        ),
    )

    text = _fmt_dossier_section(dossier)

    assert "### 量化策略锚点（系统计算——仅当来源可追溯时允许使用）" in text
    assert "合同总价：人民币15,350,000元" in text
    assert "每降低10个百分点≈人民币1,535,000元" in text
```

Add this test to `tests/review/test_report_writer.py`:

```python
from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, QuantitativeContext, ReportDossier
from contract_risk_analysis.review.report_writer import _build_combined_prompt


def test_combined_prompt_refuses_amount_quantification_when_total_price_missing() -> None:
    free_output = FreeReviewOutput(
        contract_id="test",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        favorable_terms=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="overall",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        quantitative_context=QuantitativeContext(
            contract_amount=None,
            quantification_allowed=False,
            warnings=["缺少合同总价，禁止把百分比换算成金额"],
        ),
    )

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "缺少合同总价时，不得把百分比换算成金额" in prompt
    assert "因合同总价未明示，暂不做金额量化" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py tests/review/test_report_writer.py -q
```

Expected: FAIL because the Dossier section and combined prompt do not yet mention quantitative anchors or the “no total price, no money quantification” rule.

- [ ] **Step 3: Write the minimal implementation**

In `_fmt_dossier_section()` in `src/contract_risk_analysis/review/report_writer.py`, add this block after the signing-guardrail section and before the chip-linkage matrix:

```python
    if dossier.quantitative_context:
        qc = dossier.quantitative_context
        lines.append("### 量化策略锚点（系统计算——仅当来源可追溯时允许使用）")
        lines.append("")
        if qc.contract_amount is not None:
            lines.append(f"- 合同总价：人民币{qc.contract_amount:,.0f}元")
            if qc.amount_source_text:
                lines.append(f"- 金额来源：{qc.amount_source_text}")
        else:
            lines.append("- 合同总价：未从合同原文中稳定提取")
        for anchor in qc.payment_anchors:
            if anchor.amount is not None:
                lines.append(
                    f"- {anchor.label}：{anchor.percentage:.0f}% ≈ 人民币{anchor.amount:,.0f}元"
                )
            else:
                lines.append(f"- {anchor.label}：{anchor.percentage:.0f}%（仅可保留百分比，不得换算金额）")
        for hint in qc.exchange_rate_hints:
            lines.append(f"- 交换比率提示：{hint}")
        for warning in qc.warnings:
            lines.append(f"- 量化限制：{warning}")
        lines.append("")
```

In `_build_combined_prompt()`, add this rule block inside the prompt before the chapter-structure instructions:

```python
### 量化写作规则（本次优化重点，强制执行）

- 如果 Dossier 提供了“量化策略锚点”，第三章的商业影响、第四章的优化建议、第五章的交换比率必须优先原样使用这些数字。
- 允许直接引用的数字只有三类：
  1. Dossier 的量化策略锚点
  2. Dossier/BN 已冻结的反事实概率数字
  3. 合同原文证据中的金额、比例、天数
- 如果 Dossier 明确显示缺少合同总价时，不得把百分比换算成金额。
  必须写明：“因合同总价未明示，暂不做金额量化，仅保留比例级判断。”
- 第五章至少写出一个量化交换比率；如果没有可追溯金额，只能写比例/天数级交换比率，不得编造金额。
```

And in `_combined_system_prompt()` add one short hard rule:

```python
f"7. 任何金额化表达都必须可追溯到合同原文、Dossier量化锚点或BN冻结数字；"
f"如果总价未明示，禁止把百分比自行换算成金额。\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py tests/review/test_report_writer.py -q
```

Expected: PASS, including the new Dossier and prompt assertions.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/report_writer.py tests/review/test_report_writer_negotiation_chip.py tests/review/test_report_writer.py
git commit -m "feat: anchor report strategy to deterministic quantitative context"
```

---

### Task 4 (P1): Strengthen LLM₁ quantitative instructions without changing schema

**Files:**
- Modify: `src/contract_risk_analysis/review/ai_review.py:466-569`
- Modify: `tests/review/test_ai_review.py`

- [ ] **Step 1: Write the failing tests**

Add this test to `tests/review/test_ai_review.py`:

```python
from contract_risk_analysis.review.ai_review import _free_review_prompt


def test_free_review_prompt_requires_traceable_quantitative_hints() -> None:
    prompt = _free_review_prompt(
        contract_text="合同总价为人民币1535万元，签约后支付80%预付款。",
        contract_id="sales-001",
        source_document=None,
        review_party="buyer",
    )

    assert "如合同原文出现百分比、金额、天数，必须在 commercial_impact 或 strategy 中原样引用" in prompt
    assert "未出现合同总价时，不得自行把百分比换算成金额" in prompt
    assert "如果合同原文明示总价，可说明换算依据" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_ai_review.py -q
```

Expected: FAIL because the current prompt does not require these quantitative behaviors.

- [ ] **Step 3: Write the minimal implementation**

Append this sentence cluster to `_build_chip_instruction()` in `src/contract_risk_analysis/review/ai_review.py`:

```python
        + "如合同原文出现百分比、金额、天数等可直接引用的数字，"
        "请在 commercial_impact 或 strategy 字段中原样引用这些数字，"
        "帮助后续报告形成可追溯的量化分析。"
        "未出现合同总价时，不得自行把百分比换算成金额。"
        "如果合同原文明示总价，可说明换算依据，如‘合同总价1535万元，80%预付款≈1228万元’。\n"
```

Do not add any new JSON fields. The output contract stays exactly the same.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_ai_review.py -q
```

Expected: PASS, with no schema-level regressions in existing prompt/parser tests.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/ai_review.py tests/review/test_ai_review.py
git commit -m "feat: require traceable quantitative hints in llm1 prompt"
```

---

### Task 5 (P1): Replace phrase-based numeric lint with source-aware numeric lint

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py:1380-1518`
- Modify: `tests/review/test_report_writer_negotiation_chip.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/review/test_report_writer_negotiation_chip.py`:

```python
from contract_risk_analysis.domain.free_review_schema import QuantitativeContext, ReportDossier
from contract_risk_analysis.review.report_writer import _run_pre_render_consistency_checks


def test_consistency_checks_allow_traceable_contract_amount_numbers() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        favorable_terms=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="整体风险较高，80%预付款对应人民币12,280,000元。",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        quantitative_context=QuantitativeContext(
            contract_amount=15_350_000,
            quantification_allowed=True,
            exchange_rate_hints=["每降低10个百分点≈人民币1,535,000元"],
        ),
    )

    violations = _run_pre_render_consistency_checks(dossier)

    assert not any("无来源数字" in msg for msg in violations)


def test_consistency_checks_flag_untraceable_freeform_range_numbers() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        favorable_terms=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="追回预付款的诉讼成本约60-150万元，成功回收率低于60%。",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        quantitative_context=QuantitativeContext(
            contract_amount=15_350_000,
            quantification_allowed=True,
        ),
    )

    violations = _run_pre_render_consistency_checks(dossier)

    assert any("无来源数字" in msg for msg in violations)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: FAIL because current lint is still phrase-based and does not know which numbers are actually allowed.

- [ ] **Step 3: Write the minimal implementation**

In `src/contract_risk_analysis/review/report_writer.py`, add a helper above `_run_pre_render_consistency_checks()`:

```python
def _allowed_numeric_tokens(dossier: ReportDossier) -> set[str]:
    tokens: set[str] = set()

    def collect(text: str) -> None:
        for token in re.findall(r"[0-9]+(?:\.[0-9]+)?%|人民币[0-9,]+元|[0-9]+(?:\.[0-9]+)?万元", text):
            tokens.add(token)

    for item in dossier.risk_items:
        collect(item.evidence_text)
        if item.commercial_impact:
            collect(item.commercial_impact)
    if dossier.quantitative_context:
        qc = dossier.quantitative_context
        if qc.contract_amount is not None:
            collect(f"人民币{qc.contract_amount:,.0f}元")
        for hint in qc.exchange_rate_hints:
            collect(hint)
    for cf in dossier.counterfactuals:
        collect(f"{cf.delta_high_risk:.1%}")
        for dd in cf.dimension_deltas:
            collect(f"{dd.base_high:.1%}")
            collect(f"{dd.counterfactual_high:.1%}")
            collect(f"{dd.delta:.1%}")
    return tokens
```

Then replace the current hardcoded marker check at the end of `_run_pre_render_consistency_checks()` with:

```python
    allowed_tokens = _allowed_numeric_tokens(dossier)
    suspicious_ranges = re.findall(r"[0-9]+(?:\.[0-9]+)?-[0-9]+(?:\.[0-9]+)?万元", "\n".join(visible_texts))
    for token in suspicious_ranges:
        if token not in allowed_tokens:
            violations.append(
                f"无来源数字问题：用户可见文本中出现不可追溯区间数字「{token}」。"
                f"正式报告中的金额区间必须来自合同原文、Dossier量化锚点或BN冻结输出。"
            )
```

Keep the existing placeholder and internal-ID checks. Do not widen this into a generic “ban all numbers” rule.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS. Traceable `1535万元/1228万元/80%`-style numbers remain allowed; invented `60-150万元` ranges are blocked.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/report_writer.py tests/review/test_report_writer_negotiation_chip.py
git commit -m "feat: make report numeric lint source-aware"
```

---

### Task 6 (P2): Run the focused suite and record the checkpoint

**Files:**
- Modify: `worklist/PROGRESS.md`
- Test: `tests/review/test_quantification.py`
- Test: `tests/review/test_report_writer.py`
- Test: `tests/review/test_report_writer_negotiation_chip.py`
- Test: `tests/review/test_ai_review.py`
- Test: `tests/regression/test_judgment_regression.py`

- [ ] **Step 1: Run the focused suite**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_quantification.py tests/review/test_report_writer.py tests/review/test_report_writer_negotiation_chip.py tests/review/test_ai_review.py tests/regression/test_judgment_regression.py -q
```

Expected: PASS for all touched report-generation, prompt, and regression tests.

- [ ] **Step 2: Update the progress log**

Add a new top entry to `worklist/PROGRESS.md` in the existing format:

```md
## 2026-05-14：v15 报告量化与交换比率增强完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 新增确定性量化上下文提取（合同总价/预付款比例/金额换算） | `src/contract_risk_analysis/review/quantification.py` `src/contract_risk_analysis/domain/free_review_schema.py` | ✅ |
| 2 | 将量化上下文接入 Dossier / fact_sheet | `backend/routers/review.py` `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | 第三/四/五章改为优先消费可追溯量化锚点 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 4 | LLM₁ prompt 补强数字引用纪律 | `src/contract_risk_analysis/review/ai_review.py` | ✅ |
| 5 | 客户版报告数字 lint 升级为来源感知 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 6 | 回归与渲染测试补强 | `tests/review/test_quantification.py` `tests/review/test_report_writer.py` `tests/review/test_report_writer_negotiation_chip.py` `tests/review/test_ai_review.py` `tests/regression/test_judgment_regression.py` | ✅ |
```

- [ ] **Step 3: Re-run the focused suite after the progress update**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_quantification.py tests/review/test_report_writer.py tests/review/test_report_writer_negotiation_chip.py tests/review/test_ai_review.py tests/regression/test_judgment_regression.py -q
```

Expected: PASS again.

- [ ] **Step 4: Commit**

```bash
git add worklist/PROGRESS.md src/contract_risk_analysis/domain/free_review_schema.py src/contract_risk_analysis/review/quantification.py src/contract_risk_analysis/review/report_writer.py src/contract_risk_analysis/review/ai_review.py backend/routers/review.py tests/review/test_quantification.py tests/review/test_report_writer.py tests/review/test_report_writer_negotiation_chip.py tests/review/test_ai_review.py tests/regression/test_judgment_regression.py
git commit -m "feat: add deterministic report quantification and exchange anchors"
```

---

## Self-Review

### Spec coverage

- **商业影响量化** → Tasks 1-3
- **量化交换比率体系** → Tasks 1-3
- **不编造数字 / 数字可追溯** → Tasks 3-5
- **保留现有立场与BN护栏** → Task 2 + regression coverage in Tasks 2 and 6
- **实施记录** → Task 6

### Placeholder scan

Checked for `TODO`, `TBD`, “implement later”, and “similar to Task N”. None remain.

### Type consistency

- New types are consistently named `QuantitativeAnchor` and `QuantitativeContext`.
- `ReportDossier.quantitative_context` is the only new Dossier field introduced.
- `build_quantitative_context()` is the single quantitative entry point.
- Existing `golden_score`, stance rules, and BN interpretation rules are intentionally unchanged.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-14-v15-report-optimization.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**