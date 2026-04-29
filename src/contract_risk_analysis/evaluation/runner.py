"""Benchmark runner for contract risk analysis pipeline (P3.1, P3.3, P3.4).

Runs LLM extraction + evidence mapping + BN inference on datasets,
computes metrics, and supports baseline comparisons.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from contract_risk_analysis.bn.inference import assess_risk
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult
from contract_risk_analysis.evaluation.metrics import (
    BenchmarkResult,
    ClauseExtractionMetrics,
    NliMetrics,
    RiskPredictionMetrics,
)
from contract_risk_analysis.pipeline.build_evidence import build_evidence


CONTRACTNLI_PATH = Path(__file__).resolve().parents[3] / "dataset" / "ContractNLI" / "contract_nli_v1.jsonl"
CUAD_PATH = Path(__file__).resolve().parents[3] / "dataset" / "CUAD" / "data" / "CUADv1.json"

# Mapping from ContractNLI labels to our BN node states
NLI_LABEL_TO_STATE = {
    "entailment": "entailment",
    "neutral": "neutral",
    "contradiction": "contradiction",
}

# Risk level order for ordinal comparison
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _nli_label_to_risk_level(label: str) -> str:
    """Map ContractNLI label to a risk level for ordinal comparison."""
    if label == "contradiction":
        return "high"
    elif label == "neutral":
        return "medium"
    else:
        return "low"


def _risk_level_from_distribution(dist: dict[str, float]) -> str:
    """Get most likely risk level from a probability distribution."""
    return max(dist, key=dist.get)


def run_contractnli_benchmark(
    max_samples: int = 200,
    split: str = "test",
    use_llm: bool = False,
    verbose: bool = False,
) -> BenchmarkResult:
    """Evaluate the full pipeline on ContractNLI data.

    For each sample, extracts findings from the premise text via LLM
    (or uses the ground-truth label directly for pure-BN evaluation),
    runs BN inference, and compares with the expected label.

    Args:
        max_samples: Maximum number of samples to evaluate.
        split: Data split to use ('train', 'dev', 'test').
        use_llm: If True, runs LLM extraction. If False, uses gold labels
                  directly as evidence (evaluating BN calibration only).
        verbose: Print per-sample details.

    Returns:
        BenchmarkResult with NLI and risk metrics.
    """
    result = BenchmarkResult(name=f"contractnli_{split}")
    nli_metrics = NliMetrics()
    risk_metrics = RiskPredictionMetrics()

    samples = []
    with open(CONTRACTNLI_PATH, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("subset") == split:
                samples.append(data)
            if len(samples) >= max_samples:
                break

    result.samples_processed = len(samples)

    for i, sample in enumerate(samples):
        try:
            gold_label = sample["label"]
            premise = sample["premise"]
            hypothesis = sample["hypothesis"]

            if use_llm:
                # LLM extraction path
                try:
                    from contract_risk_analysis.review.ai_review import review_contract_text
                    review_result = review_contract_text(
                        premise, contract_id=f"contractnli-{i}",
                        source_document="contractnli",
                    )
                except Exception as exc:
                    result.errors.append(f"LLM extraction error sample {i}: {exc}")
                    continue

                findings = review_result.findings
            else:
                # Use gold label directly as evidence (BN-only evaluation)
                findings = [
                    ReviewFinding(
                        clause_type="confidentiality",
                        status=NLI_LABEL_TO_STATE.get(gold_label, "neutral"),
                        evidence_text=premise[:100],
                        confidence=1.0,
                        hypothesis=hypothesis,
                        finding_key=None,
                    )
                ]
                review_result = ReviewResult(
                    contract_id=f"contractnli-{i}",
                    findings=findings,
                )

            # Build evidence and run BN inference
            evidence = build_evidence(review_result)
            report = assess_risk(evidence)

            # Record NLI metrics: check confidentiality_nli node state
            predicted_nli = evidence.node_states.get("confidentiality_nli", "neutral")
            nli_metrics.record(predicted_nli, gold_label)

            # Record risk metrics
            predicted_risk = report.overall_risk
            actual_risk = _nli_label_to_risk_level(gold_label)
            risk_metrics.record(predicted_risk, actual_risk)

            if verbose and i < 5:
                print(f"Sample {i}: gold={gold_label}, pred_nli={predicted_nli}, "
                      f"pred_risk={predicted_risk}, actual_risk={actual_risk}")

        except Exception as exc:
            result.errors.append(f"Sample {i} error: {exc}")

    result.nli_metrics = nli_metrics
    result.risk_metrics = risk_metrics
    return result


def run_cuad_benchmark(
    max_contracts: int = 50,
    use_llm: bool = False,
    verbose: bool = False,
) -> BenchmarkResult:
    """Evaluate clause extraction accuracy on CUAD data.

    For each contract, the LLM extracts clauses. Compares the detected
    clause types against CUAD gold labels.

    Args:
        max_contracts: Maximum contracts to evaluate.
        use_llm: If True, runs LLM extraction per contract.
        verbose: Print per-contract details.
    """
    result = BenchmarkResult(name="cuad_extraction")
    if not CUAD_PATH.exists():
        result.errors.append("CUAD dataset not found at expected path")
        return result

    with open(CUAD_PATH, encoding="utf-8") as f:
        cuad_data = json.load(f)

    # Build gold clause_type → category mapping
    # CUAD questions map to our clause types
    cuad_category_to_clause: dict[str, str] = {
        "Termination For Convenience": "termination",
        "Uncapped Liability": "liability_cap",
        "Cap On Liability": "liability_cap",
        "Governing Law": "governing_law",
        "Anti-Assignment": "termination",
        "Notice Period To Terminate Renewal": "termination",
        "Liquidated Damages": "liability_cap",
        "Insurance": "liability_cap",
        "Warranty Duration": "liability_cap",
        "Covenant Not To Sue": "liability_cap",
        "Non-Compete": "termination",
        "Exclusivity": "termination",
        "No-Solicit Of Customers": "termination",
        "No-Solicit Of Employees": "termination",
        "Non-Disparagement": "termination",
        "Change Of Control": "termination",
        "Revenue/Profit Sharing": "liability_cap",
        "Minimum Commitment": "termination",
        "Volume Restriction": "termination",
        "Ip Ownership Assignment": "termination",
        "Joint Ip Ownership": "termination",
        "License Grant": "termination",
        "Non-Transferable License": "termination",
        "Affiliate License-Licensor": "termination",
        "Affiliate License-Licensee": "termination",
        "Unlimited/All-You-Can-Eat-License": "termination",
        "Irrevocable Or Perpetual License": "termination",
        "Source Code Escrow": "termination",
        "Post-Termination Services": "termination",
        "Audit Rights": "termination",
        "Third Party Beneficiary": "termination",
        "Most Favored Nation": "termination",
        "Price Restrictions": "liability_cap",
        "Rofr/Rofo/Rofn": "termination",
        "Competitive Restriction Exception": "termination",
    }

    extraction_map: dict[str, ClauseExtractionMetrics] = {
        ct: ClauseExtractionMetrics(clause_type=ct)
        for ct in {"termination", "liability_cap", "confidentiality",
                    "governing_law", "dispute_resolution", "acceptance",
                    "payment", "delivery"}
    }

    contracts = cuad_data.get("data", [])[:max_contracts]
    result.samples_processed = len(contracts)

    for ci, contract in enumerate(contracts):
        try:
            full_text = ""
            gold_clause_types: set[str] = set()
            for para in contract.get("paragraphs", []):
                full_text += para.get("context", "") + "\n"
                for qa in para.get("qas", []):
                    question = qa.get("question", "")
                    has_answer = any(a.get("text", "") for a in qa.get("answers", []))
                    for cat_name, ct in cuad_category_to_clause.items():
                        if cat_name.lower() in question.lower() and has_answer:
                            gold_clause_types.add(ct)

            if use_llm:
                try:
                    from contract_risk_analysis.review.ai_review import review_contract_text
                    review_result = review_contract_text(
                        full_text[:8000],
                        contract_id=contract.get("title", f"cuad-{ci}"),
                        source_document="cuad",
                    )
                    detected_clause_types = {f.clause_type for f in review_result.findings}
                except Exception as exc:
                    result.errors.append(f"LLM error on contract {ci}: {exc}")
                    continue
            else:
                detected_clause_types = set()

            # Update metrics
            for ct in extraction_map:
                if ct in detected_clause_types:
                    if ct in gold_clause_types:
                        extraction_map[ct].true_positives += 1
                    else:
                        extraction_map[ct].false_positives += 1
                else:
                    if ct in gold_clause_types:
                        extraction_map[ct].false_negatives += 1
                    else:
                        extraction_map[ct].true_negatives += 1

            if verbose and ci < 3:
                print(f"Contract {ci}: gold={gold_clause_types}, detected={detected_clause_types}")

        except Exception as exc:
            result.errors.append(f"Contract {ci} error: {exc}")

    result.extraction_metrics = extraction_map
    return result


def run_baseline_comparison(
    contract_samples: list[tuple[str, str]] | None = None,
    max_samples: int = 100,
) -> list[BenchmarkResult]:
    """Compare LLM-only vs LLM+Rules vs LLM+BN (P3.4).

    Uses ContractNLI test set to compare risk prediction accuracy
    across three configurations.
    """
    results: list[BenchmarkResult] = []

    # 1. Pure BN with gold labels (upper bound)
    bn_result = run_contractnli_benchmark(max_samples=max_samples, split="test", use_llm=False)
    bn_result.name = "pure_bn_gold_evidence"
    results.append(bn_result)

    # 2. LLM + BN (if LLM available)
    # Skipped in offline mode — requires API calls
    llm_bn_result = BenchmarkResult(name="llm_bn_pipeline")
    llm_bn_result.errors.append("LLM+BN baseline requires API access — run with use_llm=True")
    results.append(llm_bn_result)

    # 3. LLM-only direct risk assessment
    llm_only = BenchmarkResult(name="llm_only")
    llm_only.errors.append("LLM-only baseline requires separate prompt design — not implemented")
    results.append(llm_only)

    return results


def save_benchmark_results(results: list[BenchmarkResult], output_path: str | Path) -> None:
    """Save benchmark results to JSON."""
    payload = {
        "benchmark_timestamp": None,  # filled by caller if needed
        "results": [r.to_dict() for r in results],
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def print_benchmark_summary(results: list[BenchmarkResult]) -> str:
    """Print a human-readable summary of benchmark results."""
    lines = ["=" * 60, "  BENCHMARK RESULTS SUMMARY", "=" * 60, ""]
    for r in results:
        lines.append(f"--- {r.name} ---")
        lines.append(f"  Samples: {r.samples_processed}, Errors: {len(r.errors)}")
        m = r.nli_metrics
        if m.total > 0:
            lines.append(f"  NLI Accuracy: {m.accuracy:.4f} ({m.correct}/{m.total})")
            lines.append(f"  Confusion Matrix: {json.dumps(m.confusion, ensure_ascii=False)}")
        rm = r.risk_metrics
        if rm.total > 0:
            lines.append(f"  Risk Accuracy: {rm.accuracy:.4f}")
            lines.append(f"  Risk Adjacent Accuracy: {rm.adjacent_accuracy:.4f}")
        for ct, em in r.extraction_metrics.items():
            if em.true_positives + em.false_negatives > 0:
                lines.append(f"  [{ct}] P={em.precision:.3f} R={em.recall:.3f} F1={em.f1:.3f}")
        if r.errors:
            lines.append(f"  Errors ({len(r.errors)}):")
            for e in r.errors[:3]:
                lines.append(f"    - {e}")
        lines.append("")
    return "\n".join(lines)
