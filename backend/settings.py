"""User-settings persistence for the module builder.

Stores the AI provider choice, API key, chosen model, and the target folder
into which finished modules are copied. Everything lives in a single
``config.json`` file at the project root and is only ever read/written by
this module.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT_ROOT / "config.json"
WORKSPACE_DIR = PROJECT_ROOT / "workspace"

DEFAULT_TARGET = (PROJECT_ROOT.parent / "src" / "modules").resolve()

SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini")

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "gemini": "gemini-2.0-flash",
}


def _defaults() -> dict[str, Any]:
    return {
        "provider": None,
        "api_key": "",
        "model": "",
        "target_modules_dir": str(DEFAULT_TARGET),
        "panel_width": 800,
        "panel_height": 480,
    }


def load_settings() -> dict[str, Any]:
    """Load settings, filling in defaults for any missing keys."""
    settings = _defaults()
    if SETTINGS_FILE.is_file():
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as fh:
                on_disk = json.load(fh)
            if isinstance(on_disk, dict):
                settings.update(on_disk)
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning("Ignoring invalid settings file %s: %s", SETTINGS_FILE, exc)
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    """Persist settings to disk (creates the file if needed)."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)


def update_settings(**changes: Any) -> dict[str, Any]:
    """Merge ``changes`` into stored settings and persist."""
    settings = load_settings()
    settings.update({k: v for k, v in changes.items() if v is not None})
    save_settings(settings)
    return settings


def is_configured(settings: dict[str, Any] | None = None) -> bool:
    """Return True iff provider + API key + model are all set."""
    settings = settings or load_settings()
    return bool(
        settings.get("provider") in SUPPORTED_PROVIDERS
        and settings.get("api_key")
        and settings.get("model")
    )


def workspace_dir() -> Path:
    """Return the staging folder used for generated modules."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSPACE_DIR


def target_modules_dir(settings: dict[str, Any] | None = None) -> Path:
    """Return the resolved on-disk path where finished modules are copied."""
    settings = settings or load_settings()
    return Path(os.path.expanduser(str(settings.get("target_modules_dir", DEFAULT_TARGET)))).resolve()
