# tests/unit/agents/test_parser.py
import json
import unittest
from kathoros.agents.envelope import build_envelope
from kathoros.agents.parser import EnvelopeParser, ParseResult
from kathoros.core.enums import TrustLevel, AccessMode

NONCE = "session-nonce-001"
AGENT_ID = "agent-001"
AGENT_NAME = "test-agent"
TRUST = TrustLevel.TRUSTED
MODE = AccessMode.FULL_ACCESS


def parse(raw, trust=TRUST, mode=MODE, nonce=NONCE):
    return EnvelopeParser().parse(
        raw_output=raw,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trust_level=trust,
        access_mode=mode,
        session_nonce=nonce,
    )


class TestParserNoMatch(unittest.TestCase):

    def test_empty_string(self):
        result = parse("")
        self.assertIsNone(result.tool_request)
        self.assertEqual(result.detected_via, "none")

    def test_plain_text(self):
        result = parse("The derivative of x^2 is 2x.")
        self.assertIsNone(result.tool_request)
        self.assertEqual(result.display_text, "The derivative of x^2 is 2x.")

    def test_oversized_input_skipped(self):
        big = "x" * (1024 * 1024)  # 1MB — over the 512KB limit
        result = parse(big)
        self.assertIsNone(result.tool_request)


class TestParserJsonEnvelope(unittest.TestCase):

    def test_whole_output_is_envelope(self):
        raw = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "file_analyze",
                             {"targets": [{"path": "docs/paper.pdf"}]})
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertEqual(result.detected_via, "json_envelope")
        self.assertEqual(result.tool_request.tool_name, "file_analyze")
        self.assertTrue(result.tool_request.enveloped)

    def test_envelope_embedded_in_text(self):
        envelope = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "file_analyze", {"x": 1})
        raw = f"I will now call the tool:\n{envelope}\nDone."
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertEqual(result.detected_via, "json_envelope")
        self.assertTrue(result.tool_request.enveloped)

    def test_agent_identity_from_session_not_envelope(self):
        """
        Even if envelope claims a different agent_id, session values win.
        This prevents identity spoofing via crafted envelopes.
        """
        raw = build_envelope(NONCE, "SPOOFED_ID", "SPOOFED_NAME", "tool", {})
        result = parse(raw, trust=TRUST, mode=MODE, nonce=NONCE)
        self.assertIsNotNone(result.tool_request)
        # Session values must be used, not envelope claims
        self.assertEqual(result.tool_request.agent_id, AGENT_ID)
        self.assertEqual(result.tool_request.agent_name, AGENT_NAME)

    def test_nonce_from_envelope_payload(self):
        """Nonce is read from envelope — router validates it."""
        raw = build_envelope("different-nonce", AGENT_ID, AGENT_NAME, "tool", {})
        result = parse(raw)
        self.assertEqual(result.tool_request.nonce, "different-nonce")

    def test_run_id_from_envelope(self):
        raw = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "tool", {},
                             run_id="run-abcdefgh")
        result = parse(raw)
        self.assertEqual(result.tool_request.run_id, "run-abcdefgh")

    def test_priority_over_json_struct(self):
        """Envelope takes priority even if output also contains json_struct pattern."""
        envelope = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "file_analyze", {"x": 1})
        mixed = f'{{"tool": "other_tool", "args": {{}}}}\n{envelope}'
        result = parse(mixed)
        self.assertEqual(result.detected_via, "json_envelope")
        self.assertEqual(result.tool_request.tool_name, "file_analyze")


class TestParserJsonStruct(unittest.TestCase):

    def test_basic_json_struct(self):
        raw = '{"tool": "sagemath", "args": {"expr": "x^2"}}'
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertEqual(result.detected_via, "json_struct")
        self.assertEqual(result.tool_request.tool_name, "sagemath")
        self.assertFalse(result.tool_request.enveloped)

    def test_json_struct_in_text(self):
        raw = 'Let me compute this. {"tool": "sagemath", "args": {"expr": "2+2"}} Done.'
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertEqual(result.detected_via, "json_struct")

    def test_json_struct_not_enveloped(self):
        raw = '{"tool": "file_analyze", "args": {"path": "docs/x.pdf"}}'
        result = parse(raw)
        self.assertFalse(result.tool_request.enveloped)

    def test_json_struct_session_nonce_injected(self):
        """Non-envelope detections get the session nonce injected."""
        raw = '{"tool": "t", "args": {}}'
        result = parse(raw, nonce="my-session-nonce")
        self.assertEqual(result.tool_request.nonce, "my-session-nonce")


class TestParserXmlTag(unittest.TestCase):

    def test_basic_xml_tag(self):
        raw = "<tool:sagemath>x^2 + y^2</tool:sagemath>"
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertEqual(result.detected_via, "xml_tag")
        self.assertEqual(result.tool_request.tool_name, "sagemath")
        self.assertFalse(result.tool_request.enveloped)

    def test_xml_tag_json_args(self):
        raw = '<tool:file_analyze>{"targets": [{"path": "docs/x.pdf"}]}</tool:file_analyze>'
        result = parse(raw)
        self.assertEqual(result.tool_request.args,
                         {"targets": [{"path": "docs/x.pdf"}]})

    def test_xml_tag_plain_content_wrapped(self):
        raw = "<tool:sagemath>integrate(sin(x), x)</tool:sagemath>"
        result = parse(raw)
        self.assertEqual(result.tool_request.args,
                         {"input": "integrate(sin(x), x)"})

    def test_xml_tag_in_surrounding_text(self):
        raw = "Here is my tool call:\n<tool:sagemath>x^2</tool:sagemath>\nend."
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertIn("Here is my tool call", result.display_text)
        self.assertIn("end.", result.display_text)


class TestParserMarkdownBlock(unittest.TestCase):

    def test_basic_markdown_block(self):
        raw = "```sagemath\nx^2 + 1\n```"
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertEqual(result.detected_via, "markdown_block")
        self.assertEqual(result.tool_request.tool_name, "sagemath")
        self.assertFalse(result.tool_request.enveloped)

    def test_markdown_json_content(self):
        raw = '```file_analyze\n{"targets": [{"path": "docs/x.pdf"}]}\n```'
        result = parse(raw)
        self.assertEqual(result.tool_request.args,
                         {"targets": [{"path": "docs/x.pdf"}]})

    def test_markdown_plain_content_wrapped(self):
        raw = "```sagemath\nsolve(x^2 - 4, x)\n```"
        result = parse(raw)
        self.assertEqual(result.tool_request.args,
                         {"input": "solve(x^2 - 4, x)"})

    def test_markdown_in_surrounding_text(self):
        raw = "I'll use the tool now:\n```sagemath\n1+1\n```\nAll done."
        result = parse(raw)
        self.assertIsNotNone(result.tool_request)
        self.assertIn("I'll use the tool now", result.display_text)


class TestParserPriority(unittest.TestCase):
    """Verify detection priority order is strictly respected."""

    def test_envelope_beats_xml(self):
        envelope = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "correct_tool", {})
        raw = f"<tool:wrong_tool>x</tool:wrong_tool>\n{envelope}"
        result = parse(raw)
        self.assertEqual(result.detected_via, "json_envelope")
        self.assertEqual(result.tool_request.tool_name, "correct_tool")

    def test_envelope_beats_markdown(self):
        envelope = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "correct_tool", {})
        raw = f"```wrong_tool\nx\n```\n{envelope}"
        result = parse(raw)
        self.assertEqual(result.detected_via, "json_envelope")
        self.assertEqual(result.tool_request.tool_name, "correct_tool")

    def test_json_struct_beats_xml(self):
        raw = '{"tool": "json_tool", "args": {}}\n<tool:xml_tool>x</tool:xml_tool>'
        result = parse(raw)
        self.assertEqual(result.detected_via, "json_struct")
        self.assertEqual(result.tool_request.tool_name, "json_tool")

    def test_xml_beats_markdown(self):
        raw = "<tool:xml_tool>x</tool:xml_tool>\n```markdown_tool\ny\n```"
        result = parse(raw)
        self.assertEqual(result.detected_via, "xml_tag")
        self.assertEqual(result.tool_request.tool_name, "xml_tool")


class TestParserRequestId(unittest.TestCase):

    def test_unique_request_ids(self):
        """Each parse call produces a unique request_id."""
        raw = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "tool", {})
        r1 = parse(raw)
        r2 = parse(raw)
        self.assertNotEqual(
            r1.tool_request.request_id,
            r2.tool_request.request_id,
        )

    def test_request_id_is_uuid_format(self):
        import re
        raw = build_envelope(NONCE, AGENT_ID, AGENT_NAME, "tool", {})
        result = parse(raw)
        uuid_re = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        )
        self.assertRegex(result.tool_request.request_id, uuid_re)


class TestParserDisplayText(unittest.TestCase):

    def test_display_text_excludes_tool_block(self):
        raw = "Here is the analysis.\n```sagemath\n1+1\n```\nPlease review."
        result = parse(raw)
        self.assertNotIn("```sagemath", result.display_text)
        self.assertIn("Here is the analysis", result.display_text)
        self.assertIn("Please review", result.display_text)

    def test_no_tool_display_text_unchanged(self):
        raw = "No tool here, just text."
        result = parse(raw)
        self.assertEqual(result.display_text, raw)


if __name__ == "__main__":
    unittest.main()
