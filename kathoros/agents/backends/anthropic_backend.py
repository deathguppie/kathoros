"""
AnthropicBackend — Anthropic Claude streaming backend.
No Qt imports. No DB imports. No tool execution.
API key loaded from KeyStore at runtime only.
"""
import logging
from typing import Callable
from kathoros.config.key_store import load_key

_log = logging.getLogger("kathoros.agents.backends.anthropic_backend")

_DEFAULT_MAX_TOKENS = 4096


class AnthropicBackend:
    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        _log.info("AnthropicBackend initialized: model=%s", model)

    def stream(
        self,
        messages: list[dict],
        on_chunk: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        system_prompt: str = "",
    ) -> None:
        import anthropic
        key = load_key("anthropic")
        if not key:
            on_error("Anthropic API key not set. Add it in Settings.")
            return
        try:
            client = anthropic.Anthropic(api_key=key)
            kwargs = dict(
                model=self.model,
                max_tokens=_DEFAULT_MAX_TOKENS,
                messages=list(messages),
            )
            if system_prompt:
                kwargs["system"] = system_prompt
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if text:
                        on_chunk(text)
            on_done()
        except Exception as exc:
            _log.warning("anthropic stream error: %s", exc)
            on_error(str(exc))

    def test_connection(self) -> bool:
        key = load_key("anthropic")
        if not key:
            return False
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            client.models.list()
            return True
        except Exception as exc:
            _log.warning("anthropic connection test failed: %s", exc)
            return False
