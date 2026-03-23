from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from gobby.communications.adapters import (
    _ADAPTER_REGISTRY,
    get_adapter_class,
    list_adapter_types,
    register_adapter,
)
from gobby.communications.adapters.base import BaseChannelAdapter

if TYPE_CHECKING:
    from gobby.communications.models import (
        ChannelCapabilities,
        ChannelConfig,
        CommsMessage,
    )


class MockAdapter(BaseChannelAdapter):
    @property
    def channel_type(self) -> str:
        return "mock"

    @property
    def max_message_length(self) -> int:
        return 100

    @property
    def supports_webhooks(self) -> bool:
        return True

    @property
    def supports_polling(self) -> bool:
        return False

    async def initialize(
        self, config: ChannelConfig, secret_resolver: Callable[[str], str | None]
    ) -> None:
        pass

    async def send_message(self, message: CommsMessage) -> str | None:
        return "msg_id"

    async def shutdown(self) -> None:
        pass

    def capabilities(self) -> ChannelCapabilities:
        return MagicMock()

    def parse_webhook(
        self, payload: dict[str, Any] | bytes, headers: dict[str, str]
    ) -> list[CommsMessage]:
        return []

    def verify_webhook(self, payload: bytes, headers: dict[str, str], secret: str) -> bool:
        return True


def test_adapter_registry():
    # Clear registry for test
    original_registry = _ADAPTER_REGISTRY.copy()
    _ADAPTER_REGISTRY.clear()

    try:
        register_adapter("mock", MockAdapter)
        assert get_adapter_class("mock") == MockAdapter
        assert "mock" in list_adapter_types()
        assert get_adapter_class("nonexistent") is None
    finally:
        _ADAPTER_REGISTRY.clear()
        _ADAPTER_REGISTRY.update(original_registry)


def test_chunk_message():
    adapter = MockAdapter()

    # Test simple chunking
    content = "Hello world this is a test"
    chunks = adapter.chunk_message(content, max_length=10)
    assert chunks == ["Hello", "world this", "is a test"]

    # Test hard split
    content = "0123456789ABCDE"
    chunks = adapter.chunk_message(content, max_length=5)
    assert chunks == ["01234", "56789", "ABCDE"]

    # Test with multiple spaces
    content = "a b  c   d"
    chunks = adapter.chunk_message(content, max_length=2)
    assert chunks == ["a", "b", "c", "d"]

    # Test exactly limit
    content = "12345"
    chunks = adapter.chunk_message(content, max_length=5)
    assert chunks == ["12345"]

    # Test shorter than limit
    content = "123"
    chunks = adapter.chunk_message(content, max_length=5)
    assert chunks == ["123"]
