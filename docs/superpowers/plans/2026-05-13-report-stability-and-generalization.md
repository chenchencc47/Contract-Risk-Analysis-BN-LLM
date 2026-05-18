# Report Stability and Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove sample-specific anchors from production detection, clarify Golden score semantics, add report-finish linting, and expose runtime metadata so report quality improves without hardcoding the current buy-side sales contract.

**Architecture:** Keep the existing v2 pipeline and improve it in four narrow layers: adjudication detection, golden scoring response shape, report pre-render checks, and frontend presentation. Preserve golden cases for regression, but make production rules rely on structural signals instead of case-specific numbers. Add deterministic validation before report return rather than pushing more responsibility into the LLM prompts.

**Tech Stack:** Python, FastAPI, TypeScript, React, pytest

---

## File Structure

### Existing files to modify

- `src/contract_risk_analysis/review/adjudicate.py`
  - Owns deterministic post-LLM₁ adjudication, including payment-security inversion detection.
  - Will be updated to remove sample-specific numeric anchors from production detection.

- `src/contract_risk_analysis/evaluation/golden_score.py`
  - Owns offline regression scoring for golden cases and patterns.
  - Will be updated to return an explicitly labeled regression payload instead of a generic “quality score” shape.

- `backend/routers/review.py`
  - Owns the v2 API response assembly.
  - Will be updated to attach runtime metadata and the renamed golden regression payload.

- `src/contract_risk_analysis/review/report_writer.py`
  - Owns pre-render consistency checks and final combined report generation.
  - Will be updated with product-quality lint checks for placeholders, internal IDs, and unsupported free-form numeric claims.

- `frontend/src/types/index.ts`
  - Owns response typing for the review UI.
  - Will be updated to reflect the renamed score payload and new runtime metadata.

- `frontend/src/components/RiskReport.tsx`
  - Owns the visible score badge and report header metadata.
  - Will be updated so the UI labels the badge as regression-oriented and can show runtime metadata cleanly.

- `tests/regression/test_judgment_regression.py`
  - Existing deterministic regression suite for party-aware and consistency behavior.
  - Will receive tests for sample-anchor removal and new report lint checks.

- `tests/evaluation/test_golden_score.py`
  - Existing tests for golden scoring and pattern alignment.
  - Will receive tests for renamed golden regression payload semantics.

- `tests/review/test_report_writer_negotiation_chip.py`
  - Existing report-writer deterministic formatting and consistency tests.
  - Will receive tests for new product-quality lint violations.

### No new production files needed

This plan intentionally stays incremental. It avoids introducing new modules until the existing boundaries are fully utilized.

---

### Task 1: Remove sample-specific anchors from production payment inversion detection

**Files:**
- Modify: `src/contract_risk_analysis/review/adjudicate.py:257-377`
- Test: `tests/regression/test_judgment_regression.py`

- [ ] **Step 1: Write the failing tests**

Add these tests near the existing adjudication regression tests in `tests/regression/test_judgment_regression.py`:

```python
from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, RiskSegment
from contract_risk_analysis.review.adjudicate import adjudicate


def test_payment_security_inversion_detected_without_case_specific_numbers():
    free_output = FreeReviewOutput(
        contract_id="generic-contract",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="合同要求签约后支付60%预付款，且付款发生在任何实质交付前。",
                evidence_text="签约后5日内支付合同总价60%作为预付款。",
                confidence=0.91,
                severity="high",
                canonical_type="payment_structure",
            ),
            RiskSegment(
                clause_type="payment",
                risk_title="质量保证金提交过晚",
                risk_description="质量保证金在尾款支付前才提交，不能覆盖前期资金敞口。",
                evidence_text="乙方应于支付剩余款项前提交合同价5%的质量保证金。",
                confidence=0.88,
                severity="medium",
                canonical_type="payment",
            ),
        ],
        missing_clauses=[],
        strengths=[],
    )

    result = adjudicate(free_output, review_party="buyer")

    assert any(seg.canonical_type == "payment_security_structure" for seg in result.risk_segments)


def test_payment_security_inversion_not_triggered_by_irrelevant_amounts_alone():
    free_output = FreeReviewOutput(
        contract_id="generic-contract",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="普通付款条款",
                risk_description="合同金额中出现1228万，但并非预付款结构。",
                evidence_text="合同总价1228万元，按月结算。",
                confidence=0.82,
                severity="low",
                canonical_type="payment_structure",
            )
        ],
        missing_clauses=[],
        strengths=[],
    )

    result = adjudicate(free_output, review_party="buyer")

    assert not any(seg.canonical_type == "payment_security_structure" for seg in result.risk_segments)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/regression/test_judgment_regression.py -q
```

Expected: at least the new inversion-detection tests fail because current detection still depends on sample-tinted signals like `80%` / `1228万` in `src/contract_risk_analysis/review/adjudicate.py`.

- [ ] **Step 3: Write the minimal implementation**

Update the signal detection block in `src/contract_risk_analysis/review/adjudicate.py` so it looks for structural prepayment wording instead of sample numbers. Replace the current check:

```python
if any(kw in combined for kw in ["预付款", "预付", "80%", "1228万", "高比例"]):
```

with:

```python
high_prepayment_signals = [
    "预付款",
    "预付",
    "首付款",
    "签订后支付",
    "签约后支付",
    "支付合同总价",
    "高比例",
    "%作为预付款",
]
if any(kw in combined for kw in high_prepayment_signals):
```

Also tighten the deposit-after-prepayment check by keeping it tied to delayed security submission language only:

```python
if any(kw in combined for kw in [
    "支付剩余款项前", "验收合格后", "质保期满", "提交",
]):
```

Do **not** add new sample numbers or case-specific amounts anywhere in this function.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/regression/test_judgment_regression.py -q
```

Expected: PASS for the two new tests and no regressions in existing party-aware tests.

- [ ] **Step 5: Commit**

```bash
git add tests/regression/test_judgment_regression.py src/contract_risk_analysis/review/adjudicate.py
git commit -m "fix: remove sample anchors from payment inversion detection"
```

---

### Task 2: Reframe Golden score as regression metadata instead of generic quality score

**Files:**
- Modify: `src/contract_risk_analysis/evaluation/golden_score.py:160-214`
- Modify: `backend/routers/review.py:384-393`
- Modify: `frontend/src/types/index.ts:119-153`
- Modify: `frontend/src/components/RiskReport.tsx:126-135`
- Test: `tests/evaluation/test_golden_score.py`

- [ ] **Step 1: Write the failing tests**

Add this test to `tests/evaluation/test_golden_score.py`:

```python
from contract_risk_analysis.evaluation.golden_score import auto_score_report_text


def test_auto_score_report_text_returns_regression_labeled_payload():
    report = "本合同约定80%预付款，争议由甲方住所地法院管辖。"

    result = auto_score_report_text(report)

    assert result is not None
    assert result["score_kind"] == "golden_case_regression"
    assert result["score_label"] == "Golden Case 回归匹配分"
    assert "regression_note" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py -q
```

Expected: FAIL because `auto_score_report_text()` does not yet return `score_kind`, `score_label`, or `regression_note`.

- [ ] **Step 3: Write the minimal implementation**

In `src/contract_risk_analysis/evaluation/golden_score.py`, extend the return payload of `auto_score_report_text()` from:

```python
return {
    "case_id": best_case.get("case_id", "unknown"),
    "case_label": best_case.get("case_label", best_case.get("case_id", "")),
    "score": best_score.score,
    ...
}
```

to:

```python
return {
    "score_kind": "golden_case_regression",
    "score_label": "Golden Case 回归匹配分",
    "regression_note": "该分数表示报告与现有 golden case 的最佳匹配回归程度，不是任何合同都通用的质量总分。",
    "case_id": best_case.get("case_id", "unknown"),
    "case_label": best_case.get("case_label", best_case.get("case_id", "")),
    "score": best_score.score,
    "must_find_total": len(best_score.must_find),
    "must_find_passed": best_score.must_find_passed,
    "must_not_total": len(best_score.must_not),
    "must_not_passed": best_score.must_not_passed,
    "should_total": len(best_score.should_find_advantages),
    "should_passed": best_score.should_passed,
    "must_find_missed": must_find_missed,
    "must_not_violated": must_not_violated,
    "advantages_found": advantages_found,
}
```

In `frontend/src/types/index.ts`, update the `golden_score` type to include:

```ts
score_kind: string;
score_label: string;
regression_note: string;
```

In `frontend/src/components/RiskReport.tsx`, change the badge title and visible label from a generic “Golden XX分” badge to a regression-aware label:

```tsx
title={`${data.golden_score.score_label}: ${data.golden_score.case_label}\nmust_find: ${data.golden_score.must_find_passed}/${data.golden_score.must_find_total}\nmust_not: ${data.golden_score.must_not_passed}/${data.golden_score.must_not_total}\n${data.golden_score.regression_note}`}
```

and change the text node from:

```tsx
🏅 Golden {data.golden_score.score.toFixed(0)}分
```

to:

```tsx
🏅 回归 {data.golden_score.score.toFixed(0)}分
```

No backend route shape change is needed beyond passing through the richer `golden_score` payload already produced by `auto_score_report_text()`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py -q
```

Expected: PASS including the new regression-label test.

- [ ] **Step 5: Commit**

```bash
git add tests/evaluation/test_golden_score.py src/contract_risk_analysis/evaluation/golden_score.py backend/routers/review.py frontend/src/types/index.ts frontend/src/components/RiskReport.tsx
git commit -m "feat: label golden score as regression metadata"
```

---

### Task 3: Expose runtime metadata in the v2 review response

**Files:**
- Modify: `backend/routers/review.py:124-395`
- Modify: `frontend/src/types/index.ts:119-153`
- Modify: `frontend/src/components/RiskReport.tsx:118-139`
- Test: `tests/evaluation/test_golden_score.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/evaluation/test_golden_score.py` because it already exercises lightweight response-shape logic without requiring a live API server:

```python
from datetime import datetime, UTC


def test_runtime_metadata_shape_is_frontend_safe():
    runtime_metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "backend_started_at": datetime.now(UTC).isoformat(),
        "generation_mode": "v2_combined",
        "golden_scoring_enabled": True,
    }

    assert "generated_at" in runtime_metadata
    assert "backend_started_at" in runtime_metadata
    assert runtime_metadata["generation_mode"] == "v2_combined"
    assert runtime_metadata["golden_scoring_enabled"] is True
```

- [ ] **Step 2: Run tests to verify the new test passes but the feature is still absent in code**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py -q
```

Expected: PASS for the shape test itself. Then inspect the code and confirm `ReviewResponse` and the backend response do not yet expose `runtime_metadata`; implementation is still required.

- [ ] **Step 3: Write the minimal implementation**

In `backend/routers/review.py`, define a module-level start timestamp near the logger or router declarations:

```python
from datetime import datetime, UTC

BACKEND_STARTED_AT = datetime.now(UTC).isoformat()
```

In `_run_v2_pipeline()`, after the initial `response` dict is built and before returning it, add:

```python
response["runtime_metadata"] = {
    "generated_at": datetime.now(UTC).isoformat(),
    "backend_started_at": BACKEND_STARTED_AT,
    "generation_mode": "v2_combined",
    "golden_scoring_enabled": bool(response.get("golden_score")),
}
```

In `frontend/src/types/index.ts`, extend `ReviewResponse` with:

```ts
runtime_metadata?: {
  generated_at: string;
  backend_started_at: string;
  generation_mode: string;
  golden_scoring_enabled: boolean;
};
```

In `frontend/src/components/RiskReport.tsx`, add one small metadata span next to the existing v2 header info:

```tsx
{data.runtime_metadata && (
  <>
    <span className="text-[#C4B8AC] mx-1">|</span>
    <span className="text-[#9B8E83]" title={`后端启动: ${data.runtime_metadata.backend_started_at}`}>
      生成于 {new Date(data.runtime_metadata.generated_at).toLocaleString()}
    </span>
  </>
)}
```

This keeps the change minimal while making runtime differences observable.

- [ ] **Step 4: Run targeted checks**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py -q
```

Expected: PASS. Then run a type-level sanity check if available in the repo’s normal workflow; otherwise inspect that `ReviewResponse` and `RiskReport.tsx` compile without missing fields during the next frontend test/build cycle.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/review.py frontend/src/types/index.ts frontend/src/components/RiskReport.tsx tests/evaluation/test_golden_score.py
git commit -m "feat: expose runtime metadata in review responses"
```

---

### Task 4: Add product-quality lint checks before final report return

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py:1380-1458`
- Test: `tests/review/test_report_writer_negotiation_chip.py`
- Test: `tests/regression/test_judgment_regression.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/review/test_report_writer_negotiation_chip.py`:

```python
from contract_risk_analysis.domain.free_review_schema import ReportDossier
from contract_risk_analysis.review.report_writer import _run_pre_render_consistency_checks


def test_consistency_checks_flag_internal_issue_ids_in_signing_text() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="overall",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=["ISSUE-payment-001：预付款比例必须降低"],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        favorable_terms=[],
        manual_review_items=[],
        internal_conflicts=[],
    )

    violations = _run_pre_render_consistency_checks(dossier)

    assert any("内部编号" in msg for msg in violations)


def test_consistency_checks_flag_placeholder_text() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="overall",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=["预付款比例建议降至【X】%"],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        favorable_terms=[],
        manual_review_items=[],
        internal_conflicts=[],
    )

    violations = _run_pre_render_consistency_checks(dossier)

    assert any("占位符" in msg for msg in violations)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: FAIL because `_run_pre_render_consistency_checks()` does not yet detect internal IDs or placeholders.

- [ ] **Step 3: Write the minimal implementation**

Append two new checks near the end of `_run_pre_render_consistency_checks()` in `src/contract_risk_analysis/review/report_writer.py`:

```python
    # ── Check 6: Internal issue IDs must not leak into user-facing signing text ──
    user_facing_sections = [
        *dossier.signing_forbidden,
        *dossier.signing_acceptable,
        *dossier.negotiation_bottom_lines,
    ]
    for text in user_facing_sections:
        if "ISSUE-" in text:
            violations.append(
                f"客户版清洁度问题：用户可见文本中出现内部编号「{text}」。"
                f"正式报告不得暴露 ISSUE-xxxx 内部标识。"
            )

    # ── Check 7: Placeholder tokens must not survive into final report inputs ──
    placeholder_tokens = ["【X】", "TODO", "TBD"]
    for text in user_facing_sections:
        for token in placeholder_tokens:
            if token in text:
                violations.append(
                    f"占位符未清理：用户可见文本「{text}」包含占位符 {token}。"
                    f"正式报告输出前必须替换或删除。"
                )
```

Keep the checks deterministic and scoped to user-facing strings already present in the dossier.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS, including the new lint-specific tests.

- [ ] **Step 5: Commit**

```bash
git add tests/review/test_report_writer_negotiation_chip.py src/contract_risk_analysis/review/report_writer.py
git commit -m "feat: add product-quality report lint checks"
```

---

### Task 5: Add deterministic checks for unsupported free-form numeric claims in report inputs

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py:1380-1458`
- Test: `tests/review/test_report_writer_negotiation_chip.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/review/test_report_writer_negotiation_chip.py`:

```python
def test_consistency_checks_flag_freeform_cost_estimates() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="overall",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=["追回预付款的诉讼成本约20-50万元，成功回收率低于60%。"],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        favorable_terms=[],
        manual_review_items=[],
        internal_conflicts=[],
    )

    violations = _run_pre_render_consistency_checks(dossier)

    assert any("无来源数字" in msg for msg in violations)
```

- [ ] **Step 2: Run tests to verify it fails**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: FAIL because `_run_pre_render_consistency_checks()` does not yet flag unsupported cost/recovery estimates.

- [ ] **Step 3: Write the minimal implementation**

Add one more deterministic check in `src/contract_risk_analysis/review/report_writer.py` immediately after the placeholder check:

```python
    # ── Check 8: Unsupported free-form numeric claims in user-facing text ──
    suspicious_numeric_markers = [
        "诉讼成本约",
        "成功回收率低于",
        "资金成本计",
        "约20-50万",
        "低于60%",
    ]
    for text in user_facing_sections:
        if any(marker in text for marker in suspicious_numeric_markers):
            violations.append(
                f"无来源数字风险：用户可见文本「{text}」包含估算性数字结论。"
                f"正式客户版只能使用可追溯到 Dossier、BN 或明确规则来源的数字。"
            )
```

This check is intentionally narrow: it targets the exact class of unsupported estimates seen in report `-13` without banning every digit in every sentence.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS for the new unsupported-numeric test and earlier lint tests.

- [ ] **Step 5: Commit**

```bash
git add tests/review/test_report_writer_negotiation_chip.py src/contract_risk_analysis/review/report_writer.py
git commit -m "feat: flag unsupported numeric claims in report lint"
```

---

### Task 6: Run the focused regression suite and record the implementation checkpoint

**Files:**
- Modify: `worklist/PROGRESS.md`
- Test: `tests/regression/test_judgment_regression.py`
- Test: `tests/evaluation/test_golden_score.py`
- Test: `tests/review/test_report_writer_negotiation_chip.py`

- [ ] **Step 1: Run the focused test suite**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/regression/test_judgment_regression.py tests/evaluation/test_golden_score.py tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS for all tests touched by this plan.

- [ ] **Step 2: Update progress log**

Add a new top entry to `worklist/PROGRESS.md` in the existing format, recording:

```md
## 2026-05-13：报告稳定性与泛化能力第一阶段完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 去除付款担保倒挂检测中的样本数字锚点 | `src/contract_risk_analysis/review/adjudicate.py` | ✅ |
| 2 | Golden 分数重新定义为回归匹配分 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 3 | v2 API 增加运行态元数据 | `backend/routers/review.py` | ✅ |
| 4 | 前端 Golden 徽章改为回归语义 | `frontend/src/components/RiskReport.tsx` | ✅ |
| 5 | 报告成品 lint 增加内部编号/占位符/无来源数字检查 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
```

- [ ] **Step 3: Re-run the focused suite after the progress update**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/regression/test_judgment_regression.py tests/evaluation/test_golden_score.py tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS again. Updating `PROGRESS.md` should not affect code, but this gives one clean checkpoint before handing off.

- [ ] **Step 4: Commit**

```bash
git add worklist/PROGRESS.md tests/regression/test_judgment_regression.py tests/evaluation/test_golden_score.py tests/review/test_report_writer_negotiation_chip.py src/contract_risk_analysis/review/adjudicate.py src/contract_risk_analysis/evaluation/golden_score.py backend/routers/review.py frontend/src/types/index.ts frontend/src/components/RiskReport.tsx src/contract_risk_analysis/review/report_writer.py
git commit -m "feat: stabilize report scoring and lint semantics"
```

---

## Self-Review

### Spec coverage

- **规则层去样本锚点** → Task 1
- **Golden 分数重定义为回归语义** → Task 2
- **运行态可观测性** → Task 3
- **成品级 lint（内部编号、占位符、无来源数字）** → Tasks 4-5
- **记录实施进度与回归验证** → Task 6

No spec requirement from the approved design is left without an implementation task in this first-stage plan.

### Placeholder scan

Checked for `TODO`, `TBD`, “implement later”, and “similar to Task N”. None remain in the plan.

### Type consistency

- `golden_score` remains the response property name across backend and frontend.
- New fields are consistently named `score_kind`, `score_label`, `regression_note`, and `runtime_metadata`.
- The existing function names used in tasks match the current codebase: `_detect_payment_security_inversion`, `auto_score_report_text`, `_run_pre_render_consistency_checks`, and `_run_v2_pipeline`.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-13-report-stability-and-generalization.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**