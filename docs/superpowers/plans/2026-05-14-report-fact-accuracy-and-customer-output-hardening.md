# Report Fact Accuracy and Customer Output Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the next buy-side report source-faithful to the original contract and safe for customer delivery by fixing deterministic amount extraction, removing internal-only renderer leakage from customer output, and tightening clause analysis around early delivery / risk-transfer ambiguity.

**Architecture:** Keep the current `LLM₁ → adjudication/BN → Dossier → LLM₂` pipeline, but harden two deterministic boundaries: (1) source-fact extraction before the Dossier is built, and (2) customer-facing rendering after the Dossier is frozen. Amount recognition should become more tolerant of table/OCR-style contract text, while customer output should stop exposing internal QA / renderer-note mechanics directly in the main narrative report. Clause-level interpretation changes should stay narrow and source-backed.

**Tech Stack:** Python, FastAPI, pytest

---

## File Structure

### Existing production files to modify

- `src/contract_risk_analysis/review/quantification.py`
  - Harden deterministic contract-amount extraction so source text like `总价 15,350,000元` and table/OCR variants are recognized.

- `backend/routers/review.py`
  - Preserve the richer fact sheet output, but prepare for customer/internal output separation without changing API shape more than necessary.

- `src/contract_risk_analysis/review/report_writer.py`
  - Split customer-facing narrative constraints from internal QA / renderer-note content.
  - Tighten customer-output rules around internal IDs, internal conflicts, and dual-sided clause analysis.

- `src/contract_risk_analysis/review/ai_review.py`
  - Refine LLM₁ prompt guidance for clauses like `视为交付` so risks and surviving buyer protections are both captured.

### Existing test files to modify

- `tests/review/test_quantification.py`
  - Add regression tests for table-style total-price extraction and OCR-tolerant variants.

- `tests/review/test_report_writer.py`
  - Add customer-facing rendering regression tests.

- `tests/review/test_report_writer_negotiation_chip.py`
  - Add Dossier/render separation assertions if needed.

- `tests/review/test_ai_review.py`
  - Add prompt-level guardrail assertions for dual-sided early-delivery / risk-transfer analysis.

### Tracking files to modify

- `worklist/worklist-v2/WORKLIST.md`
  - Switch current mainline from Stage B completion to the new source-fact / customer-output hardening track.

- `worklist/worklist-v2/PROGRESS.md`
  - Record plan creation, implementation checkpoint, and next continuation entry.

---

### Task 1 (P0): Fix deterministic contract-amount extraction for real contract text

**Files:**
- Modify: `src/contract_risk_analysis/review/quantification.py`
- Modify: `tests/review/test_quantification.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/review/test_quantification.py`:

```python
def test_build_quantitative_context_extracts_table_style_total_price() -> None:
    contract_text = (
        "货物名称：终端设备。单价153,500元，数量100台，总价15,350,000元。"
        "甲方于本合同签订后10日内支付合同金额的80%作为预付款。"
    )
    free_output = FreeReviewOutput(
        contract_id="sales-003",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高。",
                evidence_text="甲方于本合同签订后10日内支付合同金额的80%作为预付款。",
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
    assert ctx.payment_anchors[0].amount == 12_280_000


def test_build_quantitative_context_extracts_spaced_total_price() -> None:
    contract_text = (
        "合同货物总价 人民币 15,350,000 元。"
        "甲方于本合同签订后10日内支付合同金额的80%作为预付款。"
    )
    free_output = FreeReviewOutput(
        contract_id="sales-004",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="预付款比例过高。",
                evidence_text="甲方于本合同签订后10日内支付合同金额的80%作为预付款。",
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_quantification.py -q
```

Expected: FAIL because `_parse_contract_amount()` only matches a narrow `合同总价为...` shape.

- [ ] **Step 3: Write minimal implementation**

In `src/contract_risk_analysis/review/quantification.py`, widen the amount patterns so they accept:

```python
_AMOUNT_PATTERNS = [
    re.compile(r"合同总价(?:为|：|:)?\s*人民币?\s*([0-9]+(?:\.[0-9]+)?)\s*万元"),
    re.compile(r"合同总价(?:为|：|:)?\s*人民币?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*元"),
    re.compile(r"(?:合同货物)?总价(?:为|：|:)?\s*人民币?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*元"),
    re.compile(r"总金额(?:为|：|:)?\s*人民币?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*元"),
]
```

Then normalize whitespace before searching:

```python
def _normalize_contract_text(contract_text: str) -> str:
    return re.sub(r"\s+", " ", contract_text)
```

And update `_parse_contract_amount()` to search normalized text first.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_quantification.py -q
```

Expected: PASS, including the new table-style and spaced-text regressions.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/quantification.py tests/review/test_quantification.py
git commit -m "fix: broaden deterministic contract amount extraction"
```

---

### Task 2 (P0): Stop leaking internal-only renderer notes into customer-facing report body

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py`
- Modify: `tests/review/test_report_writer.py`
- Modify: `tests/review/test_report_writer_negotiation_chip.py`

- [ ] **Step 1: Write the failing tests**

Add a report-writer regression asserting the customer-facing prompt no longer forces an always-on `## 渲染器备注` section in the final main narrative instructions.

```python
def test_combined_prompt_keeps_internal_renderer_notes_out_of_customer_required_sections() -> None:
    free_output = FreeReviewOutput(
        contract_id="test-contract",
        overall_assessment="overall",
        risk_segments=[],
        missing_clauses=[],
        strengths=[],
    )
    dossier = _build_dossier(free_output, None, "buyer")

    prompt = _build_combined_prompt(free_output, None, dossier, "buyer")

    assert "## 渲染器备注（强制执行，不可跳过）" not in prompt
    assert "客户版报告不得暴露内部编号、渲染器问责或系统自检过程" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer.py tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: FAIL because the current prompt hard-requires renderer notes in the customer report body.

- [ ] **Step 3: Write minimal implementation**

Adjust `src/contract_risk_analysis/review/report_writer.py` so:

1. `_combined_system_prompt()` no longer forces every customer report to contain `## 渲染器备注`.
2. `_build_combined_prompt()` replaces that required output section with a hard customer-facing rule:

```python
- 客户版报告不得暴露内部编号、渲染器问责、系统冲突排查过程或“我作为渲染器”的自述。
- 如果系统存在 internal_conflicts 或 manual_review_items，应在对应条款处写“建议人工复核”，
  但不要展开内部机制。
```

3. Keep internal conflicts inside `fact_sheet` / structured response, not the customer-facing main narrative requirement.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer.py tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/report_writer.py tests/review/test_report_writer.py tests/review/test_report_writer_negotiation_chip.py
git commit -m "fix: keep internal renderer notes out of customer reports"
```

---

### Task 3 (P1): Tighten LLM₁ guidance for `视为交付` / 风险转移双面分析

**Files:**
- Modify: `src/contract_risk_analysis/review/ai_review.py`
- Modify: `tests/review/test_ai_review.py`

- [ ] **Step 1: Write the failing test**

Add this prompt-level regression:

```python
def test_free_review_prompt_requires_dual_sided_analysis_for_deemed_delivery_clause() -> None:
    prompt = _free_review_prompt(
        "甲方经初验签字后视为乙方已交付，且外观验收不免除内在质量责任。",
        "sales-005",
        None,
        "buyer",
    )

    assert "对‘视为交付/签字即交付/逾期未提异议视为合格’类条款，必须同时判断" in prompt
    assert "是否提前触发交付完成或风险转移解释" in prompt
    assert "合同中是否仍保留质量责任、拒收、退换货或终验保护" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_ai_review.py -q
```

Expected: FAIL because the current prompt mentions the risk but not the required two-sided analysis discipline explicitly enough.

- [ ] **Step 3: Write minimal implementation**

In `src/contract_risk_analysis/review/ai_review.py`, strengthen the clause-quality section with wording like:

```python
"4. **是否存在[视为交付/验收]语言陷阱**：注意区分[外观验收]、[交付完成]和[风险转移]——"
"出现[签字即视为交付]、[逾期未提出异议视为合格]等表述时，"
"必须同时判断两面：其一，该表述是否可能提前触发交付完成或风险转移解释；"
"其二，合同中是否仍保留质量责任、拒收/退换货、终验或试运行保护。"
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_ai_review.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/review/ai_review.py tests/review/test_ai_review.py
git commit -m "feat: require dual-sided analysis for deemed delivery clauses"
```

---

### Task 4 (P1): Update resumable tracking after each finished slice

**Files:**
- Modify: `worklist/worklist-v2/WORKLIST.md`
- Modify: `worklist/worklist-v2/PROGRESS.md`

- [ ] **Step 1: Update WORKLIST mainline**

Change the current mainline from Stage B batch regression completion to the new optimization line:

```text
阶段 B 后续：报告事实准确性与客户版输出收口
→ 先修复合同总价/金额锚点识别失准
→ 再收口客户版与内部渲染信息边界
→ 最后补强“视为交付/风险转移”双面分析稳定性
```

- [ ] **Step 2: Add a PROGRESS checkpoint entry**

Add a new top entry summarizing:
- plan file path
- current implemented slice
- test command/result
- next continuation point

- [ ] **Step 3: Re-run focused regression after each checkpoint**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_quantification.py tests/review/test_report_writer.py tests/review/test_report_writer_negotiation_chip.py tests/review/test_ai_review.py tests/regression/test_judgment_regression.py -q
```

Expected: PASS for the touched report pipeline suite.

- [ ] **Step 4: Commit**

```bash
git add worklist/worklist-v2/WORKLIST.md worklist/worklist-v2/PROGRESS.md
git commit -m "docs: track report fact accuracy hardening mainline"
```

---

## Self-Review

### Spec coverage

- **合同事实准确性修复** → Task 1
- **客户版/内部版边界收口** → Task 2
- **`视为交付` 双面分析稳定性** → Task 3
- **续做文档同步** → Task 4

### Placeholder scan

Checked for `TODO`, `TBD`, `implement later`, and vague “add tests later” phrasing. None remain.

### Type consistency

- Keeps `QuantitativeContext` as the deterministic amount source.
- Keeps `ReportDossier` as the frozen truth source.
- Does not introduce new public API objects unless a later task explicitly requires them.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-14-report-fact-accuracy-and-customer-output-hardening.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
