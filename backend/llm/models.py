"""Fetch the list of models available for each provider.

This is used by the frontend dashboard to populate the "active model"
dropdown with real, live values from the user's own account. If a call
fails (bad key, offline, endpoint missing), we fall back to a curated
static list and surface the error so the UI can hint at it.
"""

from __future__ import annotations

import logging
from typing import Callable

import requests

from .base import LLMError

_log = logging.getLogger(__name__)

_HTTP_TIMEOUT = 30

# Curated fallback lists used when the live fetch fails. Kept short and
# up-to-date rather than exhaustive — the dashboard always shows the live
# list first when it's available.
FALLBACK_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ],
    "anthropic": [
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
        "claude-3-haiku-20240307",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-1.5-pro-latest",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
    ],
    "opencode": [
        "big-pickle",
        "small-pickle",
    ],
}


def _fetch_openai(api_key: str) -> list[str]:
    r = requests.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise LLMError(f"OpenAI HTTP {r.status_code}: {r.text[:200]}")
    ids = [m.get("id") for m in (r.json().get("data") or []) if m.get("id")]
    # Keep just the conversational families to avoid drowning the dropdown
    # in embeddings, TTS, whisper, moderation, etc.
    keep = [
        x for x in ids
        if x.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4"))
    ]
    return sorted(set(keep))


def _fetch_anthropic(api_key: str) -> list[str]:
    r = requests.get(
        "https://api.anthropic.com/v1/models",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        timeout=_HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise LLMError(f"Anthropic HTTP {r.status_code}: {r.text[:200]}")
    ids = [m.get("id") for m in (r.json().get("data") or []) if m.get("id")]
    return sorted(set(ids))


def _fetch_gemini(api_key: str) -> list[str]:
    r = requests.get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
        timeout=_HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
    out: list[str] = []
    for m in r.json().get("models", []) or []:
        name = str(m.get("name") or "")
        if name.startswith("models/"):
            name = name.split("/", 1)[1]
        methods = m.get("supportedGenerationMethods") or []
        if name and "generateContent" in methods:
            out.append(name)
    return sorted(set(out))


def _fetch_opencode(api_key: str) -> list[str]:
    # OpenCode Zen is OpenAI-compatible; anonymous access uses "public".
    key = api_key or "public"
    r = requests.get(
        "https://opencode.ai/zen/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=_HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise LLMError(f"OpenCode HTTP {r.status_code}: {r.text[:200]}")
    payload = r.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    ids = [m.get("id") for m in (data or []) if isinstance(m, dict) and m.get("id")]
    return sorted(set(ids))


_FETCHERS: dict[str, Callable[[str], list[str]]] = {
    "openai": _fetch_openai,
    "anthropic": _fetch_anthropic,
    "gemini": _fetch_gemini,
    "opencode": _fetch_opencode,
}


def list_models(provider: str, api_key: str) -> tuple[list[str], str | None]:
    """Return ``(models, warning)`` for the given provider.

    When the live fetch works, ``warning`` is None. On failure we fall
    back to :data:`FALLBACK_MODELS` and return the error string so the
    UI can display it as a hint (e.g. "invalid key, showing fallback").
    """
    provider = (provider or "").strip().lower()
    fetcher = _FETCHERS.get(provider)
    if fetcher is None:
        return (list(FALLBACK_MODELS.get(provider, [])), "unknown provider")
    try:
        models = fetcher(api_key or "")
        if models:
            return (models, None)
        return (list(FALLBACK_MODELS.get(provider, [])), "no models returned")
    except (LLMError, requests.RequestException) as exc:
        _log.warning("Model fetch failed for %s: %s", provider, exc)
        return (list(FALLBACK_MODELS.get(provider, [])), str(exc))
