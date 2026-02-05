import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_services():
    return {
        "template_engine": TemplateEngine(),  # Use real one for interpolation tests
        "llm_service": AsyncMock(),
        "transcript_processor": MagicMock(),
        "config": MagicMock(),
        "mcp_manager": AsyncMock(),
        "memory_manager": MagicMock(),
    }


@pytest.fixture
def action_executor(temp_db, session_manager, mock_services):
    return ActionExecutor(
        temp_db,
        session_manager,
        mock_services["template_engine"],
        llm_service=mock_services["llm_service"],
        transcript_processor=mock_services["transcript_processor"],
        config=mock_services["config"],
        mcp_manager=mock_services["mcp_manager"],
        memory_manager=mock_services["memory_manager"],
    )


@pytest.fixture
def workflow_state():
    return WorkflowState(
        session_id="test-session-id",
        workflow_name="test-workflow",
        step="test-step",
        variables={"session_name": "test-session"},
    )


@pytest.fixture
def action_context(temp_db, session_manager, workflow_state, mock_services):
    return ActionContext(
        session_id=workflow_state.session_id,
        state=workflow_state,
        db=temp_db,
        session_manager=session_manager,
        template_engine=mock_services["template_engine"],
        mcp_manager=mock_services["mcp_manager"],
        memory_manager=mock_services["memory_manager"],
    )


@pytest.mark.asyncio
async def test_bash_run_basic(action_executor, action_context):
    with patch("asyncio.create_subprocess_shell") as mock_run:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"hello\n", b"")
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = await action_executor.execute("bash", action_context, command="echo hello")

        assert result is not None
        assert result["stdout"] == "hello"
        assert result["exit_code"] == 0
        mock_run.assert_called_once()
        assert "echo hello" in mock_run.call_args[0][0]


@pytest.mark.asyncio
async def test_bash_run_template(action_executor, action_context):
    with patch("asyncio.create_subprocess_shell") as mock_run:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"test-session\n", b"")
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = await action_executor.execute(
            "bash", action_context, command="echo {{ variables.session_name }}"
        )

        assert result is not None
        assert result["stdout"] == "test-session"
        assert result["exit_code"] == 0
        mock_run.assert_called_with(
            "echo test-session",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=None,
        )


@pytest.mark.asyncio
async def test_bash_run_background(action_executor, action_context):
    with patch("asyncio.create_subprocess_shell") as mock_run:
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_run.return_value = mock_proc

        result = await action_executor.execute(
            "bash", action_context, command="sleep 10", background=True
        )

        assert result is not None
        assert result["status"] == "started"
        assert result["pid"] == 12345
        mock_run.assert_called_once()
        # Check that it didn't wait/communicate
        mock_proc.communicate.assert_not_called()


@pytest.mark.asyncio
async def test_bash_run_no_capture(action_executor, action_context):
    with patch("asyncio.create_subprocess_shell") as mock_run:
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = await action_executor.execute(
            "bash", action_context, command="echo hello", capture_output=False
        )

        assert result is not None
        assert result["stdout"] == ""
        assert result["exit_code"] == 0
        mock_run.assert_called_once()
        assert mock_run.call_args[1]["stdout"] == asyncio.subprocess.DEVNULL


@pytest.mark.asyncio
async def test_bash_run_error(action_executor, action_context):
    with patch("asyncio.create_subprocess_shell") as mock_run:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"command not found\n")
        mock_proc.returncode = 127
        mock_run.return_value = mock_proc

        result = await action_executor.execute("bash", action_context, command="nosuchcommand")

        assert result is not None
        assert result["exit_code"] == 127
        assert "command not found" in result["stderr"]


@pytest.mark.asyncio
async def test_bash_run_missing_command(action_executor, action_context):
    result = await action_executor.execute("bash", action_context)
    assert result is not None
    assert "error" in result
    assert "Missing 'command'" in result["error"]


@pytest.mark.asyncio
async def test_bash_run_template_error(action_executor, action_context):
    # Jinja2 error: accessing non-existent variable is fine by default,
    # but invalid syntax is an error.
    result = await action_executor.execute(
        "bash", action_context, command="echo {{ invalid syntax }}"
    )
    assert result is not None
    assert "error" in result
    assert "Template rendering failed" in result["error"]


@pytest.mark.asyncio
async def test_bash_run_with_event_data(action_executor, action_context):
    action_context.event_data = {"foo": "bar"}
    with patch("asyncio.create_subprocess_shell") as mock_run:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"bar\n", b"")
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = await action_executor.execute(
            "bash", action_context, command="echo {{ event.foo }}"
        )

        assert result is not None
        assert result["stdout"] == "bar"
        mock_run.assert_called_with(
            "echo bar",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=None,
        )


@pytest.mark.asyncio
async def test_bash_run_execution_exception(action_executor, action_context):
    with patch("asyncio.create_subprocess_shell", side_effect=OSError("Failed to spawn")):
        result = await action_executor.execute("bash", action_context, command="echo hello")
        assert result is not None
        assert "error" in result
        assert "Failed to spawn" in result["error"]
        assert result["exit_code"] == 1


@pytest.mark.asyncio
async def test_run_alias(action_executor, action_context):
    with patch("asyncio.create_subprocess_shell") as mock_run:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"alias\n", b"")
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = await action_executor.execute("run", action_context, command="echo alias")

        assert result is not None
        assert result["stdout"] == "alias"
        assert result["exit_code"] == 0
        mock_run.assert_called_once()