# tests/unit/router/test_registry.py
import unittest
from kathoros.router.registry import ToolRegistry
from kathoros.router.models import ToolDefinition
from kathoros.core.exceptions import UnknownToolError

MINIMAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [],
    "properties": {}
}

def make_tool(name, aliases=()):
    return ToolDefinition(
        name=name,
        description="test",
        args_schema=MINIMAL_SCHEMA,
        aliases=aliases,
    )

class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self.reg = ToolRegistry()

    def test_exact_lookup(self):
        self.reg.register(make_tool("file_analyze"))
        self.reg.build()
        tool = self.reg.lookup("file_analyze")
        self.assertEqual(tool.name, "file_analyze")

    def test_case_sensitive(self):
        self.reg.register(make_tool("file_analyze"))
        self.reg.build()
        with self.assertRaises(UnknownToolError) as ctx:
            self.reg.lookup("File_Analyze")
        self.assertIn("unknown tool", str(ctx.exception))

    def test_alias_lookup(self):
        self.reg.register(make_tool("file_analyze", aliases=("fa",)))
        self.reg.build()
        tool = self.reg.lookup("fa")
        self.assertEqual(tool.name, "file_analyze")

    def test_unknown_tool_error_message(self):
        self.reg.build()
        with self.assertRaises(UnknownToolError) as ctx:
            self.reg.lookup("nonexistent")
        self.assertIn("unknown tool", str(ctx.exception))

    def test_no_fuzzy_match(self):
        self.reg.register(make_tool("file_analyze"))
        self.reg.build()
        with self.assertRaises(UnknownToolError):
            self.reg.lookup("file_analyz")   # typo

    def test_locked_registry_rejects_register(self):
        self.reg.build()
        with self.assertRaises(RuntimeError):
            self.reg.register(make_tool("new_tool"))

    def test_duplicate_name_rejected(self):
        self.reg.register(make_tool("file_analyze"))
        with self.assertRaises(ValueError):
            self.reg.register(make_tool("file_analyze"))

    def test_exists(self):
        self.reg.register(make_tool("file_analyze"))
        self.reg.build()
        self.assertTrue(self.reg.exists("file_analyze"))
        self.assertFalse(self.reg.exists("ghost"))

if __name__ == "__main__":
    unittest.main()
