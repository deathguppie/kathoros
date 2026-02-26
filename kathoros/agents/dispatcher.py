"""
AgentDispatcher — orchestrates backend selection, conversation history,
and worker thread lifecycle.
No approval logic. No tool execution. No DB writes.
"""
import logging

from kathoros.agents.backends.anthropic_backend import AnthropicBackend
from kathoros.agents.backends.gemini_backend import GeminiBackend
from kathoros.agents.backends.ollama_backend import OllamaBackend
from kathoros.agents.backends.openai_backend import OpenAIBackend
from kathoros.agents.context_builder import build_system_prompt
from kathoros.agents.worker import AgentWorker
from kathoros.core.enums import AccessMode, TrustLevel

_log = logging.getLogger("kathoros.agents.dispatcher")


class AgentDispatcher:
    def __init__(self) -> None:
        self._history: list[dict] = []
        self._worker: AgentWorker | None = None

    def dispatch(
        self,
        message: str,
        agent: dict,
        access_mode: str = "REQUEST_FIRST",
        session_nonce: str = "",
        system_prompt: str = "",
        context: dict | None = None,
        on_chunk=None,
        on_tool_request=None,
        on_done=None,
        on_error=None,
    ) -> AgentWorker:
        # Add user message to history
        self._history.append({"role": "user", "content": message})

        # Build backend
        provider = agent.get("provider", "ollama")
        model = agent.get("model_string", "llama3.2:latest")

        if provider == "ollama":
            backend = OllamaBackend(model=model)
        elif provider == "anthropic":
            backend = AnthropicBackend(model=model)
        elif provider == "openai":
            backend = OpenAIBackend(model=model)
        elif provider == "gemini":
            backend = GeminiBackend(model=model)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        trust_level = TrustLevel[agent.get("trust_level", "MONITORED").upper()]
        mode = AccessMode[access_mode.upper()]

        # Resolve system prompt: rich context > explicit prompt > agent default
        if context is not None:
            effective_prompt = build_system_prompt(context)
        else:
            effective_prompt = system_prompt or agent.get("default_research_prompt", "")

        worker = AgentWorker(
            backend=backend,
            messages=list(self._history),
            system_prompt=effective_prompt,
            session_nonce=session_nonce,
            agent_id=str(agent.get("id", "")),
            agent_name=agent.get("name", ""),
            trust_level=trust_level,
            access_mode=mode,
        )

        if on_chunk:
            worker.chunk_ready.connect(on_chunk)
        if on_tool_request:
            worker.tool_request_detected.connect(on_tool_request)
        # Accumulate assistant response into history BEFORE on_done
        worker.response_done.connect(lambda: self._history.append({
            "role": "assistant",
            "content": worker._buffer,
        }))
        if on_done:
            worker.response_done.connect(on_done)
        if on_error:
            worker.error.connect(on_error)

        self._worker = worker
        worker.start()
        return worker

    def clear_history(self) -> None:
        self._history.clear()
        _log.info("conversation history cleared")

    def stop(self) -> None:
        if self._worker:
            self._worker.stop()
