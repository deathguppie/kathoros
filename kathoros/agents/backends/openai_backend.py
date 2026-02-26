"""
OpenAIBackend — OpenAI streaming backend.
Compatible with OpenAI API and OpenAI-compatible endpoints.
No Qt imports. No DB imports. No tool execution.
API key loaded from KeyStore at runtime only.
"""
import logging
from typing import Callable

from kathoros.config.key_store import load_key

_log = logging.getLogger("kathoros.agents.backends.openai_backend")

_DEFAULT_MAX_TOKENS = 4096


class OpenAIBackend:
    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url  # None = default OpenAI endpoint
        _log.info("OpenAIBackend initialized: model=%s", model)

    def stream(
        self,
        messages: list[dict],
        on_chunk: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        system_prompt: str = "",
    ) -> None:
        import openai
        key = load_key("openai")
        if not key:
            on_error("OpenAI API key not set. Add it in Settings.")
            return
        try:
            kwargs = dict(api_key=key)
            if self.base_url:
                kwargs["base_url"] = self.base_url
            client = openai.OpenAI(**kwargs)
            msg_list = list(messages)
            if system_prompt:
                msg_list.insert(0, {"role": "system", "content": system_prompt})
            with client.chat.completions.create(
                model=self.model,
                messages=msg_list,
                max_tokens=_DEFAULT_MAX_TOKENS,
                stream=True,
            ) as stream:
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            on_chunk(delta)
            on_done()
        except Exception as exc:
            _log.warning("openai stream error: %s", exc)
            on_error(str(exc))

    def test_connection(self) -> bool:
        key = load_key("openai")
        if not key:
            return False
        try:
            import openai
            client = openai.OpenAI(api_key=key)
            client.models.list()
            return True
        except Exception as exc:
            _log.warning("openai connection test failed: %s", exc)
            return False
