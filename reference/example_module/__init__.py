"""Hello World — a minimal InkHub module used as a reference example.

Shows two lines of centred text: a greeting from ``config.json`` and the
current time. Refreshes once every 60 seconds.
"""

from __future__ import annotations

import logging
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from ...module import Module
from ...registry import register_module

_log = logging.getLogger(__name__)


@register_module("hello_world")
class HelloWorldModule(Module):
    def __init__(self, config, size):
        super().__init__(config, size)
        self._greeting: str = str(self.config.get("greeting", "Hello, InkHub!"))
        self._refresh_seconds: int = int(self.config.get("refresh_seconds", 60))

    def next_update_delay(self) -> float | None:
        return float(self._refresh_seconds)

    def render(self) -> Image.Image:
        image = self.new_image(color=255)  # white background
        draw = ImageDraw.Draw(image)

        try:
            big = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
            small = ImageFont.truetype("DejaVuSans.ttf", 24)
        except OSError:
            big = ImageFont.load_default()
            small = ImageFont.load_default()

        now_text = datetime.now().strftime("%H:%M:%S")

        w1, h1 = draw.textbbox((0, 0), self._greeting, font=big)[2:]
        w2, h2 = draw.textbbox((0, 0), now_text, font=small)[2:]

        draw.text(
            ((self.width - w1) / 2, (self.height / 2) - h1),
            self._greeting,
            fill=0,
            font=big,
        )
        draw.text(
            ((self.width - w2) / 2, (self.height / 2) + 10),
            now_text,
            fill=0,
            font=small,
        )
        return image
