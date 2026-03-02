"""Tests for workflows/shell_actions.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_context() -> MagicMock:
    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.state.variables = {"name": "test"}
    ctx.session_id = "sess-1"
    ctx.event_data = None
    ctx.session_manager = MagicMock()
    ctx.session_manager.get.return_value = None
    ctx.db = None
    ctx.template_engine = MagicMock()
    ctx.template_engine.render.side_effect = lambda cmd, _ctx: cmd
    return ctx


@pytest.mark.asyncio
async def test_shell_run_no_command(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    result = await handle_shell_run(mock_context)
    assert result is not None
    assert "error" in result
    assert "Missing 'command'" in result["error"]


@pytest.mark.asyncio
async def test_shell_run_foreground_capture(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"hello\n", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=mock_proc):
        result = await handle_shell_run(mock_context, command="echo hello")

    assert result is not None
    assert result["stdout"] == "hello"
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_shell_run_foreground_no_capture(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    mock_proc = MagicMock()
    mock_proc.wait = AsyncMock()
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=mock_proc):
        result = await handle_shell_run(mock_context, command="echo hi", capture_output=False)

    assert result is not None
    assert result["stdout"] == ""
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_shell_run_background(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    mock_proc = MagicMock()
    mock_proc.pid = 12345

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=mock_proc):
        result = await handle_shell_run(mock_context, command="sleep 100", background=True)

    assert result is not None
    assert result["status"] == "started"
    assert result["pid"] == 12345


@pytest.mark.asyncio
async def test_shell_run_template_render_error(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    mock_context.template_engine.render.side_effect = Exception("bad template")
    result = await handle_shell_run(mock_context, command="{{ bad }}")

    assert result is not None
    assert "error" in result
    assert "Template rendering failed" in result["error"]


@pytest.mark.asyncio
async def test_shell_run_execution_error(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, side_effect=OSError("fail")):
        result = await handle_shell_run(mock_context, command="bad_cmd")

    assert result is not None
    assert "error" in result
    assert result["exit_code"] == 1


@pytest.mark.asyncio
async def test_shell_run_with_event_data(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    mock_context.event_data = {"type": "pre-tool-use"}

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=mock_proc):
        result = await handle_shell_run(mock_context, command="echo test")

    assert result["stdout"] == "ok"


@pytest.mark.asyncio
async def test_shell_run_with_session_and_project(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    session = MagicMock()
    session.project_id = "proj-1"
    mock_context.session_manager.get.return_value = session
    mock_context.db = MagicMock()

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_proc.returncode = 0

    with (
        patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=mock_proc),
        patch("gobby.storage.projects.LocalProjectManager") as MockPM,
    ):
        MockPM.return_value.get.return_value = MagicMock()
        result = await handle_shell_run(mock_context, command="echo test")

    assert result["stdout"] == "ok"


@pytest.mark.asyncio
async def test_shell_run_project_fetch_error(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    session = MagicMock()
    session.project_id = "proj-1"
    mock_context.session_manager.get.return_value = session
    mock_context.db = MagicMock()

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
    mock_proc.returncode = 0

    with (
        patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=mock_proc),
        patch("gobby.storage.projects.LocalProjectManager", side_effect=Exception("err")),
    ):
        result = await handle_shell_run(mock_context, command="echo test")

    assert result["stdout"] == "ok"


@pytest.mark.asyncio
async def test_shell_run_none_returncode(mock_context: MagicMock) -> None:
    from gobby.workflows.shell_actions import handle_shell_run

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.returncode = None

    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=mock_proc):
        result = await handle_shell_run(mock_context, command="echo")

    assert result["exit_code"] == 0
