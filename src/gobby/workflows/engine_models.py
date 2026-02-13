"""Data models for the workflow engine.

Extracted from engine.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class DotDict(dict[str, Any]):
    """Dict subclass that supports both dot-notation and .get() access.

    SimpleNamespace supports dot-notation but not .get(), which breaks
    workflow transition conditions that use ``variables.get('key')``.
    DotDict supports both patterns.
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


@dataclass
class TransitionResult:
    """Result of a workflow step transition.

    Carries both LLM-facing context (injected_messages) and user-visible
    output (system_messages) through transition chains.
    """

    injected_messages: list[str] = field(default_factory=list)
    system_messages: list[str] = field(default_factory=list)

    def extend(self, other: TransitionResult) -> None:
        """Accumulate messages from another transition result."""
        self.injected_messages.extend(other.injected_messages)
        self.system_messages.extend(other.system_messages)
