import logging
from dataclasses import dataclass
from typing import Any, Protocol

from gobby.storage.database import LocalDatabase
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks import LocalTaskManager  # noqa: F401
from gobby.workflows.definitions import WorkflowState
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
        self.register("call_mcp_tool", self._handle_call_mcp_tool)
        self.register("memory_inject", self._handle_memory_inject)
        self.register("memory_extract", self._handle_memory_extract)
        self.register("skills_learn", self._handle_skills_learn)
        self.register("memory.sync_import", self._handle_memory_sync_import)
        self.register("memory.sync_export", self._handle_memory_sync_export)
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
        """
        Inject context from a source.
        Returns: {"inject_context": "content..."}
        """
        source = kwargs.get("source")
        if not source:
            return None

        content = ""

        if source in ["previous_session_summary", "handoff"]:
            # 1. Find current session to get external/machine/project info to find parent
            current_session = context.session_manager.get(context.session_id)
            if not current_session:
                logger.warning(f"Session {context.session_id} not found")
                return None

            # Find parent manually if not linked
            if current_session.parent_session_id:
                parent = context.session_manager.get(current_session.parent_session_id)
                if parent and parent.summary_markdown:
                    content = parent.summary_markdown

        elif source == "artifacts":
            # List captured artifacts
            if context.state.artifacts:
                lines = ["## Captured Artifacts"]
                for name, path in context.state.artifacts.items():
                    lines.append(f"- {name}: {path}")
                content = "\n".join(lines)

        elif source == "observations":
            # Format observations
            if context.state.observations:
                import json

                content = "## Observations\n" + json.dumps(context.state.observations, indent=2)

        elif source == "workflow_state":
            # Format workflow state
            # Try model_dump (v2) or dict (v1)
            try:
                state_dict = context.state.model_dump(exclude={"observations", "artifacts"})
            except AttributeError:
                state_dict = context.state.dict(exclude={"observations", "artifacts"})

            import json

            content = "## Workflow State\n" + json.dumps(state_dict, indent=2, default=str)

        elif source == "compact_handoff":
            # Read compact handoff context from current session's compact_markdown
            current_session = context.session_manager.get(context.session_id)
            if current_session and current_session.compact_markdown:
                content = current_session.compact_markdown
                logger.debug(f"Loaded compact_markdown ({len(content)} chars) for session {context.session_id}")

        if content:
            # Render content if template is used
            template = kwargs.get("template")
            if template:
                render_context: dict[str, Any] = {
                    "session": context.session_manager.get(context.session_id),
                    "state": context.state,
                    "artifacts": context.state.artifacts,
                    "observations": context.state.observations,
                }

                # Add source data to context
                if source in ["previous_session_summary", "handoff"]:
                    render_context["summary"] = content
                    # Handoff implies structured access, but we only have text summary for now.
                    # We can shim it.
                    render_context["handoff"] = {"notes": content}
                elif source == "artifacts":
                    render_context["artifacts_list"] = content
                elif source == "observations":
                    render_context["observations_text"] = content
                elif source == "workflow_state":
                    render_context["workflow_state_text"] = content

                # Render
                content = context.template_engine.render(template, render_context)

            context.state.context_injected = True
            return {"inject_context": content}

        return None

    async def _handle_inject_message(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Inject a message to the user/assistant, rendering it as a template.
        """
        content = kwargs.get("content")
        if not content:
            return None

        render_context: dict[str, Any] = {
            "session": context.session_manager.get(context.session_id),
            "state": context.state,
            "artifacts": context.state.artifacts,
            "phase_action_count": context.state.phase_action_count,
            "variables": context.state.variables or {},
        }

        # Add any extra kwargs as context?
        render_context.update(kwargs)

        rendered_content = context.template_engine.render(content, render_context)

        # We return it as 'inject_message' which the hook handler should display or inject
        # The hook system currently expects 'inject_context' for prompt augmentation,
        # or we might need a new response field for 'message' (Ephemeral message?)
        # WORKFLOWS.md calls it "inject_message".
        # Ideally this shows up to the user or is injected into conversation history.

        return {"inject_message": rendered_content}

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
        if not context.llm_service or not context.transcript_processor:
            return {"error": "Missing services"}

        current_session = context.session_manager.get(context.session_id)
        if not current_session:
            return {"error": "Session not found"}

        # Get summary-worthy transcript (first 20 turns?)
        transcript_path = getattr(current_session, "jsonl_path", None)
        if not transcript_path:
            return {"error": "No transcript path"}

        try:
            import json
            from pathlib import Path

            # Read enough turns to get context
            turns = []
            path = Path(transcript_path)
            if path.exists():
                with open(path) as f:
                    for i, line in enumerate(f):
                        if i > 20:
                            break
                        if line.strip():
                            turns.append(json.loads(line))

            if not turns:
                return {"error": "Empty transcript"}

            formatted_turns = self._format_turns_for_llm(turns)

            template = kwargs.get(
                "template",
                "Create a short, concise title (3-6 words) for this coding session based on the transcript.\n\nTranscript:\n{{ transcript }}",
            )

            prompt = context.template_engine.render(template, {"transcript": formatted_turns})

            provider = context.llm_service.get_default_provider()
            title = await provider.generate_text(prompt)

            # clean title (remove quotes, etc)
            title = title.strip().strip('"').strip("'")

            context.session_manager.update_title(context.session_id, title)
            return {"title_synthesized": title}

        except Exception as e:
            logger.error(f"synthesize_title: Failed: {e}")
            return {"error": str(e)}

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
        if not context.memory_sync_manager:
            return {"error": "Memory Sync Manager not available"}

        count = await context.memory_sync_manager.import_from_files()
        logger.info(f"Memory sync import: {count} memories imported")
        return {"imported": {"memories": count}}

    async def _handle_memory_sync_export(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Export memories to filesystem."""
        if not context.memory_sync_manager:
            return {"error": "Memory Sync Manager not available"}

        count = await context.memory_sync_manager.export_to_files()
        logger.info(f"Memory sync export: {count} memories exported")
        return {"exported": {"memories": count}}

    async def _handle_persist_tasks(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Persist a list of task dicts to Gobby task system."""
        tasks = kwargs.get("tasks", [])
        try:
            from gobby.storage.tasks import LocalTaskManager

            task_manager = LocalTaskManager(context.db)

            current_session = context.session_manager.get(context.session_id)
            project_id = current_session.project_id if current_session else "default"

            created_count = 0
            ids = []

            for task_data in tasks:
                # Basic validation/defaulting
                title = task_data.get("title")
                if not title:
                    continue

                # task_data might have: description, priority, type, labels
                t = task_manager.create_task(
                    project_id=project_id,
                    title=title,
                    description=task_data.get("description"),
                    priority=task_data.get("priority", 2),
                    task_type=task_data.get("type", "task"),
                    labels=task_data.get("labels"),
                    discovered_in_session_id=context.session_id,
                )
                ids.append(t.id)
                created_count += 1

            return {"tasks_persisted": created_count, "ids": ids}
        except Exception as e:
            logger.error(f"persist_tasks: Failed: {e}")
            return {"error": str(e)}

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
        """
        Generate a handoff record by summarizing the session and saving to sessions.summary_markdown.
        Legacy combined action: Generates summary + Marks status 'handoff_ready'.
        """
        # Reuse generate_summary logic
        summary_result = await self._handle_generate_summary(context, **kwargs)
        if summary_result and "error" in summary_result:
            return summary_result

        # Mark Session Status
        context.session_manager.update_status(context.session_id, "handoff_ready")

        if not summary_result:
            return {"error": "Failed to generate summary"}

        return {"handoff_created": True, "summary_length": summary_result.get("summary_length", 0)}

    async def _handle_generate_summary(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Generate a session summary using LLM and store it in the session record.
        """
        # We need LLM service and transcript processor
        if not context.llm_service or not context.transcript_processor:
            logger.warning("generate_summary: Missing LLM service or transcript processor")
            return {"error": "Missing services"}

        current_session = context.session_manager.get(context.session_id)
        if not current_session:
            return {"error": "Session not found"}

        # Get transcript path
        transcript_path = getattr(current_session, "jsonl_path", None)
        if not transcript_path:
            logger.warning(f"generate_summary: No transcript path for session {context.session_id}")
            return {"error": "No transcript path"}

        template = kwargs.get("template")
        if not template:
            # Fallback to a default prompt if none in YAML
            template = (
                "Summarize this session, focusing on what was accomplished, "
                "key decisions, and what is left to do.\n\n"
                "Transcript:\n{transcript_summary}"
            )

        # 1. Process Transcript
        try:
            import json
            from pathlib import Path

            # Read JSONL transcript
            transcript_file = Path(transcript_path)
            if not transcript_file.exists():
                logger.warning(f"Transcript file not found: {transcript_path}")
                return {"error": "Transcript not found"}

            turns = []
            with open(transcript_file) as f:
                for line in f:
                    if line.strip():
                        turns.append(json.loads(line))

            # Get turns since last /clear (up to 50 turns)
            recent_turns = context.transcript_processor.extract_turns_since_clear(
                turns, max_turns=50
            )

            # Format turns for LLM
            transcript_summary = self._format_turns_for_llm(recent_turns)
        except Exception as e:
            logger.error(f"Failed to process transcript: {e}")
            return {"error": str(e)}

        # 2. Gather context variables for template
        # Extract last messages (last 2 user/assistant pairs)
        last_messages = context.transcript_processor.extract_last_messages(
            recent_turns, num_pairs=2
        )
        last_messages_str = self._format_turns_for_llm(last_messages) if last_messages else ""

        # Get git status and file changes
        git_status = self._get_git_status()
        file_changes = self._get_file_changes()

        # 3. Call LLM
        try:
            llm_context = {
                "turns": recent_turns,
                "transcript_summary": transcript_summary,
                "session": current_session,
                "last_messages": last_messages_str,
                "git_status": git_status,
                "file_changes": file_changes,
            }
            provider = context.llm_service.get_default_provider()
            summary_content = await provider.generate_summary(
                context=llm_context,
                prompt_template=template,
            )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return {"error": f"LLM error: {e}"}

        # 5. Save to Production Location (sessions table)
        context.session_manager.update_summary(context.session_id, summary_markdown=summary_content)

        logger.info(f"Generated summary for session {context.session_id}")
        return {"summary_generated": True, "summary_length": len(summary_content)}

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
        """
        Restore context from linked parent session.
        """
        current_session = context.session_manager.get(context.session_id)
        if not current_session or not current_session.parent_session_id:
            return None

        parent = context.session_manager.get(current_session.parent_session_id)
        if not parent or not parent.summary_markdown:
            return None

        content = parent.summary_markdown
        template = kwargs.get("template")

        if template:
            render_context = {
                "summary": content,
                "handoff": {"notes": "Restored summary"},
                "session": current_session,
                "state": context.state,
            }
            content = context.template_engine.render(template, render_context)

        return {"inject_context": content}

    async def _handle_extract_handoff_context(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """Extract handoff context from transcript and save to session.compact_markdown."""
        # Check if enabled in config
        if context.config:
            compact_config = getattr(context.config, "compact_handoff", None)
            if compact_config and not compact_config.enabled:
                return {"skipped": True, "reason": "compact_handoff disabled"}

        current_session = context.session_manager.get(context.session_id)
        if not current_session:
            return {"error": "Session not found"}

        transcript_path = getattr(current_session, "jsonl_path", None)
        if not transcript_path:
            return {"error": "No transcript path"}

        try:
            import json
            from pathlib import Path

            from gobby.sessions.analyzer import TranscriptAnalyzer

            # Read transcript
            path = Path(transcript_path)
            if not path.exists():
                return {"error": "Transcript file not found"}

            turns = []
            with open(path) as f:
                for line in f:
                    if line.strip():
                        turns.append(json.loads(line))

            analyzer = TranscriptAnalyzer()
            handoff_ctx = analyzer.extract_handoff_context(turns)

            # Enrich with real-time git status
            if not handoff_ctx.git_status:
                handoff_ctx.git_status = self._get_git_status()

            # Enrich with real git commits (more reliable than parsing transcript)
            # Get commits made during this session (last 10 commits)
            real_commits = self._get_recent_git_commits()
            if real_commits:
                handoff_ctx.git_commits = real_commits

            # Get prompt template from config
            prompt_template = None
            if context.config:
                compact_config = getattr(context.config, "compact_handoff", None)
                if compact_config:
                    prompt_template = compact_config.prompt

            # Format as markdown using config template
            markdown = self._format_handoff_as_markdown(handoff_ctx, prompt_template)

            # Save to session.compact_markdown
            context.session_manager.update_compact_markdown(context.session_id, markdown)

            logger.info(f"Saved compact handoff context ({len(markdown)} chars) to session {context.session_id}")
            return {"handoff_context_extracted": True, "markdown_length": len(markdown)}

        except Exception as e:
            logger.error(f"extract_handoff_context: Failed: {e}")
            return {"error": str(e)}

    def _format_handoff_as_markdown(self, ctx: Any, prompt_template: str | None = None) -> str:
        """Format HandoffContext as markdown for injection.

        Args:
            ctx: HandoffContext with extracted session data
            prompt_template: Optional template from config with {section} placeholders
        """
        # Build each section as pre-rendered markdown
        sections: dict[str, str] = {}

        # Active task section
        if ctx.active_gobby_task:
            task = ctx.active_gobby_task
            sections["active_task_section"] = (
                f"### Active Task\n"
                f"**{task.get('title', 'Untitled')}** ({task.get('id', 'unknown')})\n"
                f"Status: {task.get('status', 'unknown')}\n"
            )
        else:
            sections["active_task_section"] = ""

        # Todo state section
        if ctx.todo_state:
            lines = ["### In-Progress Work"]
            for todo in ctx.todo_state:
                status = todo.get("status", "pending")
                marker = "x" if status == "completed" else ">" if status == "in_progress" else " "
                lines.append(f"- [{marker}] {todo.get('content', '')}")
            sections["todo_state_section"] = "\n".join(lines) + "\n"
        else:
            sections["todo_state_section"] = ""

        # Git commits section
        if ctx.git_commits:
            lines = ["### Commits This Session"]
            for commit in ctx.git_commits:
                lines.append(f"- `{commit.get('hash', '')[:7]}` {commit.get('message', '')}")
            sections["git_commits_section"] = "\n".join(lines) + "\n"
        else:
            sections["git_commits_section"] = ""

        # Git status section
        if ctx.git_status:
            sections["git_status_section"] = (
                f"### Uncommitted Changes\n```\n{ctx.git_status}\n```\n"
            )
        else:
            sections["git_status_section"] = ""

        # Files modified section
        if ctx.files_modified:
            lines = ["### Files Being Modified"]
            for f in ctx.files_modified:
                lines.append(f"- {f}")
            sections["files_modified_section"] = "\n".join(lines) + "\n"
        else:
            sections["files_modified_section"] = ""

        # Initial goal section
        if ctx.initial_goal:
            sections["initial_goal_section"] = f"### Original Goal\n{ctx.initial_goal}\n"
        else:
            sections["initial_goal_section"] = ""

        # Recent activity section
        if ctx.recent_activity:
            lines = ["### Recent Activity"]
            for activity in ctx.recent_activity[-5:]:  # Last 5
                lines.append(f"- {activity}")
            sections["recent_activity_section"] = "\n".join(lines) + "\n"
        else:
            sections["recent_activity_section"] = ""

        # Use template if provided, otherwise use default format
        if prompt_template:
            try:
                # Remove empty sections from output by stripping multiple newlines
                result = prompt_template.format(**sections)
                # Clean up multiple blank lines
                import re
                result = re.sub(r'\n{3,}', '\n\n', result)
                return result.strip() + "\n"
            except KeyError as e:
                logger.warning(f"Invalid placeholder in compact_handoff prompt: {e}")
                # Fall through to default

        # Default format (backwards compatible)
        lines = ["## Continuation Context", ""]
        for section in [
            "active_task_section", "todo_state_section", "git_commits_section",
            "git_status_section", "files_modified_section", "initial_goal_section",
            "recent_activity_section"
        ]:
            if sections[section]:
                lines.append(sections[section])

        return "\n".join(lines)

    async def _handle_memory_inject(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Inject memory context into the session.

        Skills are no longer injected here - they are provided via the
        Claude Code native format (.claude/skills/<name>/).
        """
        if not context.memory_manager:
            return None  # Memory system disabled or not initialized

        # Check config enabled
        if not context.memory_manager.config.enabled:
            return None

        project_id = kwargs.get("project_id")
        if not project_id:
            # Try to resolve from session
            session = context.session_manager.get(context.session_id)
            if session:
                project_id = session.project_id

        if not project_id:
            logger.warning("memory_inject: No project_id found")
            return None

        from gobby.memory.context import build_memory_context

        try:
            # Recall Project Memories
            min_importance = kwargs.get("min_importance", 0.5)
            project_memories = context.memory_manager.recall(
                project_id=project_id, min_importance=min_importance
            )

            if not project_memories:
                return {"injected": False, "reason": "No memories found"}

            memory_context = build_memory_context(project_memories)

            if not memory_context:
                return {"injected": False}

            # Return as 'inject_context' trigger
            return {"inject_context": memory_context}

        except Exception as e:
            logger.error(f"memory_inject: Failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _handle_memory_extract(
        self, context: ActionContext, **kwargs: Any
    ) -> dict[str, Any] | None:
        """
        Extract memories from session summary using LLM.

        Extracts facts, preferences, patterns, and context from the session
        and creates memories with source_type='session'.
        """
        import json

        if not context.memory_manager:
            return None

        # Check config enabled
        if not context.memory_manager.config.enabled:
            return None

        if not context.memory_manager.config.auto_extract:
            logger.debug("memory_extract: auto_extract disabled")
            return None

        if not context.llm_service:
            logger.warning("memory_extract: No LLM service available")
            return None

        # Get session
        session = context.session_manager.get(context.session_id)
        if not session:
            logger.warning(f"memory_extract: Session {context.session_id} not found")
            return None

        project_id = session.project_id

        try:
            # Get session summary - prefer stored summary_markdown
            summary = session.summary_markdown
            if not summary:
                logger.debug("memory_extract: No summary available, skipping extraction")
                return {"extracted": 0, "reason": "no_summary"}

            # Get LLM provider
            memory_config = context.memory_manager.config
            provider, model, _ = context.llm_service.get_provider_for_feature(memory_config)

            # Build prompt
            prompt = memory_config.extraction_prompt.format(summary=summary)

            # Call LLM
            response = await provider.generate_text(prompt=prompt, model=model)

            # Parse JSON response
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            try:
                memories_data = json.loads(cleaned_response)
            except json.JSONDecodeError:
                logger.warning(
                    f"memory_extract: Failed to parse JSON for session {context.session_id}"
                )
                return {"extracted": 0, "error": "json_parse_error"}

            if not isinstance(memories_data, list):
                logger.warning(
                    f"memory_extract: Expected list, got {type(memories_data).__name__}"
                )
                return {"extracted": 0, "error": "invalid_response_format"}

            # Create memories
            created_count = 0
            for mem_data in memories_data:
                if not isinstance(mem_data, dict):
                    continue

                content = mem_data.get("content")
                if not content:
                    continue

                # Check for duplicates
                if context.memory_manager.content_exists(content, project_id):
                    logger.debug(f"memory_extract: Skipping duplicate: {content[:50]}...")
                    continue

                memory_type = mem_data.get("memory_type", "fact")
                if memory_type not in ("fact", "preference", "pattern", "context"):
                    memory_type = "fact"

                importance = mem_data.get("importance", 0.5)
                if not isinstance(importance, (int, float)):
                    importance = 0.5
                importance = max(0.0, min(1.0, float(importance)))

                tags = mem_data.get("tags", [])
                if not isinstance(tags, list):
                    tags = []

                try:
                    context.memory_manager.remember(
                        content=content,
                        memory_type=memory_type,
                        importance=importance,
                        project_id=project_id,
                        source_type="session",
                        source_session_id=context.session_id,
                        tags=tags,
                    )
                    created_count += 1
                    logger.info(
                        f"memory_extract: Created {memory_type} memory: {content[:50]}..."
                    )
                except Exception as e:
                    logger.error(f"memory_extract: Failed to create memory: {e}")

            return {"extracted": created_count, "session_id": context.session_id}

        except Exception as e:
            logger.error(f"memory_extract: Failed: {e}", exc_info=True)
            return {"error": str(e)}

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
        """
        Format transcript turns for LLM analysis.

        Args:
            turns: List of transcript turn dicts

        Returns:
            Formatted string with turn summaries
        """
        formatted: list[str] = []
        for i, turn in enumerate(turns):
            message = turn.get("message", {})
            role = message.get("role", "unknown")
            content = message.get("content", "")

            # Assistant messages have content as array of blocks
            if isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "thinking":
                            text_parts.append(f"[Thinking: {block.get('thinking', '')}]")
                        elif block.get("type") == "tool_use":
                            text_parts.append(f"[Tool: {block.get('name', 'unknown')}]")
                content = " ".join(text_parts)

            formatted.append(f"[Turn {i + 1} - {role}]: {content}")

        return "\n\n".join(formatted)

    def _get_git_status(self) -> str:
        """Get git status for current directory."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() or "No changes"
        except Exception:
            return "Not a git repository or git not available"

    def _get_recent_git_commits(self, max_commits: int = 10) -> list[dict[str, str]]:
        """Get recent git commits with hash and message.

        Args:
            max_commits: Maximum number of commits to return

        Returns:
            List of dicts with 'hash' and 'message' keys
        """
        import subprocess

        try:
            result = subprocess.run(
                ["git", "log", f"-{max_commits}", "--format=%H|%s"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []

            commits = []
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    hash_part, message = line.split("|", 1)
                    commits.append({"hash": hash_part, "message": message})
            return commits
        except Exception:
            return []

    def _get_file_changes(self) -> str:
        """Get detailed file changes from git."""
        import subprocess

        try:
            # Get changed files with status
            diff_result = subprocess.run(
                ["git", "diff", "HEAD", "--name-status"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Get untracked files
            untracked_result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Combine results
            changes = []
            if diff_result.stdout.strip():
                changes.append("Modified/Deleted:")
                changes.append(diff_result.stdout.strip())

            if untracked_result.stdout.strip():
                changes.append("\nUntracked:")
                changes.append(untracked_result.stdout.strip())

            return "\n".join(changes) if changes else "No changes"

        except Exception:
            return "Unable to determine file changes"
