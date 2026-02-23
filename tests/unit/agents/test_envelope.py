# tests/unit/agents/test_envelope.py
import unittest
from kathoros.agents.envelope import (
    build_envelope, parse_envelope, is_envelope, ENVELOPE_KEY,
)


class TestBuildEnvelope(unittest.TestCase):

    def test_produces_valid_json(self):
        import json
        raw = build_envelope("nonce1", "a1", "agent", "file_analyze", {"path": "docs/x.pdf"})
        parsed = json.loads(raw)
        self.assertIn(ENVELOPE_KEY, parsed)

    def test_round_trip(self):
        raw = build_envelope("nonce1", "a1", "agent", "file_analyze", {"path": "docs/x.pdf"})
        payload = parse_envelope(raw)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["tool"], "file_analyze")
        self.assertEqual(payload["args"], {"path": "docs/x.pdf"})
        self.assertEqual(payload["nonce"], "nonce1")

    def test_run_id_included_when_given(self):
        raw = build_envelope("n", "a", "agent", "tool", {}, run_id="run-12345678")
        payload = parse_envelope(raw)
        self.assertEqual(payload["run_id"], "run-12345678")

    def test_run_id_absent_when_none(self):
        raw = build_envelope("n", "a", "agent", "tool", {})
        payload = parse_envelope(raw)
        self.assertNotIn("run_id", payload)


class TestParseEnvelope(unittest.TestCase):

    def test_valid_envelope(self):
        import json
        raw = json.dumps({ENVELOPE_KEY: {
            "nonce": "abc", "agent_id": "a1", "agent_name": "x",
            "tool": "file_analyze", "args": {}
        }})
        payload = parse_envelope(raw)
        self.assertIsNotNone(payload)

    def test_not_json_returns_none(self):
        self.assertIsNone(parse_envelope("not json at all"))

    def test_wrong_root_key_returns_none(self):
        import json
        raw = json.dumps({"wrong_key": {"tool": "x", "args": {}}})
        self.assertIsNone(parse_envelope(raw))

    def test_missing_required_field_returns_none(self):
        import json
        # Missing 'tool'
        raw = json.dumps({ENVELOPE_KEY: {
            "nonce": "n", "agent_id": "a", "agent_name": "x", "args": {}
        }})
        self.assertIsNone(parse_envelope(raw))

    def test_args_not_dict_returns_none(self):
        import json
        raw = json.dumps({ENVELOPE_KEY: {
            "nonce": "n", "agent_id": "a", "agent_name": "x",
            "tool": "t", "args": "not-a-dict"
        }})
        self.assertIsNone(parse_envelope(raw))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_envelope(""))

    def test_is_envelope_true(self):
        raw = build_envelope("n", "a", "agent", "t", {})
        self.assertTrue(is_envelope(raw))

    def test_is_envelope_false(self):
        self.assertFalse(is_envelope("just some text"))


if __name__ == "__main__":
    unittest.main()
