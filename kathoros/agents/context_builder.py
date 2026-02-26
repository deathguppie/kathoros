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

_OBJECT_RULES_BLOCK = """\
## Object creation and update rules
When using object_create or object_update tools, you MUST follow these rules strictly.

### Valid field values
- **type**: concept, definition, derivation, prediction, evidence, open_question, data
- **status**: NEVER set status directly. Status is managed exclusively by the epistemic audit
  system. All new objects start as 'pending'.

### Epistemic integrity rules (MANDATORY)
1. Do NOT create objects with type 'prediction' unless they have explicit depends_on
   references to validated upstream objects (definitions or derivations).
2. A 'derivation' MUST list its premises in depends_on — never create a derivation
   without dependencies.
3. depends_on graphs must be ACYCLIC. Do not create circular dependencies.
4. Downstream objects cannot validate upstream ones — validation flows one direction.
5. An 'evidence' object must reference the prediction or derivation it supports
   via depends_on.
6. Speculative claims MUST be flagged in researcher_notes with a warning marker.
7. Do NOT duplicate existing objects — check context for objects with similar names
   before creating new ones.
8. Tags should be lowercase, underscore-separated identifiers (e.g., "quantum_mechanics",
   "toy_model", "needs_review").

### Field guidelines
- **name**: Short, descriptive, unique within the session.
- **description**: 1-3 sentence scientific summary. Be precise.
- **math_expression**: LaTeX math (no delimiters), e.g., "E = mc^2".
- **tags**: List of relevant topic tags.
- **depends_on**: List of object names (exact match) or integer IDs this object depends on.
- **researcher_notes**: Internal notes, caveats, or uncertainty flags.
"""

_TOOL_ENVELOPE_HINT = """\
## Tool use — IMPORTANT
To invoke a tool, you MUST emit a PROXENOS_TOOL_REQUEST JSON envelope in your response.
Only ONE tool call per response. Do NOT just describe what you would do — emit the JSON.

Your identity for envelopes:
  agent_id: "{agent_id}"
  agent_name: "{agent_name}"
  nonce: "{nonce}"

Envelope format:
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "<tool_name>", "args": {{...}}}}}}

### Examples

Display a graph:
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "graph_update", "args": {{"nodes": [{{"id": "A", "label": "Node A"}}, {{"id": "B", "label": "Node B"}}], "edges": [{{"source": "A", "target": "B"}}], "clear": true}}}}}}

Create objects:
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "object_create", "args": {{"objects": [{{"name": "Newton second law", "type": "definition", "description": "F = ma", "tags": ["classical_mechanics"]}}]}}}}}}

Update an object:
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "object_update", "args": {{"object_id": 5, "fields": {{"tags": ["updated_tag"]}}}}}}}}

Evaluate SageMath:
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "sagemath_eval", "args": {{"code": "print(factor(x^2 - 1))"}}}}}}

Render a matplotlib plot:
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "matplot_render", "args": {{"code": "import numpy as np\\nx = np.linspace(0, 2*np.pi, 100)\\nplt.plot(x, np.sin(x))\\nplt.title('sin(x)')"}}}}}}

Execute SQL on the database:
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "db_execute", "args": {{"sql": "CREATE TABLE test (id INTEGER PRIMARY KEY, content TEXT)", "db": "project"}}}}}}
  {{"proxenos_tool_request": {{"nonce": "{nonce}", "agent_id": "{agent_id}", "agent_name": "{agent_name}", "tool": "db_execute", "args": {{"sql": "INSERT INTO test (content) VALUES ('hello world')", "db": "project"}}}}}}
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

    # Claim-level ceiling
    if context.get("max_claim_level") == "prediction":
        parts.append(
            "## Claim-level restriction\n"
            "You are not permitted to propose claims beyond prediction level.\n"
            "Do not introduce ontology upgrades."
        )

    # Tool descriptions
    tool_desc = (context.get("tool_descriptions") or "").strip()
    if tool_desc:
        parts.append(f"## Available tools\n{tool_desc}")

    # Object creation/update rules (only when tools are available)
    if tool_desc:
        parts.append(_OBJECT_RULES_BLOCK)

    # Tool envelope hint (only when tools are available)
    nonce = context.get("session_nonce") or ""
    agent_id = str(context.get("agent_id") or "")
    agent_name = context.get("agent_name") or ""
    if tool_desc and nonce:
        parts.append(_TOOL_ENVELOPE_HINT.format(
            nonce=nonce, agent_id=agent_id, agent_name=agent_name,
        ))

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
