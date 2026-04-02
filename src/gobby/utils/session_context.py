"""Session context utilities for MCP tool calls.

Provides a per-async-task ContextVar that holds the calling session's identity.
Set by dispatch paths (HTTP routes, FastMCP, rule engine, pipeline executor)
before tool execution begins. Tools read via get_current_session_id() instead
of accepting session_id as a parameter.

Mirrors the pattern in project_context.py.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionContext:
    """Immutable snapshot of the calling session's identity.

    Intentionally minimal — sessions are mutable, so tools that need the full
    session object should call session_manager.get(session_id) using the UUID
    from this context.
    """

    session_id: str
    """Always a resolved UUID (never #N or seq_num)."""

    conversation_id: str | None = None
    """External/CLI-specific session ID (e.g., Claude Code conversation ID)."""


_current_session_context: contextvars.ContextVar[SessionContext | None] = contextvars.ContextVar(
    "current_session_context", default=None
)


def set_session_context(ctx: SessionContext | None) -> contextvars.Token[SessionContext | None]:
    """Set session context for the current async task.

    Called by dispatch paths before tool execution. Returns a token
    for reset via reset_session_context().
    """
    return _current_session_context.set(ctx)


def get_session_context() -> SessionContext | None:
    """Get the current session context, or None if not set."""
    return _current_session_context.get()


def get_current_session_id() -> str | None:
    """Convenience: get the current session UUID, or None if not set."""
    ctx = _current_session_context.get()
    return ctx.session_id if ctx else None


def reset_session_context(token: contextvars.Token[SessionContext | None]) -> None:
    """Reset session context after tool call completes."""
    _current_session_context.reset(token)


def resolve_session_ref(
    session_manager: Any,
    ref: str,
) -> str:
    """Resolve a session reference (#N, N, UUID, or prefix) to UUID.

    Uses the current project context from ContextVar for scoping.
    Shared utility replacing duplicated closures in cross-session tools.

    Args:
        session_manager: LocalSessionManager instance
        ref: Session reference string

    Returns:
        Resolved UUID string

    Raises:
        ValueError: If session cannot be resolved
    """
    if session_manager is None:
        return ref
    from gobby.utils.project_context import get_project_context

    project_ctx = get_project_context()
    project_id = project_ctx.get("id") if project_ctx else None
    return str(session_manager.resolve_session_reference(ref, project_id))


@contextmanager
def session_context_for_test(
    session_id: str = "test-session-id",
    conversation_id: str | None = None,
) -> Any:
    """Context manager for tests that need session context.

    Usage::

        with session_context_for_test("my-session-uuid"):
            result = await registry.call("create_task", {...})
    """
    ctx = SessionContext(session_id=session_id, conversation_id=conversation_id)
    token = set_session_context(ctx)
    try:
        yield ctx
    finally:
        reset_session_context(token)
