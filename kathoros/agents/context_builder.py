"""
context_builder — assembles a rich system prompt from Kathoros project context.

build_system_prompt(context) is the single entry point.

context keys (all optional — builder degrades gracefully):
    project_id        int | str
    project_name      str
    session_id        int | str
    user_goal         str        free-text research goal from Settings
    selected_objects  list[dict] objects the researcher has highlighted
    recent_objects    list[dict] fallback objects when nothing is selected
    enforce_epistemic bool       whether to append epistemic constraint block
    session_nonce     str        current session nonce (for tool envelope hint)
    tool_descriptions str        pre-formatted tool descriptions from ToolService
    import_mode       bool       if True, use compact import-only prompt
"""
import json

# ── static prose blocks ────────────────────────────────────────────────────────

_ROLE_BLOCK = """\
# Kathoros Research Agent

## Role
You are a physics research assistant operating inside Kathoros, a local-first
research platform. Be precise and rigorous. Flag speculative claims explicitly.
Distinguish validated physics from theoretical models.
"""

_EPISTEMIC_BLOCK = """\
## Epistemic constraints
- Do NOT assert validation of any object whose dependencies are not all validated.
- Claim level "prediction" requires narrative_label=TOY_MODEL until experimentally confirmed.
- A speculative_ontology object cannot carry claim_level=prediction.
- Depends-on graphs must be acyclic — do not suggest circular dependencies.
- Validation is directional: downstream objects cannot validate upstream ones.
- Flag speculative ontology claims explicitly with a ⚠ marker.
"""

_TOOL_ENVELOPE_HINT = """\
## Tool use
Request tools with a JSON envelope (one per response):
  {{"tool": "<name>", "nonce": "{nonce}", "args": {{...}}}}
All requests are reviewed by the security router before execution.
"""

_IMPORT_PROMPT = """\
# Kathoros Import Agent
Extract research objects from the provided text.
Respond ONLY with a JSON array — no preamble, no explanation.

Each element:
{{
  "name": "short descriptive name",
  "type": "concept|definition|derivation|prediction|evidence|open_question|data",
  "description": "1-3 sentence summary",
  "tags": ["tag1", "tag2"],
  "math_expression": "LaTeX or empty string",
  "depends_on": ["obj_id", ...],
  "source_file": "filename"
}}
"""

# ── public API ─────────────────────────────────────────────────────────────────

def build_system_prompt(context: dict) -> str:
    """
    Assemble a structured system prompt from project context.
    Returns a string ready to pass as system_prompt to the backend.
    """
    if context.get("import_mode"):
        return _IMPORT_PROMPT

    parts: list[str] = [_ROLE_BLOCK]

    # Project + session identity
    project_name = context.get("project_name") or ""
    project_id   = context.get("project_id") or ""
    session_id   = context.get("session_id") or ""
    user_goal    = (context.get("user_goal") or "").strip()

    if project_name or project_id:
        lines = ["## Active project"]
        if project_name:
            lines.append(f"- Project: {project_name}")
        if project_id:
            lines.append(f"- Project ID: proj_{project_id}")
        if session_id:
            lines.append(f"- Session: sess_{session_id}")
        if user_goal:
            lines.append(f"- Research goal: {user_goal}")
        parts.append("\n".join(lines))

    # Selected / recent objects
    objects = context.get("selected_objects") or context.get("recent_objects") or []
    if objects:
        label = "Selected objects" if context.get("selected_objects") else "Recent objects"
        obj_json = json.dumps(_serialize_objects(objects), indent=2)
        parts.append(f"## {label}\n{obj_json}")

    # Epistemic constraints
    if context.get("enforce_epistemic", True):
        parts.append(_EPISTEMIC_BLOCK)

    # Tool descriptions
    tool_desc = (context.get("tool_descriptions") or "").strip()
    if tool_desc:
        parts.append(f"## Available tools\n{tool_desc}")

    # Tool envelope hint (only when tools are available)
    nonce = context.get("session_nonce") or ""
    if tool_desc and nonce:
        parts.append(_TOOL_ENVELOPE_HINT.format(nonce=nonce))

    return "\n\n".join(parts)


# ── helpers ────────────────────────────────────────────────────────────────────

_OBJECT_FIELDS = (
    "id", "name", "type", "status", "description",
    "math_expression", "tags", "depends_on",
)

def _serialize_objects(objects: list[dict]) -> list[dict]:
    """Return objects with only the fields the model needs."""
    out = []
    for obj in objects:
        entry = {}
        for f in _OBJECT_FIELDS:
            val = obj.get(f)
            if val is not None and val != "" and val != [] and val != "[]":
                # tags / depends_on may be stored as JSON strings
                if f in ("tags", "depends_on") and isinstance(val, str):
                    try:
                        import json as _j
                        val = _j.loads(val)
                    except Exception:
                        val = [val] if val else []
                entry[f] = val
        out.append(entry)
    return out
