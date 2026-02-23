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
