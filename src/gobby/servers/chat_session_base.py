"""
Protocol definition for polymorphic chat sessions.

Both ChatSession (Claude SDK) and CodexChatSession implement this
protocol, allowing the WebSocket layer to work with either type
without isinstance checks in most code paths.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from gobby.llm.claude_models import ChatEvent


@runtime_checkable
class ChatSessionProtocol(Protocol):
    """Shared interface for ChatSession and CodexChatSession."""

    # Identity
    conversation_id: str
    db_session_id: str | None
    seq_num: int | None
    project_id: str | None
    project_path: str | None
    message_index: int
    chat_mode: str
    system_prompt_override: str | None
    resume_session_id: str | None

    # Lifecycle callbacks
    _on_before_agent: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None
    _on_pre_tool: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None
    _on_post_tool: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None
    _on_pre_compact: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None
    _on_stop: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None
    _on_mode_changed: Callable[[str, str], Awaitable[None]] | None
    _on_plan_ready: Callable[[str | None, dict[str, Any]], Awaitable[None]] | None

    @property
    def is_connected(self) -> bool: ...

    @property
    def model(self) -> str | None: ...

    @property
    def has_pending_question(self) -> bool: ...

    @property
    def has_pending_approval(self) -> bool: ...

    @property
    def has_pending_plan(self) -> bool: ...

    async def start(self, model: str | None = None) -> None: ...

    async def send_message(
        self, content: str | list[dict[str, Any]]
    ) -> AsyncIterator[ChatEvent]: ...

    async def interrupt(self) -> None: ...

    async def drain_pending_response(self) -> None: ...

    async def stop(self) -> None: ...

    async def switch_model(self, new_model: str) -> None: ...

    def provide_answer(self, answers: dict[str, str]) -> None: ...

    def provide_approval(self, decision: str) -> None: ...

    def provide_plan_decision(self, decision: str) -> None: ...

    def set_chat_mode(self, mode: str) -> None: ...
