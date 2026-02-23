# tests/unit/router/test_router.py
"""
Full pipeline tests for ToolRouter.
Covers all 11 steps and key security invariants.
"""
import unittest
import tempfile
import logging
from pathlib import Path
from kathoros.router.router import ToolRouter
from kathoros.router.registry import ToolRegistry
from kathoros.router.models import ToolDefinition, ToolRequest
from kathoros.core.enums import AccessMode, TrustLevel, Decision

# Silence audit log during tests
logging.getLogger("kathoros.router.audit").setLevel(logging.CRITICAL)

NONCE = "test-nonce-abc123"
AGENT_ID = "agent-001"
AGENT_NAME = "test-agent"

MINIMAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [],
    "properties": {}
}

READ_TOOL = ToolDefinition(
    name="file_analyze",
    description="Read files",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["targets"],
        "properties": {
            "targets": {
                "type": "array",
                "minItems": 1,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 512}
                    }
                }
            }
        }
    },
    write_capable=False,
    path_fields=("targets",),
    allowed_paths=("docs/", "staging/"),
)

WRITE_TOOL = ToolDefinition(
    name="file_write",
    description="Write files",
    args_schema=MINIMAL_SCHEMA,
    write_capable=True,
    requires_run_scope=True,
    allowed_paths=("artifacts/",),
    path_fields=(),
)


def make_registry(*tools):
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    reg.build()
    return reg


def make_request(tool_name, args, trust=TrustLevel.TRUSTED,
                 access=AccessMode.FULL_ACCESS, enveloped=True,
                 nonce=NONCE, run_id=None):
    return ToolRequest(
        request_id="req-0001",
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trust_level=trust,
        access_mode=access,
        tool_name=tool_name,
        args=args,
        nonce=nonce,
        enveloped=enveloped,
        detected_via="json_envelope",
        run_id=run_id,
    )


def dummy_executor(args, tool, project_root):
    return {"ok": True}


class TestRouterNonce(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        (self.root / "docs").mkdir()
        self.reg = make_registry(READ_TOOL)

    def _router(self, **kw):
        return ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={"file_analyze": dummy_executor},
            **kw,
        )

    def test_nonce_mismatch_rejected(self):
        router = self._router()
        req = make_request("file_analyze", {}, nonce="WRONG")
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertFalse(result.nonce_valid)
        self.assertEqual(len(result.validation_errors), 1)
        self.assertIn("Invalid nonce", result.validation_errors[0])

    def test_nonce_mismatch_no_tool_leakage(self):
        """Nonce failure must not reveal tool existence, schema, or path info."""
        router = self._router()
        req = make_request("nonexistent_tool", {}, nonce="WRONG")
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertEqual(len(result.validation_errors), 1)
        self.assertNotIn("unknown tool", result.validation_errors[0])
        self.assertNotIn("schema", result.validation_errors[0])

    def test_valid_nonce_passes(self):
        router = self._router()
        req = make_request(
            "file_analyze",
            {"targets": [{"path": "docs/paper.pdf"}]},
        )
        (self.root / "docs" / "paper.pdf").touch()
        result = router.handle(req)
        self.assertTrue(result.nonce_valid)


class TestRouterNoAccess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.reg = make_registry(READ_TOOL)

    def test_no_access_rejected_immediately(self):
        router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.NO_ACCESS,
        )
        req = make_request("file_analyze", {}, access=AccessMode.NO_ACCESS)
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertIn("disabled", result.validation_errors[0].lower())


class TestRouterToolLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.reg = make_registry(READ_TOOL)
        self.router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={"file_analyze": dummy_executor},
        )

    def test_unknown_tool_rejected(self):
        req = make_request("ghost_tool", {})
        result = self.router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("unknown tool" in e for e in result.validation_errors))

    def test_case_sensitive(self):
        req = make_request("File_Analyze", {})
        result = self.router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("unknown tool" in e for e in result.validation_errors))


class TestRouterEnvelope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.reg = make_registry(READ_TOOL)
        self.router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={"file_analyze": dummy_executor},
        )

    def test_untrusted_without_envelope_rejected(self):
        req = make_request(
            "file_analyze", {}, trust=TrustLevel.UNTRUSTED, enveloped=False
        )
        result = self.router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("envelope" in e for e in result.validation_errors))

    def test_monitored_without_envelope_rejected(self):
        req = make_request(
            "file_analyze", {}, trust=TrustLevel.MONITORED, enveloped=False
        )
        result = self.router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("envelope" in e for e in result.validation_errors))

    def test_trusted_without_envelope_allowed(self):
        """TRUSTED agents may omit envelope — validation still required."""
        req = make_request(
            "file_analyze",
            {"targets": [{"path": "docs/x.pdf"}]},
            trust=TrustLevel.TRUSTED,
            enveloped=False,
        )
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs" / "x.pdf").touch()
        result = self.router.handle(req)
        # Should not fail on envelope step (may fail elsewhere legitimately)
        self.assertFalse(any("envelope" in e for e in result.validation_errors))


class TestRouterSchema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        (self.root / "docs").mkdir()
        self.reg = make_registry(READ_TOOL)
        self.router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={"file_analyze": dummy_executor},
        )

    def test_schema_failure_rejected(self):
        req = make_request("file_analyze", {"targets": "not-a-list"})
        result = self.router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("schema" in e for e in result.validation_errors))

    def test_additional_properties_blocked(self):
        req = make_request(
            "file_analyze",
            {"targets": [{"path": "docs/x.pdf"}], "extra": True}
        )
        result = self.router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("schema" in e for e in result.validation_errors))


class TestRouterApproval(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.reg = make_registry(READ_TOOL)

    def test_request_first_no_callback_denied(self):
        router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.REQUEST_FIRST,
            approval_callback=None,
            executors={"file_analyze": dummy_executor},
        )
        req = make_request(
            "file_analyze",
            {"targets": [{"path": "docs/x.pdf"}]},
            trust=TrustLevel.TRUSTED,
            access=AccessMode.REQUEST_FIRST,
        )
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("denied" in e for e in result.validation_errors))

    def test_approval_callback_reject(self):
        router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.REQUEST_FIRST,
            approval_callback=lambda req, tool: False,
            executors={"file_analyze": dummy_executor},
        )
        req = make_request(
            "file_analyze",
            {"targets": [{"path": "docs/x.pdf"}]},
            trust=TrustLevel.TRUSTED,
            access=AccessMode.REQUEST_FIRST,
        )
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertTrue(any("denied" in e for e in result.validation_errors))

    def test_approval_callback_approve(self):
        (self.root / "docs").mkdir()
        (self.root / "docs" / "x.pdf").touch()
        router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.REQUEST_FIRST,
            approval_callback=lambda req, tool: True,
            executors={"file_analyze": dummy_executor},
        )
        req = make_request(
            "file_analyze",
            {"targets": [{"path": "docs/x.pdf"}]},
            trust=TrustLevel.TRUSTED,
            access=AccessMode.REQUEST_FIRST,
        )
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.APPROVED)


class TestRouterRunScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        (self.root / "artifacts").mkdir()
        self.reg = make_registry(WRITE_TOOL)

    def _router(self):
        return ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            approval_callback=lambda req, tool: True,
            executors={"file_write": dummy_executor},
        )

    def test_missing_run_id_rejected(self):
        router = self._router()
        req = make_request("file_write", {}, run_id=None)
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)
        self.assertFalse(any("denied" in e for e in result.validation_errors),
                         "Run scope failure must not show approval dialog")

    def test_invalid_run_id_format_rejected(self):
        router = self._router()
        req = make_request("file_write", {}, run_id="bad id!")
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)

    def test_valid_run_id_too_short_rejected(self):
        router = self._router()
        req = make_request("file_write", {}, run_id="abc")  # < 8 chars
        result = router.handle(req)
        self.assertEqual(result.decision, Decision.REJECTED)


class TestRouterLogging(unittest.TestCase):
    """Verify log records contain all required fields and no raw args."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        (self.root / "docs").mkdir()
        self.reg = make_registry(READ_TOOL)
        self.log_records = []

        # Capture log output
        import logging
        handler = _CapturingHandler(self.log_records)
        logger = logging.getLogger("kathoros.router.audit")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        self._handler = handler
        self._logger = logger

    def tearDown(self):
        self._logger.removeHandler(self._handler)

    def test_all_required_fields_logged(self):
        import json as _json
        from kathoros.router.logger import REQUIRED_FIELDS

        router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={"file_analyze": dummy_executor},
        )
        (self.root / "docs" / "p.pdf").touch()
        req = make_request("file_analyze", {"targets": [{"path": "docs/p.pdf"}]})
        router.handle(req)

        self.assertTrue(self.log_records, "Expected at least one log record")
        record_str = self.log_records[-1]
        record = _json.loads(record_str)
        for field in REQUIRED_FIELDS:
            self.assertIn(field, record, f"Missing required log field: {field}")

    def test_raw_args_not_logged(self):
        import json as _json
        router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={"file_analyze": dummy_executor},
        )
        req = make_request("file_analyze", {"targets": [{"path": "docs/p.pdf"}]})
        (self.root / "docs" / "p.pdf").touch()
        router.handle(req)
        record_str = self.log_records[-1]
        self.assertNotIn('"args"', record_str)
        self.assertNotIn('"raw_args"', record_str)

    def test_hash_is_64_chars(self):
        import json as _json
        router = ToolRouter(
            registry=self.reg,
            project_root=self.root,
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={"file_analyze": dummy_executor},
        )
        (self.root / "docs" / "p.pdf").touch()
        req = make_request("file_analyze", {"targets": [{"path": "docs/p.pdf"}]})
        router.handle(req)
        record = _json.loads(self.log_records[-1])
        self.assertEqual(len(record["raw_args_hash"]), 64)


class _CapturingHandler(logging.Handler):
    def __init__(self, records):
        super().__init__()
        self._records = records
    def emit(self, record):
        self._records.append(self.format(record))


if __name__ == "__main__":
    unittest.main()


class TestRouterSessionId(unittest.TestCase):
    """session_id flows through to RouterResult and log."""

    def _router(self, session_id="sess-abc"):
        return ToolRouter(
            registry=make_registry(READ_TOOL),
            project_root=Path(tempfile.mkdtemp()),
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            executors={READ_TOOL.name: dummy_executor},
            session_id=session_id,
        )

    def test_session_id_in_result(self):
        router = self._router(session_id="test-session-001")
        req = make_request(READ_TOOL.name, {"targets": [{"path": "docs/x.pdf"}]})
        result = router.handle(req)
        self.assertEqual(result.session_id, "test-session-001")

    def test_decided_at_set_after_handle(self):
        router = self._router()
        req = make_request(READ_TOOL.name, {"targets": [{"path": "docs/x.pdf"}]})
        result = router.handle(req)
        self.assertTrue(result.decided_at)
        import re
        self.assertRegex(result.decided_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestRouterAccessModeStep1(unittest.TestCase):
    """Step 1 — NO_ACCESS fires before nonce check (step 2)."""

    def test_no_access_before_nonce(self):
        """With NO_ACCESS + bad nonce, error must say access disabled, not nonce."""
        router = ToolRouter(
            registry=make_registry(READ_TOOL),
            project_root=Path(tempfile.mkdtemp()),
            session_nonce=NONCE,
            access_mode=AccessMode.NO_ACCESS,
        )
        req = make_request(READ_TOOL.name, {"targets": [{"path": "docs/x.pdf"}]},
                           nonce="WRONG-nonce", access=AccessMode.NO_ACCESS)
        result = router.handle(req)
        self.assertEqual(result.decision.value, "REJECTED")
        self.assertTrue(
            any("access disabled" in e.lower() for e in result.validation_errors),
            f"Expected access disabled, got: {result.validation_errors}"
        )
        self.assertFalse(
            any("nonce" in e.lower() for e in result.validation_errors),
            "Step 1 fired but nonce error leaked through"
        )


class TestRouterRunScopeMisconfig(unittest.TestCase):
    def test_empty_path_fields_rejected(self):
        from kathoros.router.registry import ToolRegistry
        import tempfile
        bad_tool = ToolDefinition(
            name="bad_scoped_tool",
            description="misconfigured",
            args_schema={"type": "object", "additionalProperties": False, "properties": {}},
            write_capable=True,
            requires_run_scope=True,
            path_fields=(),
            allowed_paths=("artifacts/",),
        )
        registry = ToolRegistry()
        registry.register(bad_tool)
        registry.build()
        router = ToolRouter(
            registry=registry,
            project_root=Path(tempfile.mkdtemp()),
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            approval_callback=lambda req, tool: True,
        )
        req = make_request("bad_scoped_tool", {}, nonce=NONCE,
                           trust=TrustLevel.TRUSTED, enveloped=True,
                           run_id="valid-run-id-123")
        result = router.handle(req)
        self.assertEqual(result.decision.value, "REJECTED")
        self.assertTrue(any("run-scope" in e for e in result.validation_errors))


class TestRouterInputSizeKeyword(unittest.TestCase):
    def test_input_size_error_keyword(self):
        import tempfile
        tiny_tool = ToolDefinition(
            name="tiny_tool",
            description="tiny",
            args_schema={"type": "object", "additionalProperties": False,
                         "required": ["data"], "properties": {"data": {"type": "string"}}},
            write_capable=False,
            max_input_size=10,
        )
        registry = ToolRegistry()
        registry.register(tiny_tool)
        registry.build()
        router = ToolRouter(
            registry=registry,
            project_root=Path(tempfile.mkdtemp()),
            session_nonce=NONCE,
            access_mode=AccessMode.FULL_ACCESS,
            approval_callback=lambda req, tool: True,
        )
        req = make_request("tiny_tool", {"data": "x" * 500}, nonce=NONCE,
                           trust=TrustLevel.TRUSTED, enveloped=True)
        result = router.handle(req)
        self.assertEqual(result.decision.value, "REJECTED")
        self.assertTrue(any("input size error" in e for e in result.validation_errors))

