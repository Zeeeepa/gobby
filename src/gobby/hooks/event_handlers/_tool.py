from __future__ import annotations

import logging
import os
from typing import Any

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
        """Handle BEFORE_TOOL event.

        Intercepts Skill tool calls and resolves gobby skills inline,
        injecting skill content as context and blocking the native tool call
        (which would fail with "Unknown skill" in Claude Code's registry).
        """
        input_data = event.data
        tool_name = input_data.get("tool_name", "unknown")
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"BEFORE_TOOL: {tool_name}, session {session_id}")
        else:
            self.logger.debug(f"BEFORE_TOOL: {tool_name}")

        # Intercept Skill tool calls to resolve gobby skills
        if tool_name == "Skill" and self._skill_manager:
            try:
                skill_response = self._resolve_skill_tool_call(input_data)
                if skill_response is not None:
                    return skill_response
            except Exception as e:
                self.logger.error(f"Failed to resolve skill tool call: {e}", exc_info=True)

        return HookResponse(decision="allow")

    def _resolve_skill_tool_call(self, input_data: dict[str, Any]) -> HookResponse | None:
        """Resolve a Skill tool call against gobby skills.

        If the skill name resolves via HookSkillManager, returns a blocking
        HookResponse with skill content injected as context. The model sees
        the skill instructions and follows them inline.

        If the skill doesn't resolve (not a gobby skill), returns None to
        let it through to Claude Code's native skill registry.
        """
        tool_input = input_data.get("tool_input", {})
        raw_skill_name = tool_input.get("skill", "")
        if not raw_skill_name:
            return None

        # Strip gobby: namespace prefix (Skill tool namespace separator)
        skill_name = raw_skill_name
        if skill_name.startswith("gobby:"):
            skill_name = skill_name[len("gobby:") :]

        # Non-gobby namespace (e.g. "ms-office-suite:pdf") — not ours
        if ":" in skill_name:
            return None

        if self._skill_manager is None:
            return None

        skill = self._skill_manager.resolve_skill_name(skill_name)
        if skill is None:
            return None

        # Build skill context (same format as _intercept_skill_command in _agent.py)
        parts = [f'<skill-context name="{skill.name}">']
        parts.append(skill.content)
        parts.append("</skill-context>")

        args = tool_input.get("args", "")
        if args:
            parts.append(f"\nUser arguments: {args}")

        context = "\n".join(parts)

        self.logger.info(
            "Resolved gobby skill '%s' from Skill tool call (requested: '%s')",
            skill.name,
            raw_skill_name,
        )

        return HookResponse(
            decision="block",
            reason=f"Gobby skill '{skill.name}' resolved — content injected as context",
            context=context,
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
                            self._track_session_edited_file(session_id, str(file_path), event.cwd)

                            # Trigger incremental code index update
                            if self._code_index_trigger:
                                try:
                                    project_id = self._resolve_project_id(None, event.cwd)
                                    if project_id:
                                        self._code_index_trigger.notify_file_changed(
                                            file_path=str(file_path),
                                            project_id=project_id,
                                            root_path=event.cwd or "",
                                        )
                                except Exception as e:
                                    logger.debug(f"Failed to trigger code index update: {e}")

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

    def _track_session_edited_file(self, session_id: str, file_path: str, cwd: str | None) -> None:
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
