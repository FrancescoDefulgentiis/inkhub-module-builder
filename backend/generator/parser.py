"""Extract the ``__init__.py`` and ``config.json`` blocks from an LLM reply.

The prompt tells the model to emit exactly two fenced code blocks in a
fixed order (python then json). This parser is deliberately strict so we
can catch drift early — but forgiving enough that trailing prose or extra
blank lines don't break us.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


class ParseError(Exception):
    """Raised when the LLM reply doesn't match the expected shape."""


@dataclass
class ParsedModule:
    init_py: str
    config_json: str

    @property
    def config(self) -> dict:
        return json.loads(self.config_json)


_FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_+-]*)\s*\n(?P<body>.*?)```",
    re.DOTALL,
)


def parse_llm_output(text: str) -> ParsedModule:
    """Return the two extracted files or raise :class:`ParseError`."""
    blocks: list[tuple[str, str]] = []
    for match in _FENCE_RE.finditer(text):
        lang = (match.group("lang") or "").lower()
        body = match.group("body").rstrip() + "\n"
        blocks.append((lang, body))

    if len(blocks) < 2:
        raise ParseError(
            f"Expected at least 2 fenced code blocks (python, json); got {len(blocks)}."
        )

    python_block = next((b for lang, b in blocks if lang in ("python", "py")), None)
    json_block = next((b for lang, b in blocks if lang == "json"), None)

    # Fallback: if the model didn't label them, take the first as python and the
    # second as json in the order they appeared.
    if python_block is None and blocks:
        python_block = blocks[0][1]
    if json_block is None and len(blocks) > 1:
        json_block = blocks[1][1]

    if not python_block or not json_block:
        raise ParseError("Could not find both a python block and a json block in the response.")

    try:
        json.loads(json_block)
    except json.JSONDecodeError as exc:
        raise ParseError(f"config.json block is not valid JSON: {exc}") from exc

    return ParsedModule(init_py=python_block, config_json=json_block)
