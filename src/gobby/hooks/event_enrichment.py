"""Response metadata enrichment for hook events.

EventEnricher copies session metadata, terminal context, and workflow context
from the hook event into the response for adapter injection.
Extracted from HookManager.handle() as part of the Strangler Fig decomposition.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from gobby.hooks.events import HookEvent, HookResponse

# Terminal context keys copied from event metadata to response metadata
TERMINAL_CONTEXT_KEYS = [
    "terminal_term_program",
    "terminal_tty",
    "terminal_parent_pid",
    "terminal_iterm_session_id",
    "terminal_term_session_id",
    "terminal_kitty_window_id",
    "terminal_tmux_pane",
    "terminal_vscode_terminal_id",
    "terminal_alacritty_socket",
]


class EventEnricher:
    """Enriches hook responses with session metadata and context.

    Copies platform session ID, external ID, machine ID, project ID,
    terminal context, and workflow context from the event into the response.
    Tracks first-hook-per-session for token optimization.
    """

    def __init__(
        self,
        session_storage: Any,  # Avoid runtime import of LocalSessionManager
        injected_sessions: set[str],
    ):
        self._session_storage = session_storage
        self._injected_sessions = injected_sessions

    def enrich(
        self,
        event: HookEvent,
        response: HookResponse,
        workflow_context: str | None = None,
    ) -> None:
        """Enrich response with session metadata and context.

        Copies session metadata from event to response for adapter injection.
        The adapter reads response.metadata to inject session info into agent context.

        Args:
            event: Source hook event with metadata
            response: Response to enrich (modified in place)
            workflow_context: Optional workflow context to merge into response
        """
        # Copy session metadata
        if event.metadata.get("_platform_session_id"):
            platform_session_id: str = event.metadata["_platform_session_id"]
            response.metadata["session_id"] = platform_session_id

            # Look up seq_num for session_ref (#N format)
            # Guard with try/except: during shutdown the DB may already be closed
            if self._session_storage:
                try:
                    session_obj = self._session_storage.get(platform_session_id)
                except Exception:
                    session_obj = None
                if session_obj and session_obj.seq_num:
                    response.metadata["session_ref"] = f"#{session_obj.seq_num}"

            # Track first hook per session for token optimization
            # Adapters use this flag to inject full metadata only on first hook
            session_key = f"{platform_session_id}:{event.source.value}"
            is_first = session_key not in self._injected_sessions
            if is_first:
                self._injected_sessions.add(session_key)
            response.metadata["_first_hook_for_session"] = is_first

        if event.session_id:  # external_id (e.g., Claude Code's session UUID)
            response.metadata["external_id"] = event.session_id
        if event.machine_id:
            response.metadata["machine_id"] = event.machine_id
        if event.project_id:
            response.metadata["project_id"] = event.project_id

        # Copy terminal context if present
        for key in TERMINAL_CONTEXT_KEYS:
            if event.metadata.get(key):
                response.metadata[key] = event.metadata[key]

        # Merge workflow context if present
        if workflow_context:
            if response.context:
                response.context = f"{response.context}\n\n{workflow_context}"
            else:
                response.context = workflow_context
