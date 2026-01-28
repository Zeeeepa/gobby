"""Autonomous execution workflow actions.

Actions for managing autonomous loop execution including:
- Progress tracking (start, stop, record)
- Stuck detection (detect task loops, tool loops)
- Task selection recording
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.autonomous.progress_tracker import ProgressTracker, ProgressType
    from gobby.autonomous.stuck_detector import StuckDetector
    from gobby.workflows.definitions import WorkflowState

logger = logging.getLogger(__name__)


def start_progress_tracking(
    progress_tracker: "ProgressTracker | None",
    session_id: str,
    state: "WorkflowState",
) -> dict[str, Any]:
    """Start progress tracking for a session.

    Marks the session as actively being tracked and clears any
    previous progress data.

    Args:
        progress_tracker: ProgressTracker instance
        session_id: The session to track
        state: Current workflow state (updated with tracking info)

    Returns:
        Dict with success status
    """
    if not progress_tracker:
        logger.warning("No progress_tracker available")
        return {"success": False, "error": "Progress tracker not available"}

    # Clear any existing progress data
    progress_tracker.clear_session(session_id)

    # Mark as tracking in workflow state
    state.variables["_progress_tracking_active"] = True

    logger.info(f"Started progress tracking for session {session_id}")
    return {"success": True, "session_id": session_id}


def stop_progress_tracking(
    progress_tracker: "ProgressTracker | None",
    session_id: str,
    state: "WorkflowState",
    keep_data: bool = False,
) -> dict[str, Any]:
    """Stop progress tracking for a session.

    Args:
        progress_tracker: ProgressTracker instance
        session_id: The session to stop tracking
        state: Current workflow state
        keep_data: If True, preserve progress data; otherwise clear it

    Returns:
        Dict with success status and final summary
    """
    if not progress_tracker:
        return {"success": False, "error": "Progress tracker not available"}

    # Get final summary before stopping
    summary = progress_tracker.get_summary(session_id)

    # Clear if requested
    if not keep_data:
        progress_tracker.clear_session(session_id)

    # Mark as not tracking
    state.variables["_progress_tracking_active"] = False

    logger.info(f"Stopped progress tracking for session {session_id}")
    return {
        "success": True,
        "session_id": session_id,
        "final_summary": {
            "total_events": summary.total_events,
            "high_value_events": summary.high_value_events,
            "was_stagnant": summary.is_stagnant,
        },
    }


def record_progress(
    progress_tracker: "ProgressTracker | None",
    session_id: str,
    progress_type: "ProgressType | str",
    tool_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a progress event.

    Args:
        progress_tracker: ProgressTracker instance
        session_id: The session to record for
        progress_type: Type of progress (from ProgressType enum or string)
        tool_name: Optional tool name that generated the event
        details: Optional additional details

    Returns:
        Dict with success status and event info
    """
    if not progress_tracker:
        return {"success": False, "error": "Progress tracker not available"}

    from gobby.autonomous.progress_tracker import ProgressType

    # Convert string to enum if needed
    if isinstance(progress_type, str):
        try:
            progress_type = ProgressType(progress_type)
        except ValueError:
            progress_type = ProgressType.TOOL_CALL

    event = progress_tracker.record_event(
        session_id=session_id,
        progress_type=progress_type,
        tool_name=tool_name,
        details=details,
    )

    return {
        "success": True,
        "event": {
            "type": event.progress_type.value,
            "is_high_value": event.is_high_value,
            "timestamp": event.timestamp.isoformat(),
        },
    }


def detect_task_loop(
    stuck_detector: "StuckDetector | None",
    session_id: str,
    state: "WorkflowState",
) -> dict[str, Any]:
    """Detect if the session is stuck in a task selection loop.

    Args:
        stuck_detector: StuckDetector instance
        session_id: The session to check
        state: Current workflow state (updated with detection results)

    Returns:
        Dict with detection results
    """
    if not stuck_detector:
        return {"is_stuck": False, "error": "Stuck detector not available"}

    result = stuck_detector.detect_task_loop(session_id)

    # Update workflow state
    state.variables["_task_loop_detected"] = result.is_stuck
    if result.is_stuck:
        state.variables["_task_loop_task_id"] = (
            result.details.get("task_id") if result.details else None
        )

    return {
        "is_stuck": result.is_stuck,
        "reason": result.reason,
        "layer": result.layer,
        "details": result.details,
        "suggested_action": result.suggested_action,
    }


def detect_stuck(
    stuck_detector: "StuckDetector | None",
    session_id: str,
    state: "WorkflowState",
) -> dict[str, Any]:
    """Run full stuck detection (all layers).

    Args:
        stuck_detector: StuckDetector instance
        session_id: The session to check
        state: Current workflow state (updated with detection results)

    Returns:
        Dict with detection results and optional inject_context
    """
    if not stuck_detector:
        return {"is_stuck": False, "error": "Stuck detector not available"}

    result = stuck_detector.is_stuck(session_id)

    # Update workflow state
    state.variables["_is_stuck"] = result.is_stuck
    state.variables["_stuck_layer"] = result.layer
    state.variables["_stuck_reason"] = result.reason

    response: dict[str, Any] = {
        "is_stuck": result.is_stuck,
        "reason": result.reason,
        "layer": result.layer,
        "details": result.details,
        "suggested_action": result.suggested_action,
    }

    # Add context injection if stuck
    if result.is_stuck:
        response["inject_context"] = (
            f"⚠️ **Stuck Detected** ({result.layer})\n\n"
            f"Reason: {result.reason}\n"
            f"Suggested action: {result.suggested_action or 'Review approach'}\n\n"
            f"Consider stopping or changing your approach."
        )

    return response


def record_task_selection(
    stuck_detector: "StuckDetector | None",
    session_id: str,
    task_id: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a task selection for loop detection.

    Called when the autonomous loop selects a task to work on.

    Args:
        stuck_detector: StuckDetector instance
        session_id: The session selecting the task
        task_id: The task being selected
        context: Optional context about the selection

    Returns:
        Dict with success status
    """
    if not stuck_detector:
        return {"success": False, "error": "Stuck detector not available"}

    event = stuck_detector.record_task_selection(
        session_id=session_id,
        task_id=task_id,
        context=context,
    )

    return {
        "success": True,
        "task_id": event.task_id,
        "recorded_at": event.selected_at.isoformat(),
    }


def get_progress_summary(
    progress_tracker: "ProgressTracker | None",
    session_id: str,
) -> dict[str, Any]:
    """Get a summary of progress for a session.

    Args:
        progress_tracker: ProgressTracker instance
        session_id: The session to get summary for

    Returns:
        Dict with progress summary
    """
    if not progress_tracker:
        return {"error": "Progress tracker not available"}

    summary = progress_tracker.get_summary(session_id)

    return {
        "total_events": summary.total_events,
        "high_value_events": summary.high_value_events,
        "is_stagnant": summary.is_stagnant,
        "stagnation_duration_seconds": summary.stagnation_duration_seconds,
        "last_high_value_at": (
            summary.last_high_value_at.isoformat() if summary.last_high_value_at else None
        ),
        "last_event_at": (summary.last_event_at.isoformat() if summary.last_event_at else None),
        "events_by_type": {k.value: v for k, v in summary.events_by_type.items()},
    }


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None
# Note: These handlers require executor access for progress_tracker and stuck_detector,
# so they are created as closures inside ActionExecutor._register_defaults().

# No wrapper functions are defined in this file. The actual handler implementations
# are closures created in ActionExecutor._register_defaults() which capture the
# executor's self.progress_tracker and self.stuck_detector references. See that
# method for the actual implementations and where these components are hooked up.
