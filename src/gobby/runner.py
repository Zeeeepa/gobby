from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import uvicorn

from gobby.agents.lifecycle_monitor import AgentLifecycleMonitor
from gobby.agents.runner import AgentRunner
from gobby.app_context import ServiceContainer, set_app_context
from gobby.config.app import load_config
from gobby.llm import LLMService, create_llm_service
from gobby.llm.resolver import ExecutorRegistry
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.memory.manager import MemoryManager
from gobby.memory.vectorstore import VectorStore
from gobby.search.embeddings import generate_embedding
from gobby.servers.http import HTTPServer
from gobby.servers.websocket.models import WebSocketConfig
from gobby.servers.websocket.server import WebSocketServer
from gobby.sessions.lifecycle import SessionLifecycleManager
from gobby.sessions.processor import SessionMessageProcessor
from gobby.storage.clones import LocalCloneManager
from gobby.storage.database import DatabaseProtocol, LocalDatabase
from gobby.storage.mcp import LocalMCPManager
from gobby.storage.migrations import run_migrations
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks import LocalTaskManager
from gobby.storage.worktrees import LocalWorktreeManager
from gobby.sync.memories import MemorySyncManager
from gobby.sync.tasks import TaskSyncManager
from gobby.tasks.validation import TaskValidator
from gobby.telemetry.logging import init_telemetry
from gobby.utils.machine_id import get_machine_id

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
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger(__name__)


class GobbyRunner:
    """Runner for Gobby daemon."""

    def __init__(self, config_path: Path | None = None, verbose: bool = False):
        if config_path is not None and not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}. "
                f"Use 'gobby install' to create bootstrap.yaml, "
                f"or omit --config to use the default path (~/.gobby/bootstrap.yaml)."
            )
        self._config_file = str(config_path) if config_path else None
        self.config = load_config(self._config_file)
        self.verbose = verbose

        # Initialize telemetry (logging, tracing, metrics)
        init_telemetry(self.config.telemetry, verbose=verbose)

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
        self._vector_rebuild_task: asyncio.Task[None] | None = None
        self._zombie_messages_task: asyncio.Task[None] | None = None
        self._span_cleanup_task: asyncio.Task[None] | None = None
        self._metrics_archive_task: asyncio.Task[None] | None = None
        self._metric_snapshot_task: asyncio.Task[None] | None = None

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

        # Auto-populate search.embedding_api_key from secrets if not already set
        if hasattr(self.config, "search") and not self.config.search.embedding_api_key:
            resolved_key = self._resolve_embedding_api_key(self.config.search.embedding_model)
            if resolved_key:
                self.config.search.embedding_api_key = resolved_key

        # Populate model costs from LiteLLM into DB and load into memory
        from gobby.llm.cost_table import init as init_cost_table
        from gobby.storage.model_costs import ModelCostStore

        try:
            cost_store = ModelCostStore(self.database)
            cost_store.populate_from_litellm()
            init_cost_table(self.database)
        except Exception as e:
            logger.warning(f"Failed to populate model costs: {e}")

        self.session_manager = LocalSessionManager(self.database)
        self.task_manager = LocalTaskManager(self.database)
        self.session_task_manager = SessionTaskManager(self.database)

        # Initialize Span Storage and wire OTel exporter
        from gobby.storage.spans import SpanStorage

        self.span_storage = SpanStorage(self.database)

        if self.config.telemetry and self.config.telemetry.traces_enabled:
            from gobby.telemetry.providers import add_span_storage_exporter

            def _broadcast_proxy(span: dict[str, Any]) -> None:
                """Proxy for trace event broadcasting via WebSocket."""
                if hasattr(self, "websocket_server") and self.websocket_server:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self.websocket_server.broadcast_trace_event(span))
                    except RuntimeError:
                        # No running loop (likely shutdown or too early)
                        pass

            add_span_storage_exporter(self.span_storage, broadcast_callback=_broadcast_proxy)
            logger.debug("Local span storage exporter wired to OTel")

        from gobby.utils.dev import is_dev_mode

        self._dev_mode = is_dev_mode(Path.cwd())

        # In dev mode, auto-sync bundled content so YAML edits are picked up
        # on every daemon restart without needing a full `gobby install`.
        if self._dev_mode:
            from gobby.cli.installers.shared import sync_bundled_content_to_db

            sync_result = sync_bundled_content_to_db(self.database)
            total = sync_result["total_synced"]
            if total > 0:
                logger.info(f"Dev mode: synced {total} bundled items on startup")

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
                SkillsMPProvider,
            )

            skills_config = self.config.skills if hasattr(self.config, "skills") else SkillsConfig()

            # Resolve hub API keys from env vars
            api_keys: dict[str, str] = {}
            for _hub_name, hub_config in skills_config.hubs.items():
                if hub_config.auth_key_name:
                    value = os.environ.get(hub_config.auth_key_name)
                    if value:
                        api_keys[hub_config.auth_key_name] = value

            self.hub_manager = HubManager(configs=skills_config.hubs, api_keys=api_keys)
            self.hub_manager.register_provider_factory("clawdhub", ClawdHubProvider)
            self.hub_manager.register_provider_factory("skillsmp", SkillsMPProvider)
            self.hub_manager.register_provider_factory(
                "github-collection", GitHubCollectionProvider
            )
            self.hub_manager.register_provider_factory("claude-plugins", ClaudePluginsProvider)
            self.hub_manager._skill_description_config = (
                self.config.skill_description if hasattr(self.config, "skill_description") else None
            )
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
                gobby_home = Path(os.environ.get("GOBBY_HOME", str(Path.home() / ".gobby")))
                qdrant_path = self.config.memory.qdrant_path or str(
                    gobby_home / "services" / "qdrant"
                )
                self.vector_store = VectorStore(
                    path=qdrant_path if not self.config.memory.qdrant_url else None,
                    url=self.config.memory.qdrant_url,
                    api_key=self.config.memory.qdrant_api_key,
                    embedding_dim=self.config.memory.embedding_dim,
                )
                embed_fn: Callable[..., Any] | None = None
                if self.llm_service:
                    from functools import partial

                    _mem_api_key = (
                        self.config.memory.embedding_api_key
                        or self._resolve_embedding_api_key(self.config.memory.embedding_model)
                    )
                    _mem_embed_kwargs: dict[str, Any] = {
                        "model": self.config.memory.embedding_model,
                        "api_key": _mem_api_key,
                    }
                    if self.config.memory.embedding_api_base:
                        _mem_embed_kwargs["api_base"] = self.config.memory.embedding_api_base
                    embed_fn = partial(
                        generate_embedding,
                        **_mem_embed_kwargs,
                    )

                self.memory_manager = MemoryManager(
                    self.database,
                    self.config.memory,
                    llm_service=self.llm_service,
                    vector_store=self.vector_store,
                    embed_fn=embed_fn,
                )
            except Exception as e:
                logger.error(f"Failed to initialize MemoryManager: {e}")

        # Code Index (native AST-based symbol indexing)
        self.code_indexer: Any | None = None
        if hasattr(self.config, "code_index") and self.config.code_index.enabled:
            try:
                from gobby.code_index.graph import CodeGraph
                from gobby.code_index.indexer import CodeIndexer
                from gobby.code_index.parser import CodeParser
                from gobby.code_index.searcher import CodeSearcher
                from gobby.code_index.storage import CodeIndexStorage
                from gobby.code_index.summarizer import SymbolSummarizer

                ci_config = self.config.code_index
                ci_storage = CodeIndexStorage(self.database)
                ci_parser = CodeParser(ci_config)
                # Share Neo4j client from memory_manager if available
                ci_neo4j = None
                if self.memory_manager and getattr(self.memory_manager, "_neo4j_client", None):
                    ci_neo4j = self.memory_manager._neo4j_client
                ci_graph = CodeGraph(neo4j_client=ci_neo4j)
                ci_summarizer = (
                    SymbolSummarizer(self.llm_service, ci_config)
                    if self.llm_service and ci_config.summary_enabled
                    else None
                )

                # Reuse memory embed_fn if available
                ci_embed_fn: Callable[..., Any] | None = None
                if self.llm_service and ci_config.embedding_enabled:
                    from functools import partial

                    _ci_model = (
                        self.config.memory.embedding_model
                        if hasattr(self.config, "memory")
                        else "local/nomic-embed-text-v1.5"
                    )
                    _ci_api_key = (
                        self.config.memory.embedding_api_key
                        if hasattr(self.config, "memory") and self.config.memory.embedding_api_key
                        else self._resolve_embedding_api_key(_ci_model)
                    )
                    _ci_embed_kwargs: dict[str, Any] = {
                        "model": _ci_model,
                        "api_key": _ci_api_key,
                    }
                    if hasattr(self.config, "memory") and self.config.memory.embedding_api_base:
                        _ci_embed_kwargs["api_base"] = self.config.memory.embedding_api_base
                    ci_embed_fn = partial(
                        generate_embedding,
                        **_ci_embed_kwargs,
                    )

                ci_vector_store = self.vector_store if ci_config.embedding_enabled else None

                self.code_indexer = CodeIndexer(
                    storage=ci_storage,
                    parser=ci_parser,
                    vector_store=ci_vector_store,
                    embed_fn=ci_embed_fn,
                    graph=ci_graph if ci_config.graph_enabled else None,
                    summarizer=ci_summarizer,
                    config=ci_config,
                )

                # Create searcher and attach to indexer for http.py wiring
                ci_searcher = CodeSearcher(
                    storage=ci_storage,
                    vector_store=ci_vector_store,
                    embed_fn=ci_embed_fn,
                    graph=ci_graph if ci_config.graph_enabled else None,
                    config=ci_config,
                )
                self.code_indexer.searcher = ci_searcher

                logger.info("Code indexer initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize code indexer: {e}")

        # MCP Proxy Manager - Initialize early for tool access
        # LocalMCPManager handles server/tool storage in SQLite
        self.mcp_db_manager = LocalMCPManager(self.database)

        # Tool Metrics Manager for tracking call statistics
        from gobby.mcp_proxy.metrics import ToolMetricsManager
        from gobby.mcp_proxy.metrics_events import MetricsEventStore

        self.metrics_event_store = MetricsEventStore(self.database)
        self.metrics_manager = ToolMetricsManager(
            self.database, event_store=self.metrics_event_store
        )

        # MCPClientManager loads servers from database on init
        self.mcp_proxy = MCPClientManager(
            mcp_db_manager=self.mcp_db_manager,
            metrics_manager=self.metrics_manager,
        )

        # Task Sync Manager
        self.task_sync_manager = TaskSyncManager(self.task_manager)

        # Import synced tasks before wiring export listener
        # (e.g. from git on a new machine with more tasks than local DB)
        try:
            self.task_sync_manager.import_from_jsonl()
            logger.info("Initial task sync import completed")
        except Exception as e:
            logger.warning(f"Task sync import failed: {e}")

        # NOTE: Startup export removed to avoid git noise (#10198).
        # The pre-commit hook exports and stages JSONL files at commit time.
        # Import above pulls in changes from git; export deferred to commit.

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
                    # No per-change listener — the file is a backup, not a live mirror.
                    # Export happens at: pre-commit hook, CLI `memory backup`, or explicit sync_export.
                    logger.debug("MemorySyncManager initialized (export on commit/CLI only)")

                    # Import synced memories before exporting
                    # (e.g. from git on a new machine with more memories than local DB)
                    try:
                        imported = self.memory_sync_manager.import_sync()
                        if imported > 0:
                            logger.info(f"Imported {imported} memories from sync file")
                    except (OSError, ValueError) as e:
                        logger.warning(f"Memory import failed: {e}")

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

        # Detect project context from cwd so daemon-level services (pipelines,
        # clones) can register their MCP tools.  Per-session resolution can
        # still override via ServiceContainer.
        self.git_manager: WorktreeGitManager | None = None
        self.project_id: str | None = None
        try:
            from gobby.utils.project_context import get_project_context
            from gobby.worktrees.git import WorktreeGitManager as _WGM

            project_ctx = get_project_context(Path.cwd())
            if project_ctx and project_ctx.get("id"):
                self.project_id = str(project_ctx["id"])
                project_path = project_ctx.get("project_path")
                if project_path:
                    self.git_manager = _WGM(str(project_path))
                    logger.debug(
                        f"Daemon project context: id={self.project_id}, path={project_path}"
                    )
        except Exception as e:
            logger.debug(f"Could not detect project context from cwd: {e}")

        # WorkflowLoader is project-agnostic; pipeline executor needs project context.
        self.workflow_loader: WorkflowLoader | None = None
        self.pipeline_execution_manager: LocalPipelineExecutionManager | None = None
        self.pipeline_executor: PipelineExecutor | None = None
        try:
            from gobby.workflows.loader import WorkflowLoader

            self.workflow_loader = WorkflowLoader(db=self.database)
        except Exception as e:
            logger.warning(f"Failed to initialize workflow loader: {e}")

        # Initialize completion event registry with wake dispatcher
        from gobby.events.completion_registry import CompletionEventRegistry
        from gobby.events.wake import WakeDispatcher
        from gobby.storage.agents import LocalAgentRunManager
        from gobby.storage.inter_session_messages import InterSessionMessageManager

        ism_manager = InterSessionMessageManager(cast(LocalDatabase, self.database))
        agent_run_manager = LocalAgentRunManager(self.database)

        # tmux sender: wraps the global TmuxSessionManager singleton
        async def _tmux_send(tmux_session_name: str, message: str) -> None:
            from gobby.agents.tmux import get_tmux_session_manager

            mgr = get_tmux_session_manager()
            await mgr.send_keys(tmux_session_name, message + "\n")

        # tmux pane sender: sends keys to the invoking CLI's tmux pane
        # Uses the default tmux socket (not -L gobby) since these are user panes
        async def _tmux_pane_send(pane_id: str, message: str) -> None:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "send-keys",
                "-t",
                pane_id,
                message,
                "Enter",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"tmux send-keys to {pane_id} failed: {stderr.decode()}")

        self.wake_dispatcher = WakeDispatcher(
            session_manager=self.session_manager,
            ism_manager=ism_manager,
            tmux_sender=_tmux_send,
            tmux_pane_sender=_tmux_pane_send,
            agent_run_manager=agent_run_manager,
        )

        self.completion_registry = CompletionEventRegistry(
            wake_callback=self.wake_dispatcher.wake,
        )

        # Create pipeline executor at startup if we have project context
        if self.workflow_loader is not None and self.project_id:
            try:
                from gobby.storage.pipelines import LocalPipelineExecutionManager as _LPEM
                from gobby.workflows.pipeline_executor import PipelineExecutor as _PE
                from gobby.workflows.templates import TemplateEngine

                self.pipeline_execution_manager = _LPEM(
                    db=self.database, project_id=self.project_id
                )
                self.pipeline_executor = _PE(
                    db=self.database,
                    execution_manager=self.pipeline_execution_manager,
                    llm_service=self.llm_service,
                    loader=self.workflow_loader,
                    template_engine=TemplateEngine(),
                    session_manager=self.session_manager,
                    completion_registry=self.completion_registry,
                )
                logger.info("Pipeline executor initialized at startup")
            except Exception as e:
                logger.warning(f"Failed to initialize pipeline executor at startup: {e}")

        # Initialize Agent Runner (Phase 7 - Subagents)
        # Create executor registry for lazy executor creation
        self.executor_registry = ExecutorRegistry(
            config=self.config,
            secret_resolver=self.secret_store.get,
        )
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
                max_agent_depth=5,
                completion_registry=self.completion_registry,
            )
            logger.debug(f"AgentRunner initialized with executors: {list(executors.keys())}")
        except Exception as e:
            logger.error(f"Failed to initialize AgentRunner: {e}")

        # Agent Lifecycle Monitor (detect dead tmux sessions)
        from gobby.agents.registry import get_running_agent_registry
        from gobby.storage.agents import LocalAgentRunManager

        try:
            self.agent_lifecycle_monitor: AgentLifecycleMonitor | None = AgentLifecycleMonitor(
                agent_registry=get_running_agent_registry(),
                agent_run_manager=LocalAgentRunManager(self.database),
                clone_storage=self.clone_storage,
                completion_registry=self.completion_registry,
                task_manager=self.task_manager,
                tmux_config=self.config.tmux if hasattr(self.config, "tmux") else None,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize AgentLifecycleMonitor: {e}")
            self.agent_lifecycle_monitor = None

        # Session Lifecycle Manager (background jobs for expiring and processing)
        self.lifecycle_manager = SessionLifecycleManager(
            db=self.database,
            config=self.config.session_lifecycle,
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            memory_sync_manager=self.memory_sync_manager,
        )
        self.lifecycle_manager._memory_extraction_config = (
            self.config.memory_extraction if hasattr(self.config, "memory_extraction") else None
        )

        # Conductor manager (persistent tick-based orchestration agent)
        self.conductor_manager: object | None = None

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

            # Register pipeline heartbeat handler
            try:
                from gobby.agents.registry import get_running_agent_registry
                from gobby.storage.agents import LocalAgentRunManager
                from gobby.workflows.pipeline_heartbeat import PipelineHeartbeat

                if self.pipeline_execution_manager is None:
                    raise RuntimeError("pipeline_execution_manager required for heartbeat")

                heartbeat = PipelineHeartbeat(
                    execution_manager=self.pipeline_execution_manager,
                    agent_registry=get_running_agent_registry(),
                    task_manager=self.task_manager,
                    agent_run_manager=LocalAgentRunManager(self.database),
                    session_manager=self.session_manager,
                )
                cron_executor.register_handler("pipeline_heartbeat", heartbeat)

                # Auto-create system cron job if missing
                existing = self.cron_storage.get_job_by_name("gobby:pipeline-heartbeat")
                if not existing and self.project_id:
                    self.cron_storage.create_job(
                        project_id=self.project_id,
                        name="gobby:pipeline-heartbeat",
                        description="Safety net: detects stalled pipelines and marks dead executions as failed",
                        schedule_type="interval",
                        interval_seconds=60,
                        action_type="handler",
                        action_config={"handler": "pipeline_heartbeat"},
                        enabled=True,
                    )
                    logger.info("Created system cron job: gobby:pipeline-heartbeat")
                logger.debug("PipelineHeartbeat handler registered")
            except Exception as e:
                logger.error(f"Failed to register pipeline heartbeat: {e}")

            # Register conductor handler (if enabled)
            if self.config.conductor.enabled and self.project_id:
                try:
                    from gobby.conductor.manager import ConductorManager

                    self.conductor_manager = ConductorManager(
                        project_id=self.project_id,
                        project_path=str(Path.cwd()),
                        session_manager=self.session_manager,
                        config=self.config.conductor,
                        execution_manager=self.pipeline_execution_manager,
                    )
                    cron_executor.register_handler("conductor_tick", self.conductor_manager)
                    existing = self.cron_storage.get_job_by_name("gobby:conductor-tick")
                    if not existing:
                        self.cron_storage.create_job(
                            project_id=self.project_id,
                            name="gobby:conductor-tick",
                            description="Persistent conductor: checks tasks, dispatches agents",
                            schedule_type="interval",
                            interval_seconds=self.config.conductor.tick_interval_seconds,
                            action_type="handler",
                            action_config={"handler": "conductor_tick"},
                            enabled=True,
                        )
                        logger.info("Created system cron job: gobby:conductor-tick")
                    logger.info("Conductor enabled (model=%s)", self.config.conductor.model)
                except Exception as e:
                    logger.error("Failed to initialize conductor: %s", e)

            # Register Linear sync handler (for projects with Linear integration)
            try:
                from gobby.storage.projects import LocalProjectManager
                from gobby.sync.linear import create_linear_sync_handler

                pm = LocalProjectManager(self.database)
                for project in pm.list():
                    if project.linear_team_id:
                        handler = create_linear_sync_handler(
                            mcp_manager=self.mcp_proxy,
                            task_manager=self.task_manager,
                            project_id=project.id,
                            team_id=project.linear_team_id,
                        )
                        handler_name = f"linear_sync:{project.id}"
                        cron_executor.register_handler(handler_name, handler)

                        job_name = f"gobby:linear-sync:{project.id}"
                        existing = self.cron_storage.get_job_by_name(job_name)
                        if not existing:
                            self.cron_storage.create_job(
                                project_id=project.id,
                                name=job_name,
                                description=f"Bidirectional Linear sync for project {project.name}",
                                schedule_type="interval",
                                interval_seconds=300,
                                action_type="handler",
                                action_config={"handler": handler_name},
                                enabled=True,
                            )
                            logger.info(f"Created system cron job: {job_name}")
                logger.debug("Linear sync handlers registered")
            except Exception as e:
                logger.error(f"Failed to register Linear sync handlers: {e}")

            self.cron_scheduler = CronScheduler(
                storage=self.cron_storage,
                executor=cron_executor,
                config=self.config.cron,
            )
            logger.debug("CronScheduler initialized")
        except Exception as e:
            logger.error(f"Failed to initialize CronScheduler: {e}")

        # Communications Manager
        self.communications_manager: Any | None = None
        if hasattr(self.config, "communications") and self.config.communications.enabled:
            try:
                from gobby.communications.manager import CommunicationsManager
                from gobby.storage.communications import LocalCommunicationsStore

                comms_store = LocalCommunicationsStore(self.database)
                self.communications_manager = CommunicationsManager(
                    config=self.config.communications,
                    store=comms_store,
                    secret_store=self.secret_store,
                )
                logger.debug("CommunicationsManager initialized")
            except Exception as e:
                logger.error(f"Failed to initialize CommunicationsManager: {e}")

        # HTTP Server
        # Bundle services into container
        services = ServiceContainer(
            config=self.config,
            database=self.database,
            session_manager=self.session_manager,
            task_manager=self.task_manager,
            span_storage=self.span_storage,
            task_sync_manager=self.task_sync_manager,
            memory_sync_manager=self.memory_sync_manager,
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            vector_store=self.vector_store,
            mcp_manager=self.mcp_proxy,
            mcp_db_manager=self.mcp_db_manager,
            metrics_manager=self.metrics_manager,
            agent_runner=self.agent_runner,
            message_processor=self.message_processor,
            task_validator=self.task_validator,
            worktree_storage=self.worktree_storage,
            clone_storage=self.clone_storage,
            git_manager=self.git_manager,
            project_id=self.project_id,
            pipeline_executor=self.pipeline_executor,
            workflow_loader=self.workflow_loader,
            pipeline_execution_manager=self.pipeline_execution_manager,
            completion_registry=self.completion_registry,
            agent_lifecycle_monitor=self.agent_lifecycle_monitor,
            communications_manager=self.communications_manager,
            code_indexer=self.code_indexer,
            cron_storage=self.cron_storage,
            cron_scheduler=self.cron_scheduler,
            skill_manager=self.skill_manager,
            hub_manager=self.hub_manager,
            config_store=self.config_store,
            prompt_manager=self.prompt_manager,
            dev_mode=self._dev_mode,
            tool_proxy_getter=lambda: self.http_server.tool_proxy,
        )

        set_app_context(services)

        # Optionally create CodexAppServerClient for rich event lifecycle
        codex_client = None
        if self.config.codex_app_server:
            from gobby.adapters.codex_impl.adapter import CodexAdapter

            if CodexAdapter.is_codex_available():
                from gobby.adapters.codex_impl.client import CodexAppServerClient

                codex_client = CodexAppServerClient()
                logger.info("Codex app-server client created (will start in HTTP lifespan)")
            else:
                logger.warning("codex_app_server enabled but codex CLI not found in PATH")

        self.http_server: HTTPServer = HTTPServer(
            services=services,
            port=self.config.daemon_port,
            test_mode=self.config.test_mode,
            codex_client=codex_client,
        )

        # Inject server into container for circular ref if needed later
        # self.http_server.services = services

        # Ensure message_processor property is set (redundant but explicit):
        self.http_server.message_processor = self.message_processor

        # Wire tool_proxy_getter onto the startup-created pipeline executor.
        # The executor was created before http_server existed, so we do it now.
        if self.pipeline_executor is not None:
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
                daemon_config=self.config,
                internal_manager=self.http_server._internal_manager,
            )
            # Pass WebSocket server reference to HTTP server for broadcasting
            self.http_server.websocket_server = self.websocket_server
            # Also set on services container so lifespan can wire workflow_handler
            self.http_server.services.websocket_server = self.websocket_server
            # Also update the HTTPServer's broadcaster to use the same websocket_server
            self.http_server.broadcaster.websocket_server = self.websocket_server

            # Pass WebSocket server and session manager to message processor
            if self.message_processor:
                self.message_processor.websocket_server = self.websocket_server
                self.message_processor.session_manager = self.session_manager

            # Register agent event callback for WebSocket broadcasting
            from gobby.runner_broadcasting import (
                setup_agent_event_broadcasting,
                setup_cron_event_broadcasting,
                setup_pipeline_event_broadcasting,
            )

            setup_agent_event_broadcasting(self.websocket_server)

            # Register pipeline event callback for WebSocket broadcasting
            if self.pipeline_executor:
                setup_pipeline_event_broadcasting(self.websocket_server, self.pipeline_executor)

            # Register cron event callback for WebSocket broadcasting
            if self.cron_scheduler:
                setup_cron_event_broadcasting(self.websocket_server, self.cron_scheduler)

    def _resolve_embedding_api_key(self, model: str) -> str | None:
        """Resolve the API key for an embedding model from the secret store.

        Maps model prefixes to well-known secret names so users don't need
        to manually wire $secret: references for standard embedding providers.
        """
        # Model-prefix to secret-name mapping
        prefix_to_secret: dict[str, str] = {
            "openai/": "openai_api_key",
            "gemini/": "gemini_api_key",
            "mistral/": "mistral_api_key",
            "azure/": "azure_api_key",
            "cohere/": "cohere_api_key",
        }

        for prefix, secret_name in prefix_to_secret.items():
            if model.startswith(prefix):
                return self.secret_store.get(secret_name)

        # Local in-process models don't need an API key
        if model.startswith("local/"):
            return None

        # Ollama models don't need an API key
        if model.startswith("ollama/"):
            return None

        # Default (no prefix, e.g. "text-embedding-3-small") → OpenAI
        return self.secret_store.get("openai_api_key")

    def _init_database(self) -> DatabaseProtocol:
        """Initialize hub database."""
        hub_db_path = Path(self.config.database_path).expanduser()

        # Ensure hub db directory exists
        hub_db_path.parent.mkdir(parents=True, exist_ok=True)

        hub_db = LocalDatabase(hub_db_path)
        run_migrations(hub_db)

        logger.info(f"Database: {hub_db_path}")
        return hub_db

    async def run(self) -> None:
        from gobby.runner_maintenance import (
            cleanup_pid_file,
            cleanup_zombie_messages_loop,
            expire_approval_timeouts_loop,
            metric_snapshot_loop,
            metrics_archive_loop,
            metrics_cleanup_loop,
            rebuild_vector_store,
            savings_rollup_loop,
            setup_signal_handlers,
            span_cleanup_loop,
        )

        try:
            setup_signal_handlers(lambda: setattr(self, "_shutdown_requested", True))

            # Write PID file (ensures it exists regardless of how the runner
            # was started — CLI `gobby start`, launchctl, or direct invocation)
            from gobby.cli.utils import get_gobby_home

            pid_file = get_gobby_home() / "gobby.pid"
            try:
                pid_file.write_text(str(os.getpid()))
                logger.info(f"Wrote PID file: {pid_file} (PID {os.getpid()})")
            except OSError as e:
                logger.warning(f"Could not write PID file {pid_file}: {e}")

            # Connect MCP servers
            try:
                await asyncio.wait_for(self.mcp_proxy.connect_all(), timeout=10.0)
            except TimeoutError:
                logger.warning("MCP connection timed out")
            except Exception as e:
                logger.error(f"MCP connection failed: {e}")

            # Neo4j health check: disable KG features if unreachable
            if (
                self.memory_manager
                and hasattr(self.config, "memory")
                and self.config.memory.neo4j_url
            ):
                from gobby.cli.services import is_neo4j_healthy

                neo4j_url = self.config.memory.neo4j_url
                if not await is_neo4j_healthy(neo4j_url):
                    logger.warning(
                        f"Neo4j configured but unreachable at {neo4j_url} — graph features disabled"
                    )
                    self.memory_manager._neo4j_client = None
                    self.memory_manager._kg_service = None

            # Run metrics cleanup on startup
            try:
                deleted = self.metrics_manager.cleanup_old_metrics()
                if deleted > 0:
                    logger.info(f"Startup metrics cleanup: removed {deleted} old entries")
            except Exception as e:
                logger.warning(f"Metrics cleanup failed: {e}")

            # Initialize VectorStore and schedule rebuild in background if needed
            if self.vector_store:
                try:
                    await self.vector_store.initialize()
                    # Ensure tool_embeddings collection exists (shared Qdrant instance)
                    from gobby.mcp_proxy.semantic_search import SemanticToolSearch

                    await self.vector_store.ensure_collection(
                        SemanticToolSearch.TOOL_COLLECTION,
                        self.config.memory.embedding_dim,
                    )
                    qdrant_count = await self.vector_store.count()
                    if qdrant_count == 0 and self.memory_manager:
                        sqlite_memories = self.memory_manager.storage.list_memories(limit=10000)
                        if sqlite_memories:
                            embed_fn = self.memory_manager.embed_fn
                            if embed_fn:
                                logger.info(
                                    f"Qdrant empty, scheduling background rebuild from "
                                    f"{len(sqlite_memories)} SQLite memories..."
                                )
                                memory_dicts = [
                                    {"id": m.id, "content": m.content} for m in sqlite_memories
                                ]
                                self._vector_rebuild_task = asyncio.create_task(
                                    rebuild_vector_store(self.vector_store, memory_dicts, embed_fn),
                                    name="vector-store-rebuild",
                                )
                            else:
                                logger.warning(
                                    "No embed_fn configured, skipping VectorStore rebuild"
                                )
                except Exception as e:
                    logger.error(f"VectorStore initialization failed: {e}")

            # Start Message Processor
            if self.message_processor:
                await self.message_processor.start()

            # Start Communications Manager
            if self.communications_manager:
                try:
                    await self.communications_manager.start()
                except Exception as e:
                    logger.error(f"CommunicationsManager start failed: {e}")

            # Start Session Lifecycle Manager
            await self.lifecycle_manager.start()

            # tmux socket health check before any agent operations
            try:
                from gobby.agents.tmux.session_manager import TmuxSessionManager

                tmux_mgr = TmuxSessionManager()
                await tmux_mgr.health_check()
            except Exception as e:
                logger.warning(f"tmux health check failed on startup: {e}")

            # Recover or clean up agents from previous daemon session
            if self.agent_lifecycle_monitor:
                recovered, cleaned = await self.agent_lifecycle_monitor.recover_or_cleanup_agents()
                if recovered:
                    logger.info(
                        f"Recovered {recovered} running agent(s) from previous daemon session"
                    )
                if cleaned:
                    logger.info(
                        f"Cleaned up {cleaned} orphaned agent(s) from previous daemon session"
                    )
                await self.agent_lifecycle_monitor.start()

            # Start Cron Scheduler
            if self.cron_scheduler:
                await self.cron_scheduler.start()

            # Start periodic metrics cleanup (every 24 hours)
            self._metrics_cleanup_task = asyncio.create_task(
                metrics_cleanup_loop(self.metrics_manager, lambda: self._shutdown_requested),
                name="metrics-cleanup",
            )

            # Start periodic metrics event archiving (every 24 hours, 30-day retention)
            self._metrics_archive_task = asyncio.create_task(
                metrics_archive_loop(self.metrics_event_store, lambda: self._shutdown_requested),
                name="metrics-archive",
            )

            # Start periodic span cleanup (every 24 hours, 7-day retention)
            retention_days = 7
            if self.config.telemetry and hasattr(self.config.telemetry, "trace_retention_days"):
                retention_days = self.config.telemetry.trace_retention_days

            self._span_cleanup_task = asyncio.create_task(
                span_cleanup_loop(
                    self.database,
                    lambda: self._shutdown_requested,
                    retention_days=retention_days,
                ),
                name="span-cleanup",
            )

            # Start periodic zombie message cleanup (every 6 hours)
            self._zombie_messages_task = asyncio.create_task(
                cleanup_zombie_messages_loop(self.database, lambda: self._shutdown_requested),
                name="zombie-message-cleanup",
            )

            # Start code index maintenance loop
            self._code_index_task: asyncio.Task[None] | None = None
            if self.code_indexer:
                from gobby.code_index.maintenance import code_index_maintenance_loop

                shutdown_event = asyncio.Event()
                # Wire shutdown event to _shutdown_requested flag
                self._code_index_shutdown = shutdown_event
                self._code_index_task = asyncio.create_task(
                    code_index_maintenance_loop(
                        self.code_indexer,
                        shutdown_flag=shutdown_event,
                        interval=self.config.code_index.maintenance_interval_seconds,
                    ),
                    name="code-index-maintenance",
                )

            # Start periodic savings rollup (every 24 hours)
            self._savings_rollup_task = asyncio.create_task(
                savings_rollup_loop(self.database, lambda: self._shutdown_requested),
                name="savings-rollup",
            )

            # Start periodic metric snapshot loop (every 60s)
            self._metric_snapshot_task = asyncio.create_task(
                metric_snapshot_loop(self.database, lambda: self._shutdown_requested),
                name="metric-snapshot",
            )

            # Start periodic approval timeout expiry (every 60s)
            self._approval_timeout_task: asyncio.Task[None] | None = None
            if self.pipeline_execution_manager:
                self._approval_timeout_task = asyncio.create_task(
                    expire_approval_timeouts_loop(
                        self.pipeline_execution_manager,
                        lambda: self._shutdown_requested,
                    ),
                    name="approval-timeout-expiry",
                )

            # Resume interrupted pipelines and fail non-resumable stale executions
            if self.pipeline_executor and self.pipeline_execution_manager and self.workflow_loader:
                try:
                    from gobby.mcp_proxy.tools.workflows._pipeline_execution import (
                        resume_interrupted_pipelines,
                    )

                    resumed_ids = await resume_interrupted_pipelines(
                        loader=self.workflow_loader,
                        executor=self.pipeline_executor,
                        execution_manager=self.pipeline_execution_manager,
                        project_id=self.project_id,
                    )
                    if resumed_ids:
                        logger.info(
                            f"Resumed {len(resumed_ids)} pipeline(s) after restart: {resumed_ids}"
                        )

                    stale_count = self.pipeline_execution_manager.fail_stale_running_executions(
                        exclude_ids=set(resumed_ids),
                    )
                    if stale_count > 0:
                        logger.info(f"Failed {stale_count} non-resumable stale pipeline executions")

                    # Wake subscribers of interrupted (non-resumed) pipelines
                    if stale_count > 0 and self.completion_registry:
                        try:
                            from gobby.workflows.pipeline_state import ExecutionStatus as _ES

                            interrupted = self.pipeline_execution_manager.list_executions(
                                status=_ES.INTERRUPTED,
                            )
                            for exe in interrupted:
                                subs = self.pipeline_execution_manager.get_completion_subscribers(
                                    exe.id
                                )
                                if subs:
                                    self.completion_registry.register(exe.id, subscribers=subs)
                                    await self.completion_registry.notify(
                                        exe.id,
                                        result={
                                            "status": "interrupted",
                                            "pipeline_name": exe.pipeline_name,
                                            "error": "Daemon restarted while execution was in progress",
                                        },
                                        message=(
                                            f'[Completion Notification] Pipeline "{exe.pipeline_name}" '
                                            f"({exe.id}) was interrupted.\n"
                                            f"Status: interrupted (daemon restarted)\n"
                                            f"You may retry with run_pipeline."
                                        ),
                                    )
                                    self.pipeline_execution_manager.remove_completion_subscribers(
                                        exe.id
                                    )
                                    self.completion_registry.cleanup(exe.id)
                            logger.info(
                                "Notified subscribers of %d interrupted pipeline(s)",
                                len(interrupted),
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to wake subscribers of interrupted pipelines: %s", e
                            )
                except Exception as e:
                    logger.warning(f"Pipeline recovery after restart failed: {e}")

            # Start WebSocket server
            websocket_task = None
            if self.websocket_server:
                websocket_task = asyncio.create_task(self.websocket_server.start())

            # Auto-start UI dev server if configured
            if self.config.ui.enabled and self.config.ui.mode == "dev":
                from gobby.cli.utils import find_web_dir, spawn_ui_server

                web_dir = find_web_dir(self.config)
                if web_dir:
                    ui_log = Path(self.config.telemetry.log_file).expanduser().parent / "ui.log"
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

            if self.agent_lifecycle_monitor:
                try:
                    await asyncio.wait_for(self.agent_lifecycle_monitor.stop(), timeout=2.0)
                except TimeoutError:
                    logger.warning("Agent lifecycle monitor shutdown timed out")

            if self.conductor_manager:
                try:
                    from gobby.conductor.manager import ConductorManager

                    if isinstance(self.conductor_manager, ConductorManager):
                        await asyncio.wait_for(self.conductor_manager.shutdown(), timeout=5.0)
                except TimeoutError:
                    logger.warning("Conductor shutdown timed out")
                except Exception as e:
                    logger.debug("Conductor shutdown error: %s", e)

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

            if self.communications_manager:
                try:
                    await asyncio.wait_for(self.communications_manager.stop(), timeout=5.0)
                except TimeoutError:
                    logger.warning("CommunicationsManager shutdown timed out")

            if websocket_task:
                websocket_task.cancel()
                try:
                    await asyncio.wait_for(websocket_task, timeout=3.0)
                except (asyncio.CancelledError, TimeoutError):
                    logger.warning("WebSocket server shutdown timed out or cancelled")

            # Cancel background pipeline tasks
            try:
                from gobby.mcp_proxy.tools.workflows._pipeline_execution import (
                    cleanup_background_tasks,
                )

                await asyncio.wait_for(cleanup_background_tasks(), timeout=5.0)
            except TimeoutError:
                logger.warning("Pipeline background tasks cleanup timed out")
            except Exception as e:
                logger.warning(f"Pipeline background tasks cleanup failed: {e}")

            # Cancel metrics cleanup task
            if self._metrics_cleanup_task and not self._metrics_cleanup_task.done():
                self._metrics_cleanup_task.cancel()
                try:
                    await asyncio.wait_for(self._metrics_cleanup_task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass

            # Cancel metrics archive task
            if self._metrics_archive_task and not self._metrics_archive_task.done():
                self._metrics_archive_task.cancel()
                try:
                    await asyncio.wait_for(self._metrics_archive_task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass

            # Cancel span cleanup task
            if self._span_cleanup_task and not self._span_cleanup_task.done():
                self._span_cleanup_task.cancel()
                try:
                    await asyncio.wait_for(self._span_cleanup_task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass

            # Cancel metric snapshot task
            if self._metric_snapshot_task and not self._metric_snapshot_task.done():
                self._metric_snapshot_task.cancel()
                try:
                    await asyncio.wait_for(self._metric_snapshot_task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass

            # Cancel zombie message cleanup task
            if self._zombie_messages_task and not self._zombie_messages_task.done():
                self._zombie_messages_task.cancel()
                try:
                    await asyncio.wait_for(self._zombie_messages_task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass

            # Cancel vector store rebuild task
            if self._vector_rebuild_task and not self._vector_rebuild_task.done():
                self._vector_rebuild_task.cancel()
                try:
                    await asyncio.wait_for(self._vector_rebuild_task, timeout=2.0)
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

            # NOTE: Shutdown JSONL exports removed to avoid git noise (#10198).
            # The pre-commit hook exports and stages JSONL files at commit time.

            try:
                await asyncio.wait_for(self.mcp_proxy.disconnect_all(), timeout=3.0)
            except TimeoutError:
                logger.warning("MCP disconnect timed out")

            # Clean up PID file on graceful shutdown
            cleanup_pid_file()

            logger.info("Shutdown complete")

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            cleanup_pid_file()
            sys.exit(1)


async def run_gobby(config_path: Path | None = None, verbose: bool = False) -> None:
    runner = GobbyRunner(config_path=config_path, verbose=verbose)
    await runner.run()


def _healthy_daemon_running(port: int, host: str = "localhost") -> bool:
    """Quick check whether a healthy Gobby daemon is already listening."""
    import urllib.parse
    import urllib.request

    # Normalize wildcard addresses to localhost for health check
    if host in ("0.0.0.0", "::", ""):
        host = "localhost"
    elif ":" in host and not host.startswith("["):
        host = f"[{host}]"

    try:
        url = f"http://{host}:{port}/api/admin/health"
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:  # nosec B310
            return bool(resp.status == 200)
    except Exception:
        return False


def main(config_path: Path | None = None, verbose: bool = False) -> None:
    # Fast guard: if a healthy daemon is already serving on our port, exit
    # cleanly so launchd (KeepAlive.SuccessfulExit=false) won't respawn us.
    from gobby.config.bootstrap import load_bootstrap

    bootstrap = load_bootstrap(str(config_path) if config_path else None)
    if _healthy_daemon_running(bootstrap.daemon_port, bootstrap.bind_host):
        print(
            f"Gobby daemon already healthy on port {bootstrap.daemon_port}, exiting.",
            file=sys.stderr,
        )
        sys.exit(0)

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
