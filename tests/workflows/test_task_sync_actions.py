"""Tests for workflows/task_sync_actions.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_session() -> MagicMock:
    s = MagicMock()
    s.project_id = "proj-123"
    return s


@pytest.fixture
def mock_session_manager(mock_session: MagicMock) -> MagicMock:
    mgr = MagicMock()
    mgr.get.return_value = mock_session
    return mgr


@pytest.fixture
def mock_task_sync_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.import_from_jsonl = MagicMock()
    mgr.export_to_jsonl = MagicMock()
    return mgr


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.variables = {}
    state.workflow_name = "test-workflow"
    state.task_list = []
    state.current_task_index = None
    return state


# --- task_sync_import ---


@pytest.mark.asyncio
async def test_task_sync_import_success(
    mock_task_sync_manager: MagicMock,
    mock_session_manager: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import task_sync_import

    result = await task_sync_import(mock_task_sync_manager, mock_session_manager, "sess-1")
    assert result == {"imported": True}


@pytest.mark.asyncio
async def test_task_sync_import_no_manager(mock_session_manager: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import task_sync_import

    result = await task_sync_import(None, mock_session_manager, "sess-1")
    assert result == {"error": "Task Sync Manager not available"}


@pytest.mark.asyncio
async def test_task_sync_import_no_session(mock_task_sync_manager: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import task_sync_import

    mgr = MagicMock()
    mgr.get.return_value = None
    result = await task_sync_import(mock_task_sync_manager, mgr, "sess-1")
    assert result == {"imported": True}


@pytest.mark.asyncio
async def test_task_sync_import_error(
    mock_session_manager: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import task_sync_import

    bad_mgr = MagicMock()
    bad_mgr.import_from_jsonl.side_effect = RuntimeError("boom")
    result = await task_sync_import(bad_mgr, mock_session_manager, "sess-1")
    assert "error" in result
    assert "boom" in result["error"]


# --- task_sync_export ---


@pytest.mark.asyncio
async def test_task_sync_export_success(
    mock_task_sync_manager: MagicMock,
    mock_session_manager: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import task_sync_export

    result = await task_sync_export(mock_task_sync_manager, mock_session_manager, "sess-1")
    assert result == {"exported": True}


@pytest.mark.asyncio
async def test_task_sync_export_no_manager(mock_session_manager: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import task_sync_export

    result = await task_sync_export(None, mock_session_manager, "sess-1")
    assert result == {"error": "Task Sync Manager not available"}


@pytest.mark.asyncio
async def test_task_sync_export_error(mock_session_manager: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import task_sync_export

    bad_mgr = MagicMock()
    bad_mgr.export_to_jsonl.side_effect = RuntimeError("fail")
    result = await task_sync_export(bad_mgr, mock_session_manager, "sess-1")
    assert "error" in result


# --- persist_tasks ---


@pytest.mark.asyncio
async def test_persist_tasks_empty_list(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import persist_tasks

    result = await persist_tasks(MagicMock(), mock_session_manager, "sess-1", mock_state)
    assert result["tasks_persisted"] == 0


@pytest.mark.asyncio
async def test_persist_tasks_from_source_variable(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import persist_tasks

    mock_state.variables = {"my_tasks": [{"title": "Task 1"}]}

    with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
        mock_persist.return_value = {"temp-1": "real-1"}
        result = await persist_tasks(
            MagicMock(), mock_session_manager, "sess-1", mock_state, source="my_tasks"
        )
    assert result["tasks_persisted"] == 1


@pytest.mark.asyncio
async def test_persist_tasks_from_source_dict_with_tasks_key(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import persist_tasks

    mock_state.variables = {"plan": {"tasks": [{"title": "T1"}, {"title": "T2"}]}}

    with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
        mock_persist.return_value = {"t1": "r1", "t2": "r2"}
        result = await persist_tasks(
            MagicMock(), mock_session_manager, "sess-1", mock_state, source="plan"
        )
    assert result["tasks_persisted"] == 2


@pytest.mark.asyncio
async def test_persist_tasks_with_explicit_tasks(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import persist_tasks

    with patch("gobby.workflows.task_actions.persist_decomposed_tasks") as mock_persist:
        mock_persist.return_value = {"t1": "r1"}
        result = await persist_tasks(
            MagicMock(),
            mock_session_manager,
            "sess-1",
            mock_state,
            tasks=[{"title": "Explicit"}],
            workflow_name="my-wf",
        )
    assert result["tasks_persisted"] == 1


@pytest.mark.asyncio
async def test_persist_tasks_error(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import persist_tasks

    with patch(
        "gobby.workflows.task_actions.persist_decomposed_tasks", side_effect=RuntimeError("db err")
    ):
        result = await persist_tasks(
            MagicMock(),
            mock_session_manager,
            "sess-1",
            mock_state,
            tasks=[{"title": "T"}],
        )
    assert "error" in result


# --- get_workflow_tasks ---


@pytest.mark.asyncio
async def test_get_workflow_tasks_no_workflow_name(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import get_workflow_tasks

    mock_state.workflow_name = None
    result = await get_workflow_tasks(MagicMock(), mock_session_manager, "sess-1", mock_state)
    assert result == {"error": "No workflow name specified"}


@pytest.mark.asyncio
async def test_get_workflow_tasks_success(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import get_workflow_tasks

    mock_task = MagicMock()
    mock_task.to_dict.return_value = {"id": "t1", "title": "Test", "status": "open"}
    mock_task.id = "t1"
    mock_task.title = "Test"
    mock_task.status = "open"

    with patch("gobby.workflows.task_actions.get_workflow_tasks", return_value=[mock_task]):
        result = await get_workflow_tasks(
            MagicMock(), mock_session_manager, "sess-1", mock_state, output_as="result_var"
        )
    assert result["count"] == 1
    assert mock_state.variables["result_var"] is not None


@pytest.mark.asyncio
async def test_get_workflow_tasks_error(
    mock_session_manager: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.task_sync_actions import get_workflow_tasks

    with patch(
        "gobby.workflows.task_actions.get_workflow_tasks", side_effect=RuntimeError("fail")
    ):
        result = await get_workflow_tasks(MagicMock(), mock_session_manager, "sess-1", mock_state)
    assert "error" in result


# --- update_workflow_task ---


@pytest.mark.asyncio
async def test_update_workflow_task_no_task_id(mock_state: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import update_workflow_task

    mock_state.task_list = None
    mock_state.current_task_index = None
    result = await update_workflow_task(MagicMock(), mock_state)
    assert result == {"error": "No task_id specified"}


@pytest.mark.asyncio
async def test_update_workflow_task_from_index(mock_state: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import update_workflow_task

    mock_state.task_list = [{"id": "task-abc"}]
    mock_state.current_task_index = 0

    mock_task = MagicMock()
    mock_task.to_dict.return_value = {"id": "task-abc", "status": "closed"}

    with patch(
        "gobby.workflows.task_actions.update_task_from_workflow", return_value=mock_task
    ):
        result = await update_workflow_task(MagicMock(), mock_state, status="closed")
    assert result["updated"] is True


@pytest.mark.asyncio
async def test_update_workflow_task_not_found(mock_state: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import update_workflow_task

    with patch("gobby.workflows.task_actions.update_task_from_workflow", return_value=None):
        result = await update_workflow_task(MagicMock(), mock_state, task_id="missing")
    assert result["updated"] is False


@pytest.mark.asyncio
async def test_update_workflow_task_error(mock_state: MagicMock) -> None:
    from gobby.workflows.task_sync_actions import update_workflow_task

    with patch(
        "gobby.workflows.task_actions.update_task_from_workflow",
        side_effect=RuntimeError("db fail"),
    ):
        result = await update_workflow_task(MagicMock(), mock_state, task_id="t1")
    assert result["updated"] is False
    assert "error" in result
    assert "db fail" in result["error"]
