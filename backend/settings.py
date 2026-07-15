"""User-settings persistence and InkHub auto-discovery helpers.

Stores the AI provider choice, API key, model, and copy target in
``config.json`` at the project root. It also tries to locate the sibling
InkHub repository and infer the panel size from its ``src/config.json``.
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

LEGACY_DEFAULT_TARGET = (PROJECT_ROOT.parent / "src" / "modules").resolve()
DEFAULT_PANEL_SIZE = (800, 480)

_PANEL_DRIVER_SIZES: dict[str, tuple[int, int]] = {
    "epd1in54": (200, 200),
    "epd2in13": (250, 122),
    "epd2in13v2": (250, 122),
    "epd2in7": (264, 176),
    "epd2in9": (296, 128),
    "epd2in9v2": (296, 128),
    "epd3in7": (480, 280),
    "epd4in2": (400, 300),
    "epd5in65f": (600, 448),
    "epd5in83": (600, 448),
    "epd7in3f": (800, 480),
    "epd7in5": (800, 480),
    "epd7in5v2": (800, 480),
}

SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini", "opencode")
API_KEY_OPTIONAL_PROVIDERS = ("opencode",)

PROVIDER_LABELS = {
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "gemini": "Google (Gemini)",
    "opencode": "OpenCode (free)",
}

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "gemini": "gemini-2.0-flash",
    "opencode": "big-pickle",
}


def _defaults() -> dict[str, Any]:
    panel_width, panel_height = resolve_panel_size()
    return {
        # New multi-provider model: each entry is {"api_key": "..."}.
        "providers": {},
        "active_provider": None,
        "active_model": "",
        # Legacy fields kept in sync so llm.get_client(settings) still works.
        "provider": None,
        "api_key": "",
        "model": "",
        "target_modules_dir": str(default_target_modules_dir()),
        "panel_width": panel_width,
        "panel_height": panel_height,
    }


def provider_label(provider: str | None) -> str:
    key = (provider or "").strip().lower()
    return PROVIDER_LABELS.get(key, key or "")


def _migrate_legacy(settings: dict[str, Any]) -> dict[str, Any]:
    """Fold pre-multi-provider config (flat provider/api_key/model) into the
    new providers dict so old config.json files keep working."""
    if not isinstance(settings.get("providers"), dict):
        settings["providers"] = {}
    legacy_provider = str(settings.get("provider") or "").strip().lower()
    if legacy_provider in SUPPORTED_PROVIDERS and legacy_provider not in settings["providers"]:
        settings["providers"][legacy_provider] = {
            "api_key": str(settings.get("api_key") or ""),
        }
        if not settings.get("active_provider"):
            settings["active_provider"] = legacy_provider
        if not settings.get("active_model"):
            settings["active_model"] = str(
                settings.get("model") or DEFAULT_MODELS.get(legacy_provider, "")
            )
    return settings


def _sync_active(settings: dict[str, Any]) -> dict[str, Any]:
    """Mirror active_provider/active_model back into the flat provider/api_key/model
    fields so legacy consumers (like llm.get_client) keep working unchanged."""
    providers = settings.get("providers") or {}
    active = str(settings.get("active_provider") or "").strip().lower()
    if active and active in providers:
        settings["provider"] = active
        settings["api_key"] = str(providers[active].get("api_key") or "")
        settings["model"] = str(
            settings.get("active_model") or DEFAULT_MODELS.get(active, "")
        )
    else:
        settings["provider"] = None
        settings["api_key"] = ""
        settings["model"] = ""
    return settings


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
    settings = _migrate_legacy(settings)
    settings = _sync_active(settings)
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    """Persist settings to disk (creates the file if needed)."""
    _sync_active(settings)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)


def update_settings(**changes: Any) -> dict[str, Any]:
    """Merge ``changes`` into stored settings and persist."""
    settings = load_settings()
    settings.update({k: v for k, v in changes.items() if v is not None})
    save_settings(settings)
    return settings


def upsert_provider(name: str, api_key: str) -> dict[str, Any]:
    """Add or update a provider entry. Auto-selects it if none is active yet."""
    name = (name or "").strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider {name!r}")
    settings = load_settings()
    providers = settings.setdefault("providers", {})
    providers[name] = {"api_key": (api_key or "").strip()}
    if not settings.get("active_provider"):
        settings["active_provider"] = name
        if not settings.get("active_model"):
            settings["active_model"] = DEFAULT_MODELS.get(name, "")
    save_settings(settings)
    return settings


def remove_provider(name: str) -> dict[str, Any]:
    """Remove a provider entry; if it was active, fall back to another one."""
    name = (name or "").strip().lower()
    settings = load_settings()
    providers = settings.setdefault("providers", {})
    providers.pop(name, None)
    if settings.get("active_provider") == name:
        remaining = next(iter(providers), None)
        settings["active_provider"] = remaining
        settings["active_model"] = (
            DEFAULT_MODELS.get(remaining, "") if remaining else ""
        )
    save_settings(settings)
    return settings


def set_active(provider: str | None, model: str | None) -> dict[str, Any]:
    """Point active_provider / active_model at a configured provider."""
    settings = load_settings()
    if provider is not None:
        provider = provider.strip().lower() or None
        if provider and provider not in (settings.get("providers") or {}):
            raise ValueError(f"Provider {provider!r} is not configured")
        settings["active_provider"] = provider
        if provider and not (model or settings.get("active_model")):
            settings["active_model"] = DEFAULT_MODELS.get(provider, "")
    if model is not None:
        settings["active_model"] = model.strip()
    save_settings(settings)
    return settings


def provider_requires_api_key(provider: str | None) -> bool:
    provider = (provider or "").strip().lower()
    return provider in SUPPORTED_PROVIDERS and provider not in API_KEY_OPTIONAL_PROVIDERS


def is_configured(settings: dict[str, Any] | None = None) -> bool:
    """Return True iff an active provider + model are set (+ key if needed)."""
    settings = settings or load_settings()
    active = str(settings.get("active_provider") or "").strip().lower()
    if active not in SUPPORTED_PROVIDERS:
        return False
    if not settings.get("active_model"):
        return False
    entry = (settings.get("providers") or {}).get(active) or {}
    if provider_requires_api_key(active) and not entry.get("api_key"):
        return False
    return True


def workspace_dir() -> Path:
    """Return the staging folder used for generated modules."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSPACE_DIR


def _normalize_panel_driver(driver_name: str | None) -> str:
    raw = (driver_name or "").strip().lower()
    return "".join(ch for ch in raw if ch.isalnum())


def _is_inkhub_repo_root(root: Path) -> bool:
    return (
        (root / "run.py").is_file()
        and (root / "src" / "config.json").is_file()
        and (root / "src" / "modules").is_dir()
    )


def _safe_resolve(path_like: str | Path) -> Path | None:
    try:
        return Path(path_like).expanduser().resolve()
    except OSError:
        return None


def _candidate_inkhub_roots(settings: dict[str, Any] | None = None) -> list[Path]:
    candidates: list[Path] = []

    env_root = os.environ.get("INKHUB_ROOT")
    if env_root:
        resolved = _safe_resolve(env_root)
        if resolved is not None:
            candidates.append(resolved)

    settings = settings or {}
    target_raw = str(settings.get("target_modules_dir") or "").strip()
    if target_raw:
        target = _safe_resolve(target_raw)
        if target is not None and target.name == "modules" and target.parent.name == "src":
            candidates.append(target.parent.parent)

    parent = PROJECT_ROOT.parent
    candidates.extend([
        parent / "inkHub",
        parent / "inkhub",
        parent / "InkHub",
    ])
    return candidates


def find_inkhub_root(settings: dict[str, Any] | None = None) -> Path | None:
    """Return the first local InkHub repository root we can confidently identify."""
    for candidate in _candidate_inkhub_roots(settings):
        resolved = _safe_resolve(candidate)
        if resolved is not None and _is_inkhub_repo_root(resolved):
            return resolved
    return None


def default_target_modules_dir(settings: dict[str, Any] | None = None) -> Path:
    """Return the automatic destination folder for final module delivery."""
    inkhub_root = find_inkhub_root(settings)
    if inkhub_root is not None:
        return (inkhub_root / "src" / "modules").resolve()
    return LEGACY_DEFAULT_TARGET


def _read_inkhub_config(settings: dict[str, Any] | None = None) -> dict[str, Any] | None:
    inkhub_root = find_inkhub_root(settings)
    if inkhub_root is None:
        return None
    config_path = inkhub_root / "src" / "config.json"
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except OSError as exc:
        _log.warning("Could not read InkHub config %s: %s", config_path, exc)
        return None
    except json.JSONDecodeError as exc:
        _log.warning("Invalid InkHub config JSON at %s: %s", config_path, exc)
        return None
    if not isinstance(payload, dict):
        _log.warning("Ignoring non-object InkHub config at %s", config_path)
        return None
    return payload


def detect_inkhub(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return discovery metadata for the local InkHub repository."""
    inkhub_root = find_inkhub_root(settings)
    panel_size = DEFAULT_PANEL_SIZE
    panel_size_source = "fallback_default"
    panel_driver = None

    config = _read_inkhub_config(settings)
    if config is not None:
        raw_driver = str(config.get("panel_driver") or "").strip()
        panel_driver = raw_driver or None
        normalized_driver = _normalize_panel_driver(raw_driver)
        if normalized_driver in _PANEL_DRIVER_SIZES:
            panel_size = _PANEL_DRIVER_SIZES[normalized_driver]
            panel_size_source = "inkhub_panel_driver"
        elif raw_driver:
            panel_size_source = "unknown_panel_driver_default"

    config_path = (inkhub_root / "src" / "config.json") if inkhub_root is not None else None
    return {
        "repo_root": str(inkhub_root) if inkhub_root is not None else None,
        "config_path": str(config_path) if config_path is not None else None,
        "panel_driver": panel_driver,
        "panel_width": panel_size[0],
        "panel_height": panel_size[1],
        "panel_size_source": panel_size_source,
    }


def resolve_panel_size(settings: dict[str, Any] | None = None) -> tuple[int, int]:
    """Return the panel size used for prompting + validation."""
    detected = detect_inkhub(settings)
    return int(detected["panel_width"]), int(detected["panel_height"])


def target_modules_dir(settings: dict[str, Any] | None = None) -> Path:
    """Return the resolved on-disk path where finished modules are copied."""
    settings = settings or load_settings()
    raw_target = str(settings.get("target_modules_dir") or "").strip()
    auto_target = default_target_modules_dir(settings)
    if not raw_target:
        return auto_target
    target = _safe_resolve(os.path.expanduser(raw_target))
    if target is None:
        return auto_target
    if target == LEGACY_DEFAULT_TARGET and auto_target != LEGACY_DEFAULT_TARGET:
        return auto_target
    return target
