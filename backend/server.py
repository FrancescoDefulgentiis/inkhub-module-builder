"""Flask app: setup page, wizard, generation, validation, delivery."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from .generator import (
    ModuleWriteError,
    ParseError,
    copy_module_to_target,
    parse_llm_output,
    write_module,
)
from .llm import LLMError, LLMMessage, get_client, list_models
from .settings import (
    DEFAULT_MODELS,
    PROVIDER_LABELS,
    SUPPORTED_PROVIDERS,
    detect_inkhub,
    is_configured,
    load_settings,
    provider_label,
    provider_requires_api_key,
    remove_provider,
    resolve_panel_size,
    set_active,
    target_modules_dir,
    update_settings,
    upsert_provider,
    workspace_dir,
)
from .validator import validate_module
from .wizard import (
    WIZARD_STEPS,
    build_fix_prompt,
    build_system_prompt,
    build_user_prompt,
    validate_answers,
)

_log = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5001

MAX_FIX_ATTEMPTS = 3

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND = _PROJECT_ROOT / "frontend"


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    app = Flask(
        __name__,
        template_folder=str(_FRONTEND / "templates"),
        static_folder=str(_FRONTEND / "static"),
    )

    _register_routes(app)
    return app


def _register_routes(app: Flask) -> None:

    @app.get("/")
    def index() -> Any:
        settings = load_settings()
        return render_template(
            "index.html",
            configured=is_configured(settings),
            provider=settings.get("provider"),
            model=settings.get("model"),
        )

    # ------------------------------------------------------------------ #
    # Settings (target folder + panel size + read-only status)            #
    # ------------------------------------------------------------------ #
    @app.get("/api/settings")
    def get_settings() -> Any:
        s = load_settings()
        inkhub = detect_inkhub(s)
        return jsonify({
            "target_modules_dir": str(target_modules_dir(s)),
            "panel_width": inkhub["panel_width"],
            "panel_height": inkhub["panel_height"],
            "panel_size_source": inkhub["panel_size_source"],
            "inkhub_repo_root": inkhub["repo_root"],
            "inkhub_config_path": inkhub["config_path"],
            "inkhub_panel_driver": inkhub["panel_driver"],
            "supported_providers": [
                {
                    "name": p,
                    "label": provider_label(p),
                    "requires_api_key": provider_requires_api_key(p),
                    "default_model": DEFAULT_MODELS.get(p, ""),
                }
                for p in SUPPORTED_PROVIDERS
            ],
            "configured": is_configured(s),
        })

    @app.post("/api/settings")
    def post_settings() -> Any:
        """Update non-provider settings (target folder, panel dimensions)."""
        body = request.get_json(silent=True) or {}

        target = body.get("target_modules_dir")
        if target is not None:
            target = str(target).strip()

        width = body.get("panel_width")
        height = body.get("panel_height")
        try:
            width = int(width) if width is not None else None
            height = int(height) if height is not None else None
        except (TypeError, ValueError):
            return jsonify({"error": "panel_width/panel_height must be integers"}), 400

        changes: dict[str, Any] = {}
        if target:
            changes["target_modules_dir"] = target
        if width:
            changes["panel_width"] = width
        if height:
            changes["panel_height"] = height

        settings = update_settings(**changes)
        return jsonify({"ok": True, "configured": is_configured(settings)})

    # ------------------------------------------------------------------ #
    # Providers (multi-provider configuration)                            #
    # ------------------------------------------------------------------ #
    @app.get("/api/providers")
    def providers_list() -> Any:
        s = load_settings()
        providers = s.get("providers") or {}
        configured = []
        for name in SUPPORTED_PROVIDERS:
            entry = providers.get(name)
            if entry is None:
                continue
            key = str(entry.get("api_key") or "")
            if len(key) > 8:
                preview = f"{key[:4]}…{key[-4:]}"
            elif key:
                preview = "•" * len(key)
            else:
                preview = ""
            configured.append({
                "name": name,
                "label": provider_label(name),
                "requires_api_key": provider_requires_api_key(name),
                "has_api_key": bool(key),
                "api_key_preview": preview,
            })
        return jsonify({
            "providers": configured,
            "supported_providers": [
                {
                    "name": p,
                    "label": provider_label(p),
                    "requires_api_key": provider_requires_api_key(p),
                    "default_model": DEFAULT_MODELS.get(p, ""),
                    "configured": p in providers,
                }
                for p in SUPPORTED_PROVIDERS
            ],
            "active_provider": s.get("active_provider"),
            "active_model": s.get("active_model"),
            "configured": is_configured(s),
        })

    @app.post("/api/providers")
    def providers_upsert() -> Any:
        body = request.get_json(silent=True) or {}
        name = str(body.get("provider") or "").strip().lower()
        if name not in SUPPORTED_PROVIDERS:
            return jsonify({"error": f"Unsupported provider {name!r}"}), 400
        api_key = str(body.get("api_key") or "").strip()
        if provider_requires_api_key(name) and not api_key:
            return jsonify({"error": f"{provider_label(name)} requires an API key"}), 400
        try:
            settings = upsert_provider(name, api_key)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({
            "ok": True,
            "provider": name,
            "active_provider": settings.get("active_provider"),
            "active_model": settings.get("active_model"),
            "configured": is_configured(settings),
        })

    @app.delete("/api/providers/<name>")
    def providers_remove(name: str) -> Any:
        settings = remove_provider(name)
        return jsonify({
            "ok": True,
            "active_provider": settings.get("active_provider"),
            "active_model": settings.get("active_model"),
            "configured": is_configured(settings),
        })

    @app.get("/api/providers/<name>/models")
    def providers_models(name: str) -> Any:
        name = (name or "").strip().lower()
        if name not in SUPPORTED_PROVIDERS:
            return jsonify({"error": f"Unsupported provider {name!r}"}), 400
        s = load_settings()
        entry = (s.get("providers") or {}).get(name)
        if entry is None:
            return jsonify({"error": f"Provider {name!r} is not configured"}), 404
        api_key = str(entry.get("api_key") or "")
        models, warning = list_models(name, api_key)
        return jsonify({
            "provider": name,
            "models": models,
            "default_model": DEFAULT_MODELS.get(name, ""),
            "warning": warning,
        })

    # ------------------------------------------------------------------ #
    # Active provider + model                                             #
    # ------------------------------------------------------------------ #
    @app.post("/api/active")
    def providers_set_active() -> Any:
        body = request.get_json(silent=True) or {}
        provider = body.get("provider")
        model = body.get("model")
        try:
            settings = set_active(provider, model)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({
            "ok": True,
            "active_provider": settings.get("active_provider"),
            "active_model": settings.get("active_model"),
            "configured": is_configured(settings),
        })

    # ------------------------------------------------------------------ #
    # Wizard steps                                                        #
    # ------------------------------------------------------------------ #
    @app.get("/api/wizard/steps")
    def wizard_steps() -> Any:
        return jsonify({"steps": WIZARD_STEPS})

    # ------------------------------------------------------------------ #
    # Generation pipeline                                                 #
    # ------------------------------------------------------------------ #
    @app.post("/api/generate")
    def generate() -> Any:
        settings = load_settings()
        if not is_configured(settings):
            return jsonify({"error": "AI provider not configured yet. Open Settings first."}), 400

        answers = (request.get_json(silent=True) or {}).get("answers", {})
        cleaned, errors = validate_answers(answers)
        if errors:
            return jsonify({"error": "Wizard answers invalid", "details": errors}), 400

        try:
            client = get_client(settings)
        except LLMError as exc:
            return jsonify({"error": str(exc)}), 400

        panel_size = resolve_panel_size(settings)
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(cleaned, panel_size)
        conversation: list[LLMMessage] = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        attempts: list[dict[str, Any]] = []
        staged: Path | None = None
        preview: str | None = None
        last_error = ""

        for attempt in range(MAX_FIX_ATTEMPTS + 1):
            try:
                _log.info("LLM attempt %d (provider=%s model=%s)", attempt + 1, client.provider_name, client.model)
                response = client.chat(conversation)
            except LLMError as exc:
                return jsonify({"error": f"AI call failed: {exc}"}), 502

            conversation.append(LLMMessage(role="assistant", content=response.content))

            try:
                parsed = parse_llm_output(response.content)
            except ParseError as exc:
                last_error = f"Parse error: {exc}"
                attempts.append({"attempt": attempt + 1, "error": last_error})
                if attempt >= MAX_FIX_ATTEMPTS:
                    break
                conversation.append(LLMMessage(
                    role="user",
                    content=build_fix_prompt(last_error, cleaned["slug"]),
                ))
                continue

            try:
                staged = write_module(workspace_dir(), cleaned["slug"], parsed)
            except ModuleWriteError as exc:
                return jsonify({"error": f"Could not write module: {exc}"}), 500

            result = validate_module(staged, panel_size)
            attempts.append({
                "attempt": attempt + 1,
                "error": "" if result.ok else result.error,
            })
            if result.ok:
                preview = result.preview_png_base64
                last_error = ""
                break

            last_error = result.error
            if attempt >= MAX_FIX_ATTEMPTS:
                break

            conversation.append(LLMMessage(
                role="user",
                content=build_fix_prompt(last_error, cleaned["slug"]),
            ))

        if last_error:
            return jsonify({
                "ok": False,
                "error": last_error,
                "attempts": attempts,
                "staged_folder": str(staged) if staged else None,
            }), 200  # 200 so the frontend can display the error nicely

        return jsonify({
            "ok": True,
            "slug": cleaned["slug"],
            "name": cleaned.get("name"),
            "staged_folder": str(staged),
            "preview_png_base64": preview,
            "attempts": attempts,
        })

    # ------------------------------------------------------------------ #
    # Delivery: copy the staged folder into inkHub/src/modules            #
    # ------------------------------------------------------------------ #
    @app.post("/api/deliver")
    def deliver() -> Any:
        body = request.get_json(silent=True) or {}
        slug = str(body.get("slug", "")).strip()
        if not slug:
            return jsonify({"error": "Missing slug"}), 400

        staged = (workspace_dir() / slug).resolve()
        if not staged.is_dir():
            return jsonify({"error": f"No staged folder found for {slug!r}"}), 404

        try:
            destination = copy_module_to_target(staged, target_modules_dir())
        except ModuleWriteError as exc:
            return jsonify({"error": str(exc)}), 500
        except OSError as exc:
            return jsonify({"error": f"Filesystem error while copying: {exc}"}), 500
        except Exception as exc:  # last-resort catch so we don't 500 silently
            return jsonify({
                "error": f"Unexpected error: {exc}\n{traceback.format_exc()}",
            }), 500

        return jsonify({"ok": True, "destination": str(destination)})
