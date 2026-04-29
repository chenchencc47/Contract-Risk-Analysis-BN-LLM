import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_NETWORK_PATH = Path(__file__).resolve().parents[3] / "config" / "bayesian_network.json"


@dataclass(frozen=True)
class BayesianNode:
    name: str
    states: tuple[str, ...]
    parents: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def load_network_config() -> dict:
    return json.loads(DEFAULT_NETWORK_PATH.read_text(encoding="utf-8"))


def build_network_nodes() -> dict[str, BayesianNode]:
    config = load_network_config()
    return {
        name: BayesianNode(
            name=name,
            states=tuple(details["states"]),
            parents=tuple(details.get("parents", [])),
        )
        for name, details in config["nodes"].items()
    }
