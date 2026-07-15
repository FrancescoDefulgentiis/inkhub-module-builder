"""OpenAI provider (Chat Completions API).

Uses the official ``openai`` Python SDK if installed; otherwise falls back
to plain HTTPS via :mod:`requests` so the app runs even without the SDK.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .base import LLMClient, LLMError, LLMMessage, LLMResponse

_log = logging.getLogger(__name__)

_API_URL = "https://api.openai.com/v1/chat/completions"
_HTTP_TIMEOUT = 120


class OpenAIClient(LLMClient):
    provider_name = "openai"

    def chat(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(_API_URL, headers=headers, data=json.dumps(payload), timeout=_HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise LLMError(f"OpenAI network error: {exc}") from exc

        if r.status_code >= 400:
            raise LLMError(f"OpenAI HTTP {r.status_code}: {r.text[:400]}")

        try:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, ValueError, IndexError) as exc:
            raise LLMError(f"OpenAI: unexpected response shape: {exc}") from exc

        return LLMResponse(content=content, provider=self.provider_name, model=self.model)
