"""
Tests for session-related actions in gobby.workflows.actions.
"""

import pytest
from unittest.mock import MagicMock, patch
from gobby.workflows.actions import ActionExecutor, ActionContext
from gobby.storage.sessions import LocalSessionManager
from gobby.workflows.definitions import WorkflowState


@pytest.fixture
def mock_context():
    session_manager = MagicMock(spec=LocalSessionManager)
    # Mock session
    session = MagicMock()
    session.source = "claude"
    session.project_path = "/tmp/test"
    session_manager.get.return_value = session

    return ActionContext(
        session_id="sess_123",
        state=WorkflowState(
            session_id="sess_123", workflow_name="test_workflow", phase="test_phase", variables={}
        ),
        db=MagicMock(),
        session_manager=session_manager,
        template_engine=MagicMock(),
    )


@pytest.mark.asyncio
async def test_start_new_session_basic(mock_context):
    executor = ActionExecutor(
        db=MagicMock(), session_manager=mock_context.session_manager, template_engine=MagicMock()
    )

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        result = await executor._handle_start_new_session(
            mock_context, command="claude", args=["-vv"], prompt="Hello world"
        )

        assert result is not None
        assert result["started_new_session"] is True
        assert result["pid"] == 12345

        # Verify Popen called correctly
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args

        # Check command structure
        cmd_list = args[0]
        assert cmd_list[0] == "claude"
        assert "-vv" in cmd_list
        # Check URL encoded prompt injection
        assert "-p" in cmd_list
        assert "Hello world" in cmd_list

        assert kwargs["cwd"] == "/tmp/test"
        assert kwargs["start_new_session"] is True


@pytest.mark.asyncio
async def test_start_new_session_auto_detect_source(mock_context):
    executor = ActionExecutor(
        db=MagicMock(), session_manager=mock_context.session_manager, template_engine=MagicMock()
    )

    # Session source is 'claude' from fixture
    with patch("subprocess.Popen") as mock_popen:
        await executor._handle_start_new_session(mock_context)
        args, _ = mock_popen.call_args
        assert args[0][0] == "claude"

    # Change to gemini
    mock_context.session_manager.get.return_value.source = "gemini"
    with patch("subprocess.Popen") as mock_popen:
        await executor._handle_start_new_session(mock_context)
        args, _ = mock_popen.call_args
        assert args[0][0] == "gemini"


@pytest.mark.asyncio
async def test_start_new_session_explicit_cwd(mock_context):
    executor = ActionExecutor(
        db=MagicMock(), session_manager=mock_context.session_manager, template_engine=MagicMock()
    )

    with patch("subprocess.Popen") as mock_popen:
        await executor._handle_start_new_session(mock_context, cwd="/custom/path")
        _, kwargs = mock_popen.call_args
        assert kwargs["cwd"] == "/custom/path"


@pytest.mark.asyncio
async def test_mark_loop_complete(mock_context):
    executor = ActionExecutor(
        db=MagicMock(), session_manager=mock_context.session_manager, template_engine=MagicMock()
    )

    result = await executor._handle_mark_loop_complete(mock_context)

    assert result["loop_marked_complete"] is True
    assert mock_context.state.variables["stop_reason"] == "completed"
