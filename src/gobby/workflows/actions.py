from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from gobby.storage.database import DatabaseProtocol
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks import LocalTaskManager  # noqa: F401
from gobby.workflows.artifact_actions import capture_artifact, read_artifact
from gobby.workflows.autonomous_actions import (
    detect_stuck,
    detect_task_loop,
    get_progress_summary,
    record_progress,
    record_task_selection,
    start_progress_tracking,
    stop_progress_tracking,
)
from gobby.workflows.context_actions import (
    extract_handoff_context,
    format_handoff_as_markdown,
    inject_context,
    inject_message,
)
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.git_utils import get_file_changes, get_git_status, get_recent_git_commits
from gobby.workflows.llm_actions import call_llm
from gobby.workflows.mcp_actions import call_mcp_tool
from gobby.workflows.memory_actions import (
    memory_recall_relevant,
    memory_save,
    memory_sync_export,
    memory_sync_import,
    reset_memory_injection_tracking,
)
from gobby.workflows.session_actions import (
    mark_session_status,
    start_new_session,
    switch_mode,
)
from gobby.workflows.state_actions import (
    increment_variable,
    load_workflow_state,
    mark_loop_complete,
    save_workflow_state,
    set_variable,
)
from gobby.workflows.stop_signal_actions import (
    check_stop_signal,
    clear_stop_signal,
    request_stop,
)
from gobby.workflows.summary_actions import (
    format_turns_for_llm,
    generate_handoff,
    generate_summary,
    synthesize_title,
)
from gobby.workflows.task_enforcement_actions import (
    capture_baseline_dirty_files,
    require_active_task,
    require_commit_before_stop,
    require_task_complete,
    validate_session_task_scope,
)
from gobby.workflows.templates import TemplateEngine
from gobby.workflows.todo_actions import mark_todo_complete, write_todos
from gobby.workflows.webhook import WebhookAction
from gobby.workflows.webhook_executor import WebhookExecutor

logger = logging.getLogger(__name__)


@dataclass
class ActionContext:
    """Context passed to action handlers."""

    session_id: str
    state: WorkflowState
    db: DatabaseProtocol
    session_manager: LocalSessionManager
    template_engine: TemplateEngine
    llm_service: Any | None = None
    transcript_processor: Any | None = None
    config: Any | None = None
    mcp_manager: Any | None = None
    memory_manager: Any | None = None
    memory_sync_manager: Any | None = None
    task_sync_manager: Any | None = None
    session_task_manager: Any | None = None
    event_data: dict[str, Any] | None = None  # Hook event data (e.g., prompt_text)


class ActionHandler(Protocol):
    """Protocol for action handlers."""

    async def __call__(self, context: ActionContext, **kwargs: Any) -> dict[str, Any] | None: ...


class ActionExecutor:
    """Registry and executor for workflow actions."""

    def __init__(
        self,
        db: DatabaseProtocol,
        session_manager: LocalSessionManager,
        template_engine: TemplateEngine,
        llm_service: Any | None = None,
        transcript_processor: Any | None = None,
        config: Any | None = None,
        mcp_manager: Any | None = None,
        memory_manager: Any | None = None,
        memory_sync_manager: Any | None = None,
        task_manager: Any | None = None,
        task_sync_manager: Any | None = None,
        session_task_manager: Any | None = None,
        stop_registry: Any | None = None,
        progress_tracker: Any | None = None,
        stuck_detector: Any | None = None,
        websocket_server: Any | None = None,
    ):
        self.db = db
        self.session_manager = session_manager
        self.template_engine = template_engine
        self.llm_service = llm_service
        self.transcript_processor = transcript_processor
        self.config = config
        self.mcp_manager = mcp_manager
        self.memory_manager = memory_manager
        self.memory_sync_manager = memory_sync_manager
        self.task_manager = task_manager
        self.task_sync_manager = task_sync_manager
        self.session_task_manager = session_task_manager
        self.stop_registry = stop_registry
        self.progress_tracker = progress_tracker
        self.stuck_detector = stuck_detector
        self.websocket_server = websocket_server
        self._handlers: dict[str, ActionHandler] = {}

        self._register_defaults()

    def register(self, name: str, handler: ActionHandler) -> None:
        """Register an action handler."""
        self._handlers[name] = handler

    def register_plugin_actions(self, plugin_registry: Any) -> None:
        """
        Register actions from loaded plugins.

        Actions are registered with the naming convention:
        plugin:<plugin-name>:<action-name>

        Plugin actions with schemas will have their inputs validated before execution.

        Args:
            plugin_registry: PluginRegistry instance containing loaded plugins.
        """
        if plugin_registry is None:
            return

        for plugin_name, plugin in plugin_registry._plugins.items():
            for action_name, plugin_action in plugin._actions.items():
                full_name = f"plugin:{plugin_name}:{action_name}"

                # Create wrapper that validates schema before calling handler
                if plugin_action.schema:
                    wrapper = self._create_validating_wrapper(plugin_action)
                    self._handlers[full_name] = wrapper
                else:
                    # No schema, use handler directly
                    self._handlers[full_name] = plugin_action.handler

                logger.debug(f"Registered plugin action: {full_name}")

    def _create_validating_wrapper(self, plugin_action: Any) -> ActionHandler:
        """Create a wrapper handler that validates input against schema.

        Args:
            plugin_action: PluginAction with schema and handler.

        Returns:
            Wrapper handler that validates before calling the real handler.
        """

        async def validating_handler(
            context: ActionContext, **kwargs: Any
        ) -> dict[str, Any] | None:
            # Validate input against schema
            is_valid, error = plugin_action.validate_input(kwargs)
            if not is_valid:
                logger.warning(f"Plugin action '{plugin_action.name}' validation failed: {error}")
                return {"error": f"Schema validation failed: {error}"}

            # Call the actual handler
            result = await plugin_action.handler(context, **kwargs)
            return dict(result) if isinstance(result, dict) else None

        return validating_handler

    def _register_defaults(self) -> None:
        """Register built-in actions."""
        self.register("inject_context", self._handle_inject_context)
        self.register("inject_message", self._handle_inject_message)
        self.register("capture_artifact", self._handle_capture_artifact)
        self.register("generate_handoff", self._handle_generate_handoff)
        self.register("generate_summary", self._handle_generate_summary)
        self.register("mark_session_status", self._handle_mark_session_status)
        self.register("switch_mode", self._handle_switch_mode)
        self.register("read_artifact", self._handle_read_artifact)
        self.register("load_workflow_state", self._handle_load_workflow_state)
        self.register("save_workflow_state", self._handle_save_workflow_state)
        self.register("set_variable", self._handle_set_variable)
        self.register("increment_variable", self._handle_increment_variable)
        self.register("call_llm", self._handle_call_llm)
        self.register("synthesize_title", self._handle_synthesize_title)
        self.register("write_todos", self._handle_write_todos)
        self.register("mark_todo_complete", self._handle_mark_todo_complete)
        self.register("persist_tasks", self._handle_persist_tasks)
        self.register("get_workflow_tasks", self._handle_get_workflow_tasks)
        self.register("update_workflow_task", self._handle_update_workflow_task)
        self.register("call_mcp_tool", self._handle_call_mcp_tool)
        # Memory actions - underscore pattern (memory_*)
        self.register("memory_save", self._handle_save_memory)
        self.register("memory_recall_relevant", self._handle_memory_recall_relevant)
        self.register("memory_sync_import", self._handle_memory_sync_import)
        self.register("memory_sync_export", self._handle_memory_sync_export)
        self.register(
            "reset_memory_injection_tracking", self._handle_reset_memory_injection_tracking
        )
        # Task sync actions
        self.register("task_sync_import", self._handle_task_sync_import)
        self.register("task_sync_export", self._handle_task_sync_export)
        self.register("extract_handoff_context", self._handle_extract_handoff_context)
        self.register("start_new_session", self._handle_start_new_session)
        self.register("mark_loop_complete", self._handle_mark_loop_complete)
        # Task enforcement
        self.register("require_active_task", self._handle_require_active_task)
        self.register("require_commit_before_stop", self._handle_require_commit_before_stop)
        self.register("require_task_complete", self._handle_require_task_complete)
        self.register("validate_session_task_scope", self._handle_validate_session_task_scope)
        self.register("capture_baseline_dirty_files", self._handle_capture_baseline_dirty_files)
        # Webhook
        self.register("webhook", self._handle_webhook)
        # Stop signal actions
        self.register("check_stop_signal", self._handle_check_stop_signal)
        self.register("request_stop", self._handle_request_stop)
        self.register("clear_stop_signal", self._handle_clear_stop_signal)
        # Autonomous execution actions
        self.register("start_progress_tracking", self._handle_start_progress_tracking)
        self.register("stop_progress_tracking", self._handle_stop_progress_tracking)
        self.register("record_progress", self._handle_record_progress)
        self.register("detect_task_loop", self._handle_detect_task_loop)
        self.register("detect_stuck", self._handle_detect_stuck)
        self.register("record_task_selection", self._handle_record_task_selection)
        self.register("get_progress_summary", self._handle_get_progress_summary)

    async def execute(
        self, action_type: str, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Execute an action."""
        handler = self._handlers.get(action_type)
        if not handler:
            logger.warning(f"Unknown action type: {action_type}")
            return None

        try:
            return await handler(context, **kwargs)
        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}", exc_info=True)
            return {"error": str(e)}

    # --- Action Implementations ---

    async def _handle_inject_context(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Inject context from a source."""
        return inject_context(
            session_manager=context.session_manager,
            session_id=context.session_id,
            state=context.state,
            template_engine=context.template_engine,
            source=kwargs.get("source"),
            template=kwargs.get("template"),
            require=kwargs.get("require", False),
        )

    async def _handle_inject_message(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Inject a message to the user/assistant, rendering it as a template."""
        return inject_message(
            session_manager=context.session_manager,
            session_id=context.session_id,
            state=context.state,
            template_engine=context.template_engine,
            content=kwargs.get("content"),
            **{k: v for k, v in kwargs.items() if k != "content"},
        )

    async def _handle_capture_artifact(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Capture an artifact (file) and store its path in state."""
        return capture_artifact(
            state=context.state,
            pattern=kwargs.get("pattern"),
            save_as=kwargs.get("as"),
        )

    async def _handle_read_artifact(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Read an artifact's content into a workflow variable."""
        return read_artifact(
            state=context.state,
            pattern=kwargs.get("pattern"),
            variable_name=kwargs.get("as"),
        )

    async def _handle_load_workflow_state(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Load workflow state from DB."""
        return load_workflow_state(context.db, context.session_id, context.state)

    async def _handle_save_workflow_state(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Save workflow state to DB."""
        return save_workflow_state(context.db, context.state)

    async def _handle_set_variable(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Set a workflow variable."""
        return set_variable(context.state, kwargs.get("name"), kwargs.get("value"))

    async def _handle_increment_variable(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Increment a numeric workflow variable."""
        return increment_variable(context.state, kwargs.get("name"), kwargs.get("amount", 1))

    async def _handle_call_llm(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Call LLM with a prompt template and store result in variable."""
        return await call_llm(
            llm_service=context.llm_service,
            template_engine=context.template_engine,
            state=context.state,
            session=context.session_manager.get(context.session_id),
            prompt=kwargs.get("prompt"),
            output_as=kwargs.get("output_as"),
            **{k: v for k, v in kwargs.items() if k not in ("prompt", "output_as")},
        )

    async def _handle_synthesize_title(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Synthesize and set a session title."""
        # Extract prompt from event data (UserPromptSubmit hook)
        prompt = None
        if context.event_data:
            prompt = context.event_data.get("prompt")

        return await synthesize_title(
            session_manager=context.session_manager,
            session_id=context.session_id,
            llm_service=context.llm_service,
            transcript_processor=context.transcript_processor,
            template_engine=context.template_engine,
            template=kwargs.get("template"),
            prompt=prompt,
        )

    async def _handle_write_todos(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Write todos to a file (default TODO.md)."""
        return write_todos(
            todos=kwargs.get("todos", []),
            filename=kwargs.get("filename", "TODO.md"),
            mode=kwargs.get("mode", "w"),
        )

    async def _handle_mark_todo_complete(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Mark a todo as complete in TODO.md."""
        return mark_todo_complete(
            todo_text=kwargs.get("todo_text", ""),
            filename=kwargs.get("filename", "TODO.md"),
        )

    async def _handle_memory_sync_import(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Import memories from filesystem."""
        return await memory_sync_import(context.memory_sync_manager)

    async def _handle_memory_sync_export(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Export memories to filesystem."""
        return await memory_sync_export(context.memory_sync_manager)

    async def _handle_task_sync_import(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Import tasks from JSONL file.

        Reads .gobby/tasks.jsonl and imports tasks into SQLite using
        Last-Write-Wins conflict resolution based on updated_at.
        """
        if not context.task_sync_manager:
            logger.debug("task_sync_import: No task_sync_manager available")
            return {"error": "Task Sync Manager not available"}

        try:
            # Get project_id from session for project-scoped sync
            project_id = None
            session = context.session_manager.get(context.session_id)
            if session:
                project_id = session.project_id

            context.task_sync_manager.import_from_jsonl(project_id=project_id)
            logger.info("Task sync import completed")
            return {"imported": True}
        except Exception as e:
            logger.error(f"task_sync_import failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _handle_task_sync_export(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Export tasks to JSONL file.

        Writes tasks and dependencies to .gobby/tasks.jsonl for Git persistence.
        Uses content hashing to skip writes if nothing changed.
        """
        if not context.task_sync_manager:
            logger.debug("task_sync_export: No task_sync_manager available")
            return {"error": "Task Sync Manager not available"}

        try:
            # Get project_id from session for project-scoped sync
            project_id = None
            session = context.session_manager.get(context.session_id)
            if session:
                project_id = session.project_id

            context.task_sync_manager.export_to_jsonl(project_id=project_id)
            logger.info("Task sync export completed")
            return {"exported": True}
        except Exception as e:
            logger.error(f"task_sync_export failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _handle_persist_tasks(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Persist a list of task dicts to Gobby task system.

        Enhanced to support workflow integration with ID mapping.

        Args (via kwargs):
            tasks: List of task dicts (or source variable name)
            source: Variable name containing task list (alternative to tasks)
            workflow_name: Associate tasks with this workflow
            parent_task_id: Optional parent task for all created tasks

        Returns:
            Dict with tasks_persisted count, ids list, and id_mapping dict
        """
        # Get tasks from either 'tasks' kwarg or 'source' variable
        tasks = kwargs.get("tasks", [])
        source = kwargs.get("source")

        if source and context.state.variables:
            source_data = context.state.variables.get(source)
            if source_data:
                # Handle nested structure like task_list.tasks
                if isinstance(source_data, dict) and "tasks" in source_data:
                    tasks = source_data["tasks"]
                elif isinstance(source_data, list):
                    tasks = source_data

        if not tasks:
            return {"tasks_persisted": 0, "ids": [], "id_mapping": {}}

        try:
            from gobby.workflows.task_actions import persist_decomposed_tasks

            current_session = context.session_manager.get(context.session_id)
            project_id = current_session.project_id if current_session else "default"

            # Get workflow name from kwargs or state
            workflow_name = kwargs.get("workflow_name")
            if not workflow_name and context.state.workflow_name:
                workflow_name = context.state.workflow_name

            parent_task_id = kwargs.get("parent_task_id")

            id_mapping = persist_decomposed_tasks(
                db=context.db,
                project_id=project_id,
                tasks_data=tasks,
                workflow_name=workflow_name or "unnamed",
                parent_task_id=parent_task_id,
                created_in_session_id=context.session_id,
            )

            # Store ID mapping in workflow state for reference
            if not context.state.variables:
                context.state.variables = {}
            context.state.variables["task_id_mapping"] = id_mapping

            return {
                "tasks_persisted": len(id_mapping),
                "ids": list(id_mapping.values()),
                "id_mapping": id_mapping,
            }
        except Exception as e:
            logger.error(f"persist_tasks: Failed: {e}")
            return {"error": str(e)}

    async def _handle_get_workflow_tasks(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Get tasks associated with the current workflow.

        Args (via kwargs):
            workflow_name: Override workflow name (defaults to current)
            include_closed: Include closed tasks (default: False)
            as: Variable name to store result in

        Returns:
            Dict with tasks list and count
        """
        from gobby.workflows.task_actions import get_workflow_tasks

        workflow_name = kwargs.get("workflow_name")
        if not workflow_name and context.state.workflow_name:
            workflow_name = context.state.workflow_name

        if not workflow_name:
            return {"error": "No workflow name specified"}

        current_session = context.session_manager.get(context.session_id)
        project_id = current_session.project_id if current_session else None

        include_closed = kwargs.get("include_closed", False)

        tasks = get_workflow_tasks(
            db=context.db,
            workflow_name=workflow_name,
            project_id=project_id,
            include_closed=include_closed,
        )

        # Convert to dicts for YAML/JSON serialization
        tasks_data = [t.to_dict() for t in tasks]

        # Store in variable if requested
        output_as = kwargs.get("as")
        if output_as:
            if not context.state.variables:
                context.state.variables = {}
            context.state.variables[output_as] = tasks_data

        # Also update task_list in state for workflow engine use
        context.state.task_list = [
            {"id": t.id, "title": t.title, "status": t.status} for t in tasks
        ]

        return {"tasks": tasks_data, "count": len(tasks)}

    async def _handle_update_workflow_task(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Update a task from workflow context.

        Args (via kwargs):
            task_id: ID of task to update (required)
            status: New status
            verification: Verification result
            validation_status: Validation status

        Returns:
            Dict with updated task data
        """
        from gobby.workflows.task_actions import update_task_from_workflow

        task_id = kwargs.get("task_id")
        if not task_id:
            # Try to get from current_task_index in state
            if context.state.task_list and context.state.current_task_index is not None:
                idx = context.state.current_task_index
                if 0 <= idx < len(context.state.task_list):
                    task_id = context.state.task_list[idx].get("id")

        if not task_id:
            return {"error": "No task_id specified"}

        task = update_task_from_workflow(
            db=context.db,
            task_id=task_id,
            status=kwargs.get("status"),
            verification=kwargs.get("verification"),
            validation_status=kwargs.get("validation_status"),
            validation_feedback=kwargs.get("validation_feedback"),
        )

        if task:
            return {"updated": True, "task": task.to_dict()}
        return {"updated": False, "error": "Task not found"}

    async def _handle_call_mcp_tool(
        self,
        context: ActionContext,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Call an MCP tool on a connected server."""
        return await call_mcp_tool(
            mcp_manager=context.mcp_manager,
            state=context.state,
            server_name=kwargs.get("server_name"),
            tool_name=kwargs.get("tool_name"),
            arguments=kwargs.get("arguments"),
            output_as=kwargs.get("as"),
        )

    async def _handle_generate_handoff(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Generate a handoff record (summary + mark status).

        For compact mode, fetches the current session's existing summary_markdown
        as previous_summary for cumulative compression.
        """
        # Detect mode from kwargs or event data
        mode = kwargs.get("mode", "clear")

        # Check if this is a compact event based on event_data
        # Use precise matching against known compact event types to avoid false positives
        COMPACT_EVENT_TYPES = {"pre_compact", "compact"}
        if context.event_data:
            raw_event_type = context.event_data.get("event_type") or ""
            normalized_event_type = str(raw_event_type).strip().lower()
            if normalized_event_type in COMPACT_EVENT_TYPES:
                mode = "compact"

        # For compact mode, fetch previous summary for cumulative compression
        previous_summary = None
        if mode == "compact":
            current_session = context.session_manager.get(context.session_id)
            if current_session:
                previous_summary = getattr(current_session, "summary_markdown", None)
                if previous_summary:
                    logger.debug(
                        f"Compact mode: using previous summary ({len(previous_summary)} chars) "
                        f"for cumulative compression"
                    )

        return await generate_handoff(
            session_manager=context.session_manager,
            session_id=context.session_id,
            llm_service=context.llm_service,
            transcript_processor=context.transcript_processor,
            template=kwargs.get("template"),
            previous_summary=previous_summary,
            mode=mode,
        )

    async def _handle_generate_summary(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Generate a session summary using LLM."""
        return await generate_summary(
            session_manager=context.session_manager,
            session_id=context.session_id,
            llm_service=context.llm_service,
            transcript_processor=context.transcript_processor,
            template=kwargs.get("template"),
        )

    async def _handle_start_new_session(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Start a new CLI session (chaining)."""
        return start_new_session(
            session_manager=context.session_manager,
            session_id=context.session_id,
            command=kwargs.get("command"),
            args=kwargs.get("args"),
            prompt=kwargs.get("prompt"),
            cwd=kwargs.get("cwd"),
        )

    async def _handle_mark_loop_complete(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Mark the autonomous loop as complete."""
        return mark_loop_complete(context.state)

    async def _handle_extract_handoff_context(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Extract handoff context from transcript and save to session.compact_markdown."""
        return extract_handoff_context(
            session_manager=context.session_manager,
            session_id=context.session_id,
            config=context.config,
            db=self.db,
        )

    def _format_handoff_as_markdown(self, ctx: Any, prompt_template: str | None = None) -> str:
        """Format HandoffContext as markdown for injection."""
        return format_handoff_as_markdown(ctx, prompt_template)

    async def _handle_save_memory(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Save a memory directly from workflow context."""
        return await memory_save(
            memory_manager=context.memory_manager,
            session_manager=context.session_manager,
            session_id=context.session_id,
            content=kwargs.get("content"),
            memory_type=kwargs.get("memory_type", "fact"),
            importance=kwargs.get("importance", 0.5),
            tags=kwargs.get("tags"),
            project_id=kwargs.get("project_id"),
        )

    async def _handle_memory_recall_relevant(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Recall memories relevant to the current user prompt."""
        prompt_text = None
        if context.event_data:
            # Check both "prompt" (from hook event) and "prompt_text" (legacy/alternative)
            prompt_text = context.event_data.get("prompt") or context.event_data.get("prompt_text")

        return await memory_recall_relevant(
            memory_manager=context.memory_manager,
            session_manager=context.session_manager,
            session_id=context.session_id,
            prompt_text=prompt_text,
            project_id=kwargs.get("project_id"),
            limit=kwargs.get("limit", 5),
            min_importance=kwargs.get("min_importance", 0.3),
            state=context.state,
        )

    async def _handle_reset_memory_injection_tracking(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Reset memory injection tracking to allow re-injection after context loss."""
        return reset_memory_injection_tracking(state=context.state)

    async def _handle_mark_session_status(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Mark a session status (current or parent)."""
        return mark_session_status(
            session_manager=context.session_manager,
            session_id=context.session_id,
            status=kwargs.get("status"),
            target=kwargs.get("target", "current_session"),
        )

    async def _handle_switch_mode(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Signal the agent to switch modes (e.g., PLAN, ACT)."""
        return switch_mode(kwargs.get("mode"))

    def _format_turns_for_llm(self, turns: list[dict[str, Any]]) -> str:
        """Format transcript turns for LLM analysis."""
        return format_turns_for_llm(turns)

    def _get_git_status(self) -> str:
        """Get git status for current directory."""
        return get_git_status()

    def _get_recent_git_commits(self, max_commits: int = 10) -> list[dict[str, str]]:
        """Get recent git commits with hash and message."""
        return get_recent_git_commits(max_commits)

    def _get_file_changes(self) -> str:
        """Get detailed file changes from git."""
        return get_file_changes()

    async def _handle_capture_baseline_dirty_files(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Capture baseline dirty files at session start."""
        # Get project path - prioritize session lookup over hook payload
        project_path = None

        # 1. Get from session's project (most reliable - session exists by now)
        if context.session_id and context.session_manager:
            session = context.session_manager.get(context.session_id)
            if session and session.project_id:
                from gobby.storage.projects import LocalProjectManager

                project_mgr = LocalProjectManager(context.db)
                project = project_mgr.get(session.project_id)
                if project and project.repo_path:
                    project_path = project.repo_path

        # 2. Fallback to event_data.cwd (from hook payload)
        if not project_path and context.event_data:
            project_path = context.event_data.get("cwd")

        return await capture_baseline_dirty_files(
            workflow_state=context.state,
            project_path=project_path,
        )

    async def _handle_require_active_task(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Check for active task before allowing protected tools."""
        # Get project_id from session for project-scoped task filtering
        current_session = context.session_manager.get(context.session_id)
        project_id = current_session.project_id if current_session else None

        return await require_active_task(
            task_manager=self.task_manager,
            session_id=context.session_id,
            config=context.config,
            event_data=context.event_data,
            project_id=project_id,
            workflow_state=context.state,
            session_manager=context.session_manager,
            session_task_manager=context.session_task_manager,
        )

    async def _handle_require_commit_before_stop(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Block stop if task has uncommitted changes."""
        # Get project path - prioritize session lookup over hook payload
        project_path = None

        # 1. Get from session's project (most reliable - session exists by now)
        if context.session_id and context.session_manager:
            session = context.session_manager.get(context.session_id)
            if session and session.project_id:
                from gobby.storage.projects import LocalProjectManager

                project_mgr = LocalProjectManager(context.db)
                project = project_mgr.get(session.project_id)
                if project and project.repo_path:
                    project_path = project.repo_path

        # 2. Fallback to event_data.cwd (from hook payload)
        if not project_path and context.event_data:
            project_path = context.event_data.get("cwd")

        return await require_commit_before_stop(
            workflow_state=context.state,
            project_path=project_path,
            task_manager=self.task_manager,
        )

    async def _handle_require_task_complete(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Check that a task (and its subtasks) are complete before allowing stop.

        Supports:
        - Single task ID: "#47"
        - List of task IDs: ["#47", "#48"]
        - Wildcard: "*" - work until no ready tasks remain
        """
        current_session = context.session_manager.get(context.session_id)
        project_id = current_session.project_id if current_session else None

        # Get task_id from kwargs - may be a template that needs resolving
        task_spec = kwargs.get("task_id")

        # If it's a template reference like "{{ variables.session_task }}", resolve it
        if task_spec and "{{" in str(task_spec):
            task_spec = context.template_engine.render(
                str(task_spec),
                {"variables": context.state.variables or {}},
            )

        # Handle different task_spec types:
        # - None/empty: no enforcement
        # - "*": wildcard - fetch ready tasks
        # - list: multiple specific tasks
        # - string: single task ID
        task_ids: list[str] | None = None

        if not task_spec:
            return None
        elif task_spec == "*":
            # Wildcard: get all ready tasks for this project
            if self.task_manager:
                ready_tasks = self.task_manager.list_ready_tasks(
                    project_id=project_id,
                    limit=100,
                )
                task_ids = [t.id for t in ready_tasks]
                if not task_ids:
                    # No ready tasks - allow stop
                    logger.debug("require_task_complete: Wildcard mode, no ready tasks")
                    return None
        elif isinstance(task_spec, list):
            task_ids = task_spec
        else:
            task_ids = [str(task_spec)]

        return await require_task_complete(
            task_manager=self.task_manager,
            session_id=context.session_id,
            task_ids=task_ids,
            event_data=context.event_data,
            project_id=project_id,
            workflow_state=context.state,
        )

    async def _handle_validate_session_task_scope(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Validate that claimed task is within session_task scope.

        When session_task is set in workflow state, this blocks claiming
        tasks that are not descendants of session_task.
        """
        return await validate_session_task_scope(
            task_manager=self.task_manager,
            workflow_state=context.state,
            event_data=context.event_data,
        )

    async def _handle_webhook(self, context: ActionContext, **kwargs: Any) -> dict[str, Any] | None:
        """Execute a webhook HTTP request.

        Args (via kwargs):
            url: Target URL for the request (required unless webhook_id provided)
            webhook_id: ID of a pre-configured webhook (alternative to url)
            method: HTTP method (GET, POST, PUT, PATCH, DELETE), default: POST
            headers: Request headers dict (supports ${secrets.VAR} interpolation)
            payload: Request body as dict or string (supports template interpolation)
            timeout: Request timeout in seconds (1-300), default: 30
            retry: Retry configuration dict with:
                - max_attempts: Max retry attempts (1-10), default: 3
                - backoff_seconds: Initial backoff delay, default: 1
                - retry_on_status: HTTP status codes to retry on
            capture_response: Response capture config with:
                - status_var: Variable name for status code
                - body_var: Variable name for response body
                - headers_var: Variable name for response headers
            on_success: Step to transition to on success (2xx)
            on_failure: Step to transition to on failure

        Returns:
            Dict with success status, status_code, and captured response data.
        """
        try:
            # Parse WebhookAction from kwargs to validate config
            webhook_action = WebhookAction.from_dict(kwargs)
        except ValueError as e:
            logger.error(f"Invalid webhook action config: {e}")
            return {"success": False, "error": str(e)}

        # Build context for variable interpolation
        interpolation_context: dict[str, Any] = {}
        if context.state.variables:
            interpolation_context["state"] = {"variables": context.state.variables}
        if context.state.artifacts:
            interpolation_context["artifacts"] = context.state.artifacts

        # Get secrets from config if available
        secrets: dict[str, str] = {}
        if self.config:
            secrets = getattr(self.config, "webhook_secrets", {})

        # Create executor with template engine for payload interpolation
        executor = WebhookExecutor(
            template_engine=context.template_engine,
            secrets=secrets,
        )

        # Execute the webhook
        if webhook_action.url:
            result = await executor.execute(
                url=webhook_action.url,
                method=webhook_action.method,
                headers=webhook_action.headers,
                payload=webhook_action.payload,
                timeout=webhook_action.timeout,
                retry_config=webhook_action.retry.to_dict() if webhook_action.retry else None,
                context=interpolation_context,
            )
        elif webhook_action.webhook_id:
            # webhook_id execution requires a registry which would be configured
            # at the daemon level - for now we return an error if no registry
            logger.warning("webhook_id execution not yet supported without registry")
            return {"success": False, "error": "webhook_id requires configured webhook registry"}
        else:
            return {"success": False, "error": "Either url or webhook_id is required"}

        # Capture response into workflow variables if configured
        if webhook_action.capture_response:
            if not context.state.variables:
                context.state.variables = {}

            capture = webhook_action.capture_response
            if capture.status_var and result.status_code is not None:
                context.state.variables[capture.status_var] = result.status_code
            if capture.body_var and result.body is not None:
                # Try to parse as JSON, fall back to raw string
                json_body = result.json_body()
                context.state.variables[capture.body_var] = json_body if json_body else result.body
            if capture.headers_var and result.headers is not None:
                context.state.variables[capture.headers_var] = result.headers

        # Log outcome
        if result.success:
            logger.info(
                f"Webhook {webhook_action.method} {webhook_action.url} succeeded: {result.status_code}"
            )
        else:
            logger.warning(
                f"Webhook {webhook_action.method} {webhook_action.url} failed: "
                f"{result.error or result.status_code}"
            )

        return {
            "success": result.success,
            "status_code": result.status_code,
            "error": result.error,
            "body": result.body if result.success else None,
        }

    # --- Stop Signal Actions ---

    async def _handle_check_stop_signal(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Check if a stop signal has been sent for this session.

        Args (via kwargs):
            acknowledge: If True, acknowledge the signal (session will stop)

        Returns:
            Dict with has_signal, signal details, and optional inject_context
        """
        return check_stop_signal(
            stop_registry=self.stop_registry,
            session_id=context.session_id,
            state=context.state,
            acknowledge=kwargs.get("acknowledge", False),
        )

    async def _handle_request_stop(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Request a session to stop (used by stuck detection, etc.).

        Args (via kwargs):
            session_id: The session to signal (defaults to current session)
            source: Source of the request (default: "workflow")
            reason: Optional reason for the stop request

        Returns:
            Dict with success status and signal details
        """
        target_session = kwargs.get("session_id", context.session_id)
        return request_stop(
            stop_registry=self.stop_registry,
            session_id=target_session,
            source=kwargs.get("source", "workflow"),
            reason=kwargs.get("reason"),
        )

    async def _handle_clear_stop_signal(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Clear any stop signal for a session.

        Args (via kwargs):
            session_id: The session to clear (defaults to current session)

        Returns:
            Dict with success status
        """
        target_session = kwargs.get("session_id", context.session_id)
        return clear_stop_signal(
            stop_registry=self.stop_registry,
            session_id=target_session,
        )

    # --- Autonomous Execution Actions ---

    async def _broadcast_autonomous_event(self, event: str, session_id: str, **kwargs: Any) -> None:
        """Helper to broadcast autonomous events via WebSocket.

        Non-blocking fire-and-forget broadcast.

        Args:
            event: Event type (task_started, stuck_detected, etc.)
            session_id: Session ID
            **kwargs: Additional event data
        """
        import asyncio

        if not self.websocket_server:
            return

        try:
            # Create non-blocking task for broadcast
            task = asyncio.create_task(
                self.websocket_server.broadcast_autonomous_event(
                    event=event,
                    session_id=session_id,
                    **kwargs,
                )
            )
            # Add callback to log errors silently
            task.add_done_callback(
                lambda t: (
                    logger.debug(f"Broadcast {event} failed: {t.exception()}")
                    if t.exception()
                    else None
                )
            )
        except Exception as e:
            logger.debug(f"Failed to schedule broadcast for {event}: {e}")

    async def _handle_start_progress_tracking(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Start progress tracking for a session."""
        result = start_progress_tracking(
            progress_tracker=self.progress_tracker,
            session_id=context.session_id,
            state=context.state,
        )

        # Broadcast loop_started event
        if result and result.get("success"):
            await self._broadcast_autonomous_event(
                event="loop_started",
                session_id=context.session_id,
            )

        return result

    async def _handle_stop_progress_tracking(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Stop progress tracking for a session."""
        result = stop_progress_tracking(
            progress_tracker=self.progress_tracker,
            session_id=context.session_id,
            state=context.state,
            keep_data=kwargs.get("keep_data", False),
        )

        # Broadcast loop_stopped event
        if result and result.get("success"):
            await self._broadcast_autonomous_event(
                event="loop_stopped",
                session_id=context.session_id,
                final_summary=result.get("final_summary"),
            )

        return result

    async def _handle_record_progress(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Record a progress event."""
        result = record_progress(
            progress_tracker=self.progress_tracker,
            session_id=context.session_id,
            progress_type=kwargs.get("progress_type", "tool_call"),
            tool_name=kwargs.get("tool_name"),
            details=kwargs.get("details"),
        )

        # Broadcast progress_recorded event for high-value events
        if result and result.get("success") and result.get("event", {}).get("is_high_value"):
            await self._broadcast_autonomous_event(
                event="progress_recorded",
                session_id=context.session_id,
                progress_type=result.get("event", {}).get("type"),
                is_high_value=True,
            )

        return result

    async def _handle_detect_task_loop(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Detect task selection loops."""
        result = detect_task_loop(
            stuck_detector=self.stuck_detector,
            session_id=context.session_id,
            state=context.state,
        )

        # Broadcast stuck_detected if stuck
        if result and result.get("is_stuck"):
            await self._broadcast_autonomous_event(
                event="stuck_detected",
                session_id=context.session_id,
                layer="task_loop",
                reason=result.get("reason"),
                details=result.get("details"),
            )

        return result

    async def _handle_detect_stuck(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Run full stuck detection (all layers)."""
        result = detect_stuck(
            stuck_detector=self.stuck_detector,
            session_id=context.session_id,
            state=context.state,
        )

        # Broadcast stuck_detected if stuck
        if result and result.get("is_stuck"):
            await self._broadcast_autonomous_event(
                event="stuck_detected",
                session_id=context.session_id,
                layer=result.get("layer"),
                reason=result.get("reason"),
                suggested_action=result.get("suggested_action"),
            )

        return result

    async def _handle_record_task_selection(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Record a task selection for loop detection."""
        task_id = kwargs.get("task_id", "")
        result = record_task_selection(
            stuck_detector=self.stuck_detector,
            session_id=context.session_id,
            task_id=task_id,
            context=kwargs.get("context"),
        )

        # Broadcast task_started event
        if result and result.get("success"):
            await self._broadcast_autonomous_event(
                event="task_started",
                session_id=context.session_id,
                task_id=task_id,
            )

        return result

    async def _handle_get_progress_summary(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Get a summary of progress for a session."""
        return get_progress_summary(
            progress_tracker=self.progress_tracker,
            session_id=context.session_id,
        )
