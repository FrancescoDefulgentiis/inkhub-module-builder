"""Verbatim copy of the InkHub ``Module`` ABC contract.

This file is fed to the LLM verbatim so it knows exactly what interface a
generated module must implement. Keep it in sync with ``src/module.py`` in
the main InkHub repository.
"""

from __future__ import annotations

import logging
import queue as _queue
import threading
from abc import ABC, abstractmethod
from typing import Any, Mapping

from PIL import Image

_log = logging.getLogger(__name__)


class Module(ABC):
    """Abstract base class for every InkHub module.

    A module is a small, self-contained "screen" that knows how to draw
    itself onto a Pillow image sized to the e-ink panel. It may optionally
    react to the dedicated action button or schedule its own future redraws.
    """

    name: str = ""

    def __init__(self, config: Mapping[str, Any], size: tuple[int, int]) -> None:
        self.config: Mapping[str, Any] = config or {}
        self.width, self.height = size
        self._image_queue: _queue.Queue[Image.Image] = _queue.Queue(maxsize=1)
        self._render_stop = threading.Event()
        self._render_wake = threading.Event()
        self._render_thread: threading.Thread | None = None

    @property
    def image_queue(self) -> _queue.Queue[Image.Image]:
        return self._image_queue

    def start(self) -> None:
        self._render_stop.clear()
        self._render_thread = threading.Thread(
            target=self._render_loop,
            daemon=True,
            name=f"{self.name}-render",
        )
        self._render_thread.start()

    def stop(self) -> None:
        self._render_stop.set()
        self._render_wake.set()
        if self._render_thread is not None:
            self._render_thread.join(timeout=5)
            self._render_thread = None

    def on_action_button(self) -> None:
        self._render_wake.set()

    def next_update_delay(self) -> float | None:
        """Return seconds until the next display refresh, or ``None``
        to wait until :meth:`on_action_button` is called."""
        return None

    def new_image(self, color: int = 255) -> Image.Image:
        """Create a new 1-bit image sized to the panel."""
        return Image.new("1", (self.width, self.height), color)

    @abstractmethod
    def render(self) -> Image.Image:
        """Return the next image to push to the e-ink display."""
