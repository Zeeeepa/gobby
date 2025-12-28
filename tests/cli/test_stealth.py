from unittest.mock import MagicMock, patch

import pytest

from gobby.cli.tasks import get_sync_manager


@pytest.fixture
def mock_stealth_config(tmp_path):
    ctx = {
        "id": "test_project_123",
        "name": "Test Project",
        "project_path": str(tmp_path),
        "tasks_stealth": True,
    }
    return ctx


@pytest.fixture
def mock_normal_config(tmp_path):
    ctx = {
        "id": "test_project_123",
        "name": "Test Project",
        "project_path": str(tmp_path),
        "tasks_stealth": False,
    }
    return ctx


@patch("gobby.cli.tasks.get_project_context")
@patch("gobby.cli.tasks.get_task_manager")
def test_stealth_mode_enabled(mock_tm, mock_ctx, mock_stealth_config, tmp_path):
    mock_ctx.return_value = mock_stealth_config
    mock_tm.return_value = MagicMock()

    # Mock Path.home() to point to a temporary location
    with patch("pathlib.Path.home") as mock_home:
        mock_home.return_value = tmp_path

        # Mock get_sync_manager inside the context where correct config is returned
        manager = get_sync_manager()

        expected_path = tmp_path / ".gobby" / "stealth_tasks" / "test_project_123.jsonl"
        assert manager.export_path == expected_path


@patch("gobby.cli.tasks.get_project_context")
@patch("gobby.cli.tasks.get_task_manager")
def test_stealth_mode_disabled(mock_tm, mock_ctx, mock_normal_config):
    mock_ctx.return_value = mock_normal_config
    mock_tm.return_value = MagicMock()

    manager = get_sync_manager()

    assert str(manager.export_path) == ".gobby/tasks.jsonl"
