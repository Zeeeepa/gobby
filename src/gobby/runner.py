import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import uvicorn

from gobby.config.app import load_config
from gobby.llm import LLMService, create_llm_service
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.memory.manager import MemoryManager
from gobby.servers.http import HTTPServer
from gobby.servers.websocket import WebSocketConfig, WebSocketServer
from gobby.sessions.lifecycle import SessionLifecycleManager
from gobby.sessions.processor import SessionMessageProcessor
from gobby.skills import SkillLearner
from gobby.storage.database import LocalDatabase
from gobby.storage.mcp import LocalMCPManager
from gobby.storage.migrations import run_migrations
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.skills import LocalSkillManager
from gobby.storage.tasks import LocalTaskManager
from gobby.sync.memories import MemorySyncManager
from gobby.sync.skills import SkillSyncManager
from gobby.sync.tasks import TaskSyncManager
from gobby.tasks.expansion import TaskExpander
from gobby.tasks.validation import TaskValidator
from gobby.utils.logging import setup_file_logging
from gobby.utils.machine_id import get_machine_id

os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)


class GobbyRunner:
    """Runner for Gobby daemon."""

    def __init__(self, config_path: Path | None = None, verbose: bool = False):
        setup_file_logging(verbose=verbose)
        # setup_mcp_logging(verbose=verbose) # Removed as per instruction

        config_file = str(config_path) if config_path else None
        self.config = load_config(config_file)
        self.verbose = verbose
        self.machine_id = get_machine_id()
        self._shutdown_requested = False
        self._metrics_cleanup_task: asyncio.Task | None = None

        # Initialize local storage
        self.database = LocalDatabase()
        run_migrations(self.database)
        self.session_manager = LocalSessionManager(self.database)
        self.skill_storage = LocalSkillManager(self.database)
        self.message_manager = LocalSessionMessageManager(self.database)
        self.task_manager = LocalTaskManager(self.database)
        self.session_task_manager = SessionTaskManager(self.database)

        # Initialize LLM Service (needed for SkillLearner)
        self.llm_service: LLMService | None = None  # Added type hint
        try:
            self.llm_service = create_llm_service(self.config)
            logger.debug(f"LLM service initialized: {self.llm_service.enabled_providers}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")

        # Initialize Memory & Skills
        self.memory_manager: MemoryManager | None = None  # Added type hint
        if hasattr(self.config, "memory"):
            try:
                self.memory_manager = MemoryManager(self.database, self.config.memory)
            except Exception as e:
                logger.error(f"Failed to initialize MemoryManager: {e}")

        self.skill_learner: SkillLearner | None = None  # Added type hint
        if hasattr(self.config, "skills") and self.llm_service:
            try:
                self.skill_learner = SkillLearner(
                    storage=self.skill_storage,
                    message_manager=self.message_manager,
                    llm_service=self.llm_service,
                    config=self.config.skills,
                )
            except Exception as e:
                logger.error(f"Failed to initialize SkillLearner: {e}")

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
                except Exception as e:
                    logger.error(f"Failed to initialize MemorySyncManager: {e}")

        # Initialize Skill Sync Manager & Wire up listeners
        self.skill_sync_manager: SkillSyncManager | None = None
        if hasattr(self.config, "skill_sync") and self.config.skill_sync.enabled:
            try:
                self.skill_sync_manager = SkillSyncManager(
                    skill_manager=self.skill_storage,
                    config=self.config.skill_sync,
                )
                # Wire up listener to trigger export on changes
                self.skill_storage.add_change_listener(self.skill_sync_manager.trigger_export)
                logger.debug("SkillSyncManager initialized and listener attached")
            except Exception as e:
                logger.error(f"Failed to initialize SkillSyncManager: {e}")

        # Session Message Processor (Phase 6)
        # Created here and passed to HTTPServer which injects it into HookManager
        self.message_processor: SessionMessageProcessor | None = None
        if getattr(self.config, "message_tracking", None) and self.config.message_tracking.enabled:
            self.message_processor = SessionMessageProcessor(
                db=self.database,
                poll_interval=self.config.message_tracking.poll_interval,
            )

        # Initialize Task Managers (Phase 7.1)
        self.task_expander: TaskExpander | None = None
        self.task_validator: TaskValidator | None = None

        if self.llm_service:
            gobby_tasks_config = self.config.gobby_tasks
            if gobby_tasks_config.expansion.enabled:
                try:
                    self.task_expander = TaskExpander(
                        llm_service=self.llm_service,
                        config=gobby_tasks_config.expansion,
                        task_manager=self.task_manager,
                        mcp_manager=self.mcp_proxy,
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize TaskExpander: {e}")

            if gobby_tasks_config.validation.enabled:
                try:
                    self.task_validator = TaskValidator(
                        llm_service=self.llm_service,
                        config=gobby_tasks_config.validation,
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize TaskValidator: {e}")

        # Session Lifecycle Manager (background jobs for expiring and processing)
        self.lifecycle_manager = SessionLifecycleManager(
            db=self.database,
            config=self.config.session_lifecycle,
        )

        # HTTP Server
        self.http_server = HTTPServer(
            port=self.config.daemon_port,
            mcp_manager=self.mcp_proxy,
            mcp_db_manager=self.mcp_db_manager,
            config=self.config,
            session_manager=self.session_manager,
            task_manager=self.task_manager,
            task_sync_manager=self.task_sync_manager,
            message_manager=self.message_manager,
            memory_manager=self.memory_manager,
            skill_learner=self.skill_learner,
            llm_service=self.llm_service,
            message_processor=self.message_processor,
            memory_sync_manager=self.memory_sync_manager,
            skill_sync_manager=self.skill_sync_manager,
            task_expander=self.task_expander,
            task_validator=self.task_validator,
            metrics_manager=self.metrics_manager,
        )

        # Ensure message_processor property is set (redundant but explicit):
        self.http_server.message_processor = self.message_processor

        # WebSocket Server (Optional)
        self.websocket_server: WebSocketServer | None = None
        if self.config.websocket and getattr(self.config.websocket, "enabled", True):
            websocket_config = WebSocketConfig(
                host="localhost",
                port=self.config.websocket.port,
                ping_interval=self.config.websocket.ping_interval,
                ping_timeout=self.config.websocket.ping_timeout,
            )
            self.websocket_server = WebSocketServer(
                config=websocket_config,
                mcp_manager=self.mcp_proxy,
            )
            # Pass WebSocket server reference to HTTP server for broadcasting
            self.http_server.websocket_server = self.websocket_server
            # Also update the HTTPServer's broadcaster to use the same websocket_server
            self.http_server.broadcaster.websocket_server = self.websocket_server

            # Pass WebSocket server to message processor if enabled
            if self.message_processor:
                self.message_processor.websocket_server = self.websocket_server

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

            # Start Message Processor
            if self.message_processor:
                await self.message_processor.start()

            # Start Session Lifecycle Manager
            await self.lifecycle_manager.start()

            # Start periodic metrics cleanup (every 24 hours)
            self._metrics_cleanup_task = asyncio.create_task(
                self._metrics_cleanup_loop(),
                name="metrics-cleanup",
            )

            # Start WebSocket server
            websocket_task = None
            if self.websocket_server:
                websocket_task = asyncio.create_task(self.websocket_server.start())

            # Start HTTP server
            config = uvicorn.Config(
                self.http_server.app,
                host="0.0.0.0",
                port=self.http_server.port,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config)
            server_task = asyncio.create_task(server.serve())

            # Wait for shutdown
            while not self._shutdown_requested:
                await asyncio.sleep(0.5)

            # Cleanup with timeouts to prevent hanging
            server.should_exit = True
            try:
                await asyncio.wait_for(server_task, timeout=3.0)
            except TimeoutError:
                logger.warning("HTTP server shutdown timed out")

            try:
                await asyncio.wait_for(self.lifecycle_manager.stop(), timeout=2.0)
            except TimeoutError:
                logger.warning("Lifecycle manager shutdown timed out")

            if self.message_processor:
                try:
                    await asyncio.wait_for(self.message_processor.stop(), timeout=2.0)
                except TimeoutError:
                    logger.warning("Message processor shutdown timed out")

            if websocket_task:
                websocket_task.cancel()
                try:
                    await websocket_task
                except asyncio.CancelledError:
                    pass

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
