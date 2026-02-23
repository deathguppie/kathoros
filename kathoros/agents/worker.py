"""
AgentWorker — QThread wrapper for agent backend streaming.
Feeds chunks to UI via signals.
Scans completed response for tool requests via EnvelopeParser.
No DB imports. No approval logic.
"""
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from kathoros.agents.backends.ollama_backend import OllamaBackend
from kathoros.agents.parser import EnvelopeParser
from kathoros.core.enums import TrustLevel, AccessMode

_log = logging.getLogger("kathoros.agents.worker")


class AgentWorker(QThread):
    chunk_ready = pyqtSignal(str)
    tool_request_detected = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        backend: OllamaBackend,
        messages: list[dict],
        system_prompt: str = "",
        session_nonce: str = "",
        agent_id: str = "",
        agent_name: str = "",
        trust_level: TrustLevel = TrustLevel.MONITORED,
        access_mode: AccessMode = AccessMode.REQUEST_FIRST,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._messages = messages
        self._system_prompt = system_prompt
        self._session_nonce = session_nonce
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._trust_level = trust_level
        self._access_mode = access_mode
        self._stop = False
        self._buffer = ""
        self._parser = EnvelopeParser()

    def run(self) -> None:
        self._backend.stream(
            messages=self._messages,
            system_prompt=self._system_prompt,
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
        )

    def stop(self) -> None:
        self._stop = True

    def _on_chunk(self, chunk: str) -> None:
        if self._stop:
            return
        self._buffer += chunk
        self.chunk_ready.emit(chunk)

    def _on_done(self) -> None:
        result = self._parser.parse(
            self._buffer,
            agent_id=self._agent_id,
            agent_name=self._agent_name,
            trust_level=self._trust_level,
            access_mode=self._access_mode,
            session_nonce=self._session_nonce,
        )
        if result.tool_request is not None:
            req = result.tool_request
            self.tool_request_detected.emit({
                "tool_name": req.tool_name,
                "args": req.args,
                "detected_via": result.detected_via,
                "raw_block": result.raw_block,
                "enveloped": req.enveloped,
            })
        self.finished.emit()

    def _on_error(self, msg: str) -> None:
        _log.warning("agent worker error: %s", msg)
        self.error.emit(msg)
