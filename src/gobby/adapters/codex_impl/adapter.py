"""
Codex adapter implementations.

Contains the main adapter classes for Codex CLI integration:
- CodexAdapter: Main adapter for app-server mode (programmatic control)
- CodexNotifyAdapter: Notification adapter for hook events

Extracted from codex.py as part of Phase 3 Strangler Fig decomposition.
"""

from __future__ import annotations

import glob as glob_module
import logging
import os
import platform
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.adapters.base import BaseAdapter
from gobby.adapters.codex_impl.client import (
    CODEX_SESSIONS_DIR,
    CodexAppServerClient,
)
from gobby.adapters.codex_impl.types import (
    CodexThread,
)
from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager

logger = logging.getLogger(__name__)


# =============================================================================
# Shared Utilities
# =============================================================================


def _get_machine_id() -> str:
    """Get or generate a stable machine identifier.

    Priority:
    1. Hostname (if available)
    2. MAC address (if real, not random)
    3. Persisted UUID file (created on first run)
    """
    from pathlib import Path

    # Try hostname first
    node = platform.node()
    if node:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, node))

    # Try MAC address - getnode() returns random value with multicast bit set if unavailable
    mac = uuid.getnode()
    # Check if MAC is real (multicast bit / bit 0 of first octet is 0)
    if not (mac >> 40) & 1:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(mac)))

    # Fall back to persisted ID file for stability across restarts
    machine_id_file = Path.home() / ".gobby" / ".machine_id"
    try:
        if machine_id_file.exists():
            stored_id = machine_id_file.read_text().strip()
            if stored_id:
                return stored_id
    except OSError:
        pass  # Fall through to generate new ID

    # Generate and persist a new ID
    new_id = str(uuid.uuid4())
    try:
        machine_id_file.parent.mkdir(parents=True, exist_ok=True)
        machine_id_file.write_text(new_id)
    except OSError:
        pass  # Use the generated ID even if we can't persist it

    return new_id


# =============================================================================
# App-Server Adapter (for programmatic control)
# =============================================================================


class CodexAdapter(BaseAdapter):
    """Adapter for Codex CLI session tracking via app-server events.

    This adapter translates Codex app-server events to unified HookEvent
    for session tracking. It can operate in two modes:

    1. Integrated mode (recommended): Attach to existing CodexAppServerClient
       - Call attach_to_client(codex_client) with the existing client
       - Events are forwarded from the client's notification handlers

    2. Standalone mode: Use without CodexAppServerClient
       - Only provides translation methods for events received externally
       - No subprocess management (use CodexAppServerClient for that)

    Lifecycle (integrated mode):
    - attach_to_client(codex_client) registers notification handlers
    - Events processed through HookManager for session registration
    - detach_from_client() removes handlers
    """

    source = SessionSource.CODEX

    # Event type mapping: Codex app-server methods -> unified HookEventType
    EVENT_MAP: dict[str, HookEventType] = {
        "thread/started": HookEventType.SESSION_START,
        "thread/archive": HookEventType.SESSION_END,
        "turn/started": HookEventType.BEFORE_AGENT,
        "turn/completed": HookEventType.AFTER_AGENT,
        # Approval requests map to BEFORE_TOOL
        "item/commandExecution/requestApproval": HookEventType.BEFORE_TOOL,
        "item/fileChange/requestApproval": HookEventType.BEFORE_TOOL,
        # Completed items map to AFTER_TOOL
        "item/completed": HookEventType.AFTER_TOOL,
    }

    # Tool name mapping: Codex tool names -> canonical CC-style names
    # Codex uses different tool names - normalize to Claude Code conventions
    # so block_tools rules work across CLIs
    TOOL_MAP: dict[str, str] = {
        # File operations
        "read_file": "Read",
        "ReadFile": "Read",
        "write_file": "Write",
        "WriteFile": "Write",
        "edit_file": "Edit",
        "EditFile": "Edit",
        # Shell
        "run_shell_command": "Bash",
        "RunShellCommand": "Bash",
        "commandExecution": "Bash",
        # Search
        "glob": "Glob",
        "grep": "Grep",
        "GlobTool": "Glob",
        "GrepTool": "Grep",
    }

    # Item types that represent tool operations
    TOOL_ITEM_TYPES = {"commandExecution", "fileChange", "mcpToolCall"}

    # Events we want to listen for session tracking
    SESSION_TRACKING_EVENTS = [
        "thread/started",
        "turn/started",
        "turn/completed",
        "item/completed",
    ]

    def __init__(self, hook_manager: HookManager | None = None):
        """Initialize the Codex adapter.

        Args:
            hook_manager: Reference to HookManager for event processing.
        """
        self._hook_manager = hook_manager
        self._codex_client: CodexAppServerClient | None = None
        self._machine_id: str | None = None
        self._attached = False

    @staticmethod
    def is_codex_available() -> bool:
        """Check if Codex CLI is installed and available.

        Returns:
            True if `codex` command is found in PATH.
        """
        import shutil

        return shutil.which("codex") is not None

    def _get_machine_id(self) -> str:
        """Get or generate a machine identifier."""
        if self._machine_id is None:
            self._machine_id = _get_machine_id()
        return self._machine_id

    def normalize_tool_name(self, codex_tool_name: str) -> str:
        """Normalize Codex tool name to canonical CC-style format.

        This ensures block_tools rules work consistently across CLIs.

        Args:
            codex_tool_name: Tool name from Codex CLI.

        Returns:
            Normalized tool name (e.g., "Bash", "Read", "Write", "Edit").
        """
        return self.TOOL_MAP.get(codex_tool_name, codex_tool_name)

    def attach_to_client(self, codex_client: CodexAppServerClient) -> None:
        """Attach to an existing CodexAppServerClient for event handling.

        Registers notification handlers on the client to receive session
        tracking events. This is the preferred integration mode.

        Args:
            codex_client: The CodexAppServerClient to attach to.
        """
        if self._attached:
            logger.warning("CodexAdapter already attached to a client")
            return

        self._codex_client = codex_client

        # Register handlers for session tracking events
        for method in self.SESSION_TRACKING_EVENTS:
            codex_client.add_notification_handler(method, self._handle_notification)

        self._attached = True
        logger.debug("CodexAdapter attached to CodexAppServerClient")

    def detach_from_client(self) -> None:
        """Detach from the CodexAppServerClient.

        Removes notification handlers. Call this before disposing the adapter.
        """
        if not self._attached or not self._codex_client:
            return

        # Remove handlers
        for method in self.SESSION_TRACKING_EVENTS:
            self._codex_client.remove_notification_handler(method, self._handle_notification)

        self._codex_client = None
        self._attached = False
        logger.debug("CodexAdapter detached from CodexAppServerClient")

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle notification from CodexAppServerClient.

        This is the callback registered with the client for session tracking events.
        """
        try:
            hook_event = self.translate_to_hook_event({"method": method, "params": params})

            if hook_event and self._hook_manager:
                # Process through HookManager (fire-and-forget for notifications)
                self._hook_manager.handle(hook_event)
                logger.debug(f"Processed Codex event: {method} -> {hook_event.event_type}")
        except Exception as e:
            logger.error(f"Error handling Codex notification {method}: {e}")

    def _translate_approval_event(self, method: str, params: dict[str, Any]) -> HookEvent | None:
        """Translate approval request to HookEvent."""
        if method not in self.EVENT_MAP:
            logger.debug(f"Unknown approval method: {method}")
            return None

        thread_id = params.get("threadId", "")
        item_id = params.get("itemId", "")

        # Determine tool name from method and normalize to CC-style
        if "commandExecution" in method:
            original_tool = "commandExecution"
            tool_name = self.normalize_tool_name(original_tool)  # -> "Bash"
            tool_input = params.get("parsedCmd", params.get("command", ""))
        elif "fileChange" in method:
            original_tool = "fileChange"
            tool_name = "Write"  # File changes are writes
            tool_input = params.get("changes", [])
        else:
            original_tool = "unknown"
            tool_name = "unknown"
            tool_input = params

        return HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id=thread_id,
            source=self.source,
            timestamp=datetime.now(UTC),
            machine_id=self._get_machine_id(),
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "item_id": item_id,
                "turn_id": params.get("turnId", ""),
                "reason": params.get("reason"),
                "risk": params.get("risk"),
            },
            metadata={
                "requires_response": True,
                "item_id": item_id,
                "approval_method": method,
                "original_tool_name": original_tool,
                "normalized_tool_name": tool_name,
            },
        )

    def translate_to_hook_event(self, native_event: dict[str, Any]) -> HookEvent | None:
        """Convert Codex app-server event to unified HookEvent.

        Codex events come as JSON-RPC notifications:
        {
            "method": "thread/started",
            "params": {
                "thread": {"id": "thr_123", "preview": "...", ...}
            }
        }

        Args:
            native_event: JSON-RPC notification with method and params.

        Returns:
            Unified HookEvent, or None for unsupported events.
        """
        method = native_event.get("method", "")
        params = native_event.get("params", {})

        # Handle different event types
        if method == "thread/started":
            thread = params.get("thread", {})
            return HookEvent(
                event_type=HookEventType.SESSION_START,
                session_id=thread.get("id", ""),
                source=self.source,
                timestamp=self._parse_timestamp(thread.get("createdAt")),
                machine_id=self._get_machine_id(),
                data={
                    "preview": thread.get("preview", ""),
                    "model_provider": thread.get("modelProvider", ""),
                },
            )

        if method == "thread/archive":
            return HookEvent(
                event_type=HookEventType.SESSION_END,
                session_id=params.get("threadId", ""),
                source=self.source,
                timestamp=datetime.now(UTC),
                machine_id=self._get_machine_id(),
                data=params,
            )

        if method == "turn/started":
            turn = params.get("turn", {})
            return HookEvent(
                event_type=HookEventType.BEFORE_AGENT,
                session_id=params.get("threadId", turn.get("id", "")),
                source=self.source,
                timestamp=datetime.now(UTC),
                machine_id=self._get_machine_id(),
                data={
                    "turn_id": turn.get("id", ""),
                    "status": turn.get("status", ""),
                },
            )

        if method == "turn/completed":
            turn = params.get("turn", {})
            return HookEvent(
                event_type=HookEventType.AFTER_AGENT,
                session_id=params.get("threadId", turn.get("id", "")),
                source=self.source,
                timestamp=datetime.now(UTC),
                machine_id=self._get_machine_id(),
                data={
                    "turn_id": turn.get("id", ""),
                    "status": turn.get("status", ""),
                    "error": turn.get("error"),
                },
            )

        if method == "item/completed":
            item = params.get("item", {})
            item_type = item.get("type", "")

            # Only translate tool-related items
            if item_type in self.TOOL_ITEM_TYPES:
                return HookEvent(
                    event_type=HookEventType.AFTER_TOOL,
                    session_id=params.get("threadId", ""),
                    source=self.source,
                    timestamp=datetime.now(UTC),
                    machine_id=self._get_machine_id(),
                    data={
                        "item_id": item.get("id", ""),
                        "item_type": item_type,
                        "status": item.get("status", ""),
                    },
                )

        # Unknown/unsupported event
        logger.debug(f"Unsupported Codex event: {method}")
        return None

    def translate_from_hook_response(
        self, response: HookResponse, hook_type: str | None = None
    ) -> dict[str, Any]:
        """Convert HookResponse to Codex approval response format.

        Codex expects approval responses as:
        {
            "decision": "accept" | "decline"
        }

        Args:
            response: Unified HookResponse.
            hook_type: Original Codex method (unused, kept for interface).

        Returns:
            Dict with decision field.
        """
        return {
            "decision": "accept" if response.decision != "deny" else "decline",
        }

    def _parse_timestamp(self, unix_ts: int | float | None) -> datetime:
        """Parse Unix timestamp to datetime.

        Args:
            unix_ts: Unix timestamp (seconds).

        Returns:
            Timezone-aware datetime object, or now(UTC) if parsing fails.
        """
        if unix_ts:
            try:
                return datetime.fromtimestamp(unix_ts, tz=UTC)
            except (ValueError, OSError):
                pass
        return datetime.now(UTC)

    async def sync_existing_sessions(self) -> int:
        """Sync existing Codex threads to platform sessions.

        Uses the attached CodexAppServerClient to list threads and registers
        them as sessions via HookManager.

        Requires:
        - CodexAdapter attached to a CodexAppServerClient
        - CodexAppServerClient is connected
        - HookManager is set

        Returns:
            Number of threads synced.
        """
        if not self._hook_manager:
            logger.warning("No hook_manager - cannot sync sessions")
            return 0

        if not self._codex_client:
            logger.warning("No CodexAppServerClient attached - cannot sync sessions")
            return 0

        if not self._codex_client.is_connected:
            logger.warning("CodexAppServerClient not connected - cannot sync sessions")
            return 0

        try:
            # Use CodexAppServerClient to list threads
            all_threads: list[CodexThread] = []
            cursor = None

            while True:
                threads, next_cursor = await self._codex_client.list_threads(
                    cursor=cursor, limit=100
                )
                all_threads.extend(threads)

                if not next_cursor:
                    break
                cursor = next_cursor

            synced = 0
            for thread in all_threads:
                try:
                    event = HookEvent(
                        event_type=HookEventType.SESSION_START,
                        session_id=thread.id,
                        source=self.source,
                        timestamp=self._parse_timestamp(thread.created_at),
                        machine_id=self._get_machine_id(),
                        data={
                            "preview": thread.preview,
                            "model_provider": thread.model_provider,
                            "synced_from_existing": True,
                        },
                    )
                    self._hook_manager.handle(event)
                    synced += 1
                except Exception as e:
                    logger.error(f"Failed to sync thread {thread.id}: {e}")

            logger.debug(f"Synced {synced} existing Codex threads")
            return synced

        except Exception as e:
            logger.error(f"Failed to sync existing sessions: {e}")
            return 0


# =============================================================================
# Notify Adapter (for installed hooks via `gobby install --codex`)
# =============================================================================


class CodexNotifyAdapter(BaseAdapter):
    """Adapter for Codex CLI notify events.

    Translates notify payloads to unified HookEvent format.
    The notify hook only fires on `agent-turn-complete`, so we:
    - Treat first event for a thread as session start + prompt submit
    - Track thread IDs to avoid duplicate session registration

    This adapter handles events from the hook_dispatcher.py script installed
    by `gobby install --codex`.
    """

    source = SessionSource.CODEX

    # Default max size for seen threads cache
    DEFAULT_MAX_SEEN_THREADS = 1000

    def __init__(
        self,
        hook_manager: HookManager | None = None,
        max_seen_threads: int | None = None,
    ):
        """Initialize the adapter.

        Args:
            hook_manager: Optional HookManager reference.
            max_seen_threads: Max threads to track (default 1000). Oldest evicted when full.
        """
        self._hook_manager = hook_manager
        self._machine_id: str | None = None
        # Track threads we've seen using LRU cache to avoid unbounded growth
        self._max_seen_threads = max_seen_threads or self.DEFAULT_MAX_SEEN_THREADS
        self._seen_threads: OrderedDict[str, bool] = OrderedDict()

    def _get_machine_id(self) -> str:
        """Get or generate a machine identifier."""
        if self._machine_id is None:
            self._machine_id = _get_machine_id()
        return self._machine_id

    def _mark_thread_seen(self, thread_id: str) -> None:
        """Mark a thread as seen, evicting oldest if cache is full.

        Args:
            thread_id: The thread ID to mark as seen.
        """
        # If already present, move to end (most recent)
        if thread_id in self._seen_threads:
            self._seen_threads.move_to_end(thread_id)
            return

        # Evict oldest entries if at capacity
        while len(self._seen_threads) >= self._max_seen_threads:
            self._seen_threads.popitem(last=False)

        self._seen_threads[thread_id] = True

    def clear_seen_threads(self) -> int:
        """Clear the seen threads cache.

        Returns:
            Number of entries cleared.
        """
        count = len(self._seen_threads)
        self._seen_threads.clear()
        return count

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
        # Escape special glob characters in thread_id
        safe_thread_id = glob_module.escape(thread_id)
        pattern = str(CODEX_SESSIONS_DIR / "**" / f"*{safe_thread_id}.jsonl")
        matches = glob_module.glob(pattern, recursive=True)

        if matches:
            # Return the most recent match (in case of duplicates)
            return max(matches, key=os.path.getmtime)
        return None

    def _get_first_prompt(self, input_messages: list[Any]) -> str | None:
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

    def translate_to_hook_event(self, native_event: dict[str, Any]) -> HookEvent | None:
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
            self._mark_thread_seen(thread_id)

        # Get first prompt for title synthesis (only on first event)
        first_prompt = self._get_first_prompt(input_messages) if is_first_event else None

        # All Codex notify events are AFTER_AGENT (turn complete)
        # The HookManager will auto-register the session if it doesn't exist
        return HookEvent(
            event_type=HookEventType.AFTER_AGENT,
            session_id=thread_id,
            source=self.source,
            timestamp=datetime.now(UTC),
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
    ) -> dict[str, Any]:
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
        self, native_event: dict[str, Any], hook_manager: HookManager
    ) -> dict[str, Any]:
        """Process native Codex notify event.

        Args:
            native_event: The payload from HTTP endpoint.
            hook_manager: HookManager instance for processing.

        Returns:
            Response dict.
        """
        hook_event = self.translate_to_hook_event(native_event)
        if not hook_event:
            return {"status": "skipped", "message": "Unsupported event"}

        hook_response = hook_manager.handle(hook_event)
        return self.translate_from_hook_response(hook_response)


__all__ = [
    "_get_machine_id",
    "CodexAdapter",
    "CodexNotifyAdapter",
]
