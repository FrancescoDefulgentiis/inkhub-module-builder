"""Write parsed module files into staging and copy to the InkHub target."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .parser import ParsedModule

_log = logging.getLogger(__name__)


class ModuleWriteError(Exception):
    """Raised when we can't write the generated module to disk."""


def write_module(workspace: Path, slug: str, parsed: ParsedModule) -> Path:
    """Write ``parsed`` into ``workspace/<slug>/`` and return that folder.

    Any previously-staged folder with the same slug is wiped first, so a
    fresh generation always overwrites its predecessor.
    """
    if not slug or "/" in slug or "\\" in slug or slug in ("..", "."):
        raise ModuleWriteError(f"Invalid slug: {slug!r}")

    target = (workspace / slug).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        raise ModuleWriteError(f"Slug {slug!r} escapes the workspace")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    (target / "__init__.py").write_text(parsed.init_py, encoding="utf-8")
    (target / "config.json").write_text(parsed.config_json, encoding="utf-8")
    _log.info("Wrote generated module to %s", target)
    return target


def copy_module_to_target(staged_folder: Path, target_modules_dir: Path) -> Path:
    """Copy a staged module folder into the InkHub ``src/modules/`` folder.

    If a folder with the same name already exists in the target it is
    overwritten. Returns the final on-disk path in the target.
    """
    if not staged_folder.is_dir():
        raise ModuleWriteError(f"Staged folder {staged_folder} does not exist")
    target_modules_dir.mkdir(parents=True, exist_ok=True)
    destination = target_modules_dir / staged_folder.name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(staged_folder, destination)
    _log.info("Copied %s -> %s", staged_folder, destination)
    return destination
