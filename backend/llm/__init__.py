"""LLM provider abstraction.

Every provider implements the :class:`LLMClient` interface. The factory
:func:`get_client` picks the right implementation based on the user's
settings. Provider SDKs are imported lazily so users only need to install
the one they've chosen.
"""

from __future__ import annotations

from .base import LLMClient, LLMError, LLMMessage, LLMResponse  # noqa: F401
from .factory import get_client  # noqa: F401
from .models import FALLBACK_MODELS, list_models  # noqa: F401
