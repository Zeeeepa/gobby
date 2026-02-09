"""HookManager subsystem factory.

Creates and wires all HookManager subsystems in a single factory method.
Extracted from HookManager.__init__() as part of the Strangler Fig decomposition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.autonomous.progress_tracker import ProgressTracker
from gobby.autonomous.stop_registry import StopRegistry
from gobby.autonomous.stuck_detector import StuckDetector
from gobby.hooks.event_handlers import EventHandlers
from gobby.hooks.health_monitor import HealthMonitor
from gobby.hooks.plugins import PluginLoader
from gobby.hooks.session_coordinator import SessionCoordinator
from gobby.hooks.skill_manager import HookSkillManager
from gobby.hooks.webhooks import WebhookDispatcher
from gobby.memory.manager import MemoryManager
from gobby.sessions.manager import SessionManager
from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
from gobby.sessions.transcripts.hook_assembler import HookTranscriptAssembler
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
    import asyncio
    from collections.abc import Callable

    from gobby.llm.service import LLMService

logger = logging.getLogger(__name__)

# Backward-compatible alias (moved from hook_manager.py)
TranscriptProcessor = ClaudeTranscriptParser


@dataclass
class HookManagerComponents:
    """All subsystem instances created by HookManagerFactory."""

    config: Any  # DaemonConfig | None
    database: LocalDatabase
    daemon_client: DaemonClient
    transcript_processor: ClaudeTranscriptParser
    session_storage: LocalSessionManager
    session_task_manager: SessionTaskManager
    memory_storage: LocalMemoryManager
    message_manager: LocalSessionMessageManager
    task_manager: LocalTaskManager
    agent_run_manager: LocalAgentRunManager
    worktree_manager: LocalWorktreeManager
    artifact_manager: Any  # LocalArtifactManager
    artifact_capture_hook: Any  # ArtifactCaptureHook
    stop_registry: StopRegistry
    progress_tracker: ProgressTracker
    stuck_detector: StuckDetector
    memory_manager: MemoryManager
    workflow_loader: WorkflowLoader
    workflow_state_manager: WorkflowStateManager
    template_engine: Any  # TemplateEngine
    skill_manager: HookSkillManager
    pipeline_executor: Any  # PipelineExecutor | None
    action_executor: Any  # ActionExecutor
    workflow_engine: Any  # WorkflowEngine
    workflow_handler: WorkflowHookHandler
    webhook_dispatcher: WebhookDispatcher
    plugin_loader: PluginLoader | None
    session_manager: SessionManager
    session_coordinator: SessionCoordinator
    health_monitor: HealthMonitor
    hook_assembler: HookTranscriptAssembler
    event_handlers: EventHandlers


class HookManagerFactory:
    """Factory for creating and wiring all HookManager subsystems."""

    @staticmethod
    def create(
        *,
        daemon_host: str,
        daemon_port: int,
        llm_service: LLMService | None,
        config: Any | None,
        hook_logger: logging.Logger,
        loop: asyncio.AbstractEventLoop | None,
        broadcaster: Any | None,
        tool_proxy_getter: Any | None,
        message_processor: Any | None,
        memory_sync_manager: Any | None,
        task_sync_manager: Any | None,
        get_machine_id: Callable[[], str],
        resolve_project_id: Callable[[str | None, str | None], str],
    ) -> HookManagerComponents:
        """Create all HookManager subsystems.

        Args:
            daemon_host: Daemon host for communication
            daemon_port: Daemon port for communication
            llm_service: Optional LLMService for multi-provider support
            config: Optional DaemonConfig instance
            hook_logger: Configured logger instance
            loop: Event loop for async operations
            broadcaster: Optional HookEventBroadcaster instance
            tool_proxy_getter: Callable returning ToolProxyService
            message_processor: SessionMessageProcessor instance
            memory_sync_manager: Optional MemorySyncManager instance
            task_sync_manager: Optional TaskSyncManager instance
            get_machine_id: Callable returning machine ID
            resolve_project_id: Callable resolving project ID from (project_id, cwd)

        Returns:
            HookManagerComponents with all wired subsystem instances
        """
        # Load configuration if not provided
        if not config:
            try:
                from gobby.config.app import load_config

                config = load_config()
            except Exception as e:
                hook_logger.error(
                    f"Failed to load config in HookManager, using defaults: {e}",
                    exc_info=True,
                )

        # Extract config values
        health_check_interval = 10.0
        if config:
            health_check_interval = config.daemon_health_check_interval

        # Initialize Database
        if config and config.database_path:
            db_path = Path(config.database_path).expanduser()
            database = LocalDatabase(db_path)
        else:
            database = LocalDatabase()

        # Create session-agnostic subsystems
        daemon_client = DaemonClient(
            host=daemon_host,
            port=daemon_port,
            timeout=5.0,
            logger=hook_logger,
        )
        transcript_processor = TranscriptProcessor(logger_instance=hook_logger)

        # Create local storage
        session_storage = LocalSessionManager(database)
        session_task_manager = SessionTaskManager(database)
        memory_storage = LocalMemoryManager(database)
        message_manager = LocalSessionMessageManager(database)
        task_manager = LocalTaskManager(database)
        agent_run_manager = LocalAgentRunManager(database)
        worktree_manager = LocalWorktreeManager(database)

        # Initialize Artifact storage and capture hook
        from gobby.hooks.artifact_capture import ArtifactCaptureHook
        from gobby.storage.artifacts import LocalArtifactManager

        artifact_manager = LocalArtifactManager(database)
        artifact_capture_hook = ArtifactCaptureHook(artifact_manager=artifact_manager)

        # Initialize autonomous execution components
        stop_registry = StopRegistry(database)
        progress_tracker = ProgressTracker(database)
        stuck_detector = StuckDetector(database, progress_tracker=progress_tracker)

        # Memory config
        memory_config = config.memory if config and hasattr(config, "memory") else None
        if not memory_config:
            from gobby.config.persistence import MemoryConfig

            memory_config = MemoryConfig()

        mem_manager = MemoryManager(database, memory_config)

        # Initialize Workflow Engine
        from gobby.workflows.actions import ActionExecutor
        from gobby.workflows.engine import WorkflowEngine
        from gobby.workflows.templates import TemplateEngine

        workflow_loader = WorkflowLoader(
            workflow_dirs=[Path.home() / ".gobby" / "workflows"]
        )
        workflow_state_manager = WorkflowStateManager(database)
        template_engine = TemplateEngine()

        # Skill manager for core skill injection
        skill_manager = HookSkillManager()

        # Get websocket_server from broadcaster if available
        websocket_server = None
        if broadcaster and hasattr(broadcaster, "websocket_server"):
            websocket_server = broadcaster.websocket_server

        # Initialize pipeline executor
        pipeline_executor = None
        try:
            from gobby.storage.pipelines import LocalPipelineExecutionManager
            from gobby.workflows.pipeline_executor import PipelineExecutor

            project_id = resolve_project_id(None, None)
            pipeline_execution_manager = LocalPipelineExecutionManager(database, project_id)
            pipeline_executor = PipelineExecutor(
                db=database,
                execution_manager=pipeline_execution_manager,
                llm_service=llm_service,
                loader=workflow_loader,
            )
        except Exception as e:
            logger.debug(f"Pipeline executor not available: {e}")

        action_executor = ActionExecutor(
            db=database,
            session_manager=session_storage,
            template_engine=template_engine,
            llm_service=llm_service,
            transcript_processor=transcript_processor,
            config=config,
            tool_proxy_getter=tool_proxy_getter,
            memory_manager=mem_manager,
            memory_sync_manager=memory_sync_manager,
            task_manager=task_manager,
            task_sync_manager=task_sync_manager,
            session_task_manager=session_task_manager,
            stop_registry=stop_registry,
            progress_tracker=progress_tracker,
            stuck_detector=stuck_detector,
            websocket_server=websocket_server,
            skill_manager=skill_manager,
            pipeline_executor=pipeline_executor,
            workflow_loader=workflow_loader,
        )

        workflow_engine = WorkflowEngine(
            loader=workflow_loader,
            state_manager=workflow_state_manager,
            action_executor=action_executor,
        )

        # Register task_manager with evaluator for task_tree_complete() condition helper
        if task_manager and workflow_engine.evaluator:
            workflow_engine.evaluator.register_task_manager(task_manager)
        # Register stop_registry with evaluator for has_stop_signal() condition helper
        if stop_registry and workflow_engine.evaluator:
            workflow_engine.evaluator.register_stop_registry(stop_registry)

        workflow_timeout: float = 0.0  # 0 = no timeout
        workflow_enabled = True
        if config:
            workflow_timeout = config.workflow.timeout
            workflow_enabled = config.workflow.enabled

        workflow_handler = WorkflowHookHandler(
            engine=workflow_engine,
            loop=loop,
            timeout=workflow_timeout,
            enabled=workflow_enabled,
        )

        # Initialize Webhook Dispatcher
        webhooks_config = None
        if config and hasattr(config, "hook_extensions"):
            webhooks_config = config.hook_extensions.webhooks
        if not webhooks_config:
            from gobby.config.extensions import WebhooksConfig

            webhooks_config = WebhooksConfig()
        webhook_dispatcher = WebhookDispatcher(webhooks_config)

        # Initialize Plugin Loader
        plugin_loader: PluginLoader | None = None
        plugins_config = None
        if config and hasattr(config, "hook_extensions"):
            plugins_config = config.hook_extensions.plugins
        if plugins_config is not None and plugins_config.enabled:
            plugin_loader = PluginLoader(plugins_config)
            try:
                loaded = plugin_loader.load_all()
                if loaded:
                    hook_logger.info(
                        f"Loaded {len(loaded)} plugin(s): {', '.join(p.name for p in loaded)}"
                    )
                    # Register plugin actions and conditions with workflow system
                    action_executor.register_plugin_actions(plugin_loader.registry)
                    workflow_engine.evaluator.register_plugin_conditions(
                        plugin_loader.registry
                    )
            except Exception as e:
                hook_logger.error(f"Failed to load plugins: {e}", exc_info=True)

        # Session manager
        session_mgr = SessionManager(
            session_storage=session_storage,
            logger_instance=hook_logger,
            config=config,
        )

        # Session coordinator
        session_coordinator = SessionCoordinator(
            session_storage=session_storage,
            message_processor=message_processor,
            agent_run_manager=agent_run_manager,
            worktree_manager=worktree_manager,
            logger=hook_logger,
        )

        # Health monitor
        health_monitor = HealthMonitor(
            daemon_client=daemon_client,
            health_check_interval=health_check_interval,
            logger=hook_logger,
        )

        # Hook-based transcript assembler
        hook_assembler = HookTranscriptAssembler()

        # Event handlers
        event_handlers = EventHandlers(
            session_manager=session_mgr,
            workflow_handler=workflow_handler,
            session_storage=session_storage,
            session_task_manager=session_task_manager,
            message_processor=message_processor,
            task_manager=task_manager,
            session_coordinator=session_coordinator,
            message_manager=message_manager,
            skill_manager=skill_manager,
            skills_config=config.skills if config else None,
            artifact_capture_hook=artifact_capture_hook,
            workflow_config=config.workflow if config else None,
            get_machine_id=get_machine_id,
            resolve_project_id=resolve_project_id,
            logger=hook_logger,
        )

        return HookManagerComponents(
            config=config,
            database=database,
            daemon_client=daemon_client,
            transcript_processor=transcript_processor,
            session_storage=session_storage,
            session_task_manager=session_task_manager,
            memory_storage=memory_storage,
            message_manager=message_manager,
            task_manager=task_manager,
            agent_run_manager=agent_run_manager,
            worktree_manager=worktree_manager,
            artifact_manager=artifact_manager,
            artifact_capture_hook=artifact_capture_hook,
            stop_registry=stop_registry,
            progress_tracker=progress_tracker,
            stuck_detector=stuck_detector,
            memory_manager=mem_manager,
            workflow_loader=workflow_loader,
            workflow_state_manager=workflow_state_manager,
            template_engine=template_engine,
            skill_manager=skill_manager,
            pipeline_executor=pipeline_executor,
            action_executor=action_executor,
            workflow_engine=workflow_engine,
            workflow_handler=workflow_handler,
            webhook_dispatcher=webhook_dispatcher,
            plugin_loader=plugin_loader,
            session_manager=session_mgr,
            session_coordinator=session_coordinator,
            health_monitor=health_monitor,
            hook_assembler=hook_assembler,
            event_handlers=event_handlers,
        )
