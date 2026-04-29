import json
from functools import lru_cache
from pathlib import Path


DEFAULT_NODE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "node_schema_v1.json"
)


@lru_cache(maxsize=1)
def load_node_schema() -> dict:
    return json.loads(DEFAULT_NODE_SCHEMA_PATH.read_text(encoding="utf-8"))


def load_priority_nodes(priority: str) -> list[str]:
    schema = load_node_schema()
    return [
        node["node_name"]
        for node in schema.get("nodes", [])
        if node.get("priority") == priority
    ]


def get_node_metadata(node_name: str) -> dict | None:
    schema = load_node_schema()
    for node in schema.get("nodes", []):
        if node.get("node_name") == node_name:
            return node
    return None


def get_allowed_states(node_name: str) -> list[str]:
    node_metadata = get_node_metadata(node_name) or {}
    return list(node_metadata.get("states", []))


def is_allowed_state(node_name: str, state: str) -> bool:
    allowed_states = get_allowed_states(node_name)
    return not allowed_states or state in allowed_states


def is_allowed_priority(
    node_name: str, allowed_priorities: set[str] | None = None
) -> bool:
    if not allowed_priorities:
        return True
    node_metadata = get_node_metadata(node_name) or {}
    return node_metadata.get("priority") in allowed_priorities
