"""Evaluation metrics for contract risk analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClauseExtractionMetrics:
    """Per-clause-type extraction quality metrics."""
    clause_type: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        denom = self.true_positives + self.false_positives + self.false_negatives + self.true_negatives
        return (self.true_positives + self.true_negatives) / denom if denom > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "clause_type": self.clause_type,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
            "support": self.true_positives + self.false_negatives,
        }


@dataclass
class NliMetrics:
    """NLI task metrics for confidentiality node."""
    total: int = 0
    correct: int = 0
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0

    def record(self, predicted: str, actual: str) -> None:
        self.total += 1
        if predicted == actual:
            self.correct += 1
        self.confusion.setdefault(actual, {}).setdefault(predicted, 0)
        self.confusion[actual][predicted] += 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "accuracy": round(self.accuracy, 4),
            "confusion_matrix": {
                actual: {pred: count for pred, count in preds.items()}
                for actual, preds in self.confusion.items()
            },
        }


@dataclass
class RiskPredictionMetrics:
    """Risk level prediction metrics."""
    total: int = 0
    correct: int = 0
    within_one_level: int = 0
    level_order: dict[str, int] = field(default_factory=lambda: {"low": 0, "medium": 1, "high": 2})

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0

    @property
    def adjacent_accuracy(self) -> float:
        return (self.correct + self.within_one_level) / self.total if self.total > 0 else 0.0

    def record(self, predicted: str, actual: str) -> None:
        self.total += 1
        if predicted == actual:
            self.correct += 1
        elif abs(self.level_order.get(predicted, 0) - self.level_order.get(actual, 0)) == 1:
            self.within_one_level += 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "exact_accuracy": round(self.accuracy, 4),
            "adjacent_accuracy": round(self.adjacent_accuracy, 4),
        }


@dataclass
class BenchmarkResult:
    """Aggregated benchmark results."""
    name: str
    nli_metrics: NliMetrics = field(default_factory=NliMetrics)
    risk_metrics: RiskPredictionMetrics = field(default_factory=RiskPredictionMetrics)
    extraction_metrics: dict[str, ClauseExtractionMetrics] = field(default_factory=dict)
    samples_processed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "samples_processed": self.samples_processed,
            "error_count": len(self.errors),
            "nli": self.nli_metrics.to_dict(),
            "risk_prediction": self.risk_metrics.to_dict(),
            "extraction": {
                k: v.to_dict() for k, v in self.extraction_metrics.items()
            },
        }
