from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from gobby.storage.database import DatabaseProtocol
from gobby.storage.sessions import LocalSessionManager
from gobby.workflows.artifact_actions import (
    handle_capture_artifact,
    handle_read_artifact,
)
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
    handle_extract_handoff_context,
    handle_inject_context,
    handle_inject_message,
)
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.enforcement import (
    handle_block_tools,
    handle_capture_baseline_dirty_files,
    handle_require_active_task,
    handle_require_commit_before_stop,
    handle_require_task_complete,
    handle_require_task_review_or_close_before_stop,
    handle_track_schema_lookup,
    handle_validate_session_task_scope,
)
from gobby.workflows.llm_actions import handle_call_llm
from gobby.workflows.mcp_actions import handle_call_mcp_tool
from gobby.workflows.memory_actions import (
    handle_memory_extract,
    handle_memory_recall_relevant,
    handle_memory_save,
    handle_memory_sync_export,
    handle_memory_sync_import,
    handle_reset_memory_injection_tracking,
)
from gobby.workflows.session_actions import (
    handle_mark_session_status,
    handle_start_new_session,
    handle_switch_mode,
)
from gobby.workflows.state_actions import (
    handle_increment_variable,
    handle_load_workflow_state,
    handle_mark_loop_complete,
    handle_save_workflow_state,
    handle_set_variable,
)
from gobby.workflows.stop_signal_actions import (
    check_stop_signal,
    clear_stop_signal,
    request_stop,
)
from gobby.workflows.summary_actions import (
    handle_generate_handoff,
    handle_generate_summary,
    handle_synthesize_title,
)
from gobby.workflows.task_sync_actions import (
    handle_get_workflow_tasks,
    handle_persist_tasks,
    handle_task_sync_export,
    handle_task_sync_import,
    handle_update_workflow_task,
)
from gobby.workflows.templates import TemplateEngine
from gobby.workflows.todo_actions import (
    handle_mark_todo_complete,
    handle_write_todos,
)
from gobby.workflows.webhook_actions import handle_webhook

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
        """Register actions from loaded plugins."""
        if plugin_registry is None:
            return

        for plugin_name, plugin in plugin_registry._plugins.items():
            for action_name, plugin_action in plugin._actions.items():
                full_name = f"plugin:{plugin_name}:{action_name}"

                if plugin_action.schema:
                    wrapper = self._create_validating_wrapper(plugin_action)
                    self._handlers[full_name] = wrapper
                else:
                    self._handlers[full_name] = plugin_action.handler

                logger.debug(f"Registered plugin action: {full_name}")

    def _create_validating_wrapper(self, plugin_action: Any) -> ActionHandler:
        """Create a wrapper handler that validates input against schema."""

        async def validating_handler(
            context: ActionContext, **kwargs: Any
        ) -> dict[str, Any] | None:
            is_valid, error = plugin_action.validate_input(kwargs)
            if not is_valid:
                logger.warning(f"Plugin action '{plugin_action.name}' validation failed: {error}")
                return {"error": f"Schema validation failed: {error}"}

            result = await plugin_action.handler(context, **kwargs)
            return dict(result) if isinstance(result, dict) else None

        return validating_handler

    def _register_defaults(self) -> None:
        """Register built-in actions using external handlers."""
        # --- Context/injection actions ---
        self.register("inject_context", handle_inject_context)
        self.register("inject_message", handle_inject_message)
        self.register("extract_handoff_context", handle_extract_handoff_context)

        # --- Artifact actions ---
        self.register("capture_artifact", handle_capture_artifact)
        self.register("read_artifact", handle_read_artifact)

        # --- State actions ---
        self.register("load_workflow_state", handle_load_workflow_state)
        self.register("save_workflow_state", handle_save_workflow_state)
        self.register("set_variable", handle_set_variable)
        self.register("increment_variable", handle_increment_variable)
        self.register("mark_loop_complete", handle_mark_loop_complete)

        # --- Session actions ---
        self.register("start_new_session", handle_start_new_session)
        self.register("mark_session_status", handle_mark_session_status)
        self.register("switch_mode", handle_switch_mode)

        # --- Todo actions ---
        self.register("write_todos", handle_write_todos)
        self.register("mark_todo_complete", handle_mark_todo_complete)

        # --- LLM actions ---
        self.register("call_llm", handle_call_llm)

        # --- MCP actions ---
        self.register("call_mcp_tool", handle_call_mcp_tool)

        # --- Summary actions ---
        self.register("synthesize_title", handle_synthesize_title)
        self.register("generate_summary", handle_generate_summary)
        self.register("generate_handoff", handle_generate_handoff)

        # --- Memory actions ---
        self.register("memory_save", handle_memory_save)
        self.register("memory_recall_relevant", handle_memory_recall_relevant)
        self.register("memory_sync_import", handle_memory_sync_import)
        self.register("memory_sync_export", handle_memory_sync_export)
        self.register("memory_extract", handle_memory_extract)
        self.register("reset_memory_injection_tracking", handle_reset_memory_injection_tracking)

        # --- Task sync actions ---
        self.register("task_sync_import", handle_task_sync_import)
        self.register("task_sync_export", handle_task_sync_export)
        self.register("persist_tasks", handle_persist_tasks)
        self.register("get_workflow_tasks", handle_get_workflow_tasks)
        self.register("update_workflow_task", handle_update_workflow_task)

        # --- Task enforcement actions (closures for task_manager access) ---
        self._register_task_enforcement_actions()

        # --- Webhook (closure for config access) ---
        self._register_webhook_action()

        # --- Stop signal actions (closures for stop_registry access) ---
        self._register_stop_signal_actions()

        # --- Autonomous execution actions (closures for progress_tracker/stuck_detector) ---
        self._register_autonomous_actions()

    def _register_task_enforcement_actions(self) -> None:
        """Register task enforcement actions with task_manager closure."""
        tm = self.task_manager
        te = self.template_engine

        async def block_tools(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_block_tools(context, task_manager=tm, **kw)

        async def require_active(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_require_active_task(context, task_manager=tm, **kw)

        async def require_complete(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_require_task_complete(
                context, task_manager=tm, template_engine=te, **kw
            )

        async def require_commit(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_require_commit_before_stop(context, task_manager=tm, **kw)

        async def require_review(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_require_task_review_or_close_before_stop(
                context, task_manager=tm, **kw
            )

        async def validate_scope(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_validate_session_task_scope(context, task_manager=tm, **kw)

        async def capture_baseline(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_capture_baseline_dirty_files(context, task_manager=tm, **kw)

        async def track_schema(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_track_schema_lookup(context, task_manager=tm, **kw)

        self.register("block_tools", block_tools)
        self.register("require_active_task", require_active)
        self.register("require_task_complete", require_complete)
        self.register("require_commit_before_stop", require_commit)
        self.register("require_task_review_or_close_before_stop", require_review)
        self.register("validate_session_task_scope", validate_scope)
        self.register("capture_baseline_dirty_files", capture_baseline)
        self.register("track_schema_lookup", track_schema)

    def _register_webhook_action(self) -> None:
        """Register webhook action with config closure."""
        cfg = self.config

        async def webhook(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return await handle_webhook(context, config=cfg, **kw)

        self.register("webhook", webhook)

    def _register_stop_signal_actions(self) -> None:
        """Register stop signal actions accessing self at call time."""
        executor = self

        async def check_stop(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return check_stop_signal(
                executor.stop_registry,
                context.session_id,
                context.state,
                kw.get("acknowledge", False),
            )

        async def req_stop(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return request_stop(
                executor.stop_registry,
                context.session_id,
                kw.get("source", "workflow"),
                kw.get("reason"),
            )

        async def clear_stop(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return clear_stop_signal(
                executor.stop_registry, kw.get("session_id") or context.session_id
            )

        self.register("check_stop_signal", check_stop)
        self.register("request_stop", req_stop)
        self.register("clear_stop_signal", clear_stop)

    def _register_autonomous_actions(self) -> None:
        """Register autonomous actions accessing self at call time."""
        executor = self

        async def start_tracking(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return start_progress_tracking(
                executor.progress_tracker, context.session_id, context.state
            )

        async def stop_tracking(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return stop_progress_tracking(
                executor.progress_tracker,
                context.session_id,
                context.state,
                kw.get("keep_data", False),
            )

        async def record_prog(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return record_progress(
                executor.progress_tracker,
                context.session_id,
                kw.get("progress_type", "tool_call"),
                kw.get("tool_name"),
                kw.get("details"),
            )

        async def detect_loop(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return detect_task_loop(executor.stuck_detector, context.session_id, context.state)

        async def detect_stk(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return detect_stuck(executor.stuck_detector, context.session_id, context.state)

        async def record_sel(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return record_task_selection(
                executor.stuck_detector,
                context.session_id,
                kw.get("task_id", ""),
                kw.get("context"),
            )

        async def get_summary(context: ActionContext, **kw: Any) -> dict[str, Any] | None:
            return get_progress_summary(executor.progress_tracker, context.session_id)

        self.register("start_progress_tracking", start_tracking)
        self.register("stop_progress_tracking", stop_tracking)
        self.register("record_progress", record_prog)
        self.register("detect_task_loop", detect_loop)
        self.register("detect_stuck", detect_stk)
        self.register("record_task_selection", record_sel)
        self.register("get_progress_summary", get_summary)

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
