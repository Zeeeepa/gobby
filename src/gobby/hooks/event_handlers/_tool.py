from __future__ import annotations

import logging
import os

from gobby.hooks.event_handlers._base import EventHandlersBase
from gobby.hooks.events import HookEvent, HookResponse

logger = logging.getLogger(__name__)

EDIT_TOOLS = {
    "write_file",
    "replace",
    "edit_file",
    "notebook_edit",
    "edit",
    "write",
}


class ToolEventHandlerMixin(EventHandlersBase):
    """Mixin for handling tool-related events."""

    def handle_before_tool(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_TOOL event."""
        input_data = event.data
        tool_name = input_data.get("tool_name", "unknown")
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"BEFORE_TOOL: {tool_name}, session {session_id}")
        else:
            self.logger.debug(f"BEFORE_TOOL: {tool_name}")

        return HookResponse(decision="allow")

    def handle_after_tool(self, event: HookEvent) -> HookResponse:
        """Handle AFTER_TOOL event."""
        input_data = event.data
        tool_name = input_data.get("tool_name", "unknown")
        session_id = event.metadata.get("_platform_session_id")
        is_failure = event.metadata.get("is_failure", False)

        status = "FAIL" if is_failure else "OK"
        if session_id:
            self.logger.debug(f"AFTER_TOOL [{status}]: {tool_name}, session {session_id}")

            # Track edits for session high-water mark
            # Only if tool succeeded, matches edit tools, and session has claimed a task
            # Skip .gobby/ internal files (tasks.jsonl, memories.jsonl, etc.)
            tool_input = input_data.get("tool_input", {})

            # Simple check for edit tools (case-insensitive)
            is_edit = tool_name.lower() in EDIT_TOOLS

            # For complex tools (multi_replace, etc), check if they modify files
            # This logic could be expanded, but for now stick to the basic set

            if not is_failure and is_edit and self._session_storage:
                try:
                    # Check if file is internal .gobby file
                    file_path = (
                        tool_input.get("file_path")
                        or tool_input.get("target_file")
                        or tool_input.get("path")
                    )
                    is_internal = file_path and ".gobby/" in str(file_path)

                    if not is_internal:
                        # Track repo-relative file path in session variables
                        # (independent of task-claim gate — rules need this
                        # for per-session has_dirty_files scoping)
                        if file_path:
                            self._track_session_edited_file(
                                session_id, str(file_path), event.cwd
                            )

                        # Check if session has any claimed tasks before marking had_edits
                        has_claimed_task = False
                        if self._task_manager:
                            try:
                                claimed_tasks = self._task_manager.list_tasks(assignee=session_id)
                                has_claimed_task = len(claimed_tasks) > 0
                            except Exception as e:
                                self.logger.debug(
                                    f"Failed to check claimed tasks for session {session_id}: {e}"
                                )

                        if has_claimed_task:
                            self._session_storage.mark_had_edits(session_id)
                except Exception as e:
                    # Don't fail the event if tracking fails
                    self.logger.warning(f"Failed to process file edit: {e}")

        else:
            self.logger.debug(f"AFTER_TOOL [{status}]: {tool_name}")

        return HookResponse(decision="allow")

    def _track_session_edited_file(
        self, session_id: str, file_path: str, cwd: str | None
    ) -> None:
        """Record a repo-relative file path in session_edited_files variable.

        Used to scope ``has_dirty_files`` to only files this session touched,
        preventing bleed across concurrent sessions sharing a working directory.
        """
        try:
            if cwd:
                rel_path = os.path.normpath(os.path.relpath(file_path, cwd))
            else:
                rel_path = os.path.normpath(file_path)

            # Skip paths that escape the repo (e.g. /tmp files)
            if rel_path.startswith(".."):
                return

            from gobby.workflows.state_manager import SessionVariableManager

            db = getattr(self._session_storage, "db", None)
            if db:
                SessionVariableManager(db).append_to_set_variable(
                    session_id, "session_edited_files", [rel_path]
                )
        except Exception as e:
            logger.debug(f"Failed to track session edited file: {e}")

    def handle_before_tool_selection(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_TOOL_SELECTION event (Gemini only)."""
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"BEFORE_TOOL_SELECTION: session {session_id}")
        else:
            self.logger.debug("BEFORE_TOOL_SELECTION")

        return HookResponse(decision="allow")
