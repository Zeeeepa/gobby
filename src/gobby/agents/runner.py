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
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gobby.agents.registry import RunningAgent
from gobby.agents.session import ChildSessionConfig, ChildSessionManager
from gobby.llm.executor import AgentExecutor, AgentResult, ToolHandler, ToolResult, ToolSchema
from gobby.storage.agents import AgentRun, LocalAgentRunManager
from gobby.storage.sessions import Session
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for running an agent."""

    prompt: str
    """The prompt/task for the agent to perform."""

    # Required context - can be inferred from get_project_context() or passed explicitly
    parent_session_id: str | None = None
    """ID of the session spawning this agent. Inferred from context if not provided."""

    project_id: str | None = None
    """Project ID for the agent's session. Inferred from context if not provided."""

    machine_id: str | None = None
    """Machine identifier. Defaults to hostname if not provided."""

    source: str = "claude"
    """CLI source (claude, gemini, codex)."""

    # New spec-aligned parameters
    workflow: str | None = None
    """Workflow name or path to execute."""

    task: str | None = None
    """Task ID or 'next' for auto-select."""

    agent: str | None = None
    """Named agent definition to use."""

    lifecycle_variables: dict[str, Any] | None = None
    """Lifecycle variables to override parent settings."""

    default_variables: dict[str, Any] | None = None
    """Default variables for the agent."""

    session_context: str = "summary_markdown"
    """Context source: summary_markdown, compact_markdown, session_id:<id>, transcript:<n>, file:<path>."""

    mode: str = "in_process"
    """Execution mode: in_process, terminal, embedded, headless."""

    terminal: str = "auto"
    """Terminal for terminal/embedded modes: auto, ghostty, iterm, etc."""

    worktree_id: str | None = None
    """Existing worktree to use for terminal mode."""

    # Provider settings
    provider: str = "claude"
    """LLM provider to use."""

    model: str | None = None
    """Optional model override."""

    # Execution limits
    max_turns: int = 10
    """Maximum number of turns."""

    timeout: float = 120.0
    """Execution timeout in seconds."""

    # Legacy/internal fields (kept for compatibility)
    workflow_name: str | None = None
    """Deprecated: use 'workflow' instead. Kept for backward compatibility."""

    system_prompt: str | None = None
    """Optional system prompt override."""

    tools: list[ToolSchema] | None = None
    """Optional list of tools to provide."""

    git_branch: str | None = None
    """Git branch for the session."""

    title: str | None = None
    """Optional title for the agent session."""

    project_path: str | None = None
    """Project path for loading project-specific workflows."""

    context_injected: bool = False
    """Whether context was successfully injected into the prompt."""

    def get_effective_workflow(self) -> str | None:
        """Get the workflow name, preferring 'workflow' over legacy 'workflow_name'."""
        return self.workflow or self.workflow_name


@dataclass
class AgentRunContext:
    """
    Runtime context for an agent execution.

    Contains all the objects needed to execute an agent, created during
    the prepare phase and used during execution.
    """

    session: Session | None = None
    """Child session object created for this agent."""

    run: AgentRun | None = None
    """Agent run record from the database."""

    workflow_state: WorkflowState | None = None
    """Workflow state for the child session, if workflow specified."""

    workflow_config: WorkflowDefinition | None = None
    """Loaded workflow definition, if workflow_name was specified."""

    # Convenience accessors for IDs
    @property
    def session_id(self) -> str | None:
        """Get the child session ID."""
        return self.session.id if self.session else None

    @property
    def run_id(self) -> str | None:
        """Get the agent run ID."""
        return self.run.id if self.run else None


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
        db: DatabaseProtocol,
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
        from gobby.agents.definitions import AgentDefinitionLoader

        self._agent_loader = AgentDefinitionLoader()
        self._workflow_state_manager = WorkflowStateManager(db)

        self.logger = logger

        # Thread-safe in-memory tracking of running agents
        self._running_agents: dict[str, RunningAgent] = {}
        self._running_agents_lock = threading.Lock()

    def get_executor(self, provider: str) -> AgentExecutor | None:
        """Get executor for a provider."""
        return self._executors.get(provider)

    def register_executor(self, provider: str, executor: AgentExecutor) -> None:
        """Register an executor for a provider."""
        self._executors[provider] = executor
        self.logger.info(f"Registered executor for provider: {provider}")

    def can_spawn(self, parent_session_id: str) -> tuple[bool, str, int]:
        """
        Check if an agent can be spawned from the given session.

        Args:
            parent_session_id: The session attempting to spawn.

        Returns:
            Tuple of (can_spawn, reason, parent_depth).
            The parent_depth is returned to avoid redundant depth lookups.
        """
        return self._child_session_manager.can_spawn_child(parent_session_id)

    def prepare_run(self, config: AgentConfig) -> AgentRunContext | AgentResult:
        """
        Prepare for agent execution by creating database records.

        Creates:
        - Child session linked to parent
        - Agent run record in database
        - Workflow state (if workflow specified)

        This method can be used separately for terminal mode, where we prepare
        the database state, then spawn a terminal process that picks up from
        the session via hooks.

        Args:
            config: Agent configuration.

        Returns:
            AgentRunContext on success, or AgentResult with error on failure.
        """
        # Validate required fields
        if not config.parent_session_id:
            return AgentResult(
                output="",
                status="error",
                error="parent_session_id is required",
                turns_used=0,
            )
        if not config.project_id:
            return AgentResult(
                output="",
                status="error",
                error="project_id is required",
                turns_used=0,
            )
        if not config.machine_id:
            return AgentResult(
                output="",
                status="error",
                error="machine_id is required",
                turns_used=0,
            )

        # Type narrowing for mypy - these are guaranteed non-None after validation above
        parent_session_id: str = config.parent_session_id
        project_id: str = config.project_id
        machine_id: str = config.machine_id

        # Check if we can spawn (also get parent_depth to avoid redundant lookups)
        can_spawn, reason, _parent_depth = self.can_spawn(parent_session_id)
        if not can_spawn:
            self.logger.warning(f"Cannot spawn agent: {reason}")
            return AgentResult(
                output="",
                status="error",
                error=reason,
                turns_used=0,
            )

        # Load agent definition if specified
        if config.agent:
            agent_def = self._agent_loader.load(config.agent)
            if agent_def:
                # Merge definition into config (config takes precedence if explicitly set?)
                # Actually, definition provides defaults/overrides.
                # Logic:
                # 1. Use workflow from definition if not in config
                # 2. Use model from definition if not in config
                # 3. Merge lifecycle_variables

                if not config.workflow:
                    config.workflow = agent_def.workflow

                if not config.model:
                    config.model = agent_def.model

                # Merge lifecycle variables (definition wins? or config? usually definition sets policy)
                def_lifecycle = agent_def.lifecycle_variables or {}
                config_lifecycle = config.lifecycle_variables or {}
                # Config overrides definition? Or vice versa?
                # The Plan says "Child session created with lifecycle_variables merged in"
                # Let's say config overrides definition (standard)
                config.lifecycle_variables = {**def_lifecycle, **config_lifecycle}

                # Merge default variables
                def_vars = agent_def.default_variables or {}
                config_vars = config.default_variables or {}
                config.default_variables = {**def_vars, **config_vars}

                self.logger.info(f"Loaded agent definition '{config.agent}'")
            else:
                self.logger.warning(f"Agent definition '{config.agent}' not found")

        # Get effective workflow name (prefers 'workflow' over legacy 'workflow_name')
        effective_workflow = config.get_effective_workflow()

        # Validate workflow BEFORE creating child session to avoid orphaned sessions
        workflow_definition = None
        if effective_workflow:
            workflow_definition = self._workflow_loader.load_workflow(
                effective_workflow,
                project_path=config.project_path,
            )
            if workflow_definition:
                # Reject lifecycle workflows - they run automatically via hooks
                if workflow_definition.type == "lifecycle":
                    self.logger.error(
                        f"Cannot use lifecycle workflow '{effective_workflow}' for agent spawning"
                    )
                    return AgentResult(
                        output="",
                        status="error",
                        error=(
                            f"Cannot use lifecycle workflow '{effective_workflow}' for agent spawning. "
                            f"Lifecycle workflows run automatically on events. "
                            f"Use a step workflow like 'plan-execute' instead."
                        ),
                        turns_used=0,
                    )

        # Create child session (now safe - workflow validated above)
        try:
            child_session = self._child_session_manager.create_child_session(
                ChildSessionConfig(
                    parent_session_id=parent_session_id,
                    project_id=project_id,
                    machine_id=machine_id,
                    source=config.source,
                    workflow_name=effective_workflow,
                    title=config.title,
                    git_branch=config.git_branch,
                    lifecycle_variables=config.lifecycle_variables,
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

        # Initialize workflow state if workflow was loaded
        workflow_state = None
        if workflow_definition:
            self.logger.info(
                f"Loaded workflow '{effective_workflow}' for agent "
                f"(type={workflow_definition.type})"
            )

            # Initialize workflow state for child session
            initial_step = ""
            if workflow_definition.steps:
                initial_step = workflow_definition.steps[0].name

            # Build initial variables with agent depth information
            initial_variables = dict(workflow_definition.variables)
            initial_variables["agent_depth"] = child_session.agent_depth
            initial_variables["max_agent_depth"] = self._child_session_manager.max_agent_depth
            initial_variables["can_spawn"] = (
                child_session.agent_depth < self._child_session_manager.max_agent_depth
            )
            initial_variables["parent_session_id"] = parent_session_id

            workflow_state = WorkflowState(
                session_id=child_session.id,
                workflow_name=effective_workflow,
                step=initial_step,
                variables=initial_variables,
            )
            self._workflow_state_manager.save_state(workflow_state)
            self.logger.info(
                f"Initialized workflow state for child session {child_session.id} "
                f"(step={initial_step}, agent_depth={child_session.agent_depth})"
            )
        elif effective_workflow:
            # workflow_definition is None but effective_workflow was specified
            self.logger.warning(
                f"Workflow '{effective_workflow}' not found, proceeding without workflow"
            )

        # Create agent run record
        agent_run = self._run_storage.create(
            parent_session_id=parent_session_id,
            provider=config.provider,
            prompt=config.prompt,
            workflow_name=effective_workflow,
            model=config.model,
            child_session_id=child_session.id,
        )

        # Set terminal pickup metadata on child session for terminal mode
        # This allows terminal-spawned agents to pick up their state via hooks
        self._session_storage.update_terminal_pickup_metadata(
            session_id=child_session.id,
            workflow_name=effective_workflow,
            agent_run_id=agent_run.id,
            context_injected=config.context_injected,
            original_prompt=config.prompt,
        )

        self.logger.info(
            f"Prepared agent run {agent_run.id} "
            f"(child_session={child_session.id}, provider={config.provider})"
        )

        # Convert child session (internal type) to Session for storage
        # The create_child_session returns a Session dataclass
        session_obj = child_session

        return AgentRunContext(
            session=session_obj,
            run=agent_run,
            workflow_state=workflow_state,
            workflow_config=workflow_definition,
        )

    async def execute_run(
        self,
        context: AgentRunContext,
        config: AgentConfig,
        tool_handler: ToolHandler | None = None,
    ) -> AgentResult:
        """
        Execute an agent using prepared context.

        This method runs the agent loop using the context created by prepare_run().
        For in_process mode only - terminal mode uses a different execution path.

        Args:
            context: Prepared run context from prepare_run().
            config: Agent configuration.
            tool_handler: Optional async callable for handling tool calls.

        Returns:
            AgentResult with execution outcome.
        """
        # Validate context
        if not context.session or not context.run:
            return AgentResult(
                output="",
                status="error",
                error="Invalid context: missing session or run",
                turns_used=0,
            )

        child_session = context.session
        agent_run = context.run
        workflow_definition = context.workflow_config

        # Get executor for provider
        executor = self.get_executor(config.provider)
        if not executor:
            error_msg = f"No executor registered for provider: {config.provider}"
            self.logger.error(error_msg)
            self._run_storage.fail(agent_run.id, error=error_msg)
            return AgentResult(
                output="",
                status="error",
                error=error_msg,
                turns_used=0,
            )

        # Start the run
        self._run_storage.start(agent_run.id)
        self.logger.info(
            f"Starting agent run {agent_run.id} "
            f"(child_session={child_session.id}, provider={config.provider})"
        )

        # Track in memory for real-time status
        # Note: parent_session_id is guaranteed non-None here because execute_run
        # is only called after prepare_run validates it
        self._track_running_agent(
            run_id=agent_run.id,
            parent_session_id=config.parent_session_id,
            child_session_id=child_session.id,
            provider=config.provider,
            prompt=config.prompt,
            mode=config.mode,
            workflow_name=config.get_effective_workflow(),
            model=config.model,
            worktree_id=config.worktree_id,
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

        # Track tool calls to preserve partial progress info on exception
        # Note: Each tool call within a turn counts separately. The executor's
        # run() method handles turns - we only track tool calls for monitoring.
        tool_calls_made = 0

        async def tracking_handler(tool_name: str, arguments: dict[str, Any]) -> ToolResult:
            nonlocal tool_calls_made
            tool_calls_made += 1
            # Update in-memory state for real-time monitoring
            # Note: turns_used is tracked by the executor, not per tool call
            self._update_running_agent(
                agent_run.id,
                tool_calls_count=tool_calls_made,
            )
            return await handler(tool_name, arguments)

        # Execute the agent
        try:
            result = await executor.run(
                prompt=config.prompt,
                tools=config.tools or [],
                tool_handler=tracking_handler,
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
                self.logger.info(f"Agent run {agent_run.id} completed with status {result.status}")

            # Update session status
            if result.status in ("success", "partial"):
                self._session_storage.update_status(child_session.id, "completed")
            else:
                self._session_storage.update_status(child_session.id, "failed")

            # Persist cost to session storage for budget tracking
            if result.cost_info and result.cost_info.total_cost > 0:
                self._session_storage.add_cost(child_session.id, result.cost_info.total_cost)
                self.logger.debug(
                    f"Persisted cost ${result.cost_info.total_cost:.4f} "
                    f"for session {child_session.id}"
                )

            # Remove from in-memory tracking
            self._untrack_running_agent(agent_run.id)

            # Set run_id and child_session_id on the result so callers don't need to call list_runs()
            result.run_id = agent_run.id
            result.child_session_id = child_session.id

            return result

        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}", exc_info=True)
            # On exception, we don't know the actual turns used by the executor,
            # so we pass 0. tool_calls_made is the count we tracked.
            self._run_storage.fail(
                agent_run.id,
                error=str(e),
                tool_calls_count=tool_calls_made,
                turns_used=0,
            )
            self._session_storage.update_status(child_session.id, "failed")
            # Remove from in-memory tracking
            self._untrack_running_agent(agent_run.id)
            return AgentResult(
                output="",
                status="error",
                error=str(e),
                turns_used=0,
            )

    async def run(
        self,
        config: AgentConfig,
        tool_handler: ToolHandler | None = None,
    ) -> AgentResult:
        """
        Run an agent with the given configuration.

        This is the main entry point that combines prepare_run() and execute_run()
        for in-process agent execution.

        Args:
            config: Agent configuration.
            tool_handler: Optional async callable for handling tool calls.
                If not provided, uses a default no-op handler.

        Returns:
            AgentResult with execution outcome.
        """
        # Prepare the run (create session, run record, workflow state)
        result = self.prepare_run(config)

        # If prepare_run returned an error, return it
        if isinstance(result, AgentResult):
            return result

        # Execute the run with the prepared context
        context = result
        return await self.execute_run(context, config, tool_handler)

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

        # Remove from in-memory tracking
        with self._running_agents_lock:
            self._running_agents.pop(run_id, None)

        return True

    # -------------------------------------------------------------------------
    # In-memory Running Agents Management
    # -------------------------------------------------------------------------

    def _track_running_agent(
        self,
        run_id: str,
        parent_session_id: str | None,
        child_session_id: str,
        provider: str,
        prompt: str,
        mode: str = "in_process",
        workflow_name: str | None = None,
        model: str | None = None,
        worktree_id: str | None = None,
        pid: int | None = None,
        terminal_type: str | None = None,
        master_fd: int | None = None,
    ) -> RunningAgent:
        """
        Add an agent to the in-memory running agents dict.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID.
            parent_session_id: Session that spawned this agent.
            child_session_id: Child session created for this agent.
            provider: LLM provider.
            prompt: The task prompt (not stored, kept for API compatibility).
            mode: Execution mode.
            workflow_name: Workflow being executed.
            model: Model override (not stored, kept for API compatibility).
            worktree_id: Worktree being used.
            pid: Process ID for terminal/headless mode.
            terminal_type: Terminal type for terminal mode.
            master_fd: PTY master file descriptor for embedded mode.

        Returns:
            The created RunningAgent instance.
        """
        # Note: The registry's RunningAgent uses 'session_id' for child session
        # and doesn't store prompt/model (those are in the database AgentRun record)
        _ = prompt  # Kept for API compatibility, stored in AgentRun
        _ = model  # Kept for API compatibility, stored in AgentRun
        running_agent = RunningAgent(
            run_id=run_id,
            session_id=child_session_id,
            parent_session_id=parent_session_id if parent_session_id else "",
            mode=mode,
            provider=provider,
            workflow_name=workflow_name,
            worktree_id=worktree_id,
            pid=pid,
            terminal_type=terminal_type,
            master_fd=master_fd,
        )

        with self._running_agents_lock:
            self._running_agents[run_id] = running_agent

        self.logger.debug(f"Tracking running agent {run_id} (mode={mode})")
        return running_agent

    def _untrack_running_agent(self, run_id: str) -> RunningAgent | None:
        """
        Remove an agent from the in-memory running agents dict.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID to remove.

        Returns:
            The removed RunningAgent, or None if not found.
        """
        with self._running_agents_lock:
            agent = self._running_agents.pop(run_id, None)

        if agent:
            self.logger.debug(f"Untracked running agent {run_id}")
        return agent

    def _update_running_agent(
        self,
        run_id: str,
        turns_used: int | None = None,
        tool_calls_count: int | None = None,
    ) -> RunningAgent | None:
        """
        Update in-memory state for a running agent.

        Thread-safe operation using a lock.

        Note: The registry's RunningAgent is lightweight and doesn't track
        turns_used, tool_calls_count, or last_activity. These are tracked
        in the database AgentRun record instead. This method verifies the
        agent exists but doesn't modify it.

        Args:
            run_id: The agent run ID.
            turns_used: Updated turns count (logged but not stored in-memory).
            tool_calls_count: Updated tool calls count (logged but not stored in-memory).

        Returns:
            The RunningAgent if found, None otherwise.
        """
        _ = turns_used  # Tracked in database AgentRun record
        _ = tool_calls_count  # Tracked in database AgentRun record
        with self._running_agents_lock:
            agent = self._running_agents.get(run_id)

        return agent

    def get_running_agent(self, run_id: str) -> RunningAgent | None:
        """
        Get a running agent by ID.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID.

        Returns:
            The RunningAgent if found and running, None otherwise.
        """
        with self._running_agents_lock:
            return self._running_agents.get(run_id)

    def get_running_agents(
        self,
        parent_session_id: str | None = None,
    ) -> list[RunningAgent]:
        """
        Get all running agents, optionally filtered by parent session.

        Thread-safe operation using a lock.

        Args:
            parent_session_id: Optional filter by parent session.

        Returns:
            List of running agents.
        """
        with self._running_agents_lock:
            agents = list(self._running_agents.values())

        if parent_session_id:
            agents = [a for a in agents if a.parent_session_id == parent_session_id]

        return agents

    def get_running_agents_count(self) -> int:
        """
        Get count of running agents.

        Thread-safe operation using a lock.

        Returns:
            Number of running agents.
        """
        with self._running_agents_lock:
            return len(self._running_agents)

    def is_agent_running(self, run_id: str) -> bool:
        """
        Check if an agent is currently running.

        Thread-safe operation using a lock.

        Args:
            run_id: The agent run ID.

        Returns:
            True if the agent is in the running dict.
        """
        with self._running_agents_lock:
            return run_id in self._running_agents

    def _create_workflow_filtered_handler(
        self,
        base_handler: ToolHandler,
        session_id: str,
        workflow_definition: WorkflowDefinition,
    ) -> ToolHandler:
        """
        Create a tool handler that enforces workflow tool restrictions.

        Args:
            base_handler: The underlying tool handler to call for allowed tools.
            session_id: Session ID for looking up workflow state.
            workflow_definition: The workflow definition with step restrictions.

        Returns:
            An async callable that filters tools based on workflow state.
        """

        async def filtered_handler(tool_name: str, arguments: dict[str, Any]) -> ToolResult:
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
                self.logger.warning(f"Tool '{tool_name}' blocked by workflow step '{state.step}'")
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
