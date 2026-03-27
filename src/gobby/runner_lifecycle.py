"""GobbyRunner daemon lifecycle — startup, event loop, and shutdown.

Extracted from runner.py to keep the main module under the monolith limit.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

if TYPE_CHECKING:
    from gobby.runner import GobbyRunner

logger = logging.getLogger(__name__)


async def run_daemon(runner: GobbyRunner) -> None:
    """Main daemon startup, event loop, and shutdown sequence."""
    from gobby.runner_maintenance import (
        cleanup_comms_messages_loop,
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
        setup_signal_handlers(lambda: setattr(runner, "_shutdown_requested", True))

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
            await asyncio.wait_for(runner.mcp_proxy.connect_all(), timeout=10.0)
        except TimeoutError:
            logger.warning("MCP connection timed out")
        except Exception as e:
            logger.error(f"MCP connection failed: {e}")

        # Neo4j health check: disable KG features if unreachable
        if (
            runner.memory_manager
            and hasattr(runner.config, "memory")
            and runner.config.memory.neo4j_url
        ):
            from gobby.cli.services import is_neo4j_healthy

            neo4j_url = runner.config.memory.neo4j_url
            if not await is_neo4j_healthy(neo4j_url):
                logger.warning(
                    f"Neo4j configured but unreachable at {neo4j_url} — graph features disabled"
                )
                runner.memory_manager._neo4j_client = None
                runner.memory_manager._kg_service = None

        # Run metrics cleanup on startup
        try:
            deleted = runner.metrics_manager.cleanup_old_metrics()
            if deleted > 0:
                logger.info(f"Startup metrics cleanup: removed {deleted} old entries")
        except Exception as e:
            logger.warning(f"Metrics cleanup failed: {e}")

        # Initialize VectorStore and schedule rebuild in background if needed
        if runner.vector_store:
            try:
                await runner.vector_store.initialize()
                # Ensure tool_embeddings collection exists (shared Qdrant instance)
                from gobby.mcp_proxy.semantic_search import SemanticToolSearch

                await runner.vector_store.ensure_collection(
                    SemanticToolSearch.TOOL_COLLECTION,
                    runner.config.memory.embedding_dim,
                )
                qdrant_count = await runner.vector_store.count()
                if qdrant_count == 0 and runner.memory_manager:
                    sqlite_memories = runner.memory_manager.storage.list_memories(limit=10000)
                    if sqlite_memories:
                        embed_fn = runner.memory_manager.embed_fn
                        if embed_fn:
                            logger.info(
                                f"Qdrant empty, scheduling background rebuild from "
                                f"{len(sqlite_memories)} SQLite memories..."
                            )
                            memory_dicts = [
                                {"id": m.id, "content": m.content} for m in sqlite_memories
                            ]
                            runner._vector_rebuild_task = asyncio.create_task(
                                rebuild_vector_store(runner.vector_store, memory_dicts, embed_fn),
                                name="vector-store-rebuild",
                            )
                        else:
                            logger.warning("No embed_fn configured, skipping VectorStore rebuild")
            except Exception as e:
                logger.error(f"VectorStore initialization failed: {e}")

        # Start Message Processor
        if runner.message_processor:
            await runner.message_processor.start()

        # Start Communications Manager
        if runner.communications_manager:
            try:
                await runner.communications_manager.start()
            except Exception as e:
                logger.error(f"CommunicationsManager start failed: {e}")

        # Start Session Lifecycle Manager
        await runner.lifecycle_manager.start()

        # tmux socket health check before any agent operations
        try:
            from gobby.agents.tmux.session_manager import TmuxSessionManager

            tmux_mgr = TmuxSessionManager()
            await tmux_mgr.health_check()
        except Exception as e:
            logger.warning(f"tmux health check failed on startup: {e}")

        # Start agent lifecycle monitor — DB-driven, so it automatically
        # detects and cleans up orphaned agents from previous daemon sessions
        # on the first check iteration.
        if runner.agent_lifecycle_monitor:
            # Clean up stale pending runs from before restart
            await runner.agent_lifecycle_monitor.cleanup_stale_pending_runs()
            await runner.agent_lifecycle_monitor.start()

        # Start Cron Scheduler
        if runner.cron_scheduler:
            await runner.cron_scheduler.start()

        # Start periodic metrics cleanup (every 24 hours)
        runner._metrics_cleanup_task = asyncio.create_task(
            metrics_cleanup_loop(runner.metrics_manager, lambda: runner._shutdown_requested),
            name="metrics-cleanup",
        )

        # Start periodic metrics event archiving (every 24 hours, 30-day retention)
        runner._metrics_archive_task = asyncio.create_task(
            metrics_archive_loop(runner.metrics_event_store, lambda: runner._shutdown_requested),
            name="metrics-archive",
        )

        # Start periodic span cleanup (every 24 hours, 7-day retention)
        retention_days = 7
        if runner.config.telemetry and hasattr(runner.config.telemetry, "trace_retention_days"):
            retention_days = runner.config.telemetry.trace_retention_days

        runner._span_cleanup_task = asyncio.create_task(
            span_cleanup_loop(
                runner.database,
                lambda: runner._shutdown_requested,
                retention_days=retention_days,
            ),
            name="span-cleanup",
        )

        # Start periodic zombie message cleanup (every 6 hours)
        runner._zombie_messages_task = asyncio.create_task(
            cleanup_zombie_messages_loop(runner.database, lambda: runner._shutdown_requested),
            name="zombie-message-cleanup",
        )

        # Start periodic comms message cleanup
        runner._comms_messages_task = asyncio.create_task(
            cleanup_comms_messages_loop(runner.database, lambda: runner._shutdown_requested),
            name="comms-message-cleanup",
        )

        # Start code index maintenance loop
        runner._code_index_task = None
        if runner.code_indexer:
            from gobby.code_index.maintenance import code_index_maintenance_loop

            shutdown_event = asyncio.Event()
            # Wire shutdown event to _shutdown_requested flag
            runner._code_index_shutdown = shutdown_event
            runner._code_index_task = asyncio.create_task(
                code_index_maintenance_loop(
                    runner.code_indexer,
                    shutdown_flag=shutdown_event,
                    interval=runner.config.code_index.maintenance_interval_seconds,
                ),
                name="code-index-maintenance",
            )

        # Start periodic savings rollup (every 24 hours)
        runner._savings_rollup_task = asyncio.create_task(
            savings_rollup_loop(runner.database, lambda: runner._shutdown_requested),
            name="savings-rollup",
        )

        # Start periodic metric snapshot loop (every 60s)
        runner._metric_snapshot_task = asyncio.create_task(
            metric_snapshot_loop(runner.database, lambda: runner._shutdown_requested),
            name="metric-snapshot",
        )

        # Start periodic approval timeout expiry (every 60s)
        runner._approval_timeout_task = None
        if runner.pipeline_execution_manager:
            runner._approval_timeout_task = asyncio.create_task(
                expire_approval_timeouts_loop(
                    runner.pipeline_execution_manager,
                    lambda: runner._shutdown_requested,
                ),
                name="approval-timeout-expiry",
            )

        # Resume interrupted pipelines and fail non-resumable stale executions
        if (
            runner.pipeline_executor
            and runner.pipeline_execution_manager
            and runner.workflow_loader
        ):
            try:
                from gobby.mcp_proxy.tools.workflows._pipeline_execution import (
                    resume_interrupted_pipelines,
                )

                resumed_ids = await resume_interrupted_pipelines(
                    loader=runner.workflow_loader,
                    executor=runner.pipeline_executor,
                    execution_manager=runner.pipeline_execution_manager,
                    project_id=runner.project_id,
                )
                if resumed_ids:
                    logger.info(
                        f"Resumed {len(resumed_ids)} pipeline(s) after restart: {resumed_ids}"
                    )

                stale_count = runner.pipeline_execution_manager.fail_stale_running_executions(
                    exclude_ids=set(resumed_ids),
                )
                if stale_count > 0:
                    logger.info(f"Failed {stale_count} non-resumable stale pipeline executions")

                # Wake subscribers of interrupted (non-resumed) pipelines
                if stale_count > 0 and runner.completion_registry:
                    try:
                        from gobby.workflows.pipeline_state import ExecutionStatus as _ES

                        interrupted = runner.pipeline_execution_manager.list_executions(
                            status=_ES.INTERRUPTED,
                        )
                        for exe in interrupted:
                            subs = runner.pipeline_execution_manager.get_completion_subscribers(
                                exe.id
                            )
                            if subs:
                                runner.completion_registry.register(exe.id, subscribers=subs)
                                await runner.completion_registry.notify(
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
                                runner.pipeline_execution_manager.remove_completion_subscribers(
                                    exe.id
                                )
                                runner.completion_registry.cleanup(exe.id)
                        logger.info(
                            f"Notified subscribers of {len(interrupted)} interrupted pipeline(s)",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to wake subscribers of interrupted pipelines: {e}")
            except Exception as e:
                logger.warning(f"Pipeline recovery after restart failed: {e}")

        # Start WebSocket server
        websocket_task = None
        if runner.websocket_server:
            websocket_task = asyncio.create_task(runner.websocket_server.start())

        # Auto-start UI dev server if configured
        if runner.config.ui.enabled and runner.config.ui.mode == "dev":
            from gobby.cli.utils import find_web_dir, spawn_ui_server

            web_dir = find_web_dir(runner.config)
            if web_dir:
                ui_log = Path(runner.config.telemetry.log_file).expanduser().parent / "ui.log"
                # Inherit bind_host so the Vite dev server is reachable
                # over the network (e.g. Tailscale) when bind_host != localhost
                ui_host = runner.config.ui.host
                if runner.config.bind_host != "localhost" and ui_host == "localhost":
                    ui_host = runner.config.bind_host
                ui_pid = spawn_ui_server(
                    ui_host,
                    runner.config.ui.port,
                    web_dir,
                    ui_log,
                    daemon_port=runner.config.daemon_port,
                    ws_port=runner.config.websocket.port if runner.config.websocket else 60888,
                )
                if ui_pid:
                    logger.info(
                        f"UI dev server started (PID: {ui_pid}) "
                        f"at http://{ui_host}:{runner.config.ui.port}"
                    )
                else:
                    logger.warning("Failed to start UI dev server")
            else:
                logger.warning("UI dev mode enabled but web/ directory not found")

        # Start HTTP server
        graceful_shutdown_timeout = 15
        config = uvicorn.Config(
            runner.http_server.app,
            host=runner.config.bind_host,
            port=runner.http_server.port,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=graceful_shutdown_timeout,
        )
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())

        # Wait for shutdown
        while not runner._shutdown_requested:
            await asyncio.sleep(0.5)

        # Cleanup with timeouts to prevent hanging
        # Use timeout slightly longer than uvicorn's graceful shutdown to let it finish
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=graceful_shutdown_timeout + 5)
        except TimeoutError:
            logger.warning("HTTP server shutdown timed out")

        try:
            await asyncio.wait_for(runner.lifecycle_manager.stop(), timeout=2.0)
        except TimeoutError:
            logger.warning("Lifecycle manager shutdown timed out")

        if runner.agent_lifecycle_monitor:
            try:
                await asyncio.wait_for(runner.agent_lifecycle_monitor.stop(), timeout=2.0)
            except TimeoutError:
                logger.warning("Agent lifecycle monitor shutdown timed out")

        if runner.conductor_manager:
            try:
                from gobby.conductor.manager import ConductorManager

                if isinstance(runner.conductor_manager, ConductorManager):
                    await asyncio.wait_for(runner.conductor_manager.shutdown(), timeout=5.0)
            except TimeoutError:
                logger.warning("Conductor shutdown timed out")
            except Exception as e:
                logger.debug(f"Conductor shutdown error: {e}")

        if runner.cron_scheduler:
            try:
                await asyncio.wait_for(runner.cron_scheduler.stop(), timeout=2.0)
            except TimeoutError:
                logger.warning("Cron scheduler shutdown timed out")

        if runner.message_processor:
            try:
                await asyncio.wait_for(runner.message_processor.stop(), timeout=2.0)
            except TimeoutError:
                logger.warning("Message processor shutdown timed out")

        if runner.communications_manager:
            try:
                await asyncio.wait_for(runner.communications_manager.stop(), timeout=5.0)
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
        if runner._metrics_cleanup_task and not runner._metrics_cleanup_task.done():
            runner._metrics_cleanup_task.cancel()
            try:
                await asyncio.wait_for(runner._metrics_cleanup_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass

        # Cancel metrics archive task
        if runner._metrics_archive_task and not runner._metrics_archive_task.done():
            runner._metrics_archive_task.cancel()
            try:
                await asyncio.wait_for(runner._metrics_archive_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass

        # Cancel span cleanup task
        if runner._span_cleanup_task and not runner._span_cleanup_task.done():
            runner._span_cleanup_task.cancel()
            try:
                await asyncio.wait_for(runner._span_cleanup_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass

        # Cancel metric snapshot task
        if runner._metric_snapshot_task and not runner._metric_snapshot_task.done():
            runner._metric_snapshot_task.cancel()
            try:
                await asyncio.wait_for(runner._metric_snapshot_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass

        # Cancel code index maintenance task
        if hasattr(runner, "_code_index_shutdown") and runner._code_index_shutdown:
            runner._code_index_shutdown.set()
        if (
            hasattr(runner, "_code_index_task")
            and runner._code_index_task
            and not runner._code_index_task.done()
        ):
            runner._code_index_task.cancel()
            try:
                await asyncio.wait_for(runner._code_index_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass

        # Cancel zombie message cleanup task
        if runner._zombie_messages_task and not runner._zombie_messages_task.done():
            runner._zombie_messages_task.cancel()
            try:
                await asyncio.wait_for(runner._zombie_messages_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass

        # Cancel vector store rebuild task
        if runner._vector_rebuild_task and not runner._vector_rebuild_task.done():
            runner._vector_rebuild_task.cancel()
            try:
                await asyncio.wait_for(runner._vector_rebuild_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass

        # Stop UI dev server if we started it
        if runner.config.ui.enabled and runner.config.ui.mode == "dev":
            from gobby.cli.utils import stop_ui_server

            stop_ui_server(quiet=True)

        # Close VectorStore connection
        if runner.vector_store:
            try:
                await asyncio.wait_for(runner.vector_store.close(), timeout=5.0)
            except TimeoutError:
                logger.warning("VectorStore close timed out")
            except Exception as e:
                logger.warning(f"VectorStore close failed: {e}")

        # NOTE: Shutdown JSONL exports removed to avoid git noise (#10198).
        # The pre-commit hook exports and stages JSONL files at commit time.

        try:
            await asyncio.wait_for(runner.mcp_proxy.disconnect_all(), timeout=3.0)
        except TimeoutError:
            logger.warning("MCP disconnect timed out")

        # Clean up PID file on graceful shutdown
        cleanup_pid_file()

        logger.info("Shutdown complete")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        cleanup_pid_file()
        sys.exit(1)
