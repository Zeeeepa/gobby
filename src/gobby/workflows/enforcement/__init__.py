"""Task enforcement actions for workflow engine.

This package provides actions that enforce task tracking before allowing
certain tools, and enforce task completion before allowing agent to stop.
"""

from gobby.workflows.enforcement.blocking import (
    block_tools,
    is_discovery_tool,
    is_tool_unlocked,
    track_schema_lookup,
)
from gobby.workflows.enforcement.commit_policy import (
    capture_baseline_dirty_files,
    require_commit_before_stop,
    require_task_review_or_close_before_stop,
)
from gobby.workflows.enforcement.handlers import (
    handle_block_tools,
    handle_capture_baseline_dirty_files,
    handle_require_active_task,
    handle_require_commit_before_stop,
    handle_require_task_complete,
    handle_require_task_review_or_close_before_stop,
    handle_track_schema_lookup,
    handle_validate_session_task_scope,
)
from gobby.workflows.enforcement.task_policy import (
    require_active_task,
    require_task_complete,
    validate_session_task_scope,
)

__all__ = [
    # Blocking
    "block_tools",
    "is_discovery_tool",
    "is_tool_unlocked",
    "track_schema_lookup",
    # Commit policy
    "capture_baseline_dirty_files",
    "require_commit_before_stop",
    "require_task_review_or_close_before_stop",
    # Task policy
    "require_active_task",
    "require_task_complete",
    "validate_session_task_scope",
    # Handlers
    "handle_block_tools",
    "handle_capture_baseline_dirty_files",
    "handle_require_active_task",
    "handle_require_commit_before_stop",
    "handle_require_task_complete",
    "handle_require_task_review_or_close_before_stop",
    "handle_track_schema_lookup",
    "handle_validate_session_task_scope",
]
