from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.communications.models import (
        ChannelCapabilities,
        ChannelConfig,
        CommsMessage,
    )


class BaseChannelAdapter(ABC):
    """Abstract base class for all communication channel adapters."""

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """The unique type identifier for this channel (e.g., 'slack', 'discord')."""

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """Maximum message length supported by the platform."""

    @property
    @abstractmethod
    def supports_webhooks(self) -> bool:
        """Whether this adapter supports inbound webhooks."""

    @property
    @abstractmethod
    def supports_polling(self) -> bool:
        """Whether this adapter supports message polling."""

    @abstractmethod
    async def initialize(
        self, config: ChannelConfig, secret_resolver: Callable[[str], str | None]
    ) -> None:
        """Set up API clients, validate credentials."""

    @abstractmethod
    async def send_message(self, message: CommsMessage) -> str | None:
        """Send message and return platform message ID."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanly close connections."""

    @abstractmethod
    def capabilities(self) -> ChannelCapabilities:
        """Return channel capabilities."""

    @abstractmethod
    def parse_webhook(
        self, payload: dict[str, Any] | bytes, headers: dict[str, str]
    ) -> list[CommsMessage]:
        """Normalize inbound webhook payload."""

    @abstractmethod
    def verify_webhook(self, payload: bytes, headers: dict[str, str], secret: str) -> bool:
        """Verify webhook signature."""

    async def poll(self) -> list[CommsMessage]:
        """Poll for new messages (default implementation returns empty list)."""
        return []

    def chunk_message(self, content: str, max_length: int | None = None) -> list[str]:
        """Split long messages respecting word boundaries."""
        limit = max_length or self.max_message_length
        if len(content) <= limit:
            return [content]

        chunks = []
        remaining = content
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break

            # Check if we can split exactly at limit (next char is space)
            if remaining[limit] == " ":
                split_idx = limit
            else:
                # Find last space within limit
                split_idx = remaining.rfind(" ", 0, limit)
                if split_idx == -1:
                    # No space found, hard split
                    split_idx = limit

            chunk = remaining[:split_idx].rstrip()
            if chunk:
                chunks.append(chunk)

            remaining = remaining[split_idx:].lstrip()

        return chunks
