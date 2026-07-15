"""Common types and the LLMClient interface every provider implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


class LLMError(Exception):
    """Raised when a provider call fails (network, auth, invalid model, ...)."""


Role = Literal["system", "user", "assistant"]


@dataclass
class LLMMessage:
    role: Role
    content: str


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str


class LLMClient(ABC):
    """Minimal chat interface — one method, one call, one string back."""

    provider_name: str = ""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LLMError(f"{self.provider_name}: missing API key")
        if not model:
            raise LLMError(f"{self.provider_name}: missing model name")
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def chat(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResponse:
        """Send a chat conversation and return the assistant's reply."""
