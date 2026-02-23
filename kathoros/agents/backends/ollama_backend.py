"""
OllamaBackend — Ollama streaming backend for agent dispatch.
No Qt imports. No DB imports. No tool execution.
Tool requests are intercepted upstream by the parser.
"""
import logging
from typing import Callable
import ollama

_log = logging.getLogger("kathoros.agents.backends.ollama_backend")


class OllamaBackend:
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url
        _log.info("OllamaBackend initialized: model=%s", model)

    def stream(
        self,
        messages: list[dict],
        on_chunk: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        system_prompt: str = "",
    ) -> None:
        try:
            msg_list = list(messages)
            if system_prompt:
                msg_list.insert(0, {"role": "system", "content": system_prompt})
            response = ollama.chat(model=self.model, messages=msg_list, stream=True)
            for chunk in response:
                content = chunk.message.content
                if content:
                    on_chunk(content)
            on_done()
        except Exception as exc:
            _log.warning("ollama stream error: %s", exc)
            on_error(str(exc))

    def test_connection(self) -> bool:
        try:
            ollama.list()
            return True
        except Exception as exc:
            _log.warning("ollama connection test failed: %s", exc)
            return False
