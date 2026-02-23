# tests/unit/router/test_validator.py
import unittest
from kathoros.router.validator import validate_args
from kathoros.core.exceptions import SchemaError

VALID_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path"],
    "properties": {
        "path": {"type": "string", "minLength": 1, "maxLength": 512},
        "mode": {"type": "string", "enum": ["read", "write"]},
    }
}

class TestValidator(unittest.TestCase):

    def test_valid_args(self):
        errors = validate_args({"path": "docs/paper.pdf"}, VALID_SCHEMA)
        self.assertEqual(errors, [])

    def test_missing_required(self):
        errors = validate_args({}, VALID_SCHEMA)
        self.assertTrue(any("schema" in e for e in errors))

    def test_wrong_type(self):
        errors = validate_args({"path": 123}, VALID_SCHEMA)
        self.assertTrue(any("schema" in e for e in errors))

    def test_enum_violation(self):
        errors = validate_args({"path": "docs/x.pdf", "mode": "delete"}, VALID_SCHEMA)
        self.assertTrue(any("schema" in e for e in errors))

    def test_additional_properties_blocked(self):
        errors = validate_args({"path": "docs/x.pdf", "surprise": True}, VALID_SCHEMA)
        self.assertTrue(any("schema" in e for e in errors))

    def test_missing_additional_properties_false_raises(self):
        bad_schema = {
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}}
            # missing additionalProperties: false
        }
        with self.assertRaises(SchemaError) as ctx:
            validate_args({"path": "x"}, bad_schema)
        self.assertIn("schema", str(ctx.exception))

    def test_minlength_enforced(self):
        errors = validate_args({"path": ""}, VALID_SCHEMA)
        self.assertTrue(any("schema" in e for e in errors))

    def test_maxlength_enforced(self):
        errors = validate_args({"path": "x" * 513}, VALID_SCHEMA)
        self.assertTrue(any("schema" in e for e in errors))

    def test_items_cap_enforced(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["items"],
            "properties": {
                "items": {"type": "array", "maxItems": 10, "items": {"type": "string"}}
            }
        }
        errors = validate_args({"items": ["x"] * 501}, schema)
        self.assertTrue(any("schema" in e for e in errors))

if __name__ == "__main__":
    unittest.main()


class TestValidatorRecursiveAdditionalProperties(unittest.TestCase):
    """Nested object schemas must also require additionalProperties: false."""

    def _schema_with_nested(self, nested_has_ap=True):
        nested = {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 512},
            },
        }
        if nested_has_ap:
            nested["additionalProperties"] = False
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["targets"],
            "properties": {
                "targets": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 10,
                    "items": nested,
                }
            },
        }

    def test_nested_object_without_ap_reports_error(self):
        schema = self._schema_with_nested(nested_has_ap=False)
        args = {"targets": [{"path": "docs/x.pdf", "EXTRA": "bad"}]}
        errors = validate_args(args, schema)
        # Should flag: extra property + missing additionalProperties on nested
        self.assertTrue(any("additional" in e.lower() for e in errors), errors)

    def test_nested_object_with_ap_blocks_extra_keys(self):
        schema = self._schema_with_nested(nested_has_ap=True)
        args = {"targets": [{"path": "docs/x.pdf", "EXTRA": "bad"}]}
        errors = validate_args(args, schema)
        self.assertTrue(any("additional" in e.lower() for e in errors), errors)

    def test_valid_nested_passes(self):
        schema = self._schema_with_nested(nested_has_ap=True)
        args = {"targets": [{"path": "docs/x.pdf"}]}
        errors = validate_args(args, schema)
        self.assertEqual(errors, [])


class TestValidatorSchemaDepthFixed(unittest.TestCase):
    """_schema_depth correctly handles properties vs items."""

    def test_items_depth_counted(self):
        from kathoros.router.validator import _schema_depth
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "x": {"type": "string"}
                }
            }
        }
        depth = _schema_depth(schema)
        self.assertGreater(depth, 0)

    def test_flat_schema_depth_zero(self):
        from kathoros.router.validator import _schema_depth
        self.assertEqual(_schema_depth({"type": "string"}), 0)
