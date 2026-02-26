"""
GeminiBackend — Google Gemini streaming backend.
No Qt imports. No DB imports. No tool execution.
API key loaded from KeyStore at runtime only.
"""
import logging
from typing import Callable

from kathoros.config.key_store import load_key

_log = logging.getLogger("kathoros.agents.backends.gemini_backend")


class GeminiBackend:
    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        self.model = model
        _log.info("GeminiBackend initialized: model=%s", model)

    def stream(
        self,
        messages: list[dict],
        on_chunk: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        system_prompt: str = "",
    ) -> None:
        from google import genai
        key = load_key("gemini")
        if not key:
            on_error("Gemini API key not set. Add it in Settings.")
            return
        try:
            client = genai.Client(api_key=key)
            contents = [
                {
                    "role": "model" if m["role"] == "assistant" else m["role"],
                    "parts": [{"text": m["content"]}],
                }
                for m in messages
            ]
            config = None
            if system_prompt:
                from google.genai import types
                config = types.GenerateContentConfig(system_instruction=system_prompt)
            response = client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )
            for chunk in response:
                if chunk.text:
                    on_chunk(chunk.text)
            on_done()
        except Exception as exc:
            _log.warning("gemini stream error: %s", exc)
            on_error(str(exc))

    def test_connection(self) -> bool:
        key = load_key("gemini")
        if not key:
            return False
        try:
            from google import genai
            client = genai.Client(api_key=key)
            client.models.generate_content(
                model=self.model,
                contents="Hi",
            )
            return True
        except Exception as exc:
            _log.warning("gemini connection test failed: %s", exc)
            return False
