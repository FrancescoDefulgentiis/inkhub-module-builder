"""OpenCode Zen provider (OpenAI-compatible Chat Completions API)."""

from __future__ import annotations

import json
from typing import Any

import requests

from .base import LLMClient, LLMError, LLMMessage, LLMResponse

_API_URL = "https://opencode.ai/zen/v1/chat/completions"
_DEFAULT_API_KEY = "public"
_HTTP_TIMEOUT = 120


class OpenCodeClient(LLMClient):
    provider_name = "opencode"

    def __init__(self, api_key: str, model: str) -> None:
        if not model:
            raise LLMError(f"{self.provider_name}: missing model name")
        # OpenCode Zen supports anonymous access with the public key.
        self.api_key = api_key or _DEFAULT_API_KEY
        self.model = model

    def chat(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "inkhub-module-builder/1.0",
        }
        try:
            r = requests.post(_API_URL, headers=headers, data=json.dumps(payload), timeout=_HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise LLMError(f"OpenCode network error: {exc}") from exc

        if r.status_code >= 400:
            raise LLMError(f"OpenCode HTTP {r.status_code}: {r.text[:400]}")

        try:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            if not isinstance(content, str):
                raise TypeError("message content is not text")
        except (KeyError, ValueError, IndexError, TypeError) as exc:
            raise LLMError(f"OpenCode: unexpected response shape: {exc}") from exc

        return LLMResponse(content=content, provider=self.provider_name, model=self.model)
