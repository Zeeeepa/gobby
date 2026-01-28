"""Stop signal workflow actions for autonomous execution.

These actions enable workflows to check for and respond to stop signals
sent by external systems (HTTP, WebSocket, CLI, MCP).
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.autonomous.stop_registry import StopRegistry
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


def check_stop_signal(
    stop_registry: "StopRegistry | None",
    session_id: str,
    state: "WorkflowState",
    acknowledge: bool = False,
) -> dict[str, Any]:
    """Check if a stop signal has been sent for this session.

    This action can be used in workflow transitions or as a periodic check
    during autonomous execution.

    Args:
        stop_registry: StopRegistry instance for checking signals
        session_id: The session to check
        state: Current workflow state (updated with signal info)
        acknowledge: If True, acknowledge the signal (session will stop)

    Returns:
        Dict with:
        - has_signal: True if there's a pending stop signal
        - signal: Signal details if present (source, reason, requested_at)
        - acknowledged: True if the signal was acknowledged
        - inject_context: Optional message about the stop signal
    """
    if not stop_registry:
        logger.warning("No stop_registry available, cannot check stop signal")
        return {"has_signal": False}

    signal = stop_registry.get_signal(session_id)

    if not signal or not signal.is_pending:
        return {"has_signal": False}

    # Store signal info in workflow variables
    state.variables["_stop_signal_pending"] = True
    state.variables["_stop_signal_source"] = signal.source
    state.variables["_stop_signal_reason"] = signal.reason

    result: dict[str, Any] = {
        "has_signal": True,
        "signal": {
            "source": signal.source,
            "reason": signal.reason,
            "requested_at": signal.requested_at.isoformat(),
        },
    }

    if acknowledge:
        stop_registry.acknowledge(session_id)
        result["acknowledged"] = True
        result["inject_context"] = (
            f"🛑 **Stop Signal Received**\n\n"
            f"Source: {signal.source}\n"
            f"Reason: {signal.reason or 'No reason provided'}\n\n"
            f"The session will stop gracefully."
        )
        logger.info(f"Stop signal acknowledged for session {session_id}")
    else:
        result["acknowledged"] = False
        result["inject_context"] = (
            f"⚠️ **Stop Signal Pending**\n\n"
            f"A stop signal was received from {signal.source}.\n"
            f"Reason: {signal.reason or 'No reason provided'}\n\n"
            f"Complete current work and prepare to stop."
        )

    return result


def has_stop_signal(stop_registry: "StopRegistry | None", session_id: str) -> bool:
    """Condition function to check if a stop signal is pending.

    Use this in workflow transition conditions:

    ```yaml
    transitions:
      - to: stopping
        when: "has_stop_signal(session.id)"
    ```

    Args:
        stop_registry: StopRegistry instance
        session_id: The session to check

    Returns:
        True if there's a pending stop signal
    """
    if not stop_registry:
        return False
    return stop_registry.has_pending_signal(session_id)


def request_stop(
    stop_registry: "StopRegistry | None",
    session_id: str,
    source: str = "workflow",
    reason: str | None = None,
) -> dict[str, Any]:
    """Request a session to stop (can be used by stuck detection).

    Args:
        stop_registry: StopRegistry instance
        session_id: The session to signal
        source: Source of the request (workflow, stuck_detection, etc.)
        reason: Optional reason for the stop request

    Returns:
        Dict with success status and signal details
    """
    if not stop_registry:
        logger.warning("No stop_registry available, cannot request stop")
        return {"success": False, "error": "No stop registry available"}

    signal = stop_registry.signal_stop(session_id, source, reason)

    return {
        "success": True,
        "signal": {
            "session_id": signal.session_id,
            "source": signal.source,
            "reason": signal.reason,
            "requested_at": signal.requested_at.isoformat(),
        },
    }


def clear_stop_signal(
    stop_registry: "StopRegistry | None",
    session_id: str,
) -> dict[str, Any]:
    """Clear any stop signal for a session.

    Use this after a session has fully stopped or when the signal
    should be cancelled.

    Args:
        stop_registry: StopRegistry instance
        session_id: The session to clear

    Returns:
        Dict with success status
    """
    if not stop_registry:
        return {"success": False, "error": "No stop registry available"}

    cleared = stop_registry.clear(session_id)
    return {"success": True, "cleared": cleared}


# --- ActionHandler factory functions ---
# These create ActionHandler-compatible wrappers that close over the stop_registry.
# The ActionExecutor calls these factories in _register_defaults() to create handlers
# that have access to the executor's stop_registry instance.


def make_handle_check_stop_signal(
    stop_registry: "StopRegistry | None",
) -> Any:
    """Factory that creates a check_stop_signal handler with access to stop_registry."""

    async def handler(context: "Any", **kwargs: Any) -> dict[str, Any] | None:
        """ActionHandler for check_stop_signal."""
        return check_stop_signal(
            stop_registry=stop_registry,
            session_id=context.session_id,
            state=context.state,
            acknowledge=kwargs.get("acknowledge", False),
        )

    return handler


def make_handle_request_stop(
    stop_registry: "StopRegistry | None",
) -> Any:
    """Factory that creates a request_stop handler with access to stop_registry."""

    async def handler(context: "Any", **kwargs: Any) -> dict[str, Any] | None:
        """ActionHandler for request_stop."""
        return request_stop(
            stop_registry=stop_registry,
            session_id=kwargs.get("session_id", context.session_id),
            source=kwargs.get("source", "workflow"),
            reason=kwargs.get("reason"),
        )

    return handler


def make_handle_clear_stop_signal(
    stop_registry: "StopRegistry | None",
) -> Any:
    """Factory that creates a clear_stop_signal handler with access to stop_registry."""

    async def handler(context: "Any", **kwargs: Any) -> dict[str, Any] | None:
        """ActionHandler for clear_stop_signal."""
        return clear_stop_signal(
            stop_registry=stop_registry,
            session_id=kwargs.get("session_id", context.session_id),
        )

    return handler
