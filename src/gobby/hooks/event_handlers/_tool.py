from __future__ import annotations

from typing import Any

from gobby.hooks.event_handlers._base import EventHandlersBase
from gobby.hooks.events import HookEvent, HookResponse

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

        context_parts = []

        # Execute lifecycle workflow triggers
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.context:
                    context_parts.append(wf_response.context)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(
            decision="allow",
            context="\n\n".join(context_parts) if context_parts else None,
        )

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

            # Capture artifacts from edit tools
            if not is_failure and self._artifact_capture_hook:
                self._capture_tool_artifact(session_id, tool_name, tool_input)

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

        # Execute lifecycle workflow triggers
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
                if wf_response.context:
                    return wf_response
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(decision="allow")

    def handle_before_tool_selection(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_TOOL_SELECTION event (Gemini only)."""
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"BEFORE_TOOL_SELECTION: session {session_id}")
        else:
            self.logger.debug("BEFORE_TOOL_SELECTION")

        return HookResponse(decision="allow")

    def _capture_tool_artifact(
        self, session_id: str, tool_name: str, tool_input: dict[str, Any]
    ) -> None:
        """Capture artifacts from tool inputs for edit/write tools.

        Args:
            session_id: Platform session ID
            tool_name: Name of the tool
            tool_input: Tool input dictionary
        """
        if not self._artifact_capture_hook:
            return

        # Get content and file path from tool input
        content = tool_input.get("content") or tool_input.get("new_string")
        file_path = (
            tool_input.get("file_path") or tool_input.get("target_file") or tool_input.get("path")
        )

        if not content:
            return

        # Skip internal .gobby files
        if file_path and ".gobby/" in str(file_path):
            return

        # Detect language from file extension
        language = ""
        if file_path:
            ext_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".tsx": "tsx",
                ".jsx": "jsx",
                ".rs": "rust",
                ".go": "go",
                ".java": "java",
                ".rb": "ruby",
                ".sh": "bash",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".json": "json",
                ".md": "markdown",
                ".sql": "sql",
                ".html": "html",
                ".css": "css",
            }
            for ext, lang in ext_map.items():
                if str(file_path).endswith(ext):
                    language = lang
                    break

        # Wrap content as markdown code block for process_message
        # This reuses the deduplication and classification logic
        markdown_content = f"```{language}\n{content}\n```"

        try:
            self._artifact_capture_hook.process_message(
                session_id=session_id,
                role="assistant",
                content=markdown_content,
            )
            self.logger.debug(f"Captured artifact from {tool_name}: {file_path or 'unknown'}")
        except Exception as e:
            self.logger.warning(f"Failed to capture artifact from {tool_name}: {e}")
