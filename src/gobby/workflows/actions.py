import logging
from dataclasses import dataclass
from typing import Any, Protocol

from gobby.storage.database import LocalDatabase
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks import LocalTaskManager  # noqa: F401
from gobby.workflows.context_actions import (
    extract_handoff_context,
    format_handoff_as_markdown,
    inject_context,
    inject_message,
    restore_context,
)
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.git_utils import get_file_changes, get_git_status, get_recent_git_commits
from gobby.workflows.memory_actions import (
    memory_extract,
    memory_inject,
    memory_recall_relevant,
    memory_save,
    memory_sync_export,
    memory_sync_import,
)
from gobby.workflows.summary_actions import (
    format_turns_for_llm,
    generate_handoff,
    generate_summary,
    synthesize_title,
)
from gobby.workflows.templates import TemplateEngine

logger = logging.getLogger(__name__)


@dataclass
class ActionContext:
    """Context passed to action handlers."""

    session_id: str
    state: WorkflowState
    db: LocalDatabase
    session_manager: LocalSessionManager
    template_engine: TemplateEngine
    llm_service: Any | None = None
    transcript_processor: Any | None = None
    config: Any | None = None
    mcp_manager: Any | None = None
    memory_manager: Any | None = None
    skill_learner: Any | None = None
    memory_sync_manager: Any | None = None
    event_data: dict[str, Any] | None = None  # Hook event data (e.g., prompt_text)


class ActionHandler(Protocol):
    """Protocol for action handlers."""

    async def __call__(self, context: ActionContext, **kwargs: Any) -> dict[str, Any] | None: ...


class ActionExecutor:
    """Registry and executor for workflow actions."""

    def __init__(
        self,
        db: LocalDatabase,
        session_manager: LocalSessionManager,
        template_engine: TemplateEngine,
        llm_service: Any | None = None,
        transcript_processor: Any | None = None,
        config: Any | None = None,
        mcp_manager: Any | None = None,
        memory_manager: Any | None = None,
        skill_learner: Any | None = None,
        memory_sync_manager: Any | None = None,
        skill_sync_manager: Any | None = None,
    ):
        self.db = db
        self.session_manager = session_manager
        self.template_engine = template_engine
        self.llm_service = llm_service
        self.transcript_processor = transcript_processor
        self.config = config
        self.mcp_manager = mcp_manager
        self.memory_manager = memory_manager
        self.skill_learner = skill_learner
        self.memory_sync_manager = memory_sync_manager
        self.skill_sync_manager = skill_sync_manager
        self._handlers: dict[str, ActionHandler] = {}
        self._register_defaults()

    def register(self, name: str, handler: ActionHandler) -> None:
        """Register an action handler."""
        self._handlers[name] = handler

    def _register_defaults(self) -> None:
        """Register built-in actions."""
        self.register("inject_context", self._handle_inject_context)
        self.register("inject_message", self._handle_inject_message)
        self.register("capture_artifact", self._handle_capture_artifact)
        self.register("generate_handoff", self._handle_generate_handoff)
        self.register("generate_summary", self._handle_generate_summary)
        self.register("restore_context", self._handle_restore_context)
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
        self.register("memory_inject", self._handle_memory_inject)
        self.register("memory_extract", self._handle_memory_extract)
        self.register("memory_save", self._handle_save_memory)
        self.register("memory_recall_relevant", self._handle_memory_recall_relevant)
        self.register("memory_sync_import", self._handle_memory_sync_import)
        self.register("memory_sync_export", self._handle_memory_sync_export)
        # Skills
        self.register("skills_learn", self._handle_skills_learn)
        self.register("extract_handoff_context", self._handle_extract_handoff_context)
        self.register("start_new_session", self._handle_start_new_session)
        self.register("mark_loop_complete", self._handle_mark_loop_complete)

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
        """
        Capture an artifact (file) and store its path/content in state.
        """
        pattern = kwargs.get("pattern")
        if not pattern:
            return None

        import glob
        import os

        # Security check: Ensure pattern is relative and within allowed paths?
        # For now, assume agent has access to CWD.

        # We need the CWD of the session.
        # Session object has no CWD anymore (removed in migration 6),
        # but the agent runs in project root usually.
        # Let's assume absolute paths or relative to project root.

        # Name to store as (from 'as' arg, but kwargs uses 'as' which is reserved... passed as 'as_' or similar?)
        # Let's assume the YAML parser maps 'as' to something else or we get it from kwargs.
        save_as = kwargs.get("as")

        matches = glob.glob(pattern, recursive=True)
        if not matches:
            return None

        # Just grab the first match for now if multiple, or list?
        # If 'as' is provided, we map a single file.

        filepath = os.path.abspath(matches[0])

        if save_as:
            context.state.artifacts[save_as] = filepath

        return {"captured": filepath}

    async def _handle_read_artifact(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Read an artifact's content into a workflow variable.
        """
        pattern = kwargs.get("pattern")
        if not pattern:
            return None

        import glob
        import os

        variable_name = kwargs.get("as")
        if not variable_name:
            logger.warning("read_artifact: 'as' argument missing")
            return None

        # Check if pattern matches an existing artifact key first
        filepath = context.state.artifacts.get(pattern)

        if not filepath:
            # Try as glob pattern
            matches = glob.glob(pattern, recursive=True)
            if matches:
                filepath = os.path.abspath(matches[0])

        if not filepath or not os.path.exists(filepath):
            logger.warning(f"read_artifact: File not found for pattern '{pattern}'")
            return None

        try:
            with open(filepath) as f:
                content = f.read()

            # Initialize variables dict if None
            if not context.state.variables:
                context.state.variables = {}

            context.state.variables[variable_name] = content
            return {"read_artifact": True, "variable": variable_name, "length": len(content)}
        except Exception as e:
            logger.error(f"read_artifact: Failed to read {filepath}: {e}")
            return None

    async def _handle_load_workflow_state(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Load workflow state from DB."""
        from .state_manager import WorkflowStateManager

        state_manager = WorkflowStateManager(context.db)
        loaded_state = state_manager.get_state(context.session_id)

        if loaded_state:
            # We should probably copy attributes to the existing object
            # so references remain valid if shared.
            # But dataclasses are mutable.

            # For now, let's update attributes manualy or via __dict__?
            # Safe way:
            for field in loaded_state.model_fields:
                val = getattr(loaded_state, field)
                setattr(context.state, field, val)

            return {"state_loaded": True}

        return {"state_loaded": False}

    async def _handle_save_workflow_state(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Save workflow state to DB."""
        from .state_manager import WorkflowStateManager

        state_manager = WorkflowStateManager(context.db)
        state_manager.save_state(context.state)
        return {"state_saved": True}

    async def _handle_set_variable(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Set a workflow variable."""
        name = kwargs.get("name")
        value = kwargs.get("value")
        if not name:
            return None

        if not context.state.variables:
            context.state.variables = {}

        context.state.variables[name] = value
        return {"variable_set": name, "value": value}

    async def _handle_increment_variable(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Increment a numeric workflow variable."""
        name = kwargs.get("name")
        amount = kwargs.get("amount", 1)
        if not name:
            return None

        if not context.state.variables:
            context.state.variables = {}

        current = context.state.variables.get(name, 0)
        if not isinstance(current, (int, float)):
            logger.warning(f"increment_variable: Variable {name} is not numeric: {current}")
            current = 0

        new_value = current + amount
        context.state.variables[name] = new_value
        return {"variable_incremented": name, "value": new_value}

    async def _handle_call_llm(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Call LLM with a prompt template and store result in variable."""
        prompt = kwargs.get("prompt")
        output_as = kwargs.get("output_as")
        if not prompt or not output_as:
            return {"error": "Missing prompt or output_as"}
        if not context.llm_service:
            logger.warning("call_llm: Missing LLM service")
            return {"error": "Missing LLM service"}

        # Render prompt template
        render_context = {
            "session": context.session_manager.get(context.session_id),
            "state": context.state,
            "variables": context.state.variables or {},
        }
        # Add kwargs to context
        render_context.update(kwargs)

        rendered_prompt = context.template_engine.render(prompt, render_context)

        try:
            # Use default provider
            provider = context.llm_service.get_default_provider()

            # Use generate_text or similar (provider interface varies, assuming generic generate)
            # WORKFLOWS.md doesn't specify provider interface details, but ActionContext.llm_service implies it.
            # Assuming provider has generate(prompt) or similar.
            # Reusing generate_summary pattern which took (context, prompt_template).
            # But here we pre-rendered the prompt.
            # Let's assume a generate_text method exists.

            # If provider methods are strictly typed, we might need to check.
            # `generate_summary` was used in `generate_handoff`.
            # Let's try `generate_text` or `complete`.
            response = await provider.generate_text(rendered_prompt)

            # Store result
            if not context.state.variables:
                context.state.variables = {}
            context.state.variables[output_as] = response

            return {"llm_called": True, "output_variable": output_as}
        except Exception as e:
            logger.error(f"call_llm: Failed: {e}")
            return {"error": str(e)}

    async def _handle_synthesize_title(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Synthesize and set a session title."""
        return await synthesize_title(
            session_manager=context.session_manager,
            session_id=context.session_id,
            llm_service=context.llm_service,
            transcript_processor=context.transcript_processor,
            template_engine=context.template_engine,
            template=kwargs.get("template"),
        )

    async def _handle_write_todos(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Write todos to a file (default TODO.md)."""
        todos = kwargs.get("todos", [])
        import os

        filename = kwargs.get("filename", "TODO.md")

        # Security: Allow only relative paths?
        # Assuming filename is just a name.

        try:
            # Overwrite or append? 'write' implies overwrite often, but for todos maybe append?
            # WORKFLOWS.md doesn't specify. Assuming overwrite if not specified.
            mode = kwargs.get("mode", "w")
            formatted_todos = [f"- [ ] {todo}" for todo in todos]

            if mode == "append" and os.path.exists(filename):
                with open(filename, "a") as f:
                    f.write("\n" + "\n".join(formatted_todos) + "\n")
            else:
                with open(filename, "w") as f:
                    f.write("# TODOs\n\n" + "\n".join(formatted_todos) + "\n")

            return {"todos_written": len(todos), "file": filename}
        except Exception as e:
            logger.error(f"write_todos: Failed: {e}")
            return {"error": str(e)}

    async def _handle_mark_todo_complete(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Mark a todo as complete in TODO.md."""
        todo_text = kwargs.get("todo_text")
        if not todo_text:
            return {"error": "Missing todo_text"}
        import os

        filename = kwargs.get("filename", "TODO.md")

        if not os.path.exists(filename):
            return {"error": "File not found"}

        try:
            with open(filename) as f:
                lines = f.readlines()

            updated = False
            new_lines = []
            for line in lines:
                if todo_text in line and "- [ ]" in line:
                    new_lines.append(line.replace("- [ ]", "- [x]"))
                    updated = True
                else:
                    new_lines.append(line)

            if updated:
                with open(filename, "w") as f:
                    f.writelines(new_lines)

            return {"todo_completed": updated, "text": todo_text}
        except Exception as e:
            logger.error(f"mark_todo_complete: Failed: {e}")
            return {"error": str(e)}

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
        """Call an MCP tool on a connected server.

        Args (via kwargs):
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            as: Optional variable name to store the result in workflow state
        """
        server_name = kwargs.get("server_name")
        tool_name = kwargs.get("tool_name")
        arguments = kwargs.get("arguments", {})
        output_as = kwargs.get("as")

        if not server_name or not tool_name:
            return {"error": "Missing server_name or tool_name"}
        if not context.mcp_manager:
            logger.warning("call_mcp_tool: MCP manager not available")
            return {"error": "MCP manager not available"}

        try:
            # Check connection
            if server_name not in context.mcp_manager.connections:
                return {"error": f"Server {server_name} not connected"}

            # Call tool
            result = await context.mcp_manager.call_tool(server_name, tool_name, arguments)

            # Store result in workflow variable if 'as' specified
            if output_as:
                if not context.state.variables:
                    context.state.variables = {}
                context.state.variables[output_as] = result

            return {"result": result, "stored_as": output_as}
        except Exception as e:
            logger.error(f"call_mcp_tool: Failed: {e}")
            return {"error": str(e)}

    async def _handle_generate_handoff(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Generate a handoff record (summary + mark status)."""
        return await generate_handoff(
            session_manager=context.session_manager,
            session_id=context.session_id,
            llm_service=context.llm_service,
            transcript_processor=context.transcript_processor,
            template=kwargs.get("template"),
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
        """
        Start a new CLI session (chaining).

        args:
            command: CLI command to run (default: auto-detect from source)
            args: List of arguments
            prompt: Initial prompt/context to inject
            cwd: Working directory (default: current session's cwd)
            detached: Whether to detach the process (default: True)
        """
        session = context.session_manager.get(context.session_id)
        if not session:
            return {"error": "Session not found"}

        # Determine command
        command = kwargs.get("command")
        if not command:
            # Auto-detect from source
            source = getattr(session, "source", "claude")
            if source == "claude":
                command = "claude"
            elif source == "gemini":
                command = "gemini"
            else:
                command = "claude"  # Default fallthrough

        cmd_args = kwargs.get("args", [])
        if isinstance(cmd_args, str):
            import shlex

            cmd_args = shlex.split(cmd_args)

        # Prepare prompt/input
        prompt = kwargs.get("prompt")
        # Render prompt template if needed?
        # Usually 'prompt' here is the final string, but if it contains {{}}, template engine might have handled it?
        # ActionExecutor calls handler with kwargs coming from yaml.
        # If yaml had template syntax, the caller (WorkflowEngine) usually renders it BEFORE calling action?
        # Actually WorkflowEngine.execute_action evaluates 'args' values if they look like templates?
        # Let's assume prompt is ready string.

        cwd = kwargs.get("cwd") or getattr(session, "project_path", None) or "."

        logger.info(f"Starting new session: {command} {cmd_args} in {cwd}")

        try:
            import subprocess

            # Construct full command
            full_cmd = [command] + cmd_args

            # Inject prompt via -p flag for Claude/Codex if supported
            # Verify CLI support? For now assume user configured correctly or we default common flags.
            if prompt and command in ["claude", "gemini"]:
                full_cmd.extend(["-p", prompt])

            # Spawn process
            # We use specific flags to detach fully to survive daemon/parent death if needed?
            # Or just standard Popen.
            # If we are inside an action, we are essentially the daemon.
            # We want the new CLI to run independently.
            # But wait, usually these CLIs are interactive.
            # If we are 'chaining', are we running in 'headless' mode?
            # Gobby's goal is 'Autonomous Session Chaining'.
            # Presumably sending a prompt and letting it run until it stops.
            # If it's Claude Code, `claude -p "..."` runs and exits?
            # Or runs interactive?
            # `claude` is interactive. `echo "msg" | claude` might be better or `-p`.
            # We'll rely on the configured command args to control behavior (e.g. --non-interactive if exists).

            proc = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                stdout=subprocess.DEVNULL,  # We rely on transcripts/logs, don't pipe to daemon stdout
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach
            )

            logger.info(f"Spawned process {proc.pid}")

            return {"started_new_session": True, "pid": proc.pid, "command": str(full_cmd)}

        except Exception as e:
            logger.error(f"Failed to start new session: {e}", exc_info=True)
            return {"error": str(e)}

    async def _handle_mark_loop_complete(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Mark the autonomous loop as complete.
        Sets 'stop_reason' variable to 'completed'.
        """
        context.state.variables["stop_reason"] = "completed"
        return {"loop_marked_complete": True}

    async def _handle_restore_context(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Restore context from linked parent session."""
        return restore_context(
            session_manager=context.session_manager,
            session_id=context.session_id,
            state=context.state,
            template_engine=context.template_engine,
            template=kwargs.get("template"),
        )

    async def _handle_extract_handoff_context(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Extract handoff context from transcript and save to session.compact_markdown."""
        return extract_handoff_context(
            session_manager=context.session_manager,
            session_id=context.session_id,
            config=context.config,
        )

    def _format_handoff_as_markdown(self, ctx: Any, prompt_template: str | None = None) -> str:
        """Format HandoffContext as markdown for injection."""
        return format_handoff_as_markdown(ctx, prompt_template)

    async def _handle_memory_inject(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Inject memory context into the session."""
        return await memory_inject(
            memory_manager=context.memory_manager,
            session_manager=context.session_manager,
            session_id=context.session_id,
            project_id=kwargs.get("project_id"),
            min_importance=kwargs.get("min_importance"),
            limit=kwargs.get("limit"),
        )

    async def _handle_memory_extract(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Extract memories from session summary using LLM."""
        return await memory_extract(
            memory_manager=context.memory_manager,
            llm_service=context.llm_service,
            session_manager=context.session_manager,
            session_id=context.session_id,
        )

    async def _handle_skills_learn(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Trigger skill learning from session.
        """
        if not context.skill_learner:
            return None

        # Safe config check
        config = getattr(context.skill_learner, "config", None)
        if not config or not getattr(config, "enabled", False):
            return None

        # Fire and forget?
        # The hook workflow is usually awaited.
        # Skill learning might be slow (LLM call).
        # We should probably run it in background or allow it to take time if it's session-end.
        # But for session-end, we want it to finish before daemon shutdown if possible?
        # Actually session-end hook usually just waits for response decision.

        # Let's await it. The user sees "Gobby is thinking..." effectively.

        session = context.session_manager.get(context.session_id)
        if not session:
            return {"error": "Session not found"}

        try:
            # We can't await if we want fire-and-forget.
            # But if we want to ensure it runs, we should await.
            # Given this is "Action", it implies synchronous execution in workflow steps.
            # If user wants async, we might need a specific "async: true" flag in workflow engine,
            # but here we just implement the logic.

            # Optimized: check if we should even try (e.g. min turns)
            # SkillLearner.learn_from_session handles checks.

            new_skills = await context.skill_learner.learn_from_session(session)

            return {"skills_learned": len(new_skills), "skill_names": [s.name for s in new_skills]}
        except Exception as e:
            logger.error(f"skills_learn: Failed: {e}", exc_info=True)
            return {"error": str(e)}

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
            prompt_text = context.event_data.get("prompt_text")

        return await memory_recall_relevant(
            memory_manager=context.memory_manager,
            session_manager=context.session_manager,
            session_id=context.session_id,
            prompt_text=prompt_text,
            project_id=kwargs.get("project_id"),
            limit=kwargs.get("limit", 5),
            min_importance=kwargs.get("min_importance", 0.3),
        )

    async def _handle_mark_session_status(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Mark a session status (current or parent).
        """
        status = kwargs.get("status")
        if not status:
            return {"error": "Missing status"}
        target = kwargs.get("target", "current_session")

        session_id = context.session_id
        if target == "parent_session":
            current_session = context.session_manager.get(context.session_id)
            if current_session and current_session.parent_session_id:
                session_id = current_session.parent_session_id
            else:
                return {"error": "No parent session linked"}

        context.session_manager.update_status(session_id, status)
        return {"status_updated": True, "session_id": session_id, "status": status}

    async def _handle_switch_mode(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Signal the agent to switch modes (e.g., PLAN, ACT).
        """
        mode = kwargs.get("mode")
        if not mode:
            return {"error": "Missing mode"}
        # For now, we inject a strong system instruction
        message = (
            f"SYSTEM: SWITCH MODE TO {mode.upper()}\n"
            f"You are now in {mode.upper()} mode. Adjust your behavior accordingly."
        )

        # If we had agent-specific adapters in the context, we could call them here.
        # e.g. context.agent_adapter.set_mode(mode)

        return {"inject_context": message, "mode_switch": mode}

    def _format_turns_for_llm(self, turns: list[dict]) -> str:
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
