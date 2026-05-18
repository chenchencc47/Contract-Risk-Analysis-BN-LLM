# Stage B Batch Golden Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add directory-level batch golden-case regression so one golden case can score a whole folder of Markdown reports, print a terminal summary, and emit structured aggregate results without regressing the existing single-report CLI.

**Architecture:** Keep the current rule-based scorer in `src/contract_risk_analysis/evaluation/golden_score.py` as the single scoring engine, and add one thin batch layer around it: stable Markdown discovery, per-report scoring reuse, failure-tolerant aggregation, and human-readable summary formatting. Wire that batch layer into `src/contract_risk_analysis/cli.py` with one new command branch that prints a summary first and the structured JSON payload second, while leaving `--score-golden-case` behavior unchanged.

**Tech Stack:** Python, argparse, pathlib, pytest

---

## File Structure

### Existing production files to modify

- `src/contract_risk_analysis/evaluation/golden_score.py:16-218`
  - Add batch result dataclasses, Markdown directory scanning, per-report batch scoring, and terminal summary formatting.

- `src/contract_risk_analysis/cli.py:26-97`
  - Add `--score-golden-case-batch` and `--reports-dir`, then print the batch summary and JSON payload in one branch.

### Existing test files to modify

- `tests/evaluation/test_golden_score.py:1-238`
  - Add deterministic unit tests for directory scan, aggregation, empty-directory behavior, failure tolerance, and summary text.

- `tests/cli/test_main.py:160-228`
  - Add CLI tests for the new batch branch and its required-argument guardrail.

### Existing docs and tracking files to modify

- `docs/golden-cli-usage.md:11-325`
  - Document batch usage, output shape, and the remaining non-goals.

- `worklist/worklist-v2/WORKLIST.md`
  - Move the Stage B mainline from candidate state to completed/next-step state after implementation passes.

- `worklist/worklist-v2/PROGRESS.md`
  - Record the implementation, test command, and next continuation point.

---

### Task 1: Add batch golden-score models and aggregation logic

**Files:**
- Modify: `src/contract_risk_analysis/evaluation/golden_score.py:35-218`
- Test: `tests/evaluation/test_golden_score.py`

- [ ] **Step 1: Write the failing tests**

Add these imports near the top of `tests/evaluation/test_golden_score.py`:

```python
from pathlib import Path

from contract_risk_analysis.evaluation import golden_score
from contract_risk_analysis.evaluation.golden_score import (
    auto_score_report_text,
    format_batch_golden_summary,
    load_golden_cases,
    load_golden_patterns,
    score_golden_case,
    score_reports_against_case_batch,
    summarize_patterns,
)
```

Then add these tests:

```python
def test_score_reports_against_case_batch_aggregates_directory_scores(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not: []
should_find_advantages:
  - id: forum
    expected: 识别管辖优势
    evidence_keywords: ["甲方住所地", "管辖"]
        """.strip(),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "a.md").write_text(
        "本合同约定80%预付款。争议由甲方住所地法院管辖。",
        encoding="utf-8",
    )
    (reports_dir / "b.md").write_text(
        "本合同约定80%预付款。",
        encoding="utf-8",
    )
    (reports_dir / "notes.txt").write_text("ignore", encoding="utf-8")

    batch = score_reports_against_case_batch(case_path, reports_dir)

    assert batch.score_kind == "golden_case_batch_regression"
    assert batch.reports_scanned == 2
    assert batch.reports_scored == 2
    assert batch.average_score == 87.5
    assert batch.best_report == {"report_name": "a.md", "score": 100.0}
    assert batch.worst_report == {"report_name": "b.md", "score": 75.0}
    assert [item.report_name for item in batch.results] == ["a.md", "b.md"]
    assert batch.results[0].must_find_passed == 1
    assert batch.results[0].advantages_passed == 1


def test_score_reports_against_case_batch_returns_empty_batch_for_empty_directory(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text("case_id: demo_case\nmust_find: []\nmust_not: []\n", encoding="utf-8")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    batch = score_reports_against_case_batch(case_path, reports_dir)

    assert batch.reports_scanned == 0
    assert batch.reports_scored == 0
    assert batch.average_score is None
    assert batch.best_report is None
    assert batch.worst_report is None
    assert batch.results == []
    assert batch.failed_reports == []


def test_score_reports_against_case_batch_records_read_failures_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not: []
should_find_advantages: []
        """.strip(),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "ok.md").write_text("本合同约定80%预付款。", encoding="utf-8")
    (reports_dir / "broken.md").write_text("损坏报告", encoding="utf-8")

    original_read = golden_score._read_report_text

    def fake_read(report_path: Path) -> str:
        if report_path.name == "broken.md":
            raise UnicodeDecodeError("utf-8", b"x", 0, 1, "boom")
        return original_read(report_path)

    monkeypatch.setattr(golden_score, "_read_report_text", fake_read)

    batch = score_reports_against_case_batch(case_path, reports_dir)

    assert batch.reports_scanned == 2
    assert batch.reports_scored == 1
    assert len(batch.failed_reports) == 1
    assert batch.failed_reports[0]["report_name"] == "broken.md"
    assert "UnicodeDecodeError" in batch.failed_reports[0]["error"]


def test_format_batch_golden_summary_includes_core_fields(tmp_path: Path) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not: []
should_find_advantages:
  - id: forum
    expected: 识别管辖优势
    evidence_keywords: ["甲方住所地", "管辖"]
        """.strip(),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "a.md").write_text(
        "本合同约定80%预付款。争议由甲方住所地法院管辖。",
        encoding="utf-8",
    )
    (reports_dir / "b.md").write_text("本合同约定80%预付款。", encoding="utf-8")

    batch = score_reports_against_case_batch(case_path, reports_dir)
    summary = format_batch_golden_summary(batch)

    assert "Batch golden-case regression summary" in summary
    assert "Reports scanned: 2" in summary
    assert "Reports scored: 2" in summary
    assert "Average score: 87.5" in summary
    assert "1. a.md — 100.0" in summary
    assert "Lowest report:" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py -q
```

Expected: FAIL because `score_reports_against_case_batch`, `_read_report_text`, `format_batch_golden_summary`, and the batch dataclasses do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

In `src/contract_risk_analysis/evaluation/golden_score.py`, add these dataclasses below `GoldenCaseScore`:

```python
@dataclass
class BatchReportScore:
    report_path: str
    report_name: str
    case_id: str
    score: float
    score_label: str
    regression_note: str
    must_find_passed: int
    must_find_total: int
    must_not_passed: int
    must_not_total: int
    advantages_passed: int
    advantages_total: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_path": self.report_path,
            "report_name": self.report_name,
            "case_id": self.case_id,
            "score": self.score,
            "score_label": self.score_label,
            "regression_note": self.regression_note,
            "must_find_passed": self.must_find_passed,
            "must_find_total": self.must_find_total,
            "must_not_passed": self.must_not_passed,
            "must_not_total": self.must_not_total,
            "advantages_passed": self.advantages_passed,
            "advantages_total": self.advantages_total,
        }


@dataclass
class BatchGoldenScoreReport:
    case_id: str
    case_path: str
    reports_scanned: int
    results: list[BatchReportScore] = field(default_factory=list)
    failed_reports: list[dict[str, str]] = field(default_factory=list)

    @property
    def score_kind(self) -> str:
        return "golden_case_batch_regression"

    @property
    def reports_scored(self) -> int:
        return len(self.results)

    @property
    def average_score(self) -> float | None:
        if not self.results:
            return None
        return round(sum(item.score for item in self.results) / len(self.results), 2)

    @property
    def best_report(self) -> dict[str, Any] | None:
        if not self.results:
            return None
        best = self.results[0]
        return {"report_name": best.report_name, "score": best.score}

    @property
    def worst_report(self) -> dict[str, Any] | None:
        if not self.results:
            return None
        worst = min(self.results, key=lambda item: (item.score, item.report_name))
        return {"report_name": worst.report_name, "score": worst.score}

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_kind": self.score_kind,
            "case_id": self.case_id,
            "case_path": self.case_path,
            "reports_scanned": self.reports_scanned,
            "reports_scored": self.reports_scored,
            "average_score": self.average_score,
            "best_report": self.best_report,
            "worst_report": self.worst_report,
            "failed_reports": self.failed_reports,
            "results": [item.to_dict() for item in self.results],
        }
```

Then add these helpers below `score_report_against_case()`:

```python
def _read_report_text(report_path: Path) -> str:
    return report_path.read_text(encoding="utf-8")


def _list_markdown_reports(reports_dir: str | Path) -> list[Path]:
    root = Path(reports_dir)
    if not root.exists():
        raise FileNotFoundError(f"Reports directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Reports path is not a directory: {root}")
    return sorted((path for path in root.glob("*.md") if path.is_file()), key=lambda path: path.name)


def _to_batch_report_score(score: GoldenCaseScore) -> BatchReportScore:
    return BatchReportScore(
        report_path=score.report_path,
        report_name=Path(score.report_path).name,
        case_id=score.case_id,
        score=score.score,
        score_label="Golden Case 回归匹配分",
        regression_note="该分数表示报告与指定 golden case 的回归匹配程度，不是任何合同都通用的质量总分。",
        must_find_passed=score.must_find_passed,
        must_find_total=len(score.must_find),
        must_not_passed=score.must_not_passed,
        must_not_total=len(score.must_not),
        advantages_passed=score.should_passed,
        advantages_total=len(score.should_find_advantages),
    )


def score_reports_against_case_batch(
    case_path: str | Path,
    reports_dir: str | Path,
) -> BatchGoldenScoreReport:
    case = load_yaml(case_path)
    report_paths = _list_markdown_reports(reports_dir)
    results: list[BatchReportScore] = []
    failed_reports: list[dict[str, str]] = []

    for report_path in report_paths:
        try:
            report_text = _read_report_text(report_path)
            score = score_golden_case(case, report_text, str(report_path))
        except Exception as exc:
            failed_reports.append(
                {
                    "report_path": str(report_path),
                    "report_name": report_path.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        results.append(_to_batch_report_score(score))

    results.sort(key=lambda item: (-item.score, item.report_name))
    return BatchGoldenScoreReport(
        case_id=str(case.get("case_id", "unknown")),
        case_path=str(case_path),
        reports_scanned=len(report_paths),
        results=results,
        failed_reports=failed_reports,
    )


def format_batch_golden_summary(batch: BatchGoldenScoreReport, top_n: int = 3) -> str:
    lines = [
        "Batch golden-case regression summary",
        f"Reports scanned: {batch.reports_scanned}",
        f"Reports scored: {batch.reports_scored}",
        f"Average score: {batch.average_score:.1f}" if batch.average_score is not None else "Average score: N/A",
    ]

    if batch.results:
        lines.append("")
        lines.append("Top reports:")
        for idx, item in enumerate(batch.results[:top_n], 1):
            lines.append(f"{idx}. {item.report_name} — {item.score:.1f}")
        lines.append("")
        lines.append("Lowest report:")
        lowest = batch.worst_report
        lines.append(f"- {lowest['report_name']} — {lowest['score']:.1f}")
    else:
        lines.append("")
        lines.append("No Markdown reports were scored.")

    if batch.failed_reports:
        lines.append("")
        lines.append("Failed reports:")
        for item in batch.failed_reports:
            lines.append(f"- {item['report_name']} — {item['error']}")

    return "\n".join(lines)
```

Do not change `score_golden_case()` or `auto_score_report_text()` semantics in this task.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py -q
```

Expected: PASS, including the new batch aggregation and empty-directory cases.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/evaluation/golden_score.py tests/evaluation/test_golden_score.py
git commit -m "feat: add batch golden case aggregation"
```

---

### Task 2: Wire batch regression into the CLI without regressing single-report scoring

**Files:**
- Modify: `src/contract_risk_analysis/cli.py:26-97`
- Modify: `tests/cli/test_main.py:160-228`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/cli/test_main.py` below `test_main_scores_golden_case`:

```python
def test_main_scores_golden_case_batch(tmp_path: Path, capsys) -> None:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        """
case_id: demo_case
must_find:
  - id: prepayment
    expected: 识别预付款
    evidence_keywords: ["80%", "预付款"]
must_not: []
should_find_advantages:
  - id: forum
    expected: 识别管辖优势
    evidence_keywords: ["甲方住所地", "管辖"]
        """.strip(),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "a.md").write_text(
        "本合同约定80%预付款。争议由甲方住所地法院管辖。",
        encoding="utf-8",
    )
    (reports_dir / "b.md").write_text("本合同约定80%预付款。", encoding="utf-8")

    cli.main([
        "--score-golden-case-batch",
        str(case_path),
        "--reports-dir",
        str(reports_dir),
    ])

    output = capsys.readouterr().out.strip()
    summary_text, json_text = output.split("\n\n", 1)
    payload = json.loads(json_text)

    assert "Batch golden-case regression summary" in summary_text
    assert "Reports scanned: 2" in summary_text
    assert "Average score: 87.5" in summary_text
    assert payload["score_kind"] == "golden_case_batch_regression"
    assert payload["reports_scored"] == 2
    assert payload["best_report"]["report_name"] == "a.md"


def test_main_score_golden_case_batch_requires_reports_dir() -> None:
    try:
        cli.main(["--score-golden-case-batch", "case.yaml"])
    except SystemExit as exc:
        assert str(exc) == "--score-golden-case-batch requires --reports-dir"
    else:
        raise AssertionError("Expected SystemExit")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/cli/test_main.py -q
```

Expected: FAIL because the new CLI args and branch do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

In `src/contract_risk_analysis/cli.py`, add these parser arguments near the existing golden-case flags:

```python
    parser.add_argument(
        "--score-golden-case-batch",
        type=str,
        default=None,
        metavar="YAML",
        help="Score all Markdown reports in a directory against a golden case YAML",
    )
    parser.add_argument(
        "--reports-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Markdown reports directory for --score-golden-case-batch",
    )
```

Then add this branch above the existing `if args.score_golden_case:` block:

```python
    if args.score_golden_case_batch:
        if not args.reports_dir:
            raise SystemExit("--score-golden-case-batch requires --reports-dir")
        from contract_risk_analysis.evaluation.golden_score import (
            format_batch_golden_summary,
            score_reports_against_case_batch,
        )

        try:
            batch = score_reports_against_case_batch(
                args.score_golden_case_batch,
                args.reports_dir,
            )
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise SystemExit(str(exc)) from exc

        print(format_batch_golden_summary(batch))
        print()
        print(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2))
        return
```

Leave the existing `--score-golden-case` branch unchanged so the single-report CLI stays byte-for-byte compatible.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/cli/test_main.py -q
```

Expected: PASS, including the old single-report tests and the new batch branch.

- [ ] **Step 5: Commit**

```bash
git add src/contract_risk_analysis/cli.py tests/cli/test_main.py
git commit -m "feat: add batch golden case cli command"
```

---

### Task 3: Document the new batch workflow and update resumable project tracking

**Files:**
- Modify: `docs/golden-cli-usage.md:11-325`
- Modify: `worklist/worklist-v2/WORKLIST.md`
- Modify: `worklist/worklist-v2/PROGRESS.md`

- [ ] **Step 1: Update the CLI documentation**

In `docs/golden-cli-usage.md`, extend the feature table to:

```md
| 命令 | 用途 |
|---|---|
| `--score-golden-case` | 用指定 golden case 评测一份 Markdown 报告 |
| `--score-golden-case-batch` | 用指定 golden case 批量评测一个目录下的 Markdown 报告 |
| `--list-golden-patterns` | 查看当前已沉淀的 golden patterns 元数据 |
```

Add this new usage section after the single-report section:

```md
## 4. 对整个目录进行 Batch Golden Case 回归

### 4.1 基本命令

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli \
  --score-golden-case-batch tests/fixtures/golden_cases/sales_purchase_contract_001.yaml \
  --reports-dir 合同检测报告/买卖合同
```

含义：

- 使用同一个 golden case 评测目录中的所有 `.md` 报告；
- 终端先打印批量摘要，再输出结构化 JSON 结果；
- 适合对同一合同路线下的多版本报告做回归比较。

### 4.2 输出字段

批量 JSON 至少包含：

- `score_kind`
- `reports_scanned`
- `reports_scored`
- `average_score`
- `best_report`
- `worst_report`
- `failed_reports`
- `results`
```

Then change the “当前限制” section from:

```md
3. 暂不支持批量评测整个文件夹；
```

to:

```md
3. 已支持“单 golden case + 单报告目录”的批量评测，但仍不支持 case 目录与报告目录的自动匹配；
```

- [ ] **Step 2: Update the resumable tracking files**

At the top of `worklist/worklist-v2/PROGRESS.md`, add this entry:

```md
## 2026-05-14：阶段 B 批量 golden-case 回归完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | 为 golden score 增加目录批量扫描与聚合结果对象 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 2 | 为批量回归增加失败容忍与终端摘要格式化 | `src/contract_risk_analysis/evaluation/golden_score.py` | ✅ |
| 3 | 为 CLI 增加 `--score-golden-case-batch` / `--reports-dir` 入口 | `src/contract_risk_analysis/cli.py` | ✅ |
| 4 | 补齐批量评测与 CLI 回归测试 | `tests/evaluation/test_golden_score.py` `tests/cli/test_main.py` | ✅ |
| 5 | 更新 golden CLI 使用说明 | `docs/golden-cli-usage.md` | ✅ |
```

And update `worklist/worklist-v2/WORKLIST.md` so the “当前主线状态” block becomes:

```md
当前主线状态：

```text
阶段 B：报告质量自动评测增强（批量 golden-case 回归）
→ 已完成首个可用闭环
→ 下一步可进入“版本对比摘要增强”或“pattern / production rule 收口”
```
```

Also change “下次继续建议” to:

```md
```text
1. 基于批量结果生成“谁进步/谁退步”的自动摘要
2. 或进入 golden pattern / production rule 的进一步收口
3. 保持当前 batch regression 作为后续版本回归入口
```
```

- [ ] **Step 3: Run the focused suite after the docs/tracking update**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/evaluation/test_golden_score.py tests/cli/test_main.py -q
```

Expected: PASS again. The markdown file changes do not affect Python behavior.

- [ ] **Step 4: Commit**

```bash
git add docs/golden-cli-usage.md worklist/worklist-v2/WORKLIST.md worklist/worklist-v2/PROGRESS.md
git commit -m "docs: record batch golden regression workflow"
```

---

### Task 4: Run the end-to-end batch regression smoke command against real project fixtures

**Files:**
- Test only: `tests/fixtures/golden_cases/`
- Test only: `合同检测报告/买卖合同/`

- [ ] **Step 1: Run the real batch command**

Run:

```bash
.venv/Scripts/python.exe -m contract_risk_analysis.cli --score-golden-case-batch tests/fixtures/golden_cases/sales_purchase_contract_001.yaml --reports-dir 合同检测报告/买卖合同
```

Expected: terminal summary first, then a JSON payload whose `score_kind` is `golden_case_batch_regression` and whose `results` array is sorted by descending `score`.

- [ ] **Step 2: Verify the key fields in the output**

Check for these exact signals in the command output:

```text
Batch golden-case regression summary
Reports scanned:
Reports scored:
Average score:
Top reports:
Lowest report:
```

And in the trailing JSON:

```json
{
  "score_kind": "golden_case_batch_regression",
  "reports_scanned": 0,
  "reports_scored": 0,
  "average_score": null,
  "failed_reports": [],
  "results": []
}
```

The numbers will differ on the real dataset, but these fields must exist and parse cleanly.

- [ ] **Step 3: Commit**

```bash
git add src/contract_risk_analysis/evaluation/golden_score.py src/contract_risk_analysis/cli.py tests/evaluation/test_golden_score.py tests/cli/test_main.py docs/golden-cli-usage.md worklist/worklist-v2/WORKLIST.md worklist/worklist-v2/PROGRESS.md
git commit -m "feat: add batch golden case regression"
```

---

## Self-Review

### Spec coverage

- **目录级批量扫描** → Task 1
- **复用现有单报告评分语义** → Task 1
- **整批汇总统计** → Task 1
- **CLI 摘要输出** → Task 2
- **结构化批量结果** → Tasks 1-2
- **文档与续做入口** → Task 3
- **真实命令烟雾验证** → Task 4

### Placeholder scan

Checked for `TODO`, `TBD`, “implement later”, and “similar to Task N”. None remain.

### Type consistency

- Batch result types are consistently named `BatchReportScore` and `BatchGoldenScoreReport`.
- The batch entry point is consistently named `score_reports_against_case_batch()`.
- The CLI branch and docs both use the same argument pair: `--score-golden-case-batch` and `--reports-dir`.
- Existing single-report APIs (`score_golden_case`, `score_report_against_case`, `auto_score_report_text`) remain unchanged.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-14-stage-b-batch-golden-regression.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**