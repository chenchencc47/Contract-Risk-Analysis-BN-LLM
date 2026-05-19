"""Rule-based scoring for golden cases and golden patterns.

This module is for offline regression evaluation. It does not participate in
production contract review decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CheckResult:
    id: str
    passed: bool
    expected: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "passed": self.passed,
            "expected": self.expected,
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
        }


@dataclass
class GoldenCaseScore:
    case_id: str
    report_path: str
    must_find: list[CheckResult]
    must_not: list[CheckResult]
    should_find_advantages: list[CheckResult]

    @property
    def must_find_passed(self) -> int:
        return sum(1 for item in self.must_find if item.passed)

    @property
    def must_not_passed(self) -> int:
        return sum(1 for item in self.must_not if item.passed)

    @property
    def should_passed(self) -> int:
        return sum(1 for item in self.should_find_advantages if item.passed)

    @property
    def score(self) -> float:
        total_weight = len(self.must_find) * 3 + len(self.must_not) * 3 + len(self.should_find_advantages)
        if total_weight == 0:
            return 0.0
        earned = self.must_find_passed * 3 + self.must_not_passed * 3 + self.should_passed
        return round(earned / total_weight * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "report_path": self.report_path,
            "score": self.score,
            "summary": {
                "must_find": f"{self.must_find_passed}/{len(self.must_find)}",
                "must_not": f"{self.must_not_passed}/{len(self.must_not)}",
                "should_find_advantages": f"{self.should_passed}/{len(self.should_find_advantages)}",
            },
            "must_find": [item.to_dict() for item in self.must_find],
            "must_not": [item.to_dict() for item in self.must_not],
            "should_find_advantages": [item.to_dict() for item in self.should_find_advantages],
        }


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


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_golden_cases(directory: str | Path) -> list[dict[str, Any]]:
    root = Path(directory)
    if not root.exists():
        return []
    return [load_yaml(path) for path in sorted(root.glob("*.yaml"))]


def load_golden_patterns(directory: str | Path) -> list[dict[str, Any]]:
    root = Path(directory)
    if not root.exists():
        return []
    return [load_yaml(path) for path in sorted(root.glob("*.yaml"))]


def _normalize(text: str) -> str:
    return text.lower().replace(" ", "").replace("\n", "")


def _keyword_hits(text: str, keywords: list[str]) -> tuple[list[str], list[str]]:
    normalized = _normalize(text)
    matched: list[str] = []
    missing: list[str] = []
    for keyword in keywords:
        if _normalize(str(keyword)) in normalized:
            matched.append(str(keyword))
        else:
            missing.append(str(keyword))
    return matched, missing


def _check_expected_item(report_text: str, item: dict[str, Any]) -> CheckResult:
    keywords = [str(k) for k in item.get("evidence_keywords", [])]
    matched, missing = _keyword_hits(report_text, keywords)
    return CheckResult(
        id=str(item.get("id", "unknown")),
        expected=str(item.get("expected", "")),
        passed=bool(keywords) and bool(matched),
        matched_keywords=matched,
        missing_keywords=missing,
    )


def _check_forbidden_item(report_text: str, item: dict[str, Any]) -> CheckResult:
    patterns = [str(k) for k in item.get("wrong_patterns", [])]
    matched, missing = _keyword_hits(report_text, patterns)
    if not patterns:
        forbidden = str(item.get("forbidden", ""))
        patterns = [forbidden] if forbidden else []
        matched, missing = _keyword_hits(report_text, patterns)
    return CheckResult(
        id=str(item.get("id", "unknown")),
        expected=str(item.get("forbidden", "")),
        passed=not matched,
        matched_keywords=matched,
        missing_keywords=missing,
    )


def score_golden_case(case: dict[str, Any], report_text: str, report_path: str = "") -> GoldenCaseScore:
    must_find = [_check_expected_item(report_text, item) for item in case.get("must_find", [])]
    must_not = [_check_forbidden_item(report_text, item) for item in case.get("must_not", [])]
    should = [_check_expected_item(report_text, item) for item in case.get("should_find_advantages", [])]
    return GoldenCaseScore(
        case_id=str(case.get("case_id", "unknown")),
        report_path=report_path,
        must_find=must_find,
        must_not=must_not,
        should_find_advantages=should,
    )


def score_report_against_case(case_path: str | Path, report_path: str | Path) -> GoldenCaseScore:
    case = load_yaml(case_path)
    report = Path(report_path).read_text(encoding="utf-8")
    return score_golden_case(case, report, str(report_path))


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


def auto_score_report_text(
    report_text: str,
    cases_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """v2.16: Auto-score a report against all golden cases, return the best match.

    This is designed to be called from the API after report generation,
    giving the user immediate feedback on report quality.

    Returns None if no golden cases found, or a dict with score details.
    """
    if cases_dir is None:
        cases_dir = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "golden_cases"

    cases = load_golden_cases(cases_dir)
    if not cases:
        return None

    best_score: GoldenCaseScore | None = None
    best_case: dict[str, Any] | None = None

    for case in cases:
        score = score_golden_case(case, report_text)
        if best_score is None or score.score > best_score.score:
            best_score = score
            best_case = case

    if best_score is None or best_case is None:
        return None

    # Build a user-friendly summary
    must_find_missed = [
        item.id for item in best_score.must_find if not item.passed
    ]
    must_not_violated = [
        item.id for item in best_score.must_not if not item.passed
    ]
    advantages_found = [
        item.id for item in best_score.should_find_advantages if item.passed
    ]

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


def summarize_patterns(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return pattern metadata for reports/CLI without evaluating production logic yet."""
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        rows.append({
            "pattern_id": pattern.get("pattern_id"),
            "pattern_name": pattern.get("pattern_name"),
            "status": pattern.get("status"),
            "source_cases": pattern.get("source_cases", []),
            "applies_to": pattern.get("applies_to", {}),
        })
    return rows


# ═══════════════════════════════════════════════════════════════════
#  v2.16-D: Pattern → Production Rule alignment
# ═══════════════════════════════════════════════════════════════════


# Mapping from pattern_id to the production rules that cover it.
# Each entry lists where the pattern is enforced in the production pipeline.
PATTERN_PRODUCTION_COVERAGE: dict[str, dict] = {
    "high_prepayment_without_security": {
        "aligned": True,
        "coverage": [
            {
                "layer": "party_aware_rules",
                "rule": "payment_structure (buyer: maintain_high, seller: mark_favorable)",
                "file": "config/party_aware_rules.yaml",
            },
            {
                "layer": "adjudication",
                "rule": "_detect_payment_security_inversion — detects high prepayment + absent security",
                "file": "src/contract_risk_analysis/review/adjudicate.py",
            },
        ],
    },
    "deposit_after_prepayment_inversion": {
        "aligned": True,
        "coverage": [
            {
                "layer": "party_aware_rules",
                "rule": "payment_security_structure (buyer: maintain_high, seller: mark_favorable)",
                "file": "config/party_aware_rules.yaml",
            },
            {
                "layer": "adjudication",
                "rule": "_detect_payment_security_inversion — specifically detects deposit-after-prepayment inversion",
                "file": "src/contract_risk_analysis/review/adjudicate.py",
            },
        ],
    },
    "liability_cap_by_party_stance": {
        "aligned": True,
        "coverage": [
            {
                "layer": "party_aware_rules",
                "rule": "liability_cap (buyer: reclassify_favorable → positive, seller: maintain_high)",
                "file": "config/party_aware_rules.yaml",
            },
            {
                "layer": "bn_interpretation",
                "rule": "liability_cap / liability_cap_strength — report_usage='defensive_chip_only' (buyer)",
                "file": "src/contract_risk_analysis/review/report_writer.py",
            },
        ],
    },
    "jurisdiction_by_party_stance": {
        "aligned": True,
        "coverage": [
            {
                "layer": "party_aware_rules",
                "rule": "jurisdiction (buyer: mark_favorable + 底线筹码, seller: maintain_high)",
                "file": "config/party_aware_rules.yaml",
            },
            {
                "layer": "bn_interpretation",
                "rule": "jurisdiction_fairness — report_usage='defensive_chip_only' (buyer)",
                "file": "src/contract_risk_analysis/review/report_writer.py",
            },
        ],
    },
    "early_risk_transfer_before_final_acceptance": {
        "aligned": True,
        "coverage": [
            {
                "layer": "party_aware_rules",
                "rule": "risk_transfer (buyer: maintain_high + 底线筹码, seller: mark_favorable + 底线筹码)",
                "file": "config/party_aware_rules.yaml",
            },
        ],
    },
}


@dataclass
class PatternAlignmentReport:
    """v2.16-D: Report on which golden patterns are aligned to production rules."""
    patterns_checked: int
    patterns_aligned: int
    patterns_unaligned: int
    details: list[dict[str, Any]]

    @property
    def all_aligned(self) -> bool:
        return self.patterns_unaligned == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "patterns_checked": self.patterns_checked,
            "patterns_aligned": self.patterns_aligned,
            "patterns_unaligned": self.patterns_unaligned,
            "all_aligned": self.all_aligned,
            "details": self.details,
        }


def check_pattern_production_alignment(
    patterns_dir: str | Path | None = None,
) -> PatternAlignmentReport:
    """v2.16-D: Verify each golden pattern has corresponding production rule coverage.

    Checks each pattern in the golden_patterns directory against the known
    PATTERN_PRODUCTION_COVERAGE map. Patterns not in the map are flagged as
    unaligned and need manual review.

    Returns a PatternAlignmentReport suitable for CLI display and regression testing.
    """
    if patterns_dir is None:
        patterns_dir = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "golden_patterns"

    patterns = load_golden_patterns(patterns_dir)
    details: list[dict[str, Any]] = []
    aligned_count = 0
    unaligned_count = 0

    for p in patterns:
        pid = p.get("pattern_id", "unknown")
        coverage = PATTERN_PRODUCTION_COVERAGE.get(pid)

        if coverage and coverage.get("aligned"):
            aligned_count += 1
            details.append({
                "pattern_id": pid,
                "pattern_name": p.get("pattern_name", ""),
                "aligned": True,
                "coverage": coverage.get("coverage", []),
            })
        else:
            unaligned_count += 1
            details.append({
                "pattern_id": pid,
                "pattern_name": p.get("pattern_name", ""),
                "aligned": False,
                "coverage": coverage.get("coverage", []) if coverage else [],
                "note": "未在 PATTERN_PRODUCTION_COVERAGE 中找到对齐记录，需人工确认是否需要新增 production rule。",
            })

    return PatternAlignmentReport(
        patterns_checked=len(patterns),
        patterns_aligned=aligned_count,
        patterns_unaligned=unaligned_count,
        details=details,
    )


# ═══════════════════════════════════════════════════════════════════
#  v2.16-E: LLM-as-judge scaffolding (prompt template + schema)
# ═══════════════════════════════════════════════════════════════════


# Scoring dimensions from spec §3.6, used as JSON schema constraints
LLM_JUDGE_SCORING_DIMENSIONS = {
    "core_risk_identification": {
        "label": "核心风险识别",
        "max_score": 25,
        "description": "是否抓住真正致命问题，不遗漏、不稀释关键风险",
        "scoring_guidance": "报告识别了合同中所有致命和高风险条款（来自golden case的must_find），并按正确优先级排列",
    },
    "stance_correctness": {
        "label": "立场正确性",
        "max_score": 20,
        "description": "是否正确站在买方/卖方立场判断，不将优势误判为风险",
        "scoring_guidance": "有利条款被正确识别为优势而非风险（对应golden case的must_not和should_find_advantages）",
    },
    "evidence_binding": {
        "label": "原文证据绑定",
        "max_score": 15,
        "description": "是否引用准确的条款编号和原文摘录",
        "scoring_guidance": "每个核心风险判断都有合同原文引用，条款编号和页码准确",
    },
    "recommendation_quality": {
        "label": "修改建议质量",
        "max_score": 15,
        "description": "修改建议是否具体、可执行、可直接落地",
        "scoring_guidance": "建议包含具体修改措辞、数字基准（百分比/金额/天数），不泛泛而谈",
    },
    "negotiation_strategy": {
        "label": "谈判策略质量",
        "max_score": 15,
        "description": "是否有筹码意识、退让阶梯、交换逻辑",
        "scoring_guidance": "筹码分类正确（底线/交换/响应），每个筹码有对手话术预判和交换方案",
    },
    "bn_usage": {
        "label": "BN使用合理性",
        "max_score": 5,
        "description": "是否正确解释BN数据，不越权、不编造",
        "scoring_guidance": "BN数据使用符合v2.13-C护栏：防守筹码数据不写成修改建议，人工复核数据标注了标记",
    },
    "clarity": {
        "label": "表达与结构",
        "max_score": 5,
        "description": "是否清晰可读，结构完整，无前后矛盾",
        "scoring_guidance": "报告章节完整，语言专业且业务可读，第五章与第六章无策略矛盾",
    },
}


def build_llm_judge_prompt(
    report_text: str,
    golden_case: dict[str, Any] | None = None,
    golden_patterns_meta: list[dict[str, Any]] | None = None,
) -> str:
    """v2.16-E: Build the LLM-as-judge evaluation prompt.

    The judge MUST use the golden case/pattern criteria as evaluation standards.
    It is FORBIDDEN from inventing its own scoring criteria.

    This function does NOT call an LLM — it only constructs the prompt.
    The actual LLM call is reserved for a future implementation phase.

    Args:
        report_text: The full report Markdown text to evaluate.
        golden_case: Optional golden case YAML for reference criteria.
        golden_patterns_meta: Optional list of golden pattern metadata.

    Returns:
        A complete prompt string ready for LLM evaluation.
    """
    dimensions_desc = "\n".join(
        f"- **{d['label']}**（{d['max_score']}分）：{d['description']}\n  {d['scoring_guidance']}"
        for d in LLM_JUDGE_SCORING_DIMENSIONS.values()
    )

    golden_context = ""
    if golden_case:
        must_find_items = golden_case.get("must_find", [])
        must_not_items = golden_case.get("must_not", [])
        advantages = golden_case.get("should_find_advantages", [])

        golden_context = f"""
## 评测基准：Golden Case（评分必须基于此标准）

### 必须识别（must_find）
{chr(10).join(f"- {item.get('id')}: {item.get('expected', '')}" for item in must_find_items) if must_find_items else '（无）'}

### 禁止误判（must_not）
{chr(10).join(f"- {item.get('id')}: {item.get('forbidden', '')}" for item in must_not_items) if must_not_items else '（无）'}

### 应识别的优势（should_find_advantages）
{chr(10).join(f"- {item.get('id')}: {item.get('expected', '')}" for item in advantages) if advantages else '（无）'}
"""

    if golden_patterns_meta:
        patterns_desc = "\n".join(
            f"- {p.get('pattern_name', p.get('pattern_id', ''))}：{p.get('applies_to', {})}"
            for p in (golden_patterns_meta or [])
        )
        golden_context += f"""
## 评测基准：Golden Patterns（可泛化风险模式）

以下模式是本次评测的参考框架，报告应在满足条件时给出正确方向：
{patterns_desc}
"""

    return f"""你是一位合同风险审查报告的质量评估专家。

你的任务是根据给定的评测标准，对以下合同审查报告进行评分。

## 评分维度

{dimensions_desc}

## 评分规则

1. **你必须严格基于评测基准（Golden Case/Pattern）进行评分。** 不得自由制定评分标准。
2. 每个维度的得分必须在0到{sum(d['max_score'] for d in LLM_JUDGE_SCORING_DIMENSIONS.values())}分之间。
3. 扣分必须有明确理由，引用报告中的具体问题。
4. 如果报告在某个维度上完全符合要求，应给满分。
5. 如果报告在某个维度上存在方向性错误（如把买方优势写成风险），该维度得0分。
{golden_context}

## 输出格式

请输出严格符合以下JSON Schema的评分结果（不要输出其他内容）：

```json
{{
  "total_score": <0-100>,
  "dimensions": {{
    "core_risk_identification": {{"score": <0-25>, "reason": "<扣分或得分理由>"}},
    "stance_correctness": {{"score": <0-20>, "reason": "<扣分或得分理由>"}},
    "evidence_binding": {{"score": <0-15>, "reason": "<扣分或得分理由>"}},
    "recommendation_quality": {{"score": <0-15>, "reason": "<扣分或得分理由>"}},
    "negotiation_strategy": {{"score": <0-15>, "reason": "<扣分或得分理由>"}},
    "bn_usage": {{"score": <0-5>, "reason": "<扣分或得分理由>"}},
    "clarity": {{"score": <0-5>, "reason": "<扣分或得分理由>"}}
  }},
  "overall_assessment": "<2-3句总体评价，指出最大亮点和最严重问题>",
  "top_issues": ["<最严重的1-3个问题>"],
  "top_strengths": ["<最突出的1-3个亮点>"]
}}
```

---
## 待评测报告

{report_text[:32000]}

---
现在请严格按照上述标准和格式进行评分。直接输出JSON，不要有任何前言或后记。"""
