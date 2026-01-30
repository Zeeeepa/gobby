"""
HTTP server for Gobby daemon.

Provides a FastAPI-based HTTP server for REST endpoints, MCP tool proxying,
and session management. Local-first version: no platform auth, no remote sync.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gobby.adapters.codex_impl.adapter import CodexAdapter
from gobby.hooks.broadcaster import HookEventBroadcaster
from gobby.hooks.hook_manager import HookManager
from gobby.llm import create_llm_service
from gobby.mcp_proxy.registries import setup_internal_registries
from gobby.mcp_proxy.semantic_search import SemanticToolSearch
from gobby.mcp_proxy.server import GobbyDaemonTools, create_mcp_server
from gobby.mcp_proxy.services.tool_filter import ToolFilterService
from gobby.utils.metrics import get_metrics_collector
from gobby.utils.version import get_version

if TYPE_CHECKING:
    from gobby.app_context import ServiceContainer
    from gobby.config.app import DaemonConfig
    from gobby.llm import LLMService
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.servers.websocket import WebSocketServer
    from gobby.utils.tool_metrics import ToolMetricsManager

logger = logging.getLogger(__name__)


class HTTPServer:
    """
    FastAPI HTTP server for Gobby daemon.

    Handles MCP tool proxying, session management, and admin endpoints.
    Local-first version: no platform authentication, uses local SQLite storage.
    """

    def __init__(
        self,
        services: "ServiceContainer",
        port: int = 8000,
        test_mode: bool = False,
        codex_client: Any | None = None,
    ) -> None:
        """
        Initialize HTTP server.

        Args:
            services: ServiceContainer holding all dependencies
            port: Server port
            test_mode: Run in test mode (disable features that conflict with testing)
            codex_client: CodexAppServerClient instance for Codex integration
        """
        self.services = services
        self.port = port
        self.test_mode = test_mode
        self.codex_client = codex_client

        # WebSocket server reference (set by GobbyRunner after construction)
        self.websocket_server: WebSocketServer | None = None

        self.broadcaster = HookEventBroadcaster(services.websocket_server, services.config)

        self._start_time: float = time.time()

        # Create LLM service if not provided in container (fallback)
        if not services.llm_service and services.config:
            try:
                services.llm_service = create_llm_service(services.config)
                logger.debug(
                    f"LLM service initialized with providers: {services.llm_service.enabled_providers}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize LLM service: {e}")

        # Create MCP server instance
        self._mcp_server = None
        self._internal_manager = None
        self._tools_handler = None

        if services.mcp_manager:
            # Determine WebSocket port
            ws_port = 60888
            cfg = services.config
            if cfg and hasattr(cfg, "websocket") and cfg.websocket:
                ws_port = cfg.websocket.port

            # Create a lazy getter for tool_proxy that will be available after
            # GobbyDaemonTools is created. This allows in-process agents to route
            # tool calls through the MCP proxy.
            def tool_proxy_getter() -> Any:
                if self._tools_handler is not None:
                    return self._tools_handler.tool_proxy
                return None

            # Create merge managers if db available
            merge_storage = None
            merge_resolver = None
            inter_session_message_manager = None
            if self.services.mcp_db_manager:
                from gobby.storage.inter_session_messages import InterSessionMessageManager
                from gobby.storage.merge_resolutions import MergeResolutionManager
                from gobby.worktrees.merge.resolver import MergeResolver

                merge_storage = MergeResolutionManager(self.services.mcp_db_manager.db)
                merge_resolver = MergeResolver()
                merge_resolver._llm_service = services.llm_service
                inter_session_message_manager = InterSessionMessageManager(
                    self.services.mcp_db_manager.db
                )
                logger.debug("Merge resolution and inter-session messaging subsystems initialized")

            # Setup internal registries (gobby-tasks, gobby-memory, etc.)
            self._internal_manager = setup_internal_registries(
                _config=services.config,
                _session_manager=None,  # Not needed for internal registries
                memory_manager=services.memory_manager,
                task_manager=services.task_manager,
                sync_manager=services.task_sync_manager,
                task_validator=services.task_validator,
                message_manager=services.message_manager,
                local_session_manager=services.session_manager,
                metrics_manager=services.metrics_manager,
                llm_service=services.llm_service,
                agent_runner=services.agent_runner,
                worktree_storage=services.worktree_storage,
                clone_storage=services.clone_storage,
                git_manager=services.git_manager,
                merge_storage=merge_storage,
                merge_resolver=merge_resolver,
                project_id=services.project_id,
                tool_proxy_getter=tool_proxy_getter,
                inter_session_message_manager=inter_session_message_manager,
            )
            registry_count = len(self._internal_manager)
            logger.debug(f"Internal registries initialized: {registry_count} registries")

            # Initialize tool summarizer config
            if services.config:
                from gobby.tools.summarizer import init_summarizer_config

                init_summarizer_config(services.config.tool_summarizer)
                logger.debug("Tool summarizer config initialized")

            # Create semantic search instance if db available
            semantic_search = None
            if services.mcp_db_manager:
                semantic_search = SemanticToolSearch(db=services.mcp_db_manager.db)
                logger.debug("Semantic tool search initialized")

            # Create tool filter for workflow phase restrictions
            tool_filter = None
            if services.mcp_db_manager:
                tool_filter = ToolFilterService(db=services.mcp_db_manager.db)
                logger.debug("Tool filter service initialized")

            # Create fallback resolver for alternative tool suggestions on error
            fallback_resolver = None
            if semantic_search and services.metrics_manager:
                from gobby.mcp_proxy.services.fallback import ToolFallbackResolver

                fallback_resolver = ToolFallbackResolver(
                    semantic_search=semantic_search,
                    metrics_manager=services.metrics_manager,
                )
                logger.debug("Fallback resolver initialized")

            # Create tools handler
            self._tools_handler = GobbyDaemonTools(
                mcp_manager=services.mcp_manager,
                daemon_port=port,
                websocket_port=ws_port,
                start_time=self._start_time,
                internal_manager=self._internal_manager,
                config=services.config,
                llm_service=services.llm_service,
                session_manager=services.session_manager,
                memory_manager=services.memory_manager,
                config_manager=services.mcp_db_manager,
                semantic_search=semantic_search,
                tool_filter=tool_filter,
                fallback_resolver=fallback_resolver,
            )
            self._mcp_server = create_mcp_server(self._tools_handler)
            logger.debug("MCP server initialized and will be mounted at /mcp")

        self.app = self._create_app()
        self._running = False
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._metrics = get_metrics_collector()
        self._daemon: Any = None  # Set externally by daemon

    # Property accessors for services (delegate to container)
    @property
    def config(self) -> "DaemonConfig | None":
        return self.services.config

    @property
    def session_manager(self) -> Any:
        return self.services.session_manager

    @session_manager.setter
    def session_manager(self, value: Any) -> None:
        self.services.session_manager = value

    @property
    def task_manager(self) -> Any:
        return self.services.task_manager

    @task_manager.setter
    def task_manager(self, value: Any) -> None:
        self.services.task_manager = value

    @property
    def mcp_manager(self) -> "MCPClientManager | None":
        return self.services.mcp_manager

    @mcp_manager.setter
    def mcp_manager(self, value: "MCPClientManager | None") -> None:
        self.services.mcp_manager = value

    @property
    def llm_service(self) -> "LLMService | None":
        return self.services.llm_service

    @llm_service.setter
    def llm_service(self, value: "LLMService | None") -> None:
        self.services.llm_service = value

    @property
    def memory_manager(self) -> Any:
        return self.services.memory_manager

    @memory_manager.setter
    def memory_manager(self, value: Any) -> None:
        self.services.memory_manager = value

    @property
    def message_manager(self) -> Any:
        return self.services.message_manager

    @message_manager.setter
    def message_manager(self, value: Any) -> None:
        self.services.message_manager = value

    @property
    def message_processor(self) -> Any:
        return self.services.message_processor

    @message_processor.setter
    def message_processor(self, value: Any) -> None:
        self.services.message_processor = value

    @property
    def metrics_manager(self) -> "ToolMetricsManager | None":
        return self.services.metrics_manager

    @metrics_manager.setter
    def metrics_manager(self, value: "ToolMetricsManager | None") -> None:
        self.services.metrics_manager = value

    @property
    def _mcp_db_manager(self) -> Any:
        return self.services.mcp_db_manager

    @_mcp_db_manager.setter
    def _mcp_db_manager(self, value: Any) -> None:
        self.services.mcp_db_manager = value

    @property
    def tool_proxy(self) -> Any:
        """Get the ToolProxyService instance for routing tool calls with error enrichment."""
        if self._tools_handler is not None:
            return self._tools_handler.tool_proxy
        return None

    def _resolve_project_id(self, project_id: str | None, cwd: str | None) -> str:
        """
        Resolve project_id from cwd if not provided.

        If project_id is given, returns it directly.
        Otherwise, looks up project from .gobby/project.json in the cwd.

        Args:
            project_id: Optional explicit project ID
            cwd: Current working directory path

        Returns:
            Project ID from .gobby/project.json

        Raises:
            ValueError: If no project.json found (project not initialized)
        """
        from pathlib import Path

        if project_id:
            return project_id

        # Get cwd or use current directory
        working_dir = Path(cwd) if cwd else Path.cwd()

        # Look up project from .gobby/project.json
        from gobby.utils.project_context import get_project_context

        project_context = get_project_context(working_dir)
        if project_context and project_context.get("id"):
            return str(project_context["id"])

        # No project.json found - require explicit initialization
        raise ValueError(
            f"No .gobby/project.json found in {working_dir} or parents. "
            "Run 'gobby init' to initialize a project."
        )

    def _create_app(self) -> FastAPI:
        """
        Create and configure FastAPI application.

        Returns:
            Configured FastAPI app instance
        """

        # Create MCP app first if available (needed for lifespan)
        mcp_app = None
        if self._mcp_server:
            mcp_app = self._mcp_server.streamable_http_app()
            logger.debug("MCP HTTP app created")

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
            """Handle application startup and shutdown with combined lifespans."""
            logger.debug("Starting Gobby HTTP server on port %d", self.port)
            self._running = True
            self._start_time = time.time()

            # Startup operations
            if self.test_mode:
                logger.debug("Running in test mode - external connections disabled")

            # Initialize HookManager singleton with logging config
            hook_manager_kwargs: dict[str, Any] = {
                "daemon_host": "localhost",
                "daemon_port": self.port,
                "llm_service": self.services.llm_service,
                "config": self.services.config,
                "broadcaster": self.broadcaster,
                "mcp_manager": self.services.mcp_manager,
                "message_processor": self.services.message_processor,
                "memory_sync_manager": self.services.memory_sync_manager,
                "task_sync_manager": self.services.task_sync_manager,
            }
            if self.services.config:
                # Pass full log file path from config
                hook_manager_kwargs["log_file"] = self.services.config.logging.hook_manager
                hook_manager_kwargs["log_max_bytes"] = (
                    self.services.config.logging.max_size_mb * 1024 * 1024
                )
                hook_manager_kwargs["log_backup_count"] = self.services.config.logging.backup_count

                app.state.hook_manager = HookManager(**hook_manager_kwargs)
            logger.debug("HookManager initialized in daemon")

            # Wire up stop_registry to WebSocket server for stop_request handling
            if (
                self.services.websocket_server
                and hasattr(app.state, "hook_manager")
                and hasattr(app.state.hook_manager, "_stop_registry")
            ):
                self.services.websocket_server.stop_registry = app.state.hook_manager._stop_registry
                logger.debug("Stop registry connected to WebSocket server")

            # Store server instance for dependency injection
            app.state.server = self

            # Initialize CodexAdapter for session tracking
            app.state.codex_adapter = None
            if self.codex_client and CodexAdapter.is_codex_available():
                codex_adapter = CodexAdapter(hook_manager=app.state.hook_manager)
                codex_adapter.attach_to_client(self.codex_client)
                app.state.codex_adapter = codex_adapter
                logger.debug("CodexAdapter attached to CodexAppServerClient")

                # Sync existing Codex sessions when client is connected
                if self.codex_client.is_connected:
                    try:
                        synced = await codex_adapter.sync_existing_sessions()
                        logger.debug(f"Synced {synced} existing Codex sessions")
                    except Exception as e:
                        logger.warning(f"Failed to sync existing Codex sessions: {e}")

            # If MCP app exists, wrap its lifespan
            if mcp_app is not None:
                # Use router.lifespan_context for stable FastMCP version
                async with mcp_app.router.lifespan_context(app):
                    logger.debug("MCP server lifespan initialized")
                    yield
                logger.debug("MCP server lifespan shutdown complete")
            else:
                yield

            # Shutdown operations
            logger.debug("Shutting down Gobby HTTP server")

            # Cleanup CodexAdapter
            if hasattr(app.state, "codex_adapter") and app.state.codex_adapter:
                app.state.codex_adapter.detach_from_client()
                logger.debug("CodexAdapter detached")

            # Cleanup HookManager
            if hasattr(app.state, "hook_manager"):
                app.state.hook_manager.shutdown()
                logger.debug("HookManager shutdown complete")

            # Process graceful shutdown (tasks, MCP connections)
            await self._process_shutdown()

            self._running = False

        app = FastAPI(
            title="Gobby Daemon",
            description="Local-first HTTP server for MCP and session management",
            version=get_version(),
            lifespan=lifespan,
        )

        # Add CORS middleware for cross-origin requests
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allow all origins for local development
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register exception handlers
        self._register_exception_handlers(app)

        # Register routes
        self._register_routes(app)

        # Mount MCP server if available
        if mcp_app is not None:
            app.mount("/mcp", mcp_app)
            logger.debug("MCP server mounted at /mcp")

        return app

    def _register_exception_handlers(self, app: FastAPI) -> None:
        """
        Register global exception handlers.

        All exceptions return 200 OK to prevent Claude Code hook failures.

        Args:
            app: FastAPI application instance
        """

        @app.exception_handler(Exception)
        async def global_exception_handler(
            request: Request,
            exc: Exception,
        ) -> JSONResponse:
            """Handle all uncaught exceptions.

            HTTPException is re-raised to let FastAPI's built-in handler
            return proper status codes (404, 422, etc.). All other exceptions
            return 200 OK to prevent hook failures.
            """
            # Let HTTPException pass through to FastAPI's built-in handler
            # so proper status codes (404, 422, etc.) are returned
            if isinstance(exc, HTTPException):
                raise exc

            logger.error(
                "Unhandled exception in HTTP server: %s",
                exc,
                exc_info=True,
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "client": request.client.host if request.client else None,
                },
            )

            # Return 200 OK to prevent hook failure for non-HTTP exceptions
            return JSONResponse(
                status_code=200,
                content={
                    "status": "error",
                    "message": "Internal error occurred but request acknowledged",
                    "error_logged": True,
                },
            )

    def _register_routes(self, app: FastAPI) -> None:
        """
        Register HTTP routes using extracted router modules.

        Args:
            app: FastAPI application instance
        """
        from gobby.servers.routes import (
            create_admin_router,
            create_hooks_router,
            create_mcp_router,
            create_plugins_router,
            create_sessions_router,
            create_webhooks_router,
        )

        # Include all routers
        app.include_router(create_admin_router(self))
        app.include_router(create_sessions_router(self))
        app.include_router(create_mcp_router())
        app.include_router(create_hooks_router(self))
        app.include_router(create_plugins_router())
        app.include_router(create_webhooks_router())

    async def _process_shutdown(self) -> None:
        """
        Background task to perform graceful daemon shutdown.
        """
        start_time = time.perf_counter()

        try:
            logger.debug("Processing graceful shutdown")

            # Cancel pending background tasks immediately instead of polling
            pending_tasks_count = len(self._background_tasks)
            if pending_tasks_count > 0:
                logger.debug(
                    "Cancelling pending background tasks",
                    extra={"pending_tasks": pending_tasks_count},
                )

                # Cancel all tasks
                for task in self._background_tasks:
                    task.cancel()

                # Wait for cancellation to complete with a short timeout
                if self._background_tasks:
                    done, pending = await asyncio.wait(
                        self._background_tasks,
                        timeout=5.0,
                        return_when=asyncio.ALL_COMPLETED,
                    )

                    completed_count = len(done)
                    remaining_count = len(pending)

                    if remaining_count > 0:
                        logger.warning(
                            "Some background tasks did not cancel in time",
                            extra={
                                "completed": completed_count,
                                "remaining": remaining_count,
                            },
                        )
                    else:
                        logger.debug(
                            "All background tasks cancelled",
                            extra={"completed": completed_count},
                        )

            # Disconnect all MCP servers
            if self.services.mcp_manager:
                logger.debug("Disconnecting MCP servers...")
                try:
                    await self.services.mcp_manager.disconnect_all()
                    logger.debug("MCP servers disconnected")
                except Exception as e:
                    logger.warning(f"Error disconnecting MCP servers: {e}")

            duration_seconds = time.perf_counter() - start_time
            self._metrics.inc_counter("shutdown_succeeded_total")

            logger.debug(
                "Shutdown processed",
                extra={"duration_seconds": duration_seconds},
            )

        except Exception as e:
            duration_seconds = time.perf_counter() - start_time
            self._metrics.inc_counter("shutdown_failed_total")

            logger.error(
                "Shutdown processing failed: %s",
                e,
                exc_info=True,
                extra={"duration_seconds": duration_seconds},
            )


async def create_server(
    services: "ServiceContainer",
    port: int = 60887,
    test_mode: bool = False,
) -> HTTPServer:
    """
    Create HTTP server instance.

    Args:
        services: ServiceContainer holding dependencies
        port: Port to listen on
        test_mode: Enable test mode

    Returns:
        Configured HTTPServer instance
    """
    return HTTPServer(
        services=services,
        port=port,
        test_mode=test_mode,
    )


async def run_server(
    server: HTTPServer,
    host: str = "0.0.0.0",  # nosec B104 - local daemon needs network access
    workers: int = 1,
    limit_concurrency: int | None = 1000,
    limit_max_requests: int | None = None,
    timeout_keep_alive: int = 5,
    timeout_graceful_shutdown: int = 30,
) -> None:
    """
    Run HTTP server with production-ready Uvicorn configuration.

    Args:
        server: HTTPServer instance
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
        workers: Number of worker processes (default: 1 for async)
        limit_concurrency: Max concurrent connections (default: 1000)
        limit_max_requests: Max requests before worker restart (None = unlimited)
        timeout_keep_alive: Keep-alive timeout in seconds (default: 5)
        timeout_graceful_shutdown: Graceful shutdown timeout in seconds (default: 30)
    """
    import uvicorn

    config = uvicorn.Config(
        server.app,
        host=host,
        port=server.port,
        log_level="info",
        access_log=True,
        log_config=None,
        limit_concurrency=limit_concurrency,
        limit_max_requests=limit_max_requests,
        timeout_keep_alive=timeout_keep_alive,
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        backlog=2048,
        workers=workers,
        loop="auto",
        h11_max_incomplete_event_size=16384,
    )

    uvicorn_server = uvicorn.Server(config)

    async def shutdown_handler() -> None:
        """Handle graceful shutdown of HTTP server."""
        logger.debug("Initiating HTTP server shutdown...")
        if hasattr(server, "_daemon") and server._daemon is not None:
            try:
                server._daemon.graceful_shutdown(timeout=timeout_graceful_shutdown)
            except Exception as e:
                logger.warning(f"Error during daemon shutdown: {e}")

    try:
        await uvicorn_server.serve()
    except (KeyboardInterrupt, SystemExit):
        logger.debug("Received shutdown signal")
        await shutdown_handler()
    finally:
        logger.debug("HTTP server stopped")
