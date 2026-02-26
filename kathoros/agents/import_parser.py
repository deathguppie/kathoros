"""
ImportParser — extracts structured object suggestions from agent JSON output.
Handles JSON embedded in markdown code blocks or raw JSON arrays.
"""
import json
import logging
import re

_log = logging.getLogger("kathoros.agents.import_parser")

_VALID_TYPES = {"concept", "definition", "derivation", "prediction", "evidence", "open_question", "data"}


def parse_object_suggestions(text: str) -> list[dict]:
    """
    Extract a list of object suggestion dicts from agent output.
    Tries raw JSON array first, then fenced code block.
    Returns empty list on failure.
    """
    # Try fenced code block first
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Find first [ to last ]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            text = text[start:end+1]

    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        return [_validate(obj) for obj in data if _validate(obj)]
    except json.JSONDecodeError as exc:
        _log.warning("import parse failed: %s", exc)
        return []


def detect_batch_cycles(objects: list[dict]) -> list[str]:
    """
    Check the depends_on name-graph of a batch for cycles before any DB write.

    Returns a list of human-readable cycle descriptions (one per cycle found).
    Empty list means the graph is acyclic and safe to insert.

    Each description names every node in the cycle so the researcher can
    identify the conceptual smuggling and correct it before re-importing.

    Algorithm: iterative DFS with a per-path visited set (standard cycle
    detection on a directed graph). Operates on names only — no DB access.
    """
    # Build adjacency: name → list of dependency names (within-batch only)
    known: set[str] = {obj["name"] for obj in objects}
    adj: dict[str, list[str]] = {}
    for obj in objects:
        deps = [d for d in obj.get("depends_on", []) if d in known]
        adj[obj["name"]] = deps

    cycles: list[str] = []
    reported: set[frozenset] = set()
    visited: set[str] = set()
    rec_stack: set[str] = set()

    def _dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        for neighbour in adj.get(node, []):
            if neighbour in rec_stack:
                idx = path.index(neighbour)
                cycle_nodes = path[idx:]
                key = frozenset(cycle_nodes)
                if key not in reported:
                    reported.add(key)
                    cycle_str = " → ".join(cycle_nodes) + f" → {neighbour}"
                    _log.error(
                        "CIRCULAR DEPENDENCY in import batch: %s. "
                        "This is a potential conceptual smuggling error — "
                        "neither object can be independently grounded.",
                        cycle_str,
                    )
                    cycles.append(cycle_str)
            elif neighbour not in visited:
                _dfs(neighbour, path + [neighbour])
        rec_stack.discard(node)

    for node in adj:
        if node not in visited:
            _dfs(node, [node])

    return cycles


def _validate(obj: dict) -> dict | None:
    if not isinstance(obj, dict):
        return None
    if not obj.get("name") or not obj.get("type"):
        return None
    raw_deps = obj.get("depends_on", [])
    if isinstance(raw_deps, str):
        try:
            raw_deps = json.loads(raw_deps)
        except Exception:
            raw_deps = []
    return {
        "name": str(obj.get("name", ""))[:255],
        "type": obj.get("type", "concept") if obj.get("type") in _VALID_TYPES else "concept",
        "description": str(obj.get("description", ""))[:1000],
        "tags": [str(t) for t in obj.get("tags", []) if isinstance(t, str)][:20],
        "math_expression": str(obj.get("math_expression", ""))[:500],
        "latex": str(obj.get("latex", ""))[:2000],
        "researcher_notes": str(obj.get("researcher_notes", ""))[:2000],
        "depends_on": [str(d) for d in raw_deps if d][:50],
        "source_file": str(obj.get("source_file", ""))[:255],
    }
