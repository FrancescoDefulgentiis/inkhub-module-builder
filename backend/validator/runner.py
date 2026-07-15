"""Spawn a subprocess that imports the generated module and calls render()."""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

_HARNESS_PATH = Path(__file__).resolve().parent / "harness.py"
_HARNESS_TIMEOUT = 60  # seconds


@dataclass
class ValidationResult:
    ok: bool
    error: str
    preview_png_base64: str | None = None
    logs: str = ""


def validate_module(module_folder: Path, panel_size: tuple[int, int]) -> ValidationResult:
    """Run the generated module in a subprocess and return the outcome."""
    if not (module_folder / "__init__.py").is_file():
        return ValidationResult(ok=False, error=f"{module_folder}/__init__.py missing")

    cmd = [
        sys.executable,
        str(_HARNESS_PATH),
        "--module-dir", str(module_folder.resolve()),
        "--width", str(panel_size[0]),
        "--height", str(panel_size[1]),
    ]
    _log.info("Validator running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_HARNESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return ValidationResult(
            ok=False,
            error=f"Module render() took longer than {_HARNESS_TIMEOUT}s (likely stuck in a loop or on a network call).",
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    # The harness prints exactly one JSON line on its final stdout line.
    payload_line = None
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            payload_line = line
            break

    if payload_line is None:
        return ValidationResult(
            ok=False,
            error=f"Validator harness produced no JSON payload.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}",
        )

    try:
        payload = json.loads(payload_line)
    except json.JSONDecodeError as exc:
        return ValidationResult(
            ok=False,
            error=f"Validator harness returned malformed JSON: {exc}\n{payload_line}",
        )

    return ValidationResult(
        ok=bool(payload.get("ok")),
        error=str(payload.get("error", "")),
        preview_png_base64=payload.get("preview_png_base64"),
        logs=stderr,
    )
