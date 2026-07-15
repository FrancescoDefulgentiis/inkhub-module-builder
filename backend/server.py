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
from .llm import LLMError, LLMMessage, get_client
from .settings import (
    DEFAULT_MODELS,
    SUPPORTED_PROVIDERS,
    is_configured,
    load_settings,
    target_modules_dir,
    update_settings,
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

DEFAULT_HOST = "127.0.0.1"
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
    # Settings                                                            #
    # ------------------------------------------------------------------ #
    @app.get("/api/settings")
    def get_settings() -> Any:
        s = load_settings()
        # Never leak the API key in full — send back a redacted preview
        # so the UI can show "sk-abc…xyz" without exposing the whole thing.
        preview = ""
        if s.get("api_key"):
            k = str(s["api_key"])
            preview = f"{k[:4]}…{k[-4:]}" if len(k) > 8 else "•" * len(k)
        return jsonify({
            "provider": s.get("provider"),
            "model": s.get("model"),
            "api_key_preview": preview,
            "target_modules_dir": s.get("target_modules_dir"),
            "panel_width": s.get("panel_width"),
            "panel_height": s.get("panel_height"),
            "supported_providers": list(SUPPORTED_PROVIDERS),
            "default_models": DEFAULT_MODELS,
            "configured": is_configured(s),
        })

    @app.post("/api/settings")
    def post_settings() -> Any:
        body = request.get_json(silent=True) or {}
        provider = body.get("provider")
        if provider is not None:
            provider = str(provider).lower().strip()
            if provider not in SUPPORTED_PROVIDERS:
                return jsonify({"error": f"Unsupported provider {provider!r}"}), 400

        api_key = body.get("api_key")
        if api_key is not None:
            api_key = str(api_key).strip()

        model = body.get("model")
        if model is not None:
            model = str(model).strip()
            if not model and provider:
                model = DEFAULT_MODELS.get(provider, "")

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

        # Only forward keys the user actually sent (skip None), except for
        # empty api_key which we treat as "no change" to avoid wiping it by
        # accident from the settings dialog.
        changes: dict[str, Any] = {}
        if provider:
            changes["provider"] = provider
            if not model:
                changes["model"] = DEFAULT_MODELS.get(provider, "")
        if api_key:
            changes["api_key"] = api_key
        if model:
            changes["model"] = model
        if target:
            changes["target_modules_dir"] = target
        if width:
            changes["panel_width"] = width
        if height:
            changes["panel_height"] = height

        settings = update_settings(**changes)
        return jsonify({"ok": True, "configured": is_configured(settings)})

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

        panel_size = (int(settings["panel_width"]), int(settings["panel_height"]))
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
