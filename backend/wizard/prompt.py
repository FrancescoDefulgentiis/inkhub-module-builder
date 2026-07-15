"""Compose the LLM system + user prompts from wizard answers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import REFRESH_TO_SECONDS

_REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"


def _read(rel: str) -> str:
    return (_REFERENCE_DIR / rel).read_text(encoding="utf-8")


SYSTEM_PROMPT_TEMPLATE = """\
You generate Python source code for **InkHub**, a modular e-ink dashboard.

Your job: produce **one** new InkHub module, from a plain-English brief given \
by a non-technical user. Your output will be dropped verbatim into \
`inkHub/src/modules/<slug>/`.

## The Module contract you MUST implement

Below is the exact abstract base class every InkHub module must subclass. \
Read it carefully — signatures, imports, and behaviour must match.

```python
{module_abc}
```

## A canonical minimal example

Structurally mimic this "hello world" module. It uses relative imports \
(`from ...module import Module`, `from ...registry import register_module`) \
because your file will live at `inkHub/src/modules/<slug>/__init__.py`.

```python
{example_module}
```

Its `config.json` sits next to `__init__.py`:

```json
{example_config}
```

## Hard rules for your output

1. Output **exactly two fenced code blocks**, in this exact order:
   - First: a ```python``` block containing the full `__init__.py` file.
   - Second: a ```json``` block containing the full `config.json` file.
2. Do **not** add any prose, headings, or comments outside those two blocks.
3. Use the same relative imports as the example: \
`from ...module import Module` and `from ...registry import register_module`.
4. Register the module with `@register_module("<slug>")` where `<slug>` \
matches the wizard's slug exactly.
5. The class must subclass `Module` and implement `render(self) -> Image.Image`.
6. The image returned by `render()` MUST be a `PIL.Image.Image` sized \
exactly `(self.width, self.height)` in mode `"1"` (1-bit black and white).
7. All customisable values (URLs, cities, refresh interval, text strings, \
API keys) MUST be read from `self.config`, with sensible defaults if a key \
is missing. Their initial values go into `config.json`.
8. If the module fetches from the network, use `requests` with a 15-second \
timeout, catch exceptions, and render a graceful fallback screen — never \
let `render()` raise.
9. e-ink is grayscale/monochrome. Only use fill values `0` (black) and \
`255` (white). Never use colours.
10. Fonts: try `ImageFont.truetype("DejaVuSans.ttf", ...)` first, fall back \
to `ImageFont.load_default()` on `OSError` — the target device may not have \
the font installed.
11. Keep the code self-contained: only stdlib, `Pillow`, and `requests`. \
Do NOT add other dependencies.
12. Set `next_update_delay()` to the refresh cadence in seconds (or return \
`None` for manual-only refresh).
13. Override `on_action_button()` if the wizard asked for special behaviour \
— always end that override with `super().on_action_button()` so the display \
still wakes.
"""


USER_PROMPT_TEMPLATE = """\
Build me an InkHub module with the following brief.

- Slug (folder + registration name): `{slug}`
- Human name: {name}
- Target panel size: {width}x{height} pixels, 1-bit black-and-white

What the screen should show:
{description}

Refresh cadence: {refresh_human} (next_update_delay should return {refresh_seconds_repr})

Data source:
{data_source_or_none}

Action button behaviour: {action_button_human}
{action_button_extra}

Extra notes from the user:
{extra_notes_or_none}

Respond with the two code blocks (python then json) as specified. \
Nothing else.
"""


FIX_PROMPT_TEMPLATE = """\
Your previous module failed validation. Here is the error and traceback \
produced when we imported/instantiated your code and called `render()`:

```
{error}
```

Fix the bug and resend the two code blocks (python then json). Do not \
change the slug (`{slug}`). Keep everything else that was working. Do not \
apologise or add prose — just the two code blocks.
"""


_REFRESH_LABELS = {
    "manual": "only when the action button is pressed",
    "1min": "every minute",
    "5min": "every 5 minutes",
    "15min": "every 15 minutes",
    "1hour": "every hour",
    "1day": "once a day",
}

_ACTION_LABELS = {
    "refresh": "just refresh the screen (default behaviour)",
    "toggle_view": "toggle between two views described in the brief",
    "custom": "custom behaviour described in the brief",
}


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        module_abc=_read("module_abc.py").strip(),
        example_module=_read("example_module/__init__.py").strip(),
        example_config=_read("example_module/config.json").strip(),
    )


def build_user_prompt(answers: dict[str, Any], panel_size: tuple[int, int]) -> str:
    refresh_key = answers.get("refresh", "manual")
    refresh_seconds = REFRESH_TO_SECONDS.get(refresh_key)
    refresh_repr = "None" if refresh_seconds is None else f"{refresh_seconds}.0"
    action_key = answers.get("action_button", "refresh")
    return USER_PROMPT_TEMPLATE.format(
        slug=answers["slug"],
        name=answers.get("name", ""),
        width=panel_size[0],
        height=panel_size[1],
        description=answers.get("description", "").strip() or "(none provided)",
        refresh_human=_REFRESH_LABELS.get(refresh_key, refresh_key),
        refresh_seconds_repr=refresh_repr,
        data_source_or_none=answers.get("data_source", "").strip() or "(none — module does not fetch data)",
        action_button_human=_ACTION_LABELS.get(action_key, action_key),
        action_button_extra=(
            "The wizard notes describe the exact behaviour."
            if action_key in ("toggle_view", "custom") else ""
        ),
        extra_notes_or_none=answers.get("extra_notes", "").strip() or "(none)",
    )


def build_fix_prompt(error: str, slug: str) -> str:
    return FIX_PROMPT_TEMPLATE.format(error=error.strip(), slug=slug)
