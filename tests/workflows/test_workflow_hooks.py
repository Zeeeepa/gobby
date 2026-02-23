from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.hooks.events import HookEvent, HookEventType, HookResponse, SessionSource
from gobby.hooks.hook_manager import HookManager
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.hooks import WorkflowHookHandler

pytestmark = pytest.mark.unit

# Mock data
MOCK_SESSION_ID = "session-123"
MOCK_EXTERNAL_ID = "cli-session-abc"


@pytest.fixture
def mock_engine():
    engine = MagicMock(spec=WorkflowEngine)
    engine.handle_event = AsyncMock(return_value=HookResponse(decision="allow"))
    return engine


@pytest.fixture
def workflow_handler(mock_engine):
    # Pass None to force internal handling or just generic loop usage
    return WorkflowHookHandler(engine=mock_engine, loop=None)


def test_handler_delegates_to_evaluate(workflow_handler, mock_engine) -> None:
    """handle() delegates to evaluate() which uses the rule engine.

    Without a rule engine configured, evaluate returns allow.
    """
    event = HookEvent(
        event_type=HookEventType.SESSION_START,
        session_id=MOCK_EXTERNAL_ID,
        source=SessionSource.CLAUDE,
        timestamp=None,  # type: ignore
        data={},
    )

    response = workflow_handler.handle(event)

    assert response.decision == "allow"
    # handle() no longer delegates to engine.handle_event (dead step-based engine)
    mock_engine.handle_event.assert_not_called()


def test_handler_returns_allow_without_rule_engine(workflow_handler, mock_engine) -> None:
    """Without a rule engine, handle() returns allow regardless of engine mock."""
    mock_engine.handle_event.return_value = HookResponse(decision="block", reason="Testing block")

    event = HookEvent(
        event_type=HookEventType.BEFORE_TOOL,
        session_id=MOCK_EXTERNAL_ID,
        source=SessionSource.CLAUDE,
        timestamp=None,  # type: ignore
        data={},
    )

    response = workflow_handler.handle(event)

    # handle() delegates to evaluate() -> _evaluate_rules(), not engine.handle_event
    assert response.decision == "allow"
    mock_engine.handle_event.assert_not_called()


@pytest.mark.skip(reason="Flaky - race condition in health monitor mock setup")
def test_hook_manager_integration():
    # We need to mock dependencies of HookManager to avoid IO
    with (
        patch("gobby.hooks.factory.LocalDatabase"),
        patch("gobby.hooks.factory.LocalSessionManager"),
        patch("gobby.hooks.factory.SessionManager") as MockSessionManagerClass,
        patch("gobby.hooks.factory.SessionTaskManager"),
        patch("gobby.hooks.factory.DaemonClient") as MockDaemonClientClass,
        patch("gobby.hooks.factory.WorkflowLoader"),
        patch("gobby.hooks.factory.WorkflowStateManager"),
        patch("gobby.workflows.engine.WorkflowEngine"),
        patch("gobby.hooks.factory.WorkflowHookHandler") as MockHandlerClass,
    ):
        # Setup mocks
        mock_handler_instance = MockHandlerClass.return_value
        mock_handler_instance.handle.return_value = HookResponse(decision="allow")

        # Setup DaemonClient mock to pass health check
        mock_daemon_instance = MockDaemonClientClass.return_value
        mock_daemon_instance.check_status.return_value = (True, "OK", "healthy", None)
        # Also need check_connection to return True if it exists/is used
        mock_daemon_instance.check_connection.return_value = True

        # Setup SessionManager mock
        mock_session_manager_instance = MockSessionManagerClass.return_value
        mock_session_manager_instance.get_session_id.return_value = MOCK_SESSION_ID

        # Initialize manager
        manager = HookManager(log_file="/tmp/gobby-test.log")

        # Force ready state to bypass async health check loop race conditions
        manager._cached_daemon_is_ready = True
        manager._cached_daemon_status = "healthy"

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id=MOCK_EXTERNAL_ID,
            source=SessionSource.CLAUDE,
            timestamp=None,  # type: ignore
            data={},
            metadata={"_platform_session_id": MOCK_SESSION_ID},
        )

        # Call handle
        response = manager.handle(event)

        # Verify workflow handler was called
        mock_handler_instance.handle.assert_called_once()
        assert response.decision == "allow"


@pytest.mark.skip(reason="Flaky - race condition in health monitor mock setup")
def test_hook_manager_blocks_on_workflow():
    with (
        patch("gobby.hooks.factory.LocalDatabase"),
        patch("gobby.hooks.factory.LocalSessionManager"),
        patch("gobby.hooks.factory.SessionManager") as MockSessionManagerClass,
        patch("gobby.hooks.factory.SessionTaskManager"),
        patch("gobby.hooks.factory.DaemonClient") as MockDaemonClientClass,
        patch("gobby.hooks.factory.WorkflowLoader"),
        patch("gobby.hooks.factory.WorkflowStateManager"),
        patch("gobby.workflows.engine.WorkflowEngine"),
        patch("gobby.hooks.factory.WorkflowHookHandler") as MockHandlerClass,
    ):
        mock_handler_instance = MockHandlerClass.return_value
        mock_handler_instance.handle.return_value = HookResponse(
            decision="block", reason="Workflow denied"
        )

        # Setup DaemonClient mock to pass health check
        mock_daemon_instance = MockDaemonClientClass.return_value
        mock_daemon_instance.check_status.return_value = (True, "OK", "healthy", None)
        mock_daemon_instance.check_connection.return_value = True

        # Setup SessionManager mock
        mock_session_manager_instance = MockSessionManagerClass.return_value
        mock_session_manager_instance.get_session_id.return_value = MOCK_SESSION_ID

        manager = HookManager(log_file="/tmp/gobby-test.log")

        # Force ready state
        manager._cached_daemon_is_ready = True
        manager._cached_daemon_status = "healthy"

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id=MOCK_EXTERNAL_ID,
            source=SessionSource.CLAUDE,
            timestamp=None,  # type: ignore
            data={},
            metadata={"_platform_session_id": MOCK_SESSION_ID},
        )

        response = manager.handle(event)

        assert response.decision == "block"
        assert response.reason == "Workflow denied"


class TestWorkflowHookHandlerDisabled:
    """Tests for the workflow.enabled config flag."""

    def test_handle_disabled_returns_allow_without_engine_call(self, mock_engine) -> None:
        """When enabled=False, handle() returns allow without calling engine."""
        handler = WorkflowHookHandler(engine=mock_engine, loop=None, enabled=False)

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id=MOCK_EXTERNAL_ID,
            source=SessionSource.CLAUDE,
            timestamp=None,  # type: ignore
            data={},
        )

        response = handler.handle(event)

        assert response.decision == "allow"
        mock_engine.handle_event.assert_not_called()

    def test_evaluate_disabled_returns_allow(self, mock_engine) -> None:
        """When enabled=False, evaluate() returns allow without calling rule engine."""
        handler = WorkflowHookHandler(engine=mock_engine, loop=None, enabled=False)

        event = HookEvent(
            event_type=HookEventType.SESSION_START,
            session_id=MOCK_EXTERNAL_ID,
            source=SessionSource.CLAUDE,
            timestamp=None,  # type: ignore
            data={},
        )

        response = handler.evaluate(event)

        assert response.decision == "allow"

    def test_enabled_by_default(self, mock_engine) -> None:
        """WorkflowHookHandler is enabled by default."""
        handler = WorkflowHookHandler(engine=mock_engine, loop=None)

        # Check that internal flag is True
        assert handler._enabled is True

    def test_enabled_true_evaluates_rules(self, mock_engine) -> None:
        """When enabled=True (explicit), handle() evaluates rules (not step engine)."""
        handler = WorkflowHookHandler(engine=mock_engine, loop=None, enabled=True)

        event = HookEvent(
            event_type=HookEventType.BEFORE_TOOL,
            session_id=MOCK_EXTERNAL_ID,
            source=SessionSource.CLAUDE,
            timestamp=None,  # type: ignore
            data={},
        )

        response = handler.handle(event)

        assert response.decision == "allow"
        # handle() delegates to evaluate(), not engine.handle_event
        mock_engine.handle_event.assert_not_called()
