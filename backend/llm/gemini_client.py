"""Google Gemini provider (Generative Language API v1beta)."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .base import LLMClient, LLMError, LLMMessage, LLMResponse

_log = logging.getLogger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_HTTP_TIMEOUT = 120


class GeminiClient(LLMClient):
    provider_name = "gemini"

    def chat(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        # Gemini merges system instructions into a dedicated field.
        system_instruction = "\n\n".join(m.content for m in messages if m.role == "system") or None
        contents = []
        for m in messages:
            if m.role == "system":
                continue
            role = "model" if m.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.content}]})
        if not contents:
            raise LLMError("Gemini: at least one user message is required")

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system_instruction is not None:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{_API_BASE}/{self.model}:generateContent?key={self.api_key}"
        try:
            r = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=_HTTP_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise LLMError(f"Gemini network error: {exc}") from exc

        if r.status_code >= 400:
            raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:400]}")

        try:
            data = r.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise LLMError(f"Gemini: no candidates returned ({data})")
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)
        except (KeyError, ValueError, IndexError) as exc:
            raise LLMError(f"Gemini: unexpected response shape: {exc}") from exc

        if not content:
            raise LLMError("Gemini: empty response (possibly blocked by safety filters)")

        return LLMResponse(content=content, provider=self.provider_name, model=self.model)
