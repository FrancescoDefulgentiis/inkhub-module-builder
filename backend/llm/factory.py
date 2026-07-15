"""Factory that picks the right :class:`LLMClient` based on settings."""

from __future__ import annotations

from typing import Any

from .base import LLMClient, LLMError

_PROVIDERS: dict[str, type[LLMClient]] = {}


def _register(name: str, cls: type[LLMClient]) -> None:
    _PROVIDERS[name] = cls


def _install_providers() -> None:
    from .openai_client import OpenAIClient
    from .anthropic_client import AnthropicClient
    from .gemini_client import GeminiClient
    from .opencode_client import OpenCodeClient

    _register("openai", OpenAIClient)
    _register("anthropic", AnthropicClient)
    _register("gemini", GeminiClient)
    _register("opencode", OpenCodeClient)


_install_providers()


def get_client(settings: dict[str, Any]) -> LLMClient:
    provider = str(settings.get("provider", "")).lower()
    api_key = str(settings.get("api_key", ""))
    model = str(settings.get("model", ""))

    if provider not in _PROVIDERS:
        raise LLMError(
            f"Unknown provider {provider!r}. Available: {sorted(_PROVIDERS)}"
        )
    return _PROVIDERS[provider](api_key=api_key, model=model)
