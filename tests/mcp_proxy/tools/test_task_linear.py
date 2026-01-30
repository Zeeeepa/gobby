from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.task_linear import create_linear_sync_registry
from gobby.sync.linear import LinearNotFoundError, LinearRateLimitError

pytestmark = pytest.mark.unit

@pytest.mark.asyncio
async def test_import_linear_issues_success():
    # Mock dependencies
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_linear.LinearSyncService") as MockService:
        mock_service_instance = MockService.return_value
        mock_service_instance.import_linear_issues = AsyncMock(
            return_value=[{"id": "task_1", "title": "Linear Issue 1"}]
        )

        result = await registry.call("import_linear_issues", {"team_id": "team_1"})

        assert result["success"] is True
        assert len(result["tasks"]) == 1
        mock_service_instance.import_linear_issues.assert_called_once_with(
            team_id="team_1", state=None, labels=None
        )


@pytest.mark.asyncio
async def test_sync_task_to_linear_success():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_linear.LinearSyncService") as MockService:
        mock_service_instance = MockService.return_value
        mock_service_instance.sync_task_to_linear = AsyncMock(return_value={"status": "synced"})

        result = await registry.call("sync_task_to_linear", {"task_id": "task_123"})

        assert result["success"] is True
        assert result["linear_result"]["status"] == "synced"


@pytest.mark.asyncio
async def test_create_linear_issue_for_task_success():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_linear.LinearSyncService") as MockService:
        mock_service_instance = MockService.return_value
        mock_service_instance.create_issue_for_task = AsyncMock(return_value={"id": "lin_123"})

        result = await registry.call(
            "create_linear_issue_for_task", {"task_id": "task_123", "team_id": "team_1"}
        )

        assert result["success"] is True
        assert result["issue_id"] == "lin_123"


@pytest.mark.asyncio
async def test_link_linear_team():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    result = await registry.call("link_linear_team", {"team_id": "team_ABC"})

    assert result["success"] is True
    assert result["linear_team_id"] == "team_ABC"
    mock_project_manager.update.assert_called_with("proj_123", linear_team_id="team_ABC")


@pytest.mark.asyncio
async def test_get_linear_status():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    mock_task_manager.db.fetchone.return_value = {"count": 3}

    # Mock project
    mock_project = MagicMock()
    mock_project.linear_team_id = "team_ABC"
    mock_project_manager.get.return_value = mock_project

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.integrations.linear.LinearIntegration") as MockIntegration:
        mock_integration = MockIntegration.return_value
        mock_integration.is_available.return_value = True

        result = await registry.call("get_linear_status", {})
        assert result["success"] is True
        assert result["linear_team_id"] == "team_ABC"
        assert result["linked_tasks_count"] == 3


@pytest.mark.asyncio
async def test_unlink_linear_team():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    result = await registry.call("unlink_linear_team", {})

    assert result["success"] is True
    mock_project_manager.update.assert_called_with("proj_123", linear_team_id=None)


@pytest.mark.asyncio
async def test_import_linear_issues_errors():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_linear.LinearSyncService") as MockService:
        mock_service_instance = MockService.return_value

        # Test Rate Limit Error
        mock_service_instance.import_linear_issues.side_effect = LinearRateLimitError(
            "Rate limited", reset_at=12345
        )
        result = await registry.call("import_linear_issues", {"team_id": "team_1"})
        assert result["success"] is False
        assert result["error_type"] == "rate_limit"
        assert result["reset_at"] == 12345

        # Test Not Found Error
        mock_service_instance.import_linear_issues.side_effect = LinearNotFoundError(
            "Team not found", resource="team"
        )
        result = await registry.call("import_linear_issues", {"team_id": "team_1"})
        assert result["error_type"] == "not_found"
        assert result["resource"] == "team"


@pytest.mark.asyncio
async def test_sync_task_to_linear_errors():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_linear.LinearSyncService") as MockService:
        mock_service_instance = MockService.return_value

        # Test Rate Limit Error
        mock_service_instance.sync_task_to_linear.side_effect = LinearRateLimitError(
            "Rate limited", reset_at=12345
        )
        result = await registry.call("sync_task_to_linear", {"task_id": "task_123"})
        assert result["success"] is False
        assert result["error_type"] == "rate_limit"


@pytest.mark.asyncio
async def test_create_linear_issue_for_task_errors():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_linear_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_linear.LinearSyncService") as MockService:
        mock_service_instance = MockService.return_value

        # Test Rate Limit Error
        mock_service_instance.create_issue_for_task.side_effect = LinearRateLimitError(
            "Rate limited", reset_at=12345
        )
        result = await registry.call(
            "create_linear_issue_for_task", {"task_id": "task_123", "team_id": "team_1"}
        )
        assert result["success"] is False
        assert result["error_type"] == "rate_limit"
