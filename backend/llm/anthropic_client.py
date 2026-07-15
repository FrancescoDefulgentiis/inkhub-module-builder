"""Anthropic Claude provider (Messages API)."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .base import LLMClient, LLMError, LLMMessage, LLMResponse

_log = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_HTTP_TIMEOUT = 120
_MAX_TOKENS = 4096


class AnthropicClient(LLMClient):
    provider_name = "anthropic"

    def chat(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        # Anthropic separates the system prompt from the message list.
        system_prompt = "\n\n".join(m.content for m in messages if m.role == "system") or None
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        if not convo:
            raise LLMError("Anthropic: at least one user message is required")

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": _MAX_TOKENS,
            "temperature": temperature,
            "messages": convo,
        }
        if system_prompt is not None:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": _API_VERSION,
            "Content-Type": "application/json",
        }
        try:
            r = requests.post(_API_URL, headers=headers, data=json.dumps(payload), timeout=_HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise LLMError(f"Anthropic network error: {exc}") from exc

        if r.status_code >= 400:
            raise LLMError(f"Anthropic HTTP {r.status_code}: {r.text[:400]}")

        try:
            data = r.json()
            blocks = data["content"]
            content = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (KeyError, ValueError, TypeError) as exc:
            raise LLMError(f"Anthropic: unexpected response shape: {exc}") from exc

        return LLMResponse(content=content, provider=self.provider_name, model=self.model)
