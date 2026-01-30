"""Shared fixtures and helpers for server tests."""

from typing import Any
from unittest.mock import MagicMock

from gobby.app_context import ServiceContainer
from gobby.servers.http import HTTPServer

# Sentinel to distinguish "not provided" from "explicitly None"
_NOT_PROVIDED = object()


def create_http_server(
    port: int = 60887,
    test_mode: bool = True,
    mcp_manager: Any | None = None,
    config: Any | None = None,
    session_manager: Any = _NOT_PROVIDED,
    task_manager: Any = _NOT_PROVIDED,
    task_sync_manager: Any | None = None,
    message_processor: Any | None = None,
    message_manager: Any | None = None,
    memory_manager: Any | None = None,
    llm_service: Any | None = None,
    memory_sync_manager: Any | None = None,
    task_validator: Any | None = None,
    metrics_manager: Any | None = None,
    agent_runner: Any | None = None,
    worktree_storage: Any | None = None,
    clone_storage: Any | None = None,
    git_manager: Any | None = None,
    project_id: str | None = None,
    websocket_server: Any | None = None,
    codex_client: Any | None = None,
    database: Any | None = None,
) -> HTTPServer:
    """
    Create an HTTPServer instance with the new ServiceContainer API.

    This helper bridges the old-style kwargs to the new ServiceContainer API,
    making it easier to update tests incrementally.
    """
    # Use provided database or get from session_manager
    db = database
    if db is None and session_manager is not None and hasattr(session_manager, "db"):
        db = session_manager.db
    if db is None:
        db = MagicMock()

    # Use MagicMock only if not provided; if explicitly None, use None
    sess_mgr = MagicMock() if session_manager is _NOT_PROVIDED else session_manager
    task_mgr = MagicMock() if task_manager is _NOT_PROVIDED else task_manager

    services = ServiceContainer(
        config=config,
        database=db,
        session_manager=sess_mgr,
        task_manager=task_mgr,
        task_sync_manager=task_sync_manager,
        memory_sync_manager=memory_sync_manager,
        memory_manager=memory_manager,
        llm_service=llm_service,
        mcp_manager=mcp_manager,
        mcp_db_manager=None,
        metrics_manager=metrics_manager,
        agent_runner=agent_runner,
        message_processor=message_processor,
        message_manager=message_manager,
        task_validator=task_validator,
        worktree_storage=worktree_storage,
        clone_storage=clone_storage,
        git_manager=git_manager,
        project_id=project_id,
        websocket_server=websocket_server,
    )

    return HTTPServer(
        services=services,
        port=port,
        test_mode=test_mode,
        codex_client=codex_client,
    )
