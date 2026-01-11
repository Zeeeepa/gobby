from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource
from gobby.hooks.hook_manager import HookManager
from gobby.storage.tasks import Task


@pytest.fixture
def mock_hook_manager():
    # Mock dependencies
    with (
        patch("gobby.hooks.hook_manager.LocalDatabase"),
        patch("gobby.hooks.hook_manager.LocalSessionManager") as MockSessionManager,
        patch("gobby.hooks.hook_manager.SessionTaskManager") as MockSessionTaskManager,
        patch("gobby.hooks.hook_manager.DaemonClient"),
    ):
        manager = HookManager(log_file="/tmp/test_hook_manager.log")
        manager._session_manager = MockSessionManager.return_value
        manager._session_task_manager = MockSessionTaskManager.return_value

        # Mock cached daemon status via HealthMonitor
        manager._health_monitor.get_cached_status = MagicMock(
            return_value=(True, None, "running", None)
        )

        # Mock _session_storage to return None for get() to avoid pre-created session path
        if manager._event_handlers._session_storage:
            manager._event_handlers._session_storage.get = MagicMock(return_value=None)

        return manager


def test_hook_event_task_id(mock_hook_manager):
    """Test that task_id is populated in HookEvent during handling."""

    # Setup
    external_id = "test-session-123"
    platform_session_id = "session-uuid"
    task_id = "task-123"
    task_title = "Test Task"

    # Mock session lookup
    mock_hook_manager._session_manager.get_session_id.return_value = platform_session_id

    # Mock active task lookup
    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id
    mock_task.title = task_title
    mock_task.status = "in_progress"

    mock_hook_manager._session_task_manager.get_session_tasks.return_value = [
        {"task": mock_task, "action": "worked_on"}
    ]

    # Create event
    event = HookEvent(
        event_type=HookEventType.BEFORE_AGENT,
        session_id=external_id,
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data={"prompt": "Hello"},
    )

    # Execute handler
    # We need to mock the specific handler to avoid side effects
    mock_handler = MagicMock(return_value=HookResponse(decision="allow"))
    with patch.object(mock_hook_manager._event_handlers, "get_handler", return_value=mock_handler):
        mock_hook_manager.handle(event)

    # Verify task_id was populated on the event object
    assert event.task_id == task_id
    assert event.metadata["_task_title"] == task_title
    assert event.metadata["_platform_session_id"] == platform_session_id


def test_session_start_context_injection(mock_hook_manager):
    """Test that task context is injected into SESSION_START context."""

    external_id = "test-session-123"
    platform_session_id = "session-uuid"
    task_id = "task-123"
    task_title = "Important Feature"

    # Mock session lookup
    mock_hook_manager._session_manager.get_session_id.return_value = platform_session_id
    # Mock register_session to return session_id
    mock_hook_manager._session_manager.register_session.return_value = platform_session_id

    # Mock active task
    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id
    mock_task.title = task_title
    mock_task.status = "in_progress"

    mock_hook_manager._session_task_manager.get_session_tasks.return_value = [
        {"task": mock_task, "action": "worked_on"}
    ]

    # Create SESSION_START event
    event = HookEvent(
        event_type=HookEventType.SESSION_START,
        session_id=external_id,
        source=SessionSource.CLAUDE,
        timestamp=datetime.now(UTC),
        data={"cwd": "/tmp"},
        task_id=task_id,
        metadata={"_task_title": task_title},
    )

    # Execute real handler for session start (now on _event_handlers)
    response = mock_hook_manager._event_handlers.handle_session_start(event)

    # Verify context injection
    assert response.metadata["task_id"] == task_id
    assert response.context is not None
    assert f"You are working on task: {task_title}" in response.context
    assert f"({task_id})" in response.context
