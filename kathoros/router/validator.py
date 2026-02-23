# kathoros/router/validator.py
"""
Schema validation for tool arguments.
Pure stdlib implementation — no external dependencies.

Validates JSON Schema subset:
  required, type, enum, minLength, maxLength, minimum, maximum,
  additionalProperties (must be false), items, properties,
  plus depth/items/properties caps.

All failure messages contain "schema" per LLM_IMPLEMENTATION_RULES §5.
"""
from __future__ import annotations
from typing import Any
from kathoros.core.exceptions import SchemaError

MAX_SCHEMA_DEPTH = 10
MAX_ITEMS_CAP = 500
MAX_PROPERTIES_CAP = 50

_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def validate_args(args: dict, schema: dict) -> list[str]:
    """
    Validate args against schema subset.
    Returns list of error strings (empty = valid).
    All errors contain "schema".

    Raises SchemaError if schema itself is malformed
    (e.g. missing additionalProperties: false at top level).
    """
    if schema.get("additionalProperties") is not False:
        raise SchemaError(
            "schema missing required 'additionalProperties: false' at top level"
        )

    depth = _schema_depth(schema)
    if depth > MAX_SCHEMA_DEPTH:
        raise SchemaError(f"schema depth {depth} exceeds cap {MAX_SCHEMA_DEPTH}")

    errors: list[str] = []
    _validate_value(args, schema, path="root", errors=errors)
    return errors


def _validate_value(
    value: Any, schema: dict, path: str, errors: list[str]
) -> None:
    """Recursively validate a value against a schema node."""

    # type check
    if "type" in schema:
        expected = schema["type"]
        py_type = _TYPE_MAP.get(expected)
        if py_type is None:
            errors.append(f"schema error: unknown type {expected!r} at {path}")
            return
        # bool is subclass of int in Python — handle explicitly
        if expected == "integer" and isinstance(value, bool):
            errors.append(f"schema error: expected integer not boolean at {path}")
            return
        if not isinstance(value, py_type):
            errors.append(
                f"schema error: expected {expected}, got {type(value).__name__} at {path}"
            )
            return

    # enum
    if "enum" in schema and value not in schema["enum"]:
        errors.append(
            f"schema error: {value!r} not in enum {schema['enum']} at {path}"
        )

    # string constraints
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(
                f"schema error: string length {len(value)} < minLength "
                f"{schema['minLength']} at {path}"
            )
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(
                f"schema error: string length {len(value)} > maxLength "
                f"{schema['maxLength']} at {path}"
            )

    # numeric constraints
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(
                f"schema error: {value} < minimum {schema['minimum']} at {path}"
            )
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(
                f"schema error: {value} > maximum {schema['maximum']} at {path}"
            )

    # object constraints
    if isinstance(value, dict):
        _validate_object(value, schema, path, errors)

    # array constraints
    if isinstance(value, list):
        _validate_array(value, schema, path, errors)


def _validate_object(
    obj: dict, schema: dict, path: str, errors: list[str]
) -> None:
    props = schema.get("properties", {})

    # Properties cap
    if len(props) > MAX_PROPERTIES_CAP:
        errors.append(
            f"schema error: too many properties {len(props)} (cap {MAX_PROPERTIES_CAP})"
        )
        return

    # additionalProperties: false — reject unknown keys
    if schema.get("additionalProperties") is False:
        for key in obj:
            if key not in props:
                errors.append(
                    f"schema error: additional property {key!r} not allowed at {path}"
                )

    # required fields
    for req in schema.get("required", []):
        if req not in obj:
            errors.append(f"schema error: required field {req!r} missing at {path}")

    # Recurse into declared properties
    for key, prop_schema in props.items():
        if key in obj:
            _validate_value(obj[key], prop_schema, path=f"{path}.{key}", errors=errors)
        # nested object schemas must also declare additionalProperties: false
        if prop_schema.get("type") == "object" and prop_schema.get("additionalProperties") is not False:
            errors.append(
                f"schema error: nested object at {path}.{key} missing additionalProperties: false"
            )
        elif prop_schema.get("type") == "array":
            item_s = prop_schema.get("items", {})
            if item_s.get("type") == "object" and item_s.get("additionalProperties") is not False:
                errors.append(
                    f"schema error: array items at {path}.{key} missing additionalProperties: false"
                )


def _validate_array(
    arr: list, schema: dict, path: str, errors: list[str]
) -> None:
    # Items cap
    cap = min(schema.get("maxItems", MAX_ITEMS_CAP), MAX_ITEMS_CAP)
    if len(arr) > cap:
        errors.append(
            f"schema error: array length {len(arr)} exceeds cap {cap} at {path}"
        )
        return

    if "minItems" in schema and len(arr) < schema["minItems"]:
        errors.append(
            f"schema error: array length {len(arr)} < minItems "
            f"{schema['minItems']} at {path}"
        )

    item_schema = schema.get("items")
    if item_schema and isinstance(item_schema, dict):
        for i, item in enumerate(arr):
            _validate_value(item, item_schema, path=f"{path}[{i}]", errors=errors)


def _schema_depth(schema: Any, current: int = 0) -> int:
    if not isinstance(schema, dict):
        return current
    max_d = current
    for key in ("properties", "items"):
        child = schema.get(key)
        if isinstance(child, dict):
            for v in child.values():
                max_d = max(max_d, _schema_depth(v, current + 1))
        elif isinstance(child, dict):
            max_d = max(max_d, _schema_depth(child, current + 1))
    return max_d
