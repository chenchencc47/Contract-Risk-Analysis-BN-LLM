"""P3-2: Expected Calibration Error (ECE) for BN risk predictions.

ECE = Σ (|B_b| / N) * |acc(B_b) - conf(B_b)|

Where:
  acc(B_b): actual fraction of high-risk samples in bin b
  conf(B_b): mean predicted P(high) in bin b

ECE < 0.05: excellent, < 0.10: acceptable, >= 0.10: poorly calibrated
"""
import json, numpy as np
from collections import defaultdict
from contract_risk_analysis.bn.pgmpy_adapter import (
    load_v2_config, build_model, run_inference,
)
from contract_risk_analysis.domain.review_schema import ReviewFinding, ReviewResult
from contract_risk_analysis.pipeline.build_evidence import build_evidence

from pathlib import Path

CONTRACTNLI_PATH = (
    Path(__file__).resolve().parents[3] / "dataset" / "ContractNLI" / "contract_nli_v1.jsonl"
)


def _nli_label_to_risk_level(label: str) -> str:
    if label == "contradiction":
        return "high"
    elif label == "neutral":
        return "medium"
    return "low"


def run_ece_benchmark(max_samples: int = 500, split: str = "test"):
    """Compute ECE for BN predictions on ContractNLI."""
    config = load_v2_config()
    model = build_model(config)

    samples = []
    with open(CONTRACTNLI_PATH, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("subset") == split:
                samples.append(data)
            if len(samples) >= max_samples:
                break

    predictions: list[tuple[float, bool]] = []

    for i, sample in enumerate(samples):
        gold_label = sample["label"]
        premise = sample["premise"]
        hypothesis = sample["hypothesis"]
        actual_high = gold_label == "contradiction"

        # Build evidence from gold label
        findings = [
            ReviewFinding(
                clause_type="confidentiality",
                status={
                    "entailment": "entailment",
                    "neutral": "neutral",
                    "contradiction": "contradiction",
                }.get(gold_label, "neutral"),
                evidence_text=premise[:100],
                confidence=1.0,
                hypothesis=hypothesis,
                finding_key=None,
            )
        ]
        review_result = ReviewResult(
            contract_id=f"contractnli-ece-{i}",
            findings=findings,
        )

        try:
            evidence = build_evidence(review_result)
            result = run_inference(
                model=model,
                evidence=evidence.node_states if evidence.node_states else None,
                config=config,
            )
            p_high = result.overall_risk_distribution.get("high", 0.0)
            predictions.append((p_high, actual_high))
        except Exception:
            continue

    if not predictions:
        print("No predictions collected.")
        return

    # ECE computation: 10 bins
    n_bins = 10
    bins = defaultdict(list)
    for p_high, actual in predictions:
        bin_idx = min(int(p_high * n_bins), n_bins - 1)
        bins[bin_idx].append((p_high, actual))

    ece = 0.0
    N = len(predictions)
    print(f"ECE Analysis: {N} samples, {n_bins} bins")
    print(f'{"Bin":<12} {"Count":>6} {"Mean P(high)":>13} {"Actual High%":>13} {"|Diff|":>8} {"Weight":>8}')
    print("-" * 65)

    for b in range(n_bins):
        items = bins.get(b, [])
        if not items:
            continue
        count = len(items)
        mean_conf = np.mean([p for p, _ in items])
        actual_frac = np.mean([a for _, a in items])
        diff = abs(mean_conf - actual_frac)
        weight = count / N
        ece += weight * diff
        bar = "█" * int(mean_conf * 20)
        print(
            f"{b/n_bins:.1f}-{(b+1)/n_bins:.1f}    "
            f"{count:>6}  {mean_conf:>13.4f}  {actual_frac:>13.4f}  {diff:>8.4f}  {weight:>8.4f}  {bar}"
        )

    print("-" * 65)
    print(f"ECE = {ece:.4f}")
    if ece < 0.05:
        print("Rating: EXCELLENT (ECE < 0.05)")
    elif ece < 0.10:
        print("Rating: ACCEPTABLE (ECE < 0.10)")
    else:
        print("Rating: POORLY CALIBRATED (ECE >= 0.10)")

    return {"ece": round(ece, 4), "n_samples": N, "n_bins": n_bins}


if __name__ == "__main__":
    run_ece_benchmark(max_samples=500)
