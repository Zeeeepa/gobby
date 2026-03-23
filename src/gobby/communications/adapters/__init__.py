from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.communications.adapters.base import BaseChannelAdapter

_ADAPTER_REGISTRY: dict[str, type[BaseChannelAdapter]] = {}


def register_adapter(channel_type: str, adapter_class: type[BaseChannelAdapter]) -> None:
    """Register an adapter class for a channel type."""
    _ADAPTER_REGISTRY[channel_type] = adapter_class


def get_adapter_class(channel_type: str) -> type[BaseChannelAdapter] | None:
    """Get the adapter class for a channel type."""
    return _ADAPTER_REGISTRY.get(channel_type)


def list_adapter_types() -> list[str]:
    """List all registered adapter types."""
    return sorted(_ADAPTER_REGISTRY.keys())
