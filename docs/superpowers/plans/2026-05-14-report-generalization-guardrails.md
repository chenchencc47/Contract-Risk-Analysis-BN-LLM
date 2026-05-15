# Report Generalization Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 固化合同审查报告生成链路的实施限制，确保后续优化提升报告质量时，不会通过样本硬编码、数字编造、外部评价内嵌或客户版泄漏内部信息等方式“做假优化”。

**Architecture:** 在现有 v2 报告链路上做四层加固：LLM₁ 提示约束、LLM₂ 渲染约束、规则层推荐措辞约束、成品级确定性 lint 与回归验证。所有约束都优先写进现有源码与测试，不新增复杂后处理，不手改某一份客户报告来掩盖源头问题。

**Tech Stack:** Python, pytest, FastAPI, React

---

## Implementation Restrictions

以下限制为本方案的**硬约束**，实施时必须同时满足：

1. **禁止样本硬编码**
   - 禁止在 `ai_review.py`、`report_writer.py`、`adjudicate.py`、测试断言、前端展示文案中写入只适用于某一份合同的固定比例、固定金额、固定天数、固定地名、固定行业参数。
   - 例如不得把“30%”“50%”“10日”“北京市海淀区”“12280000 元”等写成通用答案模板，除非它们来自当前合同文本的量化提取或只是当次样本输出事实。

2. **禁止把外部评价当标准答案内嵌回系统**
   - `deepseek网页评价.md`、`AI网页端检测报告.md` 只能用于**独立分析完成后的比对**，不能反向写进 prompt、规则或回归标准，变成“系统应该模仿的答案模板”。
   - 任何比较任务都必须先独立判断，再做交叉验证。

3. **禁止数字造假或无来源数字扩写**
   - 系统中的概率、权重、P(high)、反事实 delta 只能来自 `cuad_empirical`、`contractnli_empirical`、`expert_estimated` 三类合法来源。
   - 正式客户版禁止出现无出处的诉讼成本估算、回收率估算、行业平均值估算，除非有明确来源链路。

4. **禁止把呈现问题伪装成模型修复**
   - 如果问题只是“数字不好看”“标签不够猛”“文风不够强”，优先修呈现方式、提示纪律和结构表达；不得为了让报告更好看而手调概率、篡改 BN 数值或塞入样本答案。

5. **禁止手改客户版来掩盖源头缺陷**
   - 不直接编辑 `合同检测报告/**/*.md` 某一版客户报告来完成修复。
   - 所有修复都必须落在源码、规则、测试或重跑链路上，并通过新版本报告验证。

6. **客户版必须保持清洁**
   - 正式客户版不得出现 `ISSUE-`、`渲染器备注`、`内部一致性警告`、`TODO`、`TBD`、占位符文本、内部冲突编号。

7. **优先结构性规则，不引入复杂特判**
   - 若问题可通过“结构性提示规则 + 确定性 lint + 回归测试”解决，则不新增样本特判分支。
   - 对规则层推荐，允许写“降低前置付款比例”“补强担保”“后移风险节点”这类泛化表达；禁止把某一合同的谈判答案直接升格为通用推荐。

8. **测试也必须避免样本绑定**
   - 新增测试优先断言“结构性语义”和“禁止事项”，而不是断言某个合同专属数字必须出现在通用 prompt 中。

---

## File Structure

### Existing files to modify

- `src/contract_risk_analysis/review/ai_review.py`
  - LLM₁ 自由审查提示入口。
  - 负责把“不得硬编码、法律依据必须直接匹配、主从风险分层、不得套用外部评价答案”写进源头提示纪律。

- `src/contract_risk_analysis/review/report_writer.py`
  - LLM₂ 报告渲染与成品级一致性检查入口。
  - 负责把“不得复用其他报告固定模板、BN 百分比非货币估值、客户版清洁度、无来源数字 lint”写进组合提示与确定性校验。

- `src/contract_risk_analysis/review/adjudicate.py`
  - 规则层裁决入口。
  - 负责确保结构性推荐措辞保持泛化，不把某个样本答案固化成系统建议。

- `tests/review/test_ai_review.py`
  - LLM₁ 提示纪律回归测试。

- `tests/review/test_report_writer_negotiation_chip.py`
  - LLM₂ 提示纪律与成品级 lint 回归测试。

- `tests/regression/test_judgment_regression.py`
  - 规则层与预渲染一致性回归测试。

### Existing runtime verification target

- `backend/routers/review.py`
  - 仅用于重跑现有 v2 链路验证，不计划在本方案里增加新业务逻辑。

- `合同检测报告/买卖合同/买卖合同.pdf`
  - 真实样本验证目标。

### No new production modules

本方案优先复用现有模块边界，不新增新的生产模块；只新增或收紧提示文本、规则文本、lint 和回归测试。

---

### Task 1: 固化 LLM₁ 的泛化提示纪律

**Files:**
- Modify: `src/contract_risk_analysis/review/ai_review.py:507-700`
- Test: `tests/review/test_ai_review.py`

- [ ] **Step 1: Write the failing test**

在 `tests/review/test_ai_review.py` 追加下面的测试：

```python
from contract_risk_analysis.review.ai_review import _free_review_prompt


def test_free_review_prompt_includes_generalization_guardrails() -> None:
    prompt = _free_review_prompt()

    assert "**泛化约束**" in prompt
    assert "禁止照搬其他报告中的固定比例、固定天数、固定金额、固定地名" in prompt
    assert "只能输出适用于当前合同文本的结构性判断" in prompt
    assert "不得把外部评价结论当作标准答案回写进本次审查" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_ai_review.py -q
```

Expected: FAIL，因为 `_free_review_prompt()` 还没有完整包含上述泛化约束文本。

- [ ] **Step 3: Write minimal implementation**

在 `src/contract_risk_analysis/review/ai_review.py` 的 `_free_review_prompt()` 中，紧接现有法律依据纪律后加入如下文本：

```python
        "9. **泛化约束**：只能输出适用于当前合同文本的结构性判断，禁止照搬其他报告中的固定比例、固定天数、固定金额、固定地名、固定行业参数。"
        "如果需要给出具体比例、期限、金额或节点，必须来自当前合同文本、可追溯的量化提取结果，或明确标注为需人工复核的行业参数。\n"
        "10. **外部评价隔离**：不得把外部评价结论当作标准答案回写进本次审查。即使后续存在网页评价或人工评价，它们也只能用于独立审查完成后的比对，不能反向决定当前风险识别结论。\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_ai_review.py -q
```

Expected: PASS，包括现有法律依据与付款主从分层测试一起通过。

- [ ] **Step 5: Commit**

```bash
git add tests/review/test_ai_review.py src/contract_risk_analysis/review/ai_review.py
git commit -m "test: lock LLM1 generalization guardrails"
```

---

### Task 2: 固化 LLM₂ 的去硬编码与客户版清洁约束

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py:2017-2300`
- Test: `tests/review/test_report_writer_negotiation_chip.py`

- [ ] **Step 1: Write the failing test**

在 `tests/review/test_report_writer_negotiation_chip.py` 追加下面的测试：

```python
from contract_risk_analysis.review.report_writer import _build_combined_prompt


def test_combined_prompt_includes_non_hardcoding_guardrails() -> None:
    prompt = _build_combined_prompt(review_party="buyer")

    assert "禁止把某一份合同中的固定比例、固定金额、固定期限、固定城市或固定行业惯例写成通用答案" in prompt
    assert "只能按本合同实际数字/节点填写" in prompt
    assert "不得照搬其他报告中的现成退让阶梯、三板斧标签或固定攻击标题" in prompt
    assert "客户版不得出现 ISSUE-、渲染器备注、内部一致性警告、TODO、TBD" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: FAIL，因为 `_build_combined_prompt()` 还没有完整收纳上述约束文案。

- [ ] **Step 3: Write minimal implementation**

在 `src/contract_risk_analysis/review/report_writer.py` 的 `_build_combined_prompt()` 中，加入如下约束块：

```python
    hardening_rules = (
        "- 禁止把某一份合同中的固定比例、固定金额、固定期限、固定城市或固定行业惯例写成通用答案；"
        "所有具体数字、期限、金额、地点、节点都只能按本合同实际数字/节点填写。\n"
        "- 不得照搬其他报告中的现成退让阶梯、三板斧标签或固定攻击标题；"
        "标题、话术和让步条件必须仅服务于当前合同真实争议点。\n"
        "- 客户版不得出现 ISSUE-、渲染器备注、内部一致性警告、TODO、TBD 或任何内部占位符。\n"
    )
```

并把它拼接进现有的章节要求字符串中。

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS，包括现有 report-17 一致性修复相关测试一起通过。

- [ ] **Step 5: Commit**

```bash
git add tests/review/test_report_writer_negotiation_chip.py src/contract_risk_analysis/review/report_writer.py
git commit -m "test: lock LLM2 non-hardcoding guardrails"
```

---

### Task 3: 收紧规则层推荐措辞，禁止样本答案上升为系统建议

**Files:**
- Modify: `src/contract_risk_analysis/review/adjudicate.py:257-385`
- Test: `tests/regression/test_judgment_regression.py`

- [ ] **Step 1: Write the failing test**

在 `tests/regression/test_judgment_regression.py` 追加下面的测试：

```python
from contract_risk_analysis.domain.free_review_schema import FreeReviewOutput, RiskSegment
from contract_risk_analysis.review.adjudicate import adjudicate


def test_payment_security_structure_recommendation_stays_generic() -> None:
    free_output = FreeReviewOutput(
        contract_id="generic-contract",
        overall_assessment="overall",
        risk_segments=[
            RiskSegment(
                clause_type="payment",
                risk_title="预付款比例过高",
                risk_description="签约后即支付高比例预付款。",
                evidence_text="签约后5日内支付合同总价60%作为预付款。",
                confidence=0.90,
                severity="high",
                canonical_type="payment_structure",
            ),
            RiskSegment(
                clause_type="payment",
                risk_title="质保金提交过晚",
                risk_description="保证金在尾款前才提交。",
                evidence_text="乙方应于支付剩余款项前提交质量保证金。",
                confidence=0.88,
                severity="medium",
                canonical_type="payment",
            ),
        ],
        missing_clauses=[],
        strengths=[],
    )

    result = adjudicate(free_output, review_party="buyer")
    structural = next(seg for seg in result.risk_segments if seg.canonical_type == "payment_security_structure")

    assert "显著降低前置付款比例" in structural.recommendation
    assert "覆盖资金敞口" in structural.recommendation
    assert "30%" not in structural.recommendation
    assert "10%" not in structural.recommendation
```

- [ ] **Step 2: Run test to verify it fails if sample anchors reappear**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/regression/test_judgment_regression.py -q
```

Expected: 如果规则层推荐重新出现样本化比例/金额，本测试会 FAIL；若当前已通过，则保留此测试作为回归护栏。

- [ ] **Step 3: Write minimal implementation**

确认 `src/contract_risk_analysis/review/adjudicate.py` 中 `payment_security_structure` 的 `recommendation` 保持如下泛化表达：

```python
            recommendation=(
                "优先要求：(1) 显著降低前置付款比例或将付款拆分至与交付/验收节点挂钩；"
                "(2) 将质保金/保证金提交节点提前至前置付款前或同期；"
                "(3) 如对方坚持高额前置付款，要求提供与该付款风险相匹配的有效担保或其他等价保护措施覆盖资金敞口"
            ),
```

如果当前文本已是上述形式，则不再扩改逻辑，只保留测试固化现状。

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/regression/test_judgment_regression.py -q
```

Expected: PASS，并保证规则层不会退化回“样本答案模板”。

- [ ] **Step 5: Commit**

```bash
git add tests/regression/test_judgment_regression.py src/contract_risk_analysis/review/adjudicate.py
git commit -m "test: keep adjudication recommendations sample-free"
```

---

### Task 4: 增加成品级 lint，阻止客户版泄漏与无来源数字

**Files:**
- Modify: `src/contract_risk_analysis/review/report_writer.py:1499-1605`
- Test: `tests/review/test_report_writer_negotiation_chip.py`
- Test: `tests/regression/test_judgment_regression.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/review/test_report_writer_negotiation_chip.py` 追加下面的测试：

```python
from contract_risk_analysis.domain.free_review_schema import ReportDossier
from contract_risk_analysis.review.report_writer import _run_pre_render_consistency_checks


def test_consistency_checks_flag_external_eval_mentions_in_customer_text() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="参考 DeepSeek 评价，本合同风险偏高。",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        favorable_terms=[],
        manual_review_items=[],
        internal_conflicts=[],
    )

    violations = _run_pre_render_consistency_checks(dossier)
    assert any("外部评价" in msg for msg in violations)


def test_consistency_checks_flag_freeform_numeric_estimates() -> None:
    dossier = ReportDossier(
        contract_id="test",
        review_party="buyer",
        risk_items=[],
        counterfactuals=[],
        bn_annotations=[],
        joint_risks=[],
        bn_summary="",
        overall_assessment="追回预付款的诉讼成本约20-50万元，成功回收率低于60%。",
        strengths=[],
        missing_clauses=[],
        signing_forbidden=[],
        signing_acceptable=[],
        negotiation_bottom_lines=[],
        favorable_terms=[],
        manual_review_items=[],
        internal_conflicts=[],
    )

    violations = _run_pre_render_consistency_checks(dossier)
    assert any("无来源数字" in msg for msg in violations)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: FAIL，因为 `_run_pre_render_consistency_checks()` 还没有覆盖“外部评价痕迹”与“无来源数字”这两类问题。

- [ ] **Step 3: Write minimal implementation**

在 `src/contract_risk_analysis/review/report_writer.py` 的 `_run_pre_render_consistency_checks()` 末尾加入如下检查：

```python
    # ── Check: External evaluation traces must not appear in customer-facing text ──
    external_eval_markers = ["DeepSeek", "网页评价", "AI网页端检测报告"]
    for text in visible_texts:
        if any(marker in text for marker in external_eval_markers):
            violations.append(
                f"客户版清洁度问题：用户可见文本「{text}」包含外部评价痕迹。"
                f"正式客户版必须基于本次独立审查结论输出，不得直接引用外部评价来源。"
            )

    # ── Check: Unsupported free-form numeric estimates ──
    suspicious_numeric_markers = ["诉讼成本约", "成功回收率低于", "资金成本计", "约20-50万", "低于60%"]
    for text in visible_texts:
        if any(marker in text for marker in suspicious_numeric_markers):
            violations.append(
                f"无来源数字风险：用户可见文本「{text}」包含估算性数字结论。"
                f"正式客户版只能使用可追溯到 Dossier、BN 或明确规则来源的数字。"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_report_writer_negotiation_chip.py -q
```

Expected: PASS，并继续保持已有 `ISSUE-` / 占位符 / 内部字段相关测试通过。

- [ ] **Step 5: Commit**

```bash
git add tests/review/test_report_writer_negotiation_chip.py src/contract_risk_analysis/review/report_writer.py
git commit -m "feat: lint external-eval traces and unsupported numeric claims"
```

---

### Task 5: 用真实样本做端到端验证，不覆盖旧报告

**Files:**
- Modify: `worklist/PROGRESS.md`
- Verify: `backend/routers/review.py`
- Verify: `合同检测报告/买卖合同/买卖合同.pdf`
- Verify: `合同检测报告/买卖合同/contract-review-买卖合同-*.md`

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/review/test_ai_review.py tests/review/test_report_writer_negotiation_chip.py tests/regression/test_judgment_regression.py -q
```

Expected: PASS，确认三层护栏都已被测试锁住。

- [ ] **Step 2: Re-run the real sample pipeline**

Run:

```bash
.venv/Scripts/python.exe - <<'PY'
from backend.routers.review import _run_v2_pipeline
from pathlib import Path

pdf_path = Path(r"E:\myProgram\BN-Contract-Risk-Analysis\合同检测报告\买卖合同\买卖合同.pdf")
result = _run_v2_pipeline(pdf_path)
print(type(result).__name__)
PY
```

Expected: 生成新的报告版本，不覆盖已有 `contract-review-买卖合同-19.md`。

- [ ] **Step 3: Verify the newly generated report against the guardrails**

人工核对新版本报告，确认以下项目全部满足：

```text
1. 不出现 ISSUE- / 渲染器备注 / 内部一致性警告 / TODO / TBD
2. 不直接引用 DeepSeek 或 AI 网页端评价
3. 不把某一份样本中的固定数字写成系统通用答案
4. BN 百分比只被表述为风险概率改善幅度，不被写成金钱估值
5. 付款主问题 / 质保从问题仍保持主从层次
6. 新版本文件名递增，不覆盖旧版
```

- [ ] **Step 4: Update progress log**

在 `worklist/PROGRESS.md` 顶部追加：

```md
## 2026-05-14：报告泛化实施限制固化完成

### 完成内容

| # | 事项 | 文件 | 状态 |
|---|------|------|:--:|
| 1 | LLM₁ 增加去硬编码与外评隔离约束 | `src/contract_risk_analysis/review/ai_review.py` | ✅ |
| 2 | LLM₂ 增加去硬编码与客户版清洁约束 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 3 | 规则层推荐保持泛化措辞 | `src/contract_risk_analysis/review/adjudicate.py` | ✅ |
| 4 | 成品级 lint 拦截外评痕迹与无来源数字 | `src/contract_risk_analysis/review/report_writer.py` | ✅ |
| 5 | 真实样本重跑验证通过 | `合同检测报告/买卖合同/` | ✅ |
```

- [ ] **Step 5: Commit**

```bash
git add worklist/PROGRESS.md tests/review/test_ai_review.py tests/review/test_report_writer_negotiation_chip.py tests/regression/test_judgment_regression.py src/contract_risk_analysis/review/ai_review.py src/contract_risk_analysis/review/report_writer.py src/contract_risk_analysis/review/adjudicate.py
git commit -m "feat: enforce report generalization guardrails"
```

---

## Acceptance Bar

只有同时满足以下条件，才算本方案完成：

1. 所有新增约束都进入源码提示、规则文案或确定性 lint，而不是只存在于人工口头约定。
2. 测试断言的是“泛化限制”和“禁止事项”，而不是某个样本专属数字模板。
3. 新生成客户版报告不出现内部标记、外部评价痕迹、占位符或无来源数字估算。
4. 新版本报告质量提升来自源头修复与泛化护栏，而不是手改输出文件。
5. 对未来不同合同类型复用时，不依赖买卖合同这一份样本的固定答案。

---

## Self-Review

### Spec coverage

- **不能硬编码** → Tasks 1-3
- **不能把外部评价当系统答案** → Tasks 1, 4
- **不能编造数字/必须数字可追溯** → Tasks 1, 4
- **不能手改客户版掩盖问题** → Task 5
- **客户版清洁度** → Tasks 2, 4, 5
- **适配所有合同而非单一样本** → Tasks 1-5

No requirement from the request is left uncovered.

### Placeholder scan

Checked for `TODO`, `TBD`, “implement later”, and “similar to Task N”. None remain as unresolved plan placeholders.

### Type consistency

- 使用的函数名均来自现有代码：`_free_review_prompt()`、`_build_combined_prompt()`、`_run_pre_render_consistency_checks()`、`adjudicate()`、`_run_v2_pipeline()`。
- 所有测试名与实施内容一一对应，没有引用未定义的新接口。

---

Plan complete and saved to `docs/superpowers/plans/2026-05-14-report-generalization-guardrails.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
