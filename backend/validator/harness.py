"""Subprocess harness: import a generated module and call render() once.

Prints one JSON line to stdout with the outcome. Never raises — anything
that would raise is captured and returned in the JSON payload.

We stub the ``src`` / ``src.modules`` / ``src.module`` / ``src.registry``
packages in-process so a generated module can use its normal relative
imports without needing the real InkHub installed.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import io
import json
import sys
import traceback
import types
from pathlib import Path
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Stub the src.module ABC so generated modules can `from ...module import Module`.
# ---------------------------------------------------------------------------

def _install_stubs(target_slug: str, target_dir: Path) -> None:
    from PIL import Image  # noqa: WPS433

    # src package
    src_pkg = types.ModuleType("src")
    src_pkg.__path__ = []  # marks it as a package
    sys.modules["src"] = src_pkg

    # src.module with a Module base class
    module_mod = types.ModuleType("src.module")

    class Module:
        name: str = ""

        def __init__(self, config: Mapping[str, Any], size: tuple[int, int]) -> None:
            self.config = config or {}
            self.width, self.height = size

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def on_action_button(self) -> None:
            pass

        def next_update_delay(self):
            return None

        def new_image(self, color: int = 255) -> "Image.Image":
            return Image.new("1", (self.width, self.height), color)

        def render(self) -> "Image.Image":  # pragma: no cover - abstract
            raise NotImplementedError

    module_mod.Module = Module
    sys.modules["src.module"] = module_mod

    # src.registry with a working register_module decorator that also
    # stashes the class into a private table for later retrieval.
    registry_mod = types.ModuleType("src.registry")
    registry_mod._REGISTRY = {}

    def register_module(name: str):
        def decorator(cls):
            cls.name = name
            registry_mod._REGISTRY[name] = cls
            return cls
        return decorator

    registry_mod.register_module = register_module
    sys.modules["src.registry"] = registry_mod

    # src.modules package (parent of our generated module)
    modules_pkg = types.ModuleType("src.modules")
    modules_pkg.__path__ = [str(target_dir.parent)]
    sys.modules["src.modules"] = modules_pkg

    # src.modules.<slug> — point Python at the actual folder on disk.
    spec = importlib.util.spec_from_file_location(
        f"src.modules.{target_slug}",
        target_dir / "__init__.py",
        submodule_search_locations=[str(target_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build import spec for {target_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"src.modules.{target_slug}"] = module
    spec.loader.exec_module(module)


def _emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-dir", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    args = parser.parse_args()

    module_dir = Path(args.module_dir).resolve()
    slug = module_dir.name

    # Route the subprocess into a temporary working directory so a generated
    # module's relative file writes (e.g. `Path(".cache/foo")`) don't
    # clutter the real workspace.
    import tempfile
    tempdir = Path(tempfile.mkdtemp(prefix="inkhub_validate_"))
    import os as _os
    _os.chdir(tempdir)

    try:
        _install_stubs(slug, module_dir)
    except Exception:
        _emit({
            "ok": False,
            "error": f"Failed to import module:\n{traceback.format_exc()}",
        })
        return 0

    from src.registry import _REGISTRY  # type: ignore
    if slug not in _REGISTRY:
        _emit({
            "ok": False,
            "error": (
                f"Module imported OK but did not register itself as {slug!r}. "
                f"Did you use @register_module(\"{slug}\") on your class? "
                f"Registered names: {sorted(_REGISTRY)}"
            ),
        })
        return 0

    cls = _REGISTRY[slug]
    # Load the module's own config.json (same behaviour the real registry has).
    cfg_path = module_dir / "config.json"
    try:
        with cfg_path.open("r", encoding="utf-8") as fh:
            config = json.load(fh)
    except Exception:
        _emit({
            "ok": False,
            "error": f"Could not read config.json:\n{traceback.format_exc()}",
        })
        return 0

    try:
        instance = cls(config, (args.width, args.height))
    except Exception:
        _emit({
            "ok": False,
            "error": f"Module __init__ raised:\n{traceback.format_exc()}",
        })
        return 0

    try:
        image = instance.render()
    except Exception:
        _emit({
            "ok": False,
            "error": f"render() raised:\n{traceback.format_exc()}",
        })
        return 0

    from PIL import Image  # noqa: WPS433
    if not isinstance(image, Image.Image):
        _emit({
            "ok": False,
            "error": f"render() returned {type(image).__name__!r}, expected PIL.Image.Image.",
        })
        return 0

    if image.size != (args.width, args.height):
        _emit({
            "ok": False,
            "error": (
                f"render() returned an image of size {image.size}, "
                f"expected {(args.width, args.height)}."
            ),
        })
        return 0

    # Convert to PNG so the browser can preview it; downscale on the frontend if needed.
    # Preview at 1-bit is fine — PNG supports mode "1".
    buf = io.BytesIO()
    try:
        image.save(buf, format="PNG")
    except Exception:
        # Some 1-bit variants trip PIL; convert first as a safety net.
        image.convert("L").save(buf, format="PNG")
    preview = base64.b64encode(buf.getvalue()).decode("ascii")

    _emit({"ok": True, "error": "", "preview_png_base64": preview})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
