"""Codex Notify adapter for CLI hook translation.

This adapter handles events from Codex CLI's `notify` configuration option.
Unlike the CodexAdapter (which handles app-server JSON-RPC events), this
adapter processes the simpler notify payload format.

Codex notify currently only fires on `agent-turn-complete` events.
We use the first event to register the session, and subsequent events
to track activity.
"""

import glob
import logging
import os
import platform
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from gobby.adapters.base import BaseAdapter
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager

logger = logging.getLogger(__name__)

# Codex session storage location
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


class CodexNotifyAdapter(BaseAdapter):
    """Adapter for Codex CLI notify events.

    Translates notify payloads to unified HookEvent format.
    The notify hook only fires on `agent-turn-complete`, so we:
    - Treat first event for a thread as session start + prompt submit
    - Track thread IDs to avoid duplicate session registration
    """

    source = SessionSource.CODEX

    # Track threads we've seen to avoid re-registering
    _seen_threads: set[str] = set()

    def __init__(self, hook_manager: "HookManager | None" = None):
        """Initialize the adapter.

        Args:
            hook_manager: Optional HookManager reference.
        """
        self._hook_manager = hook_manager
        self._machine_id: str | None = None

    def _get_machine_id(self) -> str:
        """Get or generate a machine identifier."""
        if self._machine_id is None:
            node = platform.node()
            if node:
                self._machine_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, node))
            else:
                self._machine_id = str(uuid.uuid4())
        return self._machine_id

    def _find_jsonl_path(self, thread_id: str) -> str | None:
        """Find the Codex session JSONL file for a thread.

        Codex stores sessions at: ~/.codex/sessions/YYYY/MM/DD/rollout-{timestamp}-{thread-id}.jsonl

        Args:
            thread_id: The Codex thread ID

        Returns:
            Path to the JSONL file, or None if not found
        """
        if not CODEX_SESSIONS_DIR.exists():
            return None

        # Search for file ending with thread-id.jsonl
        pattern = str(CODEX_SESSIONS_DIR / "**" / f"*{thread_id}.jsonl")
        matches = glob.glob(pattern, recursive=True)

        if matches:
            # Return the most recent match (in case of duplicates)
            return max(matches, key=os.path.getmtime)
        return None

    def _get_first_prompt(self, input_messages: list) -> str | None:
        """Extract the first user prompt from input_messages.

        Args:
            input_messages: List of user messages from Codex

        Returns:
            First prompt string, or None
        """
        if input_messages and isinstance(input_messages, list) and len(input_messages) > 0:
            first = input_messages[0]
            if isinstance(first, str):
                return first
            elif isinstance(first, dict):
                return first.get("text") or first.get("content")
        return None

    def translate_to_hook_event(self, native_event: dict) -> HookEvent | None:
        """Convert Codex notify payload to HookEvent.

        The native_event structure from /hooks/execute:
        {
            "hook_type": "AgentTurnComplete",
            "input_data": {
                "session_id": "thread-id",
                "event_type": "agent-turn-complete",
                "last_message": "...",
                "input_messages": [...],
                "cwd": "/path/to/project",
                "turn_id": "1"
            },
            "source": "codex"
        }

        Args:
            native_event: The payload from the HTTP endpoint.

        Returns:
            HookEvent for processing, or None if unsupported.
        """
        input_data = native_event.get("input_data", {})
        thread_id = input_data.get("session_id", "")
        event_type = input_data.get("event_type", "unknown")
        input_messages = input_data.get("input_messages", [])
        cwd = input_data.get("cwd") or os.getcwd()

        if not thread_id:
            logger.warning("Codex notify event missing thread_id")
            return None

        # Find the JSONL transcript file
        jsonl_path = self._find_jsonl_path(thread_id)

        # Track if this is the first event for this thread (for title synthesis)
        is_first_event = thread_id not in self._seen_threads
        if is_first_event:
            self._seen_threads.add(thread_id)

        # Get first prompt for title synthesis (only on first event)
        first_prompt = self._get_first_prompt(input_messages) if is_first_event else None

        # All Codex notify events are AFTER_AGENT (turn complete)
        # The HookManager will auto-register the session if it doesn't exist
        return HookEvent(
            event_type=HookEventType.AFTER_AGENT,
            session_id=thread_id,
            source=self.source,
            timestamp=datetime.now(),
            machine_id=self._get_machine_id(),
            data={
                "cwd": cwd,
                "event_type": event_type,
                "last_message": input_data.get("last_message", ""),
                "input_messages": input_messages,
                "transcript_path": jsonl_path,
                "is_first_event": is_first_event,
                "prompt": first_prompt,  # For title synthesis on first event
            },
        )

    def translate_from_hook_response(
        self, response: HookResponse, hook_type: str | None = None
    ) -> dict:
        """Convert HookResponse to Codex-expected format.

        Codex notify doesn't expect a response - it's fire-and-forget.
        This just returns a simple status dict for logging.

        Args:
            response: The HookResponse from HookManager.
            hook_type: Ignored (notify doesn't need response routing).

        Returns:
            Simple status dict.
        """
        return {
            "status": "processed",
            "decision": response.decision,
        }

    def handle_native(
        self, native_event: dict, hook_manager: "HookManager | None" = None
    ) -> dict:
        """Process native Codex notify event.

        Args:
            native_event: The payload from HTTP endpoint.
            hook_manager: Optional HookManager (uses instance if not provided).

        Returns:
            Response dict.
        """
        manager = hook_manager or self._hook_manager
        if not manager:
            logger.warning("No HookManager available for Codex notify event")
            return {"status": "error", "message": "No HookManager"}

        hook_event = self.translate_to_hook_event(native_event)
        if not hook_event:
            return {"status": "skipped", "message": "Unsupported event"}

        hook_response = manager.handle(hook_event)
        return self.translate_from_hook_response(hook_response)
