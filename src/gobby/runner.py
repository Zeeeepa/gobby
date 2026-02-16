from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import uvicorn

from gobby.agents.runner import AgentRunner
from gobby.app_context import ServiceContainer
from gobby.config.app import load_config
from gobby.llm import LLMService, create_llm_service
from gobby.llm.resolver import ExecutorRegistry
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.memory.manager import MemoryManager
from gobby.memory.vectorstore import VectorStore
from gobby.servers.http import HTTPServer
from gobby.servers.websocket.models import WebSocketConfig
from gobby.servers.websocket.server import WebSocketServer
from gobby.sessions.lifecycle import SessionLifecycleManager
from gobby.sessions.processor import SessionMessageProcessor
from gobby.storage.clones import LocalCloneManager
from gobby.storage.database import DatabaseProtocol, LocalDatabase
from gobby.storage.mcp import LocalMCPManager
from gobby.storage.migrations import run_migrations
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks import LocalTaskManager
from gobby.storage.worktrees import LocalWorktreeManager
from gobby.sync.memories import MemorySyncManager
from gobby.sync.tasks import TaskSyncManager
from gobby.tasks.validation import TaskValidator
from gobby.utils.logging import setup_file_logging
from gobby.utils.machine_id import get_machine_id
from gobby.worktrees.git import WorktreeGitManager

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Strip Claude Code session marker so SDK subprocess calls don't fail with
# "cannot be launched inside another Claude Code session" when the daemon
# was started/restarted from within a Claude Code session.
os.environ.pop("CLAUDECODE", None)

# Suppress litellm's never-awaited coroutine warnings (upstream bug in LoggingWorker)
import warnings

warnings.filterwarnings("ignore", message="coroutine.*async_success_handler.*was never awaited")

# Type hints for pipeline components (imported lazily at runtime)
if TYPE_CHECKING:
    from gobby.scheduler.scheduler import CronScheduler
    from gobby.storage.cron import CronJobStorage
    from gobby.storage.pipelines import LocalPipelineExecutionManager
    from gobby.workflows.loader import WorkflowLoader
    from gobby.workflows.pipeline_executor import PipelineExecutor

logger = logging.getLogger(__name__)


class GobbyRunner:
    """Runner for Gobby daemon."""

    def __init__(self, config_path: Path | None = None, verbose: bool = False):
        setup_file_logging(verbose=verbose)

        if config_path is not None and not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}. "
                f"Use 'gobby init' to create a default config, "
                f"or omit --config to use the default path (~/.gobby/config.yaml)."
            )
        self._config_file = str(config_path) if config_path else None
        self.config = load_config(self._config_file)
        self.verbose = verbose
        self.machine_id = get_machine_id()

        # Check tmux availability (agent spawning requires it)
        import shutil

        from gobby.agents.tmux.wsl_compat import needs_wsl

        if needs_wsl():
            if not shutil.which("wsl"):
                logger.warning(
                    "WSL is not installed. Agent spawning in terminal mode will not work. "
                    "Install: wsl --install"
                )
        elif not shutil.which("tmux"):
            logger.warning(
                "tmux is not installed. Agent spawning in terminal mode will not work. "
                "Install: brew install tmux (macOS), apt install tmux (Linux)"
            )
        self._shutdown_requested = False
        self._metrics_cleanup_task: asyncio.Task[None] | None = None

        # Initialize local storage with dual-write if in project context
        self.database = self._init_database()

        # Phase 2: Reload config from DB (secrets > env vars)
        # Phase 1 (above) used env vars only to bootstrap the database path.
        # Now that the DB is available, load config from config_store with secrets.
        from gobby.storage.config_store import ConfigStore
        from gobby.storage.secrets import SecretStore

        self.secret_store = SecretStore(self.database)
        self.config_store = ConfigStore(self.database)
        self.config = load_config(
            config_file=self._config_file,
            secret_resolver=self.secret_store.get,
            config_store=self.config_store,
        )

        self.session_manager = LocalSessionManager(self.database)
        self.message_manager = LocalSessionMessageManager(self.database)
        self.task_manager = LocalTaskManager(self.database)
        self.session_task_manager = SessionTaskManager(self.database)

        # Bundled content (skills, prompts, rules, agents) is synced to the DB
        # during `gobby install`, not on every daemon startup.  See
        # src/gobby/cli/install.py -> sync_bundled_content_to_db().

        from gobby.utils.dev import is_dev_mode

        self._dev_mode = is_dev_mode(Path.cwd())

        # Initialize Prompt Manager
        from gobby.storage.prompts import LocalPromptManager

        self.prompt_manager = LocalPromptManager(self.database, dev_mode=self._dev_mode)

        # Initialize Skill Manager and Hub Manager
        from gobby.storage.skills import LocalSkillManager

        self.skill_manager = LocalSkillManager(self.database)

        self.hub_manager: Any | None = None
        try:
            from gobby.config.skills import SkillsConfig
            from gobby.skills.hubs import (
                ClaudePluginsProvider,
                ClawdHubProvider,
                GitHubCollectionProvider,
                HubManager,
                SkillHubProvider,
            )

            skills_config = self.config.skills if hasattr(self.config, "skills") else SkillsConfig()
            self.hub_manager = HubManager(configs=skills_config.hubs)
            self.hub_manager.register_provider_factory("clawdhub", ClawdHubProvider)
            self.hub_manager.register_provider_factory("skillhub", SkillHubProvider)
            self.hub_manager.register_provider_factory(
                "github-collection", GitHubCollectionProvider
            )
            self.hub_manager.register_provider_factory("claude-plugins", ClaudePluginsProvider)
            logger.debug(f"HubManager initialized with {len(skills_config.hubs)} hubs")
        except Exception as e:
            logger.warning(f"Failed to initialize HubManager: {e}")

        # Initialize LLM Service
        self.llm_service: LLMService | None = None  # Added type hint
        try:
            self.llm_service = create_llm_service(self.config)
            logger.debug(f"LLM service initialized: {self.llm_service.enabled_providers}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")

        # Initialize VectorStore and Memory Manager
        self.vector_store: VectorStore | None = None
        self.memory_manager: MemoryManager | None = None
        if hasattr(self.config, "memory"):
            try:
                # Create VectorStore (async initialize() called during startup)
                qdrant_path = self.config.memory.qdrant_path or str(
                    Path.home() / ".gobby" / "qdrant"
                )
                self.vector_store = VectorStore(
                    path=qdrant_path if not self.config.memory.qdrant_url else None,
                    url=self.config.memory.qdrant_url,
                    api_key=self.config.memory.qdrant_api_key,
                )
                self.memory_manager = MemoryManager(
                    self.database,
                    self.config.memory,
                    vector_store=self.vector_store,
                )
            except Exception as e:
                logger.error(f"Failed to initialize MemoryManager: {e}")

        # MCP Proxy Manager - Initialize early for tool access
        # LocalMCPManager handles server/tool storage in SQLite
        self.mcp_db_manager = LocalMCPManager(self.database)

        # Tool Metrics Manager for tracking call statistics
        from gobby.mcp_proxy.metrics import ToolMetricsManager

        self.metrics_manager = ToolMetricsManager(self.database)

        # MCPClientManager loads servers from database on init
        self.mcp_proxy = MCPClientManager(
            mcp_db_manager=self.mcp_db_manager,
            metrics_manager=self.metrics_manager,
        )

        # Task Sync Manager
        self.task_sync_manager = TaskSyncManager(self.task_manager)
        # Wire up change listener for automatic export
        self.task_manager.add_change_listener(self.task_sync_manager.trigger_export)

        # Initialize Memory Sync Manager (Phase 7) & Wire up listeners
        self.memory_sync_manager: MemorySyncManager | None = None
        if hasattr(self.config, "memory_sync") and self.config.memory_sync.enabled:
            if self.memory_manager:
                try:
                    self.memory_sync_manager = MemorySyncManager(
                        db=self.database,
                        memory_manager=self.memory_manager,
                        config=self.config.memory_sync,
                    )
                    # Wire up listener to trigger export on changes
                    self.memory_manager.storage.add_change_listener(
                        self.memory_sync_manager.trigger_export
                    )
                    logger.debug("MemorySyncManager initialized and listener attached")

                    # Force initial synchronous export
                    # Ensures disk state matches DB state before we start serving
                    try:
                        self.memory_sync_manager.export_sync()
                        logger.info("Initial memory sync export completed")
                    except Exception as e:
                        logger.warning(f"Initial memory sync failed: {e}")

                except Exception as e:
                    logger.error(f"Failed to initialize MemorySyncManager: {e}")

        # Session Message Processor (Phase 6)
        # Created here and passed to HTTPServer which injects it into HookManager
        self.message_processor: SessionMessageProcessor | None = None
        if getattr(self.config, "message_tracking", None) and self.config.message_tracking.enabled:
            self.message_processor = SessionMessageProcessor(
                db=self.database,
                poll_interval=self.config.message_tracking.poll_interval,
            )

        # Initialize Task Validator (Phase 7.1)
        self.task_validator: TaskValidator | None = None

        if self.llm_service:
            gobby_tasks_config = self.config.gobby_tasks
            if gobby_tasks_config.validation.enabled:
                try:
                    self.task_validator = TaskValidator(
                        llm_service=self.llm_service,
                        config=gobby_tasks_config.validation,
                        db=self.database,
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize TaskValidator: {e}")

        # Initialize Worktree Storage (Phase 7 - Subagents)
        self.worktree_storage = LocalWorktreeManager(self.database)

        # Initialize Clone Storage (local git clones for isolated development)
        self.clone_storage = LocalCloneManager(self.database)

        # Initialize Git Manager for current project (if in a git repo)
        self.git_manager: WorktreeGitManager | None = None
        self.project_id: str | None = None
        try:
            cwd = Path.cwd()
            project_json = cwd / ".gobby" / "project.json"
            if project_json.exists():
                import json

                project_data = json.loads(project_json.read_text())
                repo_path = project_data.get("repo_path", str(cwd))
                self.project_id = project_data.get("id")
                self.git_manager = WorktreeGitManager(repo_path)
                logger.info(f"Git manager initialized for project: {self.project_id}")
        except Exception as e:
            logger.debug(f"Could not initialize git manager: {e}")

        # Initialize Pipeline Components
        self.workflow_loader: WorkflowLoader | None = None
        self.pipeline_execution_manager: LocalPipelineExecutionManager | None = None
        self.pipeline_executor: PipelineExecutor | None = None
        try:
            from gobby.storage.pipelines import LocalPipelineExecutionManager
            from gobby.workflows.loader import WorkflowLoader
            from gobby.workflows.pipeline_executor import PipelineExecutor
            from gobby.workflows.templates import TemplateEngine

            self.workflow_loader = WorkflowLoader(db=self.database)
            if self.project_id:
                self.pipeline_execution_manager = LocalPipelineExecutionManager(
                    db=self.database,
                    project_id=self.project_id,
                )
                if self.llm_service:
                    self.pipeline_executor = PipelineExecutor(
                        db=self.database,
                        execution_manager=self.pipeline_execution_manager,
                        llm_service=self.llm_service,
                        loader=self.workflow_loader,
                        template_engine=TemplateEngine(),
                    )
                    logger.debug("Pipeline executor initialized")
                else:
                    logger.debug("Pipeline executor not initialized: LLM service not available")
            else:
                logger.debug("Pipeline execution manager not initialized: no project context")
        except Exception as e:
            logger.warning(f"Failed to initialize pipeline components: {e}")

        # Initialize Agent Runner (Phase 7 - Subagents)
        # Create executor registry for lazy executor creation
        self.executor_registry = ExecutorRegistry(config=self.config)
        self.agent_runner: AgentRunner | None = None
        try:
            # Pre-initialize common executors
            executors = {}
            for provider in ["claude", "gemini", "litellm"]:
                try:
                    executors[provider] = self.executor_registry.get(provider=provider)
                    logger.info(f"Pre-initialized {provider} executor")
                except Exception as e:
                    logger.debug(f"Could not pre-initialize {provider} executor: {e}")

            self.agent_runner = AgentRunner(
                db=self.database,
                session_storage=self.session_manager,
                executors=executors,
                max_agent_depth=3,
            )
            logger.debug(f"AgentRunner initialized with executors: {list(executors.keys())}")
        except Exception as e:
            logger.error(f"Failed to initialize AgentRunner: {e}")

        # Session Lifecycle Manager (background jobs for expiring and processing)
        self.lifecycle_manager = SessionLifecycleManager(
            db=self.database,
            config=self.config.session_lifecycle,
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            memory_sync_manager=self.memory_sync_manager,
        )

        # Cron Scheduler (background jobs for recurring tasks)
        self.cron_storage: CronJobStorage | None = None
        self.cron_scheduler: CronScheduler | None = None
        try:
            from gobby.scheduler.executor import CronExecutor
            from gobby.scheduler.scheduler import CronScheduler
            from gobby.storage.cron import CronJobStorage

            self.cron_storage = CronJobStorage(self.database)
            cron_executor = CronExecutor(
                storage=self.cron_storage,
                agent_runner=self.agent_runner,
                pipeline_executor=self.pipeline_executor,
            )
            self.cron_scheduler = CronScheduler(
                storage=self.cron_storage,
                executor=cron_executor,
                config=self.config.cron,
            )
            logger.debug("CronScheduler initialized")
        except Exception as e:
            logger.error(f"Failed to initialize CronScheduler: {e}")

        # HTTP Server
        # Bundle services into container
        services = ServiceContainer(
            config=self.config,
            database=self.database,
            session_manager=self.session_manager,
            task_manager=self.task_manager,
            task_sync_manager=self.task_sync_manager,
            memory_sync_manager=self.memory_sync_manager,
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            mcp_manager=self.mcp_proxy,
            mcp_db_manager=self.mcp_db_manager,
            metrics_manager=self.metrics_manager,
            agent_runner=self.agent_runner,
            message_processor=self.message_processor,
            message_manager=self.message_manager,
            task_validator=self.task_validator,
            worktree_storage=self.worktree_storage,
            clone_storage=self.clone_storage,
            git_manager=self.git_manager,
            project_id=self.project_id,
            pipeline_executor=self.pipeline_executor,
            workflow_loader=self.workflow_loader,
            pipeline_execution_manager=self.pipeline_execution_manager,
            cron_storage=self.cron_storage,
            cron_scheduler=self.cron_scheduler,
            skill_manager=self.skill_manager,
            hub_manager=self.hub_manager,
            config_store=self.config_store,
            prompt_manager=self.prompt_manager,
            dev_mode=self._dev_mode,
        )

        self.http_server = HTTPServer(
            services=services,
            port=self.config.daemon_port,
            test_mode=self.config.test_mode,
        )

        # Inject server into container for circular ref if needed later
        # self.http_server.services = services

        # Ensure message_processor property is set (redundant but explicit):
        self.http_server.message_processor = self.message_processor

        # Wire tool_proxy_getter to PipelineExecutor for MCP step support.
        # Must happen after HTTPServer creation since tool_proxy lives on _tools_handler.
        if self.pipeline_executor:
            self.pipeline_executor.tool_proxy_getter = lambda: self.http_server.tool_proxy

        # WebSocket Server (Optional)
        self.websocket_server: WebSocketServer | None = None
        if self.config.websocket and getattr(self.config.websocket, "enabled", True):
            websocket_config = WebSocketConfig(
                host=self.config.bind_host,
                port=self.config.websocket.port,
                ping_interval=self.config.websocket.ping_interval,
                ping_timeout=self.config.websocket.ping_timeout,
            )
            self.websocket_server = WebSocketServer(
                config=websocket_config,
                mcp_manager=self.mcp_proxy,
                session_manager=self.session_manager,
                message_manager=self.message_manager,
                daemon_config=self.config,
            )
            # Pass WebSocket server reference to HTTP server for broadcasting
            self.http_server.websocket_server = self.websocket_server
            # Also update the HTTPServer's broadcaster to use the same websocket_server
            self.http_server.broadcaster.websocket_server = self.websocket_server

            # Pass WebSocket server to message processor if enabled
            if self.message_processor:
                self.message_processor.websocket_server = self.websocket_server

            # Register agent event callback for WebSocket broadcasting
            self._setup_agent_event_broadcasting()

            # Register pipeline event callback for WebSocket broadcasting
            self._setup_pipeline_event_broadcasting()

    def _init_database(self) -> DatabaseProtocol:
        """Initialize hub database."""
        hub_db_path = Path(self.config.database_path).expanduser()

        # Ensure hub db directory exists
        hub_db_path.parent.mkdir(parents=True, exist_ok=True)

        hub_db = LocalDatabase(hub_db_path)
        run_migrations(hub_db)

        logger.info(f"Database: {hub_db_path}")
        return hub_db

    def _setup_agent_event_broadcasting(self) -> None:
        """Set up WebSocket broadcasting for agent lifecycle events, PTY reading, and tmux streaming."""
        from gobby.agents.pty_reader import get_pty_reader_manager
        from gobby.agents.registry import get_running_agent_registry
        from gobby.agents.tmux import get_tmux_output_reader

        if not self.websocket_server:
            return

        registry = get_running_agent_registry()
        pty_manager = get_pty_reader_manager()
        tmux_reader = get_tmux_output_reader()

        # Set up output callbacks to broadcast via WebSocket
        async def broadcast_terminal_output(run_id: str, data: str) -> None:
            """Broadcast terminal output via WebSocket."""
            if self.websocket_server:
                await self.websocket_server.broadcast_terminal_output(run_id, data)

        pty_manager.set_output_callback(broadcast_terminal_output)
        tmux_reader.set_output_callback(broadcast_terminal_output)

        def broadcast_agent_event(event_type: str, run_id: str, data: dict[str, Any]) -> None:
            """Broadcast agent events via WebSocket (non-blocking)."""
            if not self.websocket_server:
                return

            def _log_broadcast_exception(task: asyncio.Task[None]) -> None:
                """Log exceptions from broadcast task to avoid silent failures."""
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"Failed to broadcast agent event {event_type}: {e}")

            # Handle PTY reader start/stop for embedded agents
            if event_type == "agent_started" and data.get("mode") == "embedded":
                # Start PTY reader for embedded agents
                agent = registry.get(run_id)
                if agent and agent.master_fd is not None:
                    _agent = agent  # bind for closure type narrowing

                    async def start_pty_reader() -> None:
                        await pty_manager.start_reader(_agent)

                    task = asyncio.create_task(start_pty_reader())
                    task.add_done_callback(_log_broadcast_exception)

            # Handle tmux output reader start for tmux terminal agents
            if event_type == "agent_started":
                agent = registry.get(run_id)
                if agent and agent.tmux_session_name:
                    session_name = agent.tmux_session_name

                    async def start_tmux_reader() -> None:
                        await tmux_reader.start_reader(run_id, session_name)

                    task = asyncio.create_task(start_tmux_reader())
                    task.add_done_callback(_log_broadcast_exception)

            elif event_type in (
                "agent_completed",
                "agent_failed",
                "agent_cancelled",
                "agent_timeout",
            ):
                # Stop PTY reader when agent finishes

                async def stop_pty_reader() -> None:
                    await pty_manager.stop_reader(run_id)

                task = asyncio.create_task(stop_pty_reader())
                task.add_done_callback(_log_broadcast_exception)

                # Stop tmux reader when agent finishes

                async def stop_tmux_reader() -> None:
                    await tmux_reader.stop_reader(run_id)

                task = asyncio.create_task(stop_tmux_reader())
                task.add_done_callback(_log_broadcast_exception)

            # Create async task to broadcast and attach exception callback
            task = asyncio.create_task(
                self.websocket_server.broadcast_agent_event(
                    event=event_type,
                    run_id=run_id,
                    parent_session_id=data.get("parent_session_id", ""),
                    session_id=data.get("session_id"),
                    mode=data.get("mode"),
                    provider=data.get("provider"),
                    pid=data.get("pid"),
                )
            )
            task.add_done_callback(_log_broadcast_exception)

        registry.add_event_callback(broadcast_agent_event)
        logger.debug("Agent event broadcasting and PTY reading enabled")

    def _setup_pipeline_event_broadcasting(self) -> None:
        """Set up WebSocket broadcasting for pipeline execution events."""
        if not self.websocket_server:
            return

        if not self.pipeline_executor:
            logger.debug("Pipeline event broadcasting skipped: no pipeline executor")
            return

        async def broadcast_pipeline_event(event: str, execution_id: str, **kwargs: Any) -> None:
            """Broadcast pipeline events via WebSocket."""
            if self.websocket_server:
                await self.websocket_server.broadcast_pipeline_event(
                    event=event,
                    execution_id=execution_id,
                    **kwargs,
                )

        # Set the callback on the pipeline executor
        self.pipeline_executor.event_callback = broadcast_pipeline_event
        logger.debug("Pipeline event broadcasting enabled")

    async def _metrics_cleanup_loop(self) -> None:
        """Background loop for periodic metrics cleanup (every 24 hours)."""
        interval_seconds = 24 * 60 * 60  # 24 hours

        while not self._shutdown_requested:
            try:
                await asyncio.sleep(interval_seconds)
                deleted = self.metrics_manager.cleanup_old_metrics()
                if deleted > 0:
                    logger.info(f"Periodic metrics cleanup: removed {deleted} old entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics cleanup loop: {e}")

    def _check_memory_v2_migration(self) -> None:
        """Check if Memory V2 migration is needed and log a suggestion.

        Checks if there are memories in the database but few/no cross-references,
        suggesting the user run `gobby memory migrate-v2`.
        """
        if not self.memory_manager:
            return

        try:
            # Get memory count
            memories = self.memory_manager.list_memories(limit=1)
            if not memories:
                # No memories, nothing to migrate
                return

            # Get total memory count for the threshold
            all_memories = self.memory_manager.list_memories(limit=10000)
            memory_count = len(all_memories)

            if memory_count < 5:
                # Too few memories to warrant migration check
                return

            # Get crossref count
            from gobby.storage.memories import LocalMemoryManager

            storage = LocalMemoryManager(self.database)
            crossrefs = storage.get_all_crossrefs(limit=1)

            if not crossrefs and memory_count >= 5:
                logger.warning(
                    f"Memory V2 migration recommended: {memory_count} memories found "
                    "but no cross-references. Run 'gobby memory migrate-v2' to enable "
                    "semantic search and automatic memory linking."
                )
        except Exception as e:
            # Don't fail startup on migration check errors
            logger.debug(f"Memory migration check failed (non-fatal): {e}")

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()

        def handle_shutdown() -> None:
            logger.info("Received shutdown signal, initiating graceful shutdown...")
            self._shutdown_requested = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_shutdown)

    async def run(self) -> None:
        try:
            self._setup_signal_handlers()

            # Connect MCP servers
            try:
                await asyncio.wait_for(self.mcp_proxy.connect_all(), timeout=10.0)
            except TimeoutError:
                logger.warning("MCP connection timed out")
            except Exception as e:
                logger.error(f"MCP connection failed: {e}")

            # Run metrics cleanup on startup
            try:
                deleted = self.metrics_manager.cleanup_old_metrics()
                if deleted > 0:
                    logger.info(f"Startup metrics cleanup: removed {deleted} old entries")
            except Exception as e:
                logger.warning(f"Metrics cleanup failed: {e}")

            # Check for pending Memory V2 migration
            self._check_memory_v2_migration()

            # Initialize VectorStore (async) and rebuild if needed
            if self.vector_store:
                try:
                    await self.vector_store.initialize()
                    qdrant_count = await self.vector_store.count()
                    if qdrant_count == 0 and self.memory_manager:
                        sqlite_memories = self.memory_manager.storage.list_memories(limit=10000)
                        if sqlite_memories:
                            logger.info(
                                f"Qdrant empty, rebuilding from {len(sqlite_memories)} SQLite memories..."
                            )
                            memory_dicts = [
                                {"id": m.id, "content": m.content} for m in sqlite_memories
                            ]
                            embed_fn = self.memory_manager.embed_fn
                            if embed_fn:
                                await self.vector_store.rebuild(memory_dicts, embed_fn)
                                logger.info("VectorStore rebuild complete")
                            else:
                                logger.warning(
                                    "No embed_fn configured, skipping VectorStore rebuild"
                                )
                except Exception as e:
                    logger.error(f"VectorStore initialization failed: {e}")

            # Start Message Processor
            if self.message_processor:
                await self.message_processor.start()

            # Start Session Lifecycle Manager
            await self.lifecycle_manager.start()

            # Start Cron Scheduler
            if self.cron_scheduler:
                await self.cron_scheduler.start()

            # Start periodic metrics cleanup (every 24 hours)
            self._metrics_cleanup_task = asyncio.create_task(
                self._metrics_cleanup_loop(),
                name="metrics-cleanup",
            )

            # Start WebSocket server
            websocket_task = None
            if self.websocket_server:
                websocket_task = asyncio.create_task(self.websocket_server.start())

            # Auto-start UI dev server if configured
            if self.config.ui.enabled and self.config.ui.mode == "dev":
                from gobby.cli.utils import find_web_dir, spawn_ui_server

                web_dir = find_web_dir(self.config)
                if web_dir:
                    ui_log = Path(self.config.logging.client).expanduser().parent / "ui.log"
                    # Inherit bind_host so the Vite dev server is reachable
                    # over the network (e.g. Tailscale) when bind_host != localhost
                    ui_host = self.config.ui.host
                    if self.config.bind_host != "localhost" and ui_host == "localhost":
                        ui_host = self.config.bind_host
                    ui_pid = spawn_ui_server(
                        ui_host,
                        self.config.ui.port,
                        web_dir,
                        ui_log,
                        daemon_port=self.config.daemon_port,
                        ws_port=self.config.websocket.port if self.config.websocket else 60888,
                    )
                    if ui_pid:
                        logger.info(
                            f"UI dev server started (PID: {ui_pid}) "
                            f"at http://{ui_host}:{self.config.ui.port}"
                        )
                    else:
                        logger.warning("Failed to start UI dev server")
                else:
                    logger.warning("UI dev mode enabled but web/ directory not found")

            # Start HTTP server
            graceful_shutdown_timeout = 15
            config = uvicorn.Config(
                self.http_server.app,
                host=self.config.bind_host,
                port=self.http_server.port,
                log_level="warning",
                access_log=False,
                timeout_graceful_shutdown=graceful_shutdown_timeout,
            )
            server = uvicorn.Server(config)
            server_task = asyncio.create_task(server.serve())

            # Wait for shutdown
            while not self._shutdown_requested:
                await asyncio.sleep(0.5)

            # Cleanup with timeouts to prevent hanging
            # Use timeout slightly longer than uvicorn's graceful shutdown to let it finish
            server.should_exit = True
            try:
                await asyncio.wait_for(server_task, timeout=graceful_shutdown_timeout + 5)
            except TimeoutError:
                logger.warning("HTTP server shutdown timed out")

            try:
                await asyncio.wait_for(self.lifecycle_manager.stop(), timeout=2.0)
            except TimeoutError:
                logger.warning("Lifecycle manager shutdown timed out")

            if self.cron_scheduler:
                try:
                    await asyncio.wait_for(self.cron_scheduler.stop(), timeout=2.0)
                except TimeoutError:
                    logger.warning("Cron scheduler shutdown timed out")

            if self.message_processor:
                try:
                    await asyncio.wait_for(self.message_processor.stop(), timeout=2.0)
                except TimeoutError:
                    logger.warning("Message processor shutdown timed out")

            if websocket_task:
                websocket_task.cancel()
                try:
                    await asyncio.wait_for(websocket_task, timeout=3.0)
                except (asyncio.CancelledError, TimeoutError):
                    logger.warning("WebSocket server shutdown timed out or cancelled")

            # Cancel metrics cleanup task
            if self._metrics_cleanup_task and not self._metrics_cleanup_task.done():
                self._metrics_cleanup_task.cancel()
                try:
                    await asyncio.wait_for(self._metrics_cleanup_task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass

            # Stop UI dev server if we started it
            if self.config.ui.enabled and self.config.ui.mode == "dev":
                from gobby.cli.utils import stop_ui_server

                stop_ui_server(quiet=True)

            # Close VectorStore connection
            if self.vector_store:
                try:
                    await asyncio.wait_for(self.vector_store.close(), timeout=5.0)
                except TimeoutError:
                    logger.warning("VectorStore close timed out")
                except Exception as e:
                    logger.warning(f"VectorStore close failed: {e}")

            # Export memories to JSONL backup on shutdown
            if self.memory_sync_manager:
                try:
                    count = await asyncio.wait_for(
                        self.memory_sync_manager.export_to_files(), timeout=5.0
                    )
                    if count > 0:
                        logger.info(f"Shutdown memory backup: exported {count} memories")
                except TimeoutError:
                    logger.warning("Memory backup on shutdown timed out")
                except Exception as e:
                    logger.warning(f"Memory backup on shutdown failed: {e}")

            try:
                await asyncio.wait_for(self.mcp_proxy.disconnect_all(), timeout=3.0)
            except TimeoutError:
                logger.warning("MCP disconnect timed out")

            logger.info("Shutdown complete")

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)


async def run_gobby(config_path: Path | None = None, verbose: bool = False) -> None:
    runner = GobbyRunner(config_path=config_path, verbose=verbose)
    await runner.run()


def main(config_path: Path | None = None, verbose: bool = False) -> None:
    try:
        asyncio.run(run_gobby(config_path=config_path, verbose=verbose))
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Gobby daemon")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--config", type=Path, help="Path to config file")

    args = parser.parse_args()
    main(config_path=args.config, verbose=args.verbose)
