"""Wizard step definitions and answer validation.

The wizard is deliberately just a small ordered list of questions with
strong plain-English wording. Each step returns a piece of the final
answers dict that the prompt composer turns into a specification.
"""

from __future__ import annotations

import re
from typing import Any


WIZARD_STEPS: list[dict[str, Any]] = [
    {
        "id": "name",
        "title": "Give your module a name",
        "help": "A short, human name. Example: 'Room Temperature' or 'Bitcoin Ticker'.",
        "type": "text",
        "required": True,
        "max_length": 50,
    },
    {
        "id": "description",
        "title": "What should the screen show?",
        "help": (
            "Describe in plain English what you want to see. Be specific about "
            "the layout: what should be big, what should be small, and where "
            "on the screen it should sit. Example: 'A large clock in the "
            "centre, the current CPU temperature underneath, and a small "
            "date at the top.'"
        ),
        "type": "textarea",
        "required": True,
        "max_length": 2000,
    },
    {
        "id": "refresh",
        "title": "How often should it refresh?",
        "help": "Pick how often the screen should be redrawn.",
        "type": "choice",
        "required": True,
        "choices": [
            {"value": "manual", "label": "Only when I press the action button"},
            {"value": "1min", "label": "Every minute"},
            {"value": "5min", "label": "Every 5 minutes"},
            {"value": "15min", "label": "Every 15 minutes"},
            {"value": "1hour", "label": "Every hour"},
            {"value": "1day", "label": "Once a day"},
        ],
    },
    {
        "id": "data_source",
        "title": "Does it need to fetch data from the internet?",
        "help": (
            "If yes, describe where the data comes from: which website, API, "
            "or public JSON endpoint. Example: 'Fetch the current price of "
            "Bitcoin from https://api.coindesk.com/v1/bpi/currentprice.json'."
        ),
        "type": "textarea",
        "required": False,
        "max_length": 1000,
    },
    {
        "id": "action_button",
        "title": "What should the dedicated action button do?",
        "help": "The action button is a physical button that triggers your module.",
        "type": "choice",
        "required": True,
        "choices": [
            {"value": "refresh", "label": "Just refresh the screen (default)"},
            {"value": "toggle_view", "label": "Toggle between two views (describe both above)"},
            {"value": "custom", "label": "Something else (describe above)"},
        ],
    },
    {
        "id": "extra_notes",
        "title": "Anything else the AI should know?",
        "help": "Optional. Colours (remember: e-ink is black-and-white!), fonts, quirks, edge cases.",
        "type": "textarea",
        "required": False,
        "max_length": 1000,
    },
]


REFRESH_TO_SECONDS: dict[str, int | None] = {
    "manual": None,
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "1hour": 3600,
    "1day": 86400,
}


_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slugify(name: str) -> str:
    """Turn a human name into a valid Python-package-safe folder name."""
    lowered = name.strip().lower()
    slug = _SLUG_RE.sub("_", lowered).strip("_")
    if not slug:
        slug = "custom_module"
    if slug[0].isdigit():
        slug = "m_" + slug
    return slug


def validate_answers(answers: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Validate wizard answers, returning ``(cleaned, errors)``."""
    errors: list[str] = []
    cleaned: dict[str, Any] = {}
    for step in WIZARD_STEPS:
        raw = answers.get(step["id"], "")
        value = str(raw).strip() if raw is not None else ""
        if step["type"] == "choice":
            allowed = {c["value"] for c in step["choices"]}
            if value and value not in allowed:
                errors.append(f"{step['title']}: {value!r} is not a valid choice")
                continue
            if step.get("required") and not value:
                errors.append(f"{step['title']}: please pick an option")
                continue
        else:
            if step.get("required") and not value:
                errors.append(f"{step['title']}: this field is required")
                continue
            max_len = int(step.get("max_length", 5000))
            if len(value) > max_len:
                errors.append(f"{step['title']}: keep it under {max_len} characters")
                continue
        cleaned[step["id"]] = value

    if "name" in cleaned and cleaned["name"]:
        cleaned["slug"] = slugify(cleaned["name"])
    return cleaned, errors
