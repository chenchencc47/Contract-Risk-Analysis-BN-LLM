"""BN configuration validator (P6.2).

Validates bayesian_network_v2.json for structural and probability consistency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


V2_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "bayesian_network_v2.json"


@dataclass
class ConfigIssue:
    level: str  # 'error' | 'warning'
    node: str | None
    message: str


@dataclass
class ValidationReport:
    issues: list[ConfigIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ConfigIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ConfigIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, node: str | None, message: str) -> None:
        self.issues.append(ConfigIssue("error", node, message))

    def add_warning(self, node: str | None, message: str) -> None:
        self.issues.append(ConfigIssue("warning", node, message))

    def to_text(self) -> str:
        lines = ["=== BN Config Validation Report ===", ""]
        lines.append(f"Errors: {len(self.errors)}, Warnings: {len(self.warnings)}")
        if self.is_valid:
            lines.append("Status: VALID")
        else:
            lines.append("Status: INVALID")
        lines.append("")
        for issue in self.issues:
            prefix = f"[{issue.level.upper()}]"
            node_str = f" ({issue.node})" if issue.node else ""
            lines.append(f"  {prefix}{node_str} {issue.message}")
        return "\n".join(lines)


def validate_v2_config(config_path: str | Path | None = None) -> ValidationReport:
    """Validate bayesian_network_v2.json."""
    path = Path(config_path) if config_path else V2_CONFIG_PATH
    report = ValidationReport()

    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        report.add_error(None, f"Cannot load config: {exc}")
        return report

    # 1. Schema checks
    for key in ("version", "edges", "nodes"):
        if key not in config:
            report.add_error(None, f"Missing top-level key: '{key}'")

    if "version" in config and str(config["version"]) != "2.0":
        report.add_warning(None, f"Expected version 2.0, got {config['version']}")

    nodes_dict = config.get("nodes", {})
    edges = config.get("edges", [])

    # 2. Validate nodes referenced in edges exist
    for edge in edges:
        for n in edge:
            if n not in nodes_dict:
                report.add_error(n, f"Edge references non-existent node '{n}'")

    # 3. Validate each node
    for node_name, node_config in nodes_dict.items():
        # States
        states = node_config.get("states", [])
        if not states:
            report.add_error(node_name, "Node has no states defined")
        if len(states) != len(set(states)):
            report.add_error(node_name, f"Duplicate states: {states}")

        # Parents consistency
        parents = node_config.get("parents", [])
        for p in parents:
            if p not in nodes_dict:
                report.add_error(node_name, f"Parent '{p}' not found in nodes")
        # Check parent in edges
        for p in parents:
            if [p, node_name] not in edges:
                report.add_warning(node_name, f"Parent '{p}' not connected by edge to '{node_name}'")

        # CPT checks (skip noisy-or markers)
        cpt = node_config.get("cpt", {})
        if isinstance(cpt, dict) and cpt.get("_noisy_or"):
            # Validate weights exist
            weights = node_config.get("noisy_or_weights", {})
            for p in parents:
                if p not in weights:
                    report.add_warning(node_name, f"Noisy-or parent '{p}' missing weight")
            continue

        if not parents:
            # Prior: check all states covered
            cpt_keys = set(cpt.keys())
            if "unknown" in states and "unknown" not in cpt_keys:
                report.add_warning(node_name, "Missing 'unknown' in prior CPT")
            total = sum(float(cpt.get(s, 0)) for s in states if s in cpt_keys)
            if total > 0 and abs(total - 1.0) > 0.05:
                report.add_warning(node_name, f"Prior probabilities sum to {total:.4f}")
        else:
            n_combos = 1
            for p_name in parents:
                if p_name in nodes_dict:
                    n_combos *= max(len(nodes_dict[p_name].get("states", [])), 1)
            if len(cpt) < n_combos * 0.5 and not isinstance(cpt, dict):
                pass  # CPT will be auto-filled
            if len(cpt) < n_combos * 0.5 and len(parents) <= 2 and not cpt.get("_noisy_or"):
                report.add_warning(
                    node_name,
                    f"CPT has {len(cpt)} entries but needs ~{n_combos} "
                    f"({len(parents)} parents). Will auto-fill missing."
                )

    # 4. Check for cycles (simple reachability)
    for node_name in nodes_dict:
        visited: set[str] = set()
        stack = [node_name]
        cycled = False
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            for e in edges:
                if e[0] == n:
                    if e[1] == node_name:
                        report.add_error(node_name, f"Cycle detected involving '{node_name}'")
                        cycled = True
                        break
                    stack.append(e[1])
            if cycled:
                break

    # 5. Check unused nodes (no edges)
    nodes_in_edges: set[str] = set()
    for e in edges:
        nodes_in_edges.add(e[0])
        nodes_in_edges.add(e[1])
    isolated = set(nodes_dict.keys()) - nodes_in_edges
    for n in isolated:
        report.add_warning(n, "Node is isolated (no edges)")

    return report


def print_validation(report: ValidationReport | None = None) -> str:
    """Print validation report to string."""
    if report is None:
        report = validate_v2_config()
    return report.to_text()
