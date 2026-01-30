"""
Hook Manager - Clean Coordinator for Claude Code Hooks.

This is the refactored HookManager that serves purely as a coordinator,
delegating all work to focused subsystems. It replaces the 5,774-line
God Object with a ~300-line routing layer.

Architecture:
    HookManager creates and coordinates subsystems:
    - Session-agnostic: DaemonClient, TranscriptProcessor
    - Session-scoped: SessionManager
    - Workflow-driven: WorkflowEngine handles session handoff via generate_handoff action

Example:
    ```python
    from gobby.hooks.hook_manager import HookManager

    manager = HookManager(
        daemon_host="localhost",
        daemon_port=60887
    )

    result = manager.execute(
        hook_type="session-start",
        input_data={"external_id": "abc123", ...}
    )
    ```
"""

import asyncio
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from gobby.autonomous.progress_tracker import ProgressTracker
from gobby.autonomous.stop_registry import StopRegistry
from gobby.autonomous.stuck_detector import StuckDetector
from gobby.hooks.event_handlers import EventHandlers
from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.hooks.health_monitor import HealthMonitor
from gobby.hooks.plugins import PluginLoader, run_plugin_handlers
from gobby.hooks.session_coordinator import SessionCoordinator
from gobby.hooks.skill_manager import HookSkillManager
from gobby.hooks.webhooks import WebhookDispatcher
from gobby.memory.manager import MemoryManager
from gobby.sessions.manager import SessionManager
from gobby.sessions.summary import SummaryFileGenerator
from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
from gobby.storage.agents import LocalAgentRunManager
from gobby.storage.database import LocalDatabase
from gobby.storage.memories import LocalMemoryManager
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks import LocalTaskManager
from gobby.storage.worktrees import LocalWorktreeManager
from gobby.utils.daemon_client import DaemonClient
from gobby.workflows.hooks import WorkflowHookHandler
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

if TYPE_CHECKING:
    pass

# Backward-compatible alias
TranscriptProcessor = ClaudeTranscriptParser

if TYPE_CHECKING:
    from gobby.llm.service import LLMService


class HookManager:
    """
    Session-scoped coordinator for Claude Code hooks.

    Delegates all work to subsystems:
    - DaemonClient: HTTP communication with Gobby daemon
    - TranscriptProcessor: JSONL parsing and analysis
    - WorkflowEngine: Handles session handoff and LLM-powered summaries

    Session ID Mapping:
        There are two types of session IDs used throughout the system:

        | Name                     | Description                                    | Example                                |
        |--------------------------|------------------------------------------------|----------------------------------------|
        | external_id / session_id | CLI's internal session UUID (Claude Code, etc) | 683bc13e-091e-4911-9e59-e7546e385cd6   |
        | _platform_session_id     | Gobby's internal session.id (database PK)      | 0ebb2c00-0f58-4c39-9370-eba1833dec33   |

        The _platform_session_id is derived from session_manager.get_session_id(external_id, source)
        which looks up Gobby's session by the CLI's external_id.

        When injecting into agent context:
        - "session_id" in response.metadata = Gobby's _platform_session_id (for MCP tool calls)
        - "external_id" in response.metadata = CLI's session UUID (for transcript lookups)

    Attributes:
        daemon_host: Host for daemon communication
        daemon_port: Port for daemon communication
        log_file: Full path to log file
        logger: Configured logger instance
    """

    def __init__(
        self,
        daemon_host: str = "localhost",
        daemon_port: int = 60887,
        llm_service: "LLMService | None" = None,
        config: Any | None = None,
        log_file: str | None = None,
        log_max_bytes: int = 10 * 1024 * 1024,  # 10MB
        log_backup_count: int = 5,
        broadcaster: Any | None = None,
        mcp_manager: Any | None = None,
        message_processor: Any | None = None,
        memory_sync_manager: Any | None = None,
        task_sync_manager: Any | None = None,
    ):
        """
        Initialize HookManager with subsystems.

        Args:
            daemon_host: Daemon host for communication
            daemon_port: Daemon port for communication
            llm_service: Optional LLMService for multi-provider support
            config: Optional DaemonConfig instance for feature configuration
            log_file: Full path to log file (default: ~/.gobby/logs/hook-manager.log)
            log_max_bytes: Max log file size before rotation
            log_backup_count: Number of backup log files
            broadcaster: Optional HookEventBroadcaster instance
            mcp_manager: Optional MCPClientManager instance
            message_processor: SessionMessageProcessor instance
            memory_sync_manager: Optional MemorySyncManager instance
            task_sync_manager: Optional TaskSyncManager instance
        """
        self.daemon_host = daemon_host
        self.daemon_port = daemon_port
        self.daemon_url = f"http://{daemon_host}:{daemon_port}"
        self.log_file = log_file or str(Path.home() / ".gobby" / "logs" / "hook-manager.log")
        self.log_max_bytes = log_max_bytes
        self.log_backup_count = log_backup_count
        self.broadcaster = broadcaster
        self.mcp_manager = mcp_manager
        self._message_processor = message_processor
        self.memory_sync_manager = memory_sync_manager
        self.task_sync_manager = task_sync_manager

        # Capture event loop for thread-safe broadcasting (if running in async context)
        self._loop: asyncio.AbstractEventLoop | None
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        # Setup logging first
        self.logger = self._setup_logging()

        # Store LLM service
        self._llm_service = llm_service

        # Load configuration - prefer passed config over loading new one
        self._config = config
        if not self._config:
            try:
                from gobby.config.app import load_config

                self._config = load_config()
            except Exception as e:
                self.logger.error(
                    f"Failed to load config in HookManager, using defaults: {e}",
                    exc_info=True,
                )

        # Extract config values
        if self._config:
            health_check_interval = self._config.daemon_health_check_interval

        else:
            health_check_interval = 10.0

        # Initialize Database - use config's database_path if available
        if self._config and self._config.database_path:
            db_path = Path(self._config.database_path).expanduser()
            self._database = LocalDatabase(db_path)
        else:
            self._database = LocalDatabase()

        # Create session-agnostic subsystems (shared across all sessions)
        self._daemon_client = DaemonClient(
            host=daemon_host,
            port=daemon_port,
            timeout=5.0,
            logger=self.logger,
        )
        self._transcript_processor = TranscriptProcessor(logger_instance=self.logger)

        # Create local storage for sessions
        self._session_storage = LocalSessionManager(self._database)
        self._session_task_manager = SessionTaskManager(self._database)

        # Initialize Memory storage
        self._memory_storage = LocalMemoryManager(self._database)
        self._message_manager = LocalSessionMessageManager(self._database)
        self._task_manager = LocalTaskManager(self._database)

        # Initialize Agent Run and Worktree managers (for terminal mode result capture)
        self._agent_run_manager = LocalAgentRunManager(self._database)
        self._worktree_manager = LocalWorktreeManager(self._database)

        # Initialize Artifact storage and capture hook
        from gobby.hooks.artifact_capture import ArtifactCaptureHook
        from gobby.storage.artifacts import LocalArtifactManager

        self._artifact_manager = LocalArtifactManager(self._database)
        self._artifact_capture_hook = ArtifactCaptureHook(artifact_manager=self._artifact_manager)

        # Initialize autonomous execution components
        self._stop_registry = StopRegistry(self._database)
        self._progress_tracker = ProgressTracker(self._database)
        self._stuck_detector = StuckDetector(
            self._database, progress_tracker=self._progress_tracker
        )

        # Use config or defaults
        memory_config = (
            self._config.memory if self._config and hasattr(self._config, "memory") else None
        )

        if not memory_config:
            from gobby.config.persistence import MemoryConfig

            memory_config = MemoryConfig()

        self._memory_manager = MemoryManager(self._database, memory_config)

        # Initialize Workflow Engine (Phase 0-2 + 3 Integration)
        # Import WorkflowEngine here to avoid circular import (hooks -> hook_manager -> engine -> hooks)
        from gobby.workflows.actions import ActionExecutor
        from gobby.workflows.engine import WorkflowEngine
        from gobby.workflows.templates import TemplateEngine

        # Workflow loader handles project-specific paths dynamically via project_path parameter
        # Global workflows are loaded from ~/.gobby/workflows/
        # Project-specific workflows are loaded from {project_path}/.gobby/workflows/
        # Workflows are installed via `gobby install` from install/shared/workflows/
        self._workflow_loader = WorkflowLoader(workflow_dirs=[Path.home() / ".gobby" / "workflows"])
        self._workflow_state_manager = WorkflowStateManager(self._database)

        # Initialize Template Engine
        # We can pass template directory from package templates or user templates
        # For now, let's include the built-in templates dir if we can find it
        # Assuming templates are in package 'gobby.templates.workflows'?
        # Or just use the one we are about to create in project root?
        # Ideally, we should look for templates in typical locations.
        # But 'TemplateEngine' constructor takes optional dirs.
        self._template_engine = TemplateEngine()

        # Get websocket_server from broadcaster if available
        websocket_server = None
        if self.broadcaster and hasattr(self.broadcaster, "websocket_server"):
            websocket_server = self.broadcaster.websocket_server

        self._action_executor = ActionExecutor(
            db=self._database,
            session_manager=self._session_storage,
            template_engine=self._template_engine,
            llm_service=self._llm_service,
            transcript_processor=self._transcript_processor,
            config=self._config,
            mcp_manager=self.mcp_manager,
            memory_manager=self._memory_manager,
            memory_sync_manager=self.memory_sync_manager,
            task_manager=self._task_manager,
            task_sync_manager=self.task_sync_manager,
            session_task_manager=self._session_task_manager,
            stop_registry=self._stop_registry,
            progress_tracker=self._progress_tracker,
            stuck_detector=self._stuck_detector,
            websocket_server=websocket_server,
        )
        self._workflow_engine = WorkflowEngine(
            loader=self._workflow_loader,
            state_manager=self._workflow_state_manager,
            action_executor=self._action_executor,
        )
        # Register task_manager with evaluator for task_tree_complete() condition helper
        if self._task_manager and self._workflow_engine.evaluator:
            self._workflow_engine.evaluator.register_task_manager(self._task_manager)
        # Register stop_registry with evaluator for has_stop_signal() condition helper
        if self._stop_registry and self._workflow_engine.evaluator:
            self._workflow_engine.evaluator.register_stop_registry(self._stop_registry)
        workflow_timeout: float = 0.0  # 0 = no timeout
        workflow_enabled = True
        if self._config:
            workflow_timeout = self._config.workflow.timeout
            workflow_enabled = self._config.workflow.enabled

        self._workflow_handler = WorkflowHookHandler(
            engine=self._workflow_engine,
            loop=self._loop,
            timeout=workflow_timeout,
            enabled=workflow_enabled,
        )

        # Initialize Failover Summary Generator
        self._summary_file_generator = SummaryFileGenerator(
            transcript_processor=self._transcript_processor,
            logger_instance=self.logger,
            llm_service=self._llm_service,
            config=self._config,
        )

        # Initialize Webhook Dispatcher (Sprint 8: Webhooks)
        webhooks_config = None
        if self._config and hasattr(self._config, "hook_extensions"):
            webhooks_config = self._config.hook_extensions.webhooks
        if not webhooks_config:
            from gobby.config.extensions import WebhooksConfig

            webhooks_config = WebhooksConfig()
        self._webhook_dispatcher = WebhookDispatcher(webhooks_config)

        # Initialize Plugin Loader (Sprint 9: Python Plugins)
        self._plugin_loader: PluginLoader | None = None
        plugins_config = None
        if self._config and hasattr(self._config, "hook_extensions"):
            plugins_config = self._config.hook_extensions.plugins
        if plugins_config is not None and plugins_config.enabled:
            self._plugin_loader = PluginLoader(plugins_config)
            try:
                loaded = self._plugin_loader.load_all()
                if loaded:
                    self.logger.info(
                        f"Loaded {len(loaded)} plugin(s): {', '.join(p.name for p in loaded)}"
                    )
                    # Register plugin actions and conditions with workflow system
                    self._action_executor.register_plugin_actions(self._plugin_loader.registry)
                    self._workflow_engine.evaluator.register_plugin_conditions(
                        self._plugin_loader.registry
                    )
            except Exception as e:
                self.logger.error(f"Failed to load plugins: {e}", exc_info=True)

        # Session manager handles registration, lookup, and status updates
        # Note: source is passed explicitly per call (Phase 2C+), not stored in manager
        self._session_manager = SessionManager(
            session_storage=self._session_storage,
            logger_instance=self.logger,
            config=self._config,
        )

        # Session coordination (delegated to SessionCoordinator)
        self._session_coordinator = SessionCoordinator(
            session_storage=self._session_storage,
            message_processor=self._message_processor,
            agent_run_manager=self._agent_run_manager,
            worktree_manager=self._worktree_manager,
            logger=self.logger,
        )

        # Daemon health check monitoring (delegated to HealthMonitor)
        self._health_monitor = HealthMonitor(
            daemon_client=self._daemon_client,
            health_check_interval=health_check_interval,
            logger=self.logger,
        )

        # Skill manager for core skill injection
        self._skill_manager = HookSkillManager()

        # Track sessions that have received full metadata injection
        # Key: "{platform_session_id}:{source}" - cleared on daemon restart
        self._injected_sessions: set[str] = set()

        # Event handlers (delegated to EventHandlers module)
        self._event_handlers = EventHandlers(
            session_manager=self._session_manager,
            workflow_handler=self._workflow_handler,
            session_storage=self._session_storage,
            session_task_manager=self._session_task_manager,
            message_processor=self._message_processor,
            summary_file_generator=self._summary_file_generator,
            task_manager=self._task_manager,
            session_coordinator=self._session_coordinator,
            message_manager=self._message_manager,
            skill_manager=self._skill_manager,
            skills_config=self._config.skills if self._config else None,
            artifact_capture_hook=self._artifact_capture_hook,
            workflow_config=self._config.workflow if self._config else None,
            get_machine_id=self.get_machine_id,
            resolve_project_id=self._resolve_project_id,
            logger=self.logger,
        )

        # Start background health check monitoring
        self._start_health_check_monitoring()

        # Re-register active sessions with message processor (after daemon restart)
        self._reregister_active_sessions()

        self.logger.debug("HookManager initialized")

    def _setup_logging(self) -> logging.Logger:
        """
        Setup structured logging with rotation.

        Returns:
            Configured logger instance
        """
        # Create logger
        logger = logging.getLogger("gobby.hooks")
        logger.setLevel(logging.DEBUG)

        # Avoid duplicate handlers if logger already configured
        if logger.handlers:
            return logger

        # File handler with rotation - use full path from config
        # Expand ~ to home directory before creating directories
        log_file_path = Path(self.log_file).expanduser()
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=self.log_max_bytes,
            backupCount=self.log_backup_count,
        )
        file_handler.setLevel(logging.DEBUG)

        # Formatter with context
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

        return logger

    def _reregister_active_sessions(self) -> None:
        """
        Re-register active sessions with the message processor.

        Called during HookManager initialization to restore message processing
        for sessions that were active before a daemon restart.
        """
        self._session_coordinator.reregister_active_sessions()

    def _start_health_check_monitoring(self) -> None:
        """Start background daemon health check monitoring."""
        self._health_monitor.start()

    def _get_cached_daemon_status(self) -> tuple[bool, str | None, str, str | None]:
        """
        Get cached daemon status without making HTTP call.

        Returns:
            Tuple of (is_ready, message, status, error)
        """
        return self._health_monitor.get_cached_status()

    def handle(self, event: HookEvent) -> HookResponse:
        """
        Handle unified HookEvent from any CLI source.

        This is the main entry point for hook handling. Adapters translate
        CLI-specific payloads to HookEvent and call this method.

        Args:
            event: Unified HookEvent with event_type, session_id, source, and data.

        Returns:
            HookResponse with decision, context, and reason fields.

        Raises:
            ValueError: If event_type has no registered handler.
        """
        # Check daemon status (cached)
        is_ready, _, daemon_status, error_reason = self._get_cached_daemon_status()

        # Critical hooks that should retry before giving up
        # These hooks are essential for session context preservation
        critical_hooks = {
            HookEventType.SESSION_START,
            HookEventType.SESSION_END,
            HookEventType.PRE_COMPACT,
        }
        retry_delays = [0.5, 1.0, 2.0]  # Exponential backoff

        # Retry with fresh health checks for critical hooks
        if not is_ready and event.event_type in critical_hooks:
            for attempt, delay in enumerate(retry_delays, 1):
                time.sleep(delay)
                is_ready = self._health_monitor.check_now()
                if is_ready:
                    self.logger.info(
                        f"Daemon recovered after {attempt} retry(ies) for {event.event_type}"
                    )
                    break
                self.logger.debug(
                    f"Daemon still unavailable, retry {attempt}/{len(retry_delays)} "
                    f"for {event.event_type}"
                )

        if not is_ready:
            self.logger.warning(
                f"Daemon not available after retries, skipping hook execution: {event.event_type}. "
                f"Status: {daemon_status}, Error: {error_reason}"
            )
            return HookResponse(
                decision="allow",  # Fail-open
                reason=f"Daemon {daemon_status}: {error_reason or 'Unknown'}",
            )

        # Look up platform session_id from cli_key (event.session_id is the cli_key)
        external_id = event.session_id
        platform_session_id = None

        if external_id:
            # Check SessionManager's cache first (keyed by (external_id, source))
            platform_session_id = self._session_manager.get_session_id(
                external_id, event.source.value
            )

            # If not in mapping and not session-start, try to query database
            if not platform_session_id and event.event_type != HookEventType.SESSION_START:
                with self._session_coordinator.get_lookup_lock():
                    # Double check in case another thread finished lookup
                    platform_session_id = self._session_manager.get_session_id(
                        external_id, event.source.value
                    )

                    if not platform_session_id:
                        self.logger.debug(
                            f"Session not in mapping, querying database for external_id={external_id}"
                        )
                        # Resolve context for lookup
                        machine_id = event.machine_id or self.get_machine_id()
                        cwd = event.data.get("cwd")
                        project_id = self._resolve_project_id(event.data.get("project_id"), cwd)

                        # Lookup with full composite key
                        platform_session_id = self._session_manager.lookup_session_id(
                            external_id,
                            source=event.source.value,
                            machine_id=machine_id,
                            project_id=project_id,
                        )
                        if platform_session_id:
                            self.logger.debug(
                                f"Found session_id {platform_session_id} for external_id {external_id}"
                            )
                        else:
                            # Auto-register session if not found
                            self.logger.debug(
                                f"Session not found for external_id={external_id}, auto-registering"
                            )
                            platform_session_id = self._session_manager.register_session(
                                external_id=external_id,
                                machine_id=machine_id,
                                project_id=project_id,
                                parent_session_id=None,
                                jsonl_path=event.data.get("transcript_path"),
                                source=event.source.value,
                                project_path=cwd,
                            )

            # Resolve active task for this session if we have a platform session ID
            if platform_session_id:
                try:
                    # Get tasks linked with 'worked_on' action which implies active focus
                    session_tasks = self._session_task_manager.get_session_tasks(
                        platform_session_id
                    )
                    # Filter for active 'worked_on' tasks - taking the most recent one
                    active_tasks = [t for t in session_tasks if t.get("action") == "worked_on"]
                    if active_tasks:
                        # Use the most recent task - populate full task context
                        task = active_tasks[0]["task"]
                        event.task_id = task.id
                        event.metadata["_task_context"] = {
                            "id": task.id,
                            "title": task.title,
                            "status": task.status,
                        }
                        # Keep legacy field for backwards compatibility
                        event.metadata["_task_title"] = task.title
                except Exception as e:
                    self.logger.warning(f"Failed to resolve active task: {e}")

            # Store platform session_id in event metadata for handlers
            event.metadata["_platform_session_id"] = platform_session_id

        # Get handler for this event type
        handler = self._get_event_handler(event.event_type)
        if handler is None:
            self.logger.warning(f"No handler for event type: {event.event_type}")
            return HookResponse(decision="allow")  # Fail-open for unknown events

        # --- Workflow Engine Evaluation (Phase 3) ---
        # Evalute workflow rules before executing specific handlers
        workflow_context = None
        try:
            workflow_response = self._workflow_handler.handle(event)

            # If workflow blocks or asks, return immediately
            if workflow_response.decision != "allow":
                self.logger.info(f"Workflow blocked/modified event: {workflow_response.decision}")
                return workflow_response

            # Capture context to merge later
            if workflow_response.context:
                workflow_context = workflow_response.context

        except Exception as e:
            self.logger.error(f"Workflow evaluation failed: {e}", exc_info=True)
            # Fail-open for workflow errors
        # --------------------------------------------

        # --- Blocking Webhooks Evaluation (Sprint 8) ---
        # Dispatch to blocking webhooks BEFORE handler execution
        try:
            webhook_results = self._dispatch_webhooks_sync(event, blocking_only=True)
            decision, reason = self._webhook_dispatcher.get_blocking_decision(webhook_results)
            if decision == "block":
                self.logger.info(f"Webhook blocked event: {reason}")
                return HookResponse(decision="block", reason=reason or "Blocked by webhook")
        except Exception as e:
            self.logger.error(f"Blocking webhook dispatch failed: {e}", exc_info=True)
            # Fail-open for webhook errors
        # -----------------------------------------------

        # --- Plugin Pre-Handlers (Sprint 9: can block) ---
        if self._plugin_loader:
            try:
                pre_response = run_plugin_handlers(self._plugin_loader.registry, event, pre=True)
                if pre_response and pre_response.decision in ("deny", "block"):
                    self.logger.info(f"Plugin blocked event: {pre_response.reason}")
                    return pre_response
            except Exception as e:
                self.logger.error(f"Plugin pre-handler failed: {e}", exc_info=True)
                # Fail-open for plugin errors
        # -------------------------------------------------

        # Execute handler
        try:
            response = handler(event)

            # Copy session metadata from event to response for adapter injection
            # The adapter reads response.metadata to inject session info into agent context
            if event.metadata.get("_platform_session_id"):
                platform_session_id = event.metadata["_platform_session_id"]
                response.metadata["session_id"] = platform_session_id
                # Look up seq_num for session_ref (#N format)
                if self._session_storage:
                    session_obj = self._session_storage.get(platform_session_id)
                    if session_obj and session_obj.seq_num:
                        response.metadata["session_ref"] = f"#{session_obj.seq_num}"

                # Track first hook per session for token optimization
                # Adapters use this flag to inject full metadata only on first hook
                session_key = f"{platform_session_id}:{event.source.value}"
                is_first = session_key not in self._injected_sessions
                if is_first:
                    self._injected_sessions.add(session_key)
                response.metadata["_first_hook_for_session"] = is_first
            if event.session_id:  # external_id (e.g., Claude Code's session UUID)
                response.metadata["external_id"] = event.session_id
            if event.machine_id:
                response.metadata["machine_id"] = event.machine_id
            if event.project_id:
                response.metadata["project_id"] = event.project_id
            # Copy terminal context if present
            for key in [
                "terminal_term_program",
                "terminal_tty",
                "terminal_parent_pid",
                "terminal_iterm_session_id",
                "terminal_term_session_id",
                "terminal_kitty_window_id",
                "terminal_tmux_pane",
                "terminal_vscode_terminal_id",
                "terminal_alacritty_socket",
            ]:
                if event.metadata.get(key):
                    response.metadata[key] = event.metadata[key]

            # Merge workflow context if present
            if workflow_context:
                if response.context:
                    response.context = f"{response.context}\n\n{workflow_context}"
                else:
                    response.context = workflow_context

            # Broadcast event (fire-and-forget)
            if self.broadcaster:
                try:
                    # Case 1: Running in an event loop (e.g. from app-server client)
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.broadcaster.broadcast_event(event, response))
                except RuntimeError:
                    # Case 2: Running in a thread (e.g. from HTTP endpoint via to_thread)
                    if self._loop:
                        try:
                            # Use the main loop captured at init
                            asyncio.run_coroutine_threadsafe(
                                self.broadcaster.broadcast_event(event, response),
                                self._loop,
                            )
                        except Exception as e:
                            self.logger.warning(f"Failed to schedule broadcast threadsafe: {e}")
                    else:
                        self.logger.debug("No event loop available for broadcasting")

            # Dispatch non-blocking webhooks (fire-and-forget)
            try:
                self._dispatch_webhooks_async(event)
            except Exception as e:
                self.logger.warning(f"Non-blocking webhook dispatch failed: {e}")

            # --- Plugin Post-Handlers (Sprint 9: observe only) ---
            if self._plugin_loader:
                try:
                    run_plugin_handlers(
                        self._plugin_loader.registry,
                        event,
                        pre=False,
                        core_response=response,
                    )
                except Exception as e:
                    self.logger.error(f"Plugin post-handler failed: {e}", exc_info=True)
                    # Continue - post-handlers are observe-only
            # -----------------------------------------------------

            return cast(HookResponse, response)
        except Exception as e:
            self.logger.error(f"Event handler {event.event_type} failed: {e}", exc_info=True)
            # Fail-open on handler errors
            return HookResponse(
                decision="allow",
                reason=f"Handler error: {e}",
            )

    def _get_event_handler(self, event_type: HookEventType) -> Any | None:
        """
        Get the handler method for a given HookEventType.

        Args:
            event_type: The unified event type enum value.

        Returns:
            Handler method or None if not found.
        """
        return self._event_handlers.get_handler(event_type)

    def _dispatch_webhooks_sync(self, event: HookEvent, blocking_only: bool = False) -> list[Any]:
        """
        Dispatch webhooks synchronously (for blocking webhooks).

        Args:
            event: The hook event to dispatch.
            blocking_only: If True, only dispatch to blocking (can_block=True) endpoints.

        Returns:
            List of WebhookResult objects.
        """
        from gobby.hooks.webhooks import WebhookResult

        if not self._webhook_dispatcher.config.enabled:
            return []

        # Filter endpoints if blocking_only
        matching_endpoints = [
            ep
            for ep in self._webhook_dispatcher.config.endpoints
            if ep.enabled
            and self._webhook_dispatcher._matches_event(ep, event.event_type.value)
            and (not blocking_only or ep.can_block)
        ]

        if not matching_endpoints:
            return []

        # Build payload once
        payload = self._webhook_dispatcher._build_payload(event)

        # Run async dispatch in sync context
        async def dispatch_all() -> list[WebhookResult]:
            results: list[WebhookResult] = []
            for endpoint in matching_endpoints:
                result = await self._webhook_dispatcher._dispatch_single(endpoint, payload)
                results.append(result)
            return results

        # Execute in event loop
        try:
            asyncio.get_running_loop()
            # Already in async context - this method shouldn't be called here
            # Fall back to creating a new thread to run the coroutine synchronously
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, dispatch_all())
                return future.result()
        except RuntimeError:
            # Not in async context, run synchronously
            return asyncio.run(dispatch_all())

    def _dispatch_webhooks_async(self, event: HookEvent) -> None:
        """
        Dispatch non-blocking webhooks asynchronously (fire-and-forget).

        Args:
            event: The hook event to dispatch.
        """
        if not self._webhook_dispatcher.config.enabled:
            return

        # Filter to non-blocking endpoints only
        matching_endpoints = [
            ep
            for ep in self._webhook_dispatcher.config.endpoints
            if ep.enabled
            and self._webhook_dispatcher._matches_event(ep, event.event_type.value)
            and not ep.can_block
        ]

        if not matching_endpoints:
            return

        # Build payload
        payload = self._webhook_dispatcher._build_payload(event)

        async def dispatch_all() -> None:
            tasks = [
                self._webhook_dispatcher._dispatch_single(ep, payload) for ep in matching_endpoints
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Fire and forget
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(dispatch_all())
        except RuntimeError:
            # No event loop, try using captured loop
            if self._loop:
                try:
                    asyncio.run_coroutine_threadsafe(dispatch_all(), self._loop)
                except Exception as e:
                    self.logger.warning(f"Failed to schedule async webhook: {e}")

    def shutdown(self) -> None:
        """
        Clean up HookManager resources on daemon shutdown.

        Stops background health check monitoring and transcript watchers.
        """
        self.logger.debug("HookManager shutting down")

        # Stop health check monitoring (delegated to HealthMonitor)
        self._health_monitor.stop()

        # Close webhook dispatcher HTTP client
        try:
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._webhook_dispatcher.close(), self._loop
                ).result(timeout=5.0)
            else:
                asyncio.run(self._webhook_dispatcher.close())
        except Exception as e:
            self.logger.warning(f"Failed to close webhook dispatcher: {e}")

        if hasattr(self, "_database"):
            self._database.close()

        self.logger.debug("HookManager shutdown complete")

    # ==================== HELPER METHODS ====================

    def get_machine_id(self) -> str:
        """Get unique machine identifier."""
        from gobby.utils.machine_id import get_machine_id as _get_machine_id

        result = _get_machine_id()
        return result or "unknown-machine"

    def _resolve_project_id(self, project_id: str | None, cwd: str | None) -> str:
        """
        Resolve project_id from cwd if not provided.

        If project_id is given, returns it directly.
        Otherwise, looks up project from .gobby/project.json in the cwd.
        If no project.json exists, automatically initializes the project.

        Args:
            project_id: Optional explicit project ID
            cwd: Current working directory path

        Returns:
            Project ID (existing or newly created)
        """
        if project_id:
            return project_id

        # Get cwd or use current directory
        working_dir = Path(cwd) if cwd else Path.cwd()

        # Look up project from .gobby/project.json
        from gobby.utils.project_context import get_project_context

        project_context = get_project_context(working_dir)
        if project_context and project_context.get("id"):
            return str(project_context["id"])

        # No project.json found - auto-initialize the project
        from gobby.utils.project_init import initialize_project

        result = initialize_project(cwd=working_dir)
        self.logger.info(f"Auto-initialized project '{result.project_name}' in {working_dir}")
        return result.project_id
