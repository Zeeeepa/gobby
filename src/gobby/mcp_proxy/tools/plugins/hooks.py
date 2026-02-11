"""Hook handler inspection and testing tools."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, SessionSource

if TYPE_CHECKING:
    from gobby.hooks.hook_manager import HookManager
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry

logger = logging.getLogger(__name__)


def register_hook_tools(
    registry: InternalToolRegistry,
    get_hook_manager: Callable[[], HookManager | None],
) -> None:
    """Register hook inspection and testing tools on the registry."""

    @registry.tool(
        name="list_hook_handlers",
        description="List registered hook handlers from plugins, organized by event type.",
    )
    async def list_hook_handlers(event_type: str = "") -> dict[str, Any]:
        """
        List registered hook handlers from plugins.

        Args:
            event_type: Optional event type filter (e.g., 'session_start', 'before_tool')
        """
        hm = get_hook_manager()
        if hm is None:
            return {
                "success": True,
                "handlers": {},
                "message": "Hook manager not available - plugins not loaded",
            }

        loader = getattr(hm, "plugin_loader", None)
        if loader is None:
            return {
                "success": True,
                "handlers": {},
                "message": "Plugin system not initialized",
            }

        # Filter to specific event type if provided
        if event_type:
            try:
                target_type = HookEventType(event_type)
                event_types = [target_type]
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid event type: {event_type}",
                    "valid_types": [e.value for e in HookEventType],
                }
        else:
            event_types = list(HookEventType)

        handlers_by_event: dict[str, list[dict[str, Any]]] = {}
        for et in event_types:
            handlers = loader.registry.get_handlers(et)
            if handlers:
                handlers_by_event[et.value] = [
                    {
                        "plugin": h.plugin.name,
                        "method": h.method.__name__,
                        "priority": h.priority,
                        "is_pre_handler": h.priority < 50,
                    }
                    for h in handlers
                ]

        return {
            "success": True,
            "handlers": handlers_by_event,
            "total_handlers": sum(len(h) for h in handlers_by_event.values()),
        }

    @registry.tool(
        name="test_hook_event",
        description="Send a test hook event through the plugin handler system.",
    )
    async def test_hook_event(
        event_type: str,
        source: str = "claude",
        data: str = "",
    ) -> dict[str, Any]:
        """
        Test a hook event by sending it through the hook system.

        Args:
            event_type: Hook event type (e.g., 'session_start', 'before_tool')
            source: Source CLI to simulate (claude, gemini, codex, cursor, windsurf, copilot)
            data: Optional JSON string of additional event data
        """
        hm = get_hook_manager()
        if hm is None:
            return {"success": False, "error": "Hook manager not available"}

        # Validate event type
        try:
            hook_event_type = HookEventType(event_type)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid event type: {event_type}",
                "valid_types": [e.value for e in HookEventType],
            }

        # Parse source
        try:
            session_source = SessionSource(source)
        except ValueError:
            session_source = SessionSource.CLAUDE

        # Parse extra data
        extra_data: dict[str, Any] = {}
        if data:
            import json

            try:
                extra_data = json.loads(data)
            except json.JSONDecodeError as e:
                return {"success": False, "error": f"Invalid JSON data: {e}"}

        test_data = {
            "session_id": "test-mcp-event",
            "source": source,
            **extra_data,
        }

        event = HookEvent(
            event_type=hook_event_type,
            session_id="test-mcp-event",
            source=session_source,
            timestamp=datetime.now(UTC),
            data=test_data,
        )

        try:
            result = hm.handle(event)
            return {
                "success": True,
                "event_type": event_type,
                "decision": result.decision,
                "reason": result.reason,
                "context": result.context if hasattr(result, "context") else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
