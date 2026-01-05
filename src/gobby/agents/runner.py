"""
Agent runner for orchestrating agent execution.

The AgentRunner coordinates:
- Creating child sessions for agents
- Tracking agent runs in the database
- Executing agents via LLM providers
- Handling tool calls via the MCP proxy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gobby.agents.session import ChildSessionConfig, ChildSessionManager
from gobby.llm.executor import AgentExecutor, AgentResult, ToolResult, ToolSchema
from gobby.storage.agents import LocalAgentRunManager
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase
    from gobby.storage.sessions import LocalSessionManager
    from gobby.workflows.definitions import WorkflowDefinition

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for running an agent."""

    prompt: str
    """The prompt/task for the agent to perform."""

    parent_session_id: str
    """ID of the session spawning this agent."""

    project_id: str
    """Project ID for the agent's session."""

    machine_id: str
    """Machine identifier."""

    source: str
    """CLI source (claude, gemini, codex)."""

    provider: str = "claude"
    """LLM provider to use."""

    model: str | None = None
    """Optional model override."""

    workflow_name: str | None = None
    """Optional workflow to execute."""

    system_prompt: str | None = None
    """Optional system prompt override."""

    max_turns: int = 10
    """Maximum number of turns."""

    timeout: float = 120.0
    """Execution timeout in seconds."""

    tools: list[ToolSchema] | None = None
    """Optional list of tools to provide."""

    git_branch: str | None = None
    """Git branch for the session."""

    title: str | None = None
    """Optional title for the agent session."""

    project_path: str | None = None
    """Project path for loading project-specific workflows."""


@dataclass
class AgentRunContext:
    """Runtime context for an agent execution."""

    workflow: WorkflowDefinition | None = None
    """Loaded workflow definition, if workflow_name was specified."""

    child_session_id: str | None = None
    """ID of the child session created for this agent."""

    agent_run_id: str | None = None
    """ID of the agent run record."""


class AgentRunner:
    """
    Orchestrates agent execution with session and run tracking.

    The runner:
    1. Creates a child session for the agent
    2. Records the agent run in the database
    3. Executes the agent via the appropriate LLM provider
    4. Updates run status based on execution result

    Example:
        >>> runner = AgentRunner(db, session_storage, executor)
        >>> result = await runner.run(AgentConfig(
        ...     prompt="Create a TODO list",
        ...     parent_session_id="sess-123",
        ...     project_id="proj-abc",
        ...     machine_id="machine-1",
        ...     source="claude",
        ... ))
    """

    def __init__(
        self,
        db: LocalDatabase,
        session_storage: LocalSessionManager,
        executors: dict[str, AgentExecutor],
        max_agent_depth: int = 1,
        workflow_loader: WorkflowLoader | None = None,
    ):
        """
        Initialize AgentRunner.

        Args:
            db: Database connection.
            session_storage: Session storage manager.
            executors: Map of provider name to executor instance.
            max_agent_depth: Maximum nesting depth for agents.
            workflow_loader: Optional WorkflowLoader for loading workflow definitions.
        """
        self.db = db
        self._session_storage = session_storage
        self._executors = executors
        self._child_session_manager = ChildSessionManager(
            session_storage,
            max_agent_depth=max_agent_depth,
        )
        self._run_storage = LocalAgentRunManager(db)
        self._workflow_loader = workflow_loader or WorkflowLoader()
        self._workflow_state_manager = WorkflowStateManager(db)
        self.logger = logger

    def get_executor(self, provider: str) -> AgentExecutor | None:
        """Get executor for a provider."""
        return self._executors.get(provider)

    def register_executor(self, provider: str, executor: AgentExecutor) -> None:
        """Register an executor for a provider."""
        self._executors[provider] = executor
        self.logger.info(f"Registered executor for provider: {provider}")

    def can_spawn(self, parent_session_id: str) -> tuple[bool, str]:
        """
        Check if an agent can be spawned from the given session.

        Args:
            parent_session_id: The session attempting to spawn.

        Returns:
            Tuple of (can_spawn, reason).
        """
        return self._child_session_manager.can_spawn_child(parent_session_id)

    async def run(
        self,
        config: AgentConfig,
        tool_handler: Any | None = None,
    ) -> AgentResult:
        """
        Run an agent with the given configuration.

        Args:
            config: Agent configuration.
            tool_handler: Optional async callable for handling tool calls.
                If not provided, uses a default no-op handler.

        Returns:
            AgentResult with execution outcome.
        """
        # Check if we can spawn
        can_spawn, reason = self.can_spawn(config.parent_session_id)
        if not can_spawn:
            self.logger.warning(f"Cannot spawn agent: {reason}")
            return AgentResult(
                output="",
                status="error",
                error=reason,
                turns_used=0,
            )

        # Get executor for provider
        executor = self.get_executor(config.provider)
        if not executor:
            error_msg = f"No executor registered for provider: {config.provider}"
            self.logger.error(error_msg)
            return AgentResult(
                output="",
                status="error",
                error=error_msg,
                turns_used=0,
            )

        # Create child session
        try:
            child_session = self._child_session_manager.create_child_session(
                ChildSessionConfig(
                    parent_session_id=config.parent_session_id,
                    project_id=config.project_id,
                    machine_id=config.machine_id,
                    source=config.source,
                    workflow_name=config.workflow_name,
                    title=config.title,
                    git_branch=config.git_branch,
                )
            )
        except ValueError as e:
            self.logger.error(f"Failed to create child session: {e}")
            return AgentResult(
                output="",
                status="error",
                error=str(e),
                turns_used=0,
            )

        # Load workflow definition if specified
        workflow_definition = None
        if config.workflow_name:
            workflow_definition = self._workflow_loader.load_workflow(
                config.workflow_name,
                project_path=config.project_path,
            )
            if workflow_definition:
                self.logger.info(
                    f"Loaded workflow '{config.workflow_name}' for agent "
                    f"(type={workflow_definition.type})"
                )

                # Initialize workflow state for child session
                initial_step = ""
                if workflow_definition.steps:
                    initial_step = workflow_definition.steps[0].name

                initial_state = WorkflowState(
                    session_id=child_session.id,
                    workflow_name=config.workflow_name,
                    step=initial_step,
                    variables=dict(workflow_definition.variables),  # Copy initial variables
                )
                self._workflow_state_manager.save_state(initial_state)
                self.logger.info(
                    f"Initialized workflow state for child session {child_session.id} "
                    f"(step={initial_step})"
                )
            else:
                self.logger.warning(
                    f"Workflow '{config.workflow_name}' not found, "
                    f"proceeding without workflow"
                )

        # Create agent run record
        agent_run = self._run_storage.create(
            parent_session_id=config.parent_session_id,
            provider=config.provider,
            prompt=config.prompt,
            workflow_name=config.workflow_name,
            model=config.model,
            child_session_id=child_session.id,
        )

        # Start the run
        self._run_storage.start(agent_run.id)
        self.logger.info(
            f"Starting agent run {agent_run.id} "
            f"(child_session={child_session.id}, provider={config.provider})"
        )

        # Set up tool handler with workflow filtering
        async def default_tool_handler(tool_name: str, arguments: dict[str, Any]) -> ToolResult:
            """Default tool handler that returns not implemented."""
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool {tool_name} not implemented",
            )

        base_handler = tool_handler or default_tool_handler

        # Create workflow-filtered handler if workflow is active
        if workflow_definition:
            handler = self._create_workflow_filtered_handler(
                base_handler=base_handler,
                session_id=child_session.id,
                workflow_definition=workflow_definition,
            )
        else:
            handler = base_handler

        # Execute the agent
        try:
            result = await executor.run(
                prompt=config.prompt,
                tools=config.tools or [],
                tool_handler=handler,
                system_prompt=config.system_prompt,
                model=config.model,
                max_turns=config.max_turns,
                timeout=config.timeout,
            )

            # Update run based on result
            if result.status == "success":
                self._run_storage.complete(
                    agent_run.id,
                    result=result.output,
                    tool_calls_count=len(result.tool_calls),
                    turns_used=result.turns_used,
                )
                self.logger.info(
                    f"Agent run {agent_run.id} completed successfully "
                    f"({result.turns_used} turns, {len(result.tool_calls)} tool calls)"
                )
            elif result.status == "timeout":
                self._run_storage.timeout(agent_run.id, turns_used=result.turns_used)
                self.logger.warning(f"Agent run {agent_run.id} timed out")
            elif result.status == "error":
                self._run_storage.fail(
                    agent_run.id,
                    error=result.error or "Unknown error",
                    tool_calls_count=len(result.tool_calls),
                    turns_used=result.turns_used,
                )
                self.logger.error(f"Agent run {agent_run.id} failed: {result.error}")
            else:
                # Partial completion
                self._run_storage.complete(
                    agent_run.id,
                    result=result.output,
                    tool_calls_count=len(result.tool_calls),
                    turns_used=result.turns_used,
                )
                self.logger.info(
                    f"Agent run {agent_run.id} completed with status {result.status}"
                )

            # Update session status
            if result.status in ("success", "partial"):
                self._session_storage.update_status(child_session.id, "completed")
            else:
                self._session_storage.update_status(child_session.id, "failed")

            return result

        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}", exc_info=True)
            self._run_storage.fail(agent_run.id, error=str(e))
            self._session_storage.update_status(child_session.id, "failed")
            return AgentResult(
                output="",
                status="error",
                error=str(e),
                turns_used=0,
            )

    def get_run(self, run_id: str) -> Any | None:
        """Get an agent run by ID."""
        return self._run_storage.get(run_id)

    def list_runs(
        self,
        parent_session_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List agent runs for a session."""
        return self._run_storage.list_by_session(
            parent_session_id,
            status=status,  # type: ignore
            limit=limit,
        )

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running agent."""
        run = self._run_storage.get(run_id)
        if not run:
            return False
        if run.status != "running":
            return False

        self._run_storage.cancel(run_id)

        # Also mark session as cancelled
        if run.child_session_id:
            self._session_storage.update_status(run.child_session_id, "cancelled")

        self.logger.info(f"Cancelled agent run {run_id}")
        return True

    def _create_workflow_filtered_handler(
        self,
        base_handler: Any,
        session_id: str,
        workflow_definition: WorkflowDefinition,
    ) -> Any:
        """
        Create a tool handler that enforces workflow tool restrictions.

        Args:
            base_handler: The underlying tool handler to call for allowed tools.
            session_id: Session ID for looking up workflow state.
            workflow_definition: The workflow definition with step restrictions.

        Returns:
            An async callable that filters tools based on workflow state.
        """

        async def filtered_handler(
            tool_name: str, arguments: dict[str, Any]
        ) -> ToolResult:
            # Get current workflow state
            state = self._workflow_state_manager.get_state(session_id)
            if not state:
                # No state - just pass through
                return await base_handler(tool_name, arguments)

            # Get current step
            current_step = workflow_definition.get_step(state.step)
            if not current_step:
                # No step defined - pass through
                return await base_handler(tool_name, arguments)

            # Check blocked_tools first (explicit deny)
            if tool_name in current_step.blocked_tools:
                self.logger.warning(
                    f"Tool '{tool_name}' blocked by workflow step '{state.step}'"
                )
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Tool '{tool_name}' is blocked in workflow step '{state.step}'",
                )

            # Check allowed_tools (if not "all")
            if current_step.allowed_tools != "all":
                if tool_name not in current_step.allowed_tools:
                    self.logger.warning(
                        f"Tool '{tool_name}' not allowed in workflow step '{state.step}'"
                    )
                    return ToolResult(
                        tool_name=tool_name,
                        success=False,
                        error=(
                            f"Tool '{tool_name}' is not allowed in workflow step "
                            f"'{state.step}'. Allowed tools: {current_step.allowed_tools}"
                        ),
                    )

            # Handle 'complete' tool as workflow exit condition
            if tool_name == "complete":
                result_message = arguments.get("result", "Task completed")
                self.logger.info(
                    f"Agent called 'complete' tool - workflow exit condition met "
                    f"(session={session_id}, step={state.step})"
                )

                # Update workflow state to indicate completion
                state.variables["workflow_completed"] = True
                state.variables["completion_result"] = result_message
                self._workflow_state_manager.save_state(state)

                return ToolResult(
                    tool_name=tool_name,
                    success=True,
                    result={
                        "status": "completed",
                        "message": result_message,
                        "step": state.step,
                    },
                )

            # Tool is allowed - pass through to base handler
            return await base_handler(tool_name, arguments)

        return filtered_handler
