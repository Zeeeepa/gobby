"""Claude Code Task Interop Adapter.

This adapter provides bidirectional synchronization between Claude Code's
built-in task tools (TaskCreate, TaskUpdate, TaskList, TaskGet) and Gobby's
persistent task system.

Interop Strategy:
- POST-TOOL-USE: Sync CC task changes to Gobby for persistence
- CONTEXT ENRICHMENT: Inject Gobby-specific metadata (validation, expansion)

Claude Code Task Tools (v2.1.16+):
- TaskCreate: Create tasks with subject, description, activeForm
- TaskUpdate: Update status, add dependencies, change owner
- TaskList: List tasks with brief summary
- TaskGet: Get full task details

Status Mapping:
    Claude Code         Gobby
    -----------         -----
    pending         <-> open
    in_progress     <-> in_progress
    completed       <-> closed
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


# Status mappings between Claude Code and Gobby
CC_TO_GOBBY_STATUS = {
    "pending": "open",
    "in_progress": "in_progress",
    "completed": "closed",
}

GOBBY_TO_CC_STATUS = {
    "open": "pending",
    "in_progress": "in_progress",
    "closed": "completed",
    "review": "in_progress",  # Review maps to in_progress (still active)
    "failed": "pending",
    "escalated": "pending",
    "needs_decomposition": "pending",
}

# CC task tools that we intercept
CC_TASK_TOOLS = {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}


class ClaudeCodeTaskAdapter:
    """Adapter for Claude Code Task <-> Gobby Task interoperability.

    This adapter handles:
    1. Syncing TaskCreate results to Gobby for persistence
    2. Syncing TaskUpdate changes to Gobby
    3. Enriching TaskList/TaskGet responses with Gobby metadata

    Usage in post-tool-use hook:
        adapter = ClaudeCodeTaskAdapter(task_manager, session_id, project_id)
        if tool_name == "TaskCreate":
            adapter.sync_task_create(tool_input, tool_result)
    """

    def __init__(
        self,
        task_manager: LocalTaskManager,
        session_id: str | None,
        project_id: str | None,
    ) -> None:
        """Initialize the adapter.

        Args:
            task_manager: Gobby's LocalTaskManager for task operations.
            session_id: Current session ID for linking tasks.
            project_id: Current project ID for task scoping.
        """
        self.task_manager = task_manager
        self.session_id = session_id
        self.project_id = project_id

    def handle_post_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_result: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Handle a post-tool-use event for CC task tools.

        Args:
            tool_name: Name of the tool that was called
            tool_input: Input parameters passed to the tool
            tool_result: Result returned by the tool (may be None on failure)

        Returns:
            Sync result info, or None if not a task tool or sync failed.
        """
        if tool_name not in CC_TASK_TOOLS:
            return None

        if tool_name == "TaskCreate":
            return self.sync_task_create(tool_input, tool_result)
        elif tool_name == "TaskUpdate":
            return self.sync_task_update(tool_input, tool_result)
        elif tool_name in ("TaskList", "TaskGet"):
            # Read operations don't need syncing, but we could enrich responses
            return None

        return None

    def sync_task_create(
        self, tool_input: dict[str, Any], tool_result: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Sync a TaskCreate operation to Gobby.

        Called after Claude Code's TaskCreate tool completes.
        Creates a corresponding task in Gobby for persistence.

        Args:
            tool_input: The input passed to TaskCreate (subject, description, etc.)
            tool_result: The result from TaskCreate (id, status, etc.)

        Returns:
            Gobby task reference info, or None if sync failed.
        """
        if not tool_result:
            return None

        cc_task_id = tool_result.get("id")
        if not cc_task_id:
            logger.warning("TaskCreate result missing 'id' field")
            return None

        subject = tool_input.get("subject", "Untitled")
        description = tool_input.get("description")

        # Extract Gobby-specific options from metadata.gobby if present
        metadata = tool_input.get("metadata", {})
        gobby_opts = metadata.get("gobby", {})

        task_type = gobby_opts.get("task_type", "task")
        priority = gobby_opts.get("priority", 2)
        validation_criteria = gobby_opts.get("validation_criteria")
        category = gobby_opts.get("category")

        if not self.project_id:
            logger.warning("Cannot sync TaskCreate: no project_id")
            return None

        # Store CC task ID in description for later lookup
        # Format: Original description + CC task reference at end
        full_description = description or ""
        if full_description:
            full_description += f"\n\n<!-- cc_task_id: {cc_task_id} -->"
        else:
            full_description = f"<!-- cc_task_id: {cc_task_id} -->"

        try:
            gobby_task = self.task_manager.create_task(
                project_id=self.project_id,
                title=subject,
                description=full_description,
                task_type=task_type,
                priority=priority,
                created_in_session_id=self.session_id,
                validation_criteria=validation_criteria,
                category=category,
            )

            logger.info(
                f"Synced CC TaskCreate: cc_id={cc_task_id} -> gobby_id={gobby_task.id} "
                f"(#{gobby_task.seq_num})"
            )

            return {
                "gobby_id": gobby_task.id,
                "seq_num": gobby_task.seq_num,
                "ref": f"#{gobby_task.seq_num}",
            }

        except Exception as e:
            logger.error(f"Failed to sync TaskCreate to Gobby: {e}", exc_info=True)
            return None

    def sync_task_update(
        self, tool_input: dict[str, Any], tool_result: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Sync a TaskUpdate operation to Gobby.

        Called after Claude Code's TaskUpdate tool completes.
        Updates the corresponding Gobby task.

        Args:
            tool_input: The input passed to TaskUpdate (taskId, status, etc.)
            tool_result: The result from TaskUpdate

        Returns:
            Update confirmation, or None if sync failed.
        """
        cc_task_id = tool_input.get("taskId")
        if not cc_task_id:
            return None

        # Find corresponding Gobby task by cc_task_id in metadata
        gobby_task = self._find_gobby_task_by_cc_id(cc_task_id)
        if not gobby_task:
            logger.debug(f"No Gobby task found for CC task {cc_task_id}")
            return None

        try:
            updates: dict[str, Any] = {}

            # Map status
            if "status" in tool_input:
                cc_status = tool_input["status"]
                gobby_status = CC_TO_GOBBY_STATUS.get(cc_status)
                if gobby_status:
                    updates["status"] = gobby_status

            # Map other fields
            if "subject" in tool_input:
                updates["title"] = tool_input["subject"]
            if "description" in tool_input:
                updates["description"] = tool_input["description"]
            if "owner" in tool_input:
                updates["agent_name"] = tool_input["owner"]

            # Note: CC task dependencies (addBlockedBy) are not synced to Gobby
            # because Gobby's dependency model uses parent_task_id hierarchy
            # rather than arbitrary blocking relationships

            if updates:
                self.task_manager.update_task(gobby_task.id, **updates)
                logger.info(
                    f"Synced CC TaskUpdate: cc_id={cc_task_id} -> gobby_id={gobby_task.id}"
                )

            return {"synced": True, "gobby_id": gobby_task.id}

        except Exception as e:
            logger.error(f"Failed to sync TaskUpdate to Gobby: {e}", exc_info=True)
            return None

    def enrich_task_data(self, cc_task_data: dict[str, Any]) -> dict[str, Any]:
        """Enrich a Claude Code task response with Gobby metadata.

        Adds Gobby-specific fields like validation_status, is_expanded, etc.

        Args:
            cc_task_data: Task data from Claude Code (single task)

        Returns:
            Enriched task data with 'gobby' block.
        """
        cc_task_id = cc_task_data.get("id")
        if not cc_task_id:
            return cc_task_data

        gobby_task = self._find_gobby_task_by_cc_id(cc_task_id)
        if not gobby_task:
            return cc_task_data

        try:
            # Count subtasks (children of this task)
            subtasks = self.task_manager.list_tasks(
                project_id=self.project_id or "",
                parent_task_id=gobby_task.id,
            )
            subtask_count = len(subtasks) if subtasks else 0

            # Add Gobby enrichment block
            cc_task_data["gobby"] = {
                "uuid": gobby_task.id,
                "seq_num": gobby_task.seq_num,
                "ref": f"#{gobby_task.seq_num}",
                "validation_status": gobby_task.validation_status,
                "validation_criteria": gobby_task.validation_criteria,
                "is_expanded": gobby_task.is_expanded,
                "subtask_count": subtask_count,
                "commit_count": len(gobby_task.commits or []),
                "path_cache": gobby_task.path_cache,
                "task_type": gobby_task.task_type,
                "priority": gobby_task.priority,
                "category": gobby_task.category,
            }

            return cc_task_data

        except Exception as e:
            logger.debug(f"Could not enrich task {cc_task_id}: {e}")
            return cc_task_data

    def _find_gobby_task_by_cc_id(self, cc_task_id: str) -> Any | None:
        """Find a Gobby task by its Claude Code task ID.

        Searches tasks in the current project for one with matching
        cc_task_id marker in the description.

        Args:
            cc_task_id: Claude Code task ID

        Returns:
            Gobby Task object, or None if not found.
        """
        if not self.project_id:
            return None

        try:
            # Get all tasks for the project and search by cc_task_id in description
            # Note: This is inefficient - consider adding a dedicated field
            cc_marker = f"<!-- cc_task_id: {cc_task_id} -->"
            tasks = self.task_manager.list_tasks(project_id=self.project_id)
            for task in tasks:
                if task.description and cc_marker in task.description:
                    return task
            return None
        except Exception:
            return None

    @staticmethod
    def get_cc_status(gobby_status: str) -> str:
        """Convert Gobby status to Claude Code status."""
        return GOBBY_TO_CC_STATUS.get(gobby_status, "pending")

    @staticmethod
    def get_gobby_status(cc_status: str) -> str:
        """Convert Claude Code status to Gobby status."""
        return CC_TO_GOBBY_STATUS.get(cc_status, "open")

    @staticmethod
    def is_cc_task_tool(tool_name: str) -> bool:
        """Check if a tool name is a Claude Code task tool."""
        return tool_name in CC_TASK_TOOLS
