from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.task_github import create_github_sync_registry
from gobby.sync.github import GitHubNotFoundError, GitHubRateLimitError


@pytest.mark.asyncio
async def test_import_github_issues_success():
    # Mock dependencies
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    # Mock project context
    mock_project_manager.get.return_value = AsyncMock(github_repo="owner/repo")

    # Create registry
    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )
    print(f"DEBUG: Registry dir: {dir(registry)}")
    print(f"DEBUG: Registry type: {type(registry)}")

    # Mock internal service call
    with patch("gobby.mcp_proxy.tools.task_github.GitHubSyncService") as MockService:
        mock_service_instance = MockService.return_value
        mock_service_instance.import_github_issues = AsyncMock(
            return_value=[{"id": "task_1", "title": "Issue 1"}]
        )

        # Call tool
        result = await registry.call(
            "import_github_issues", {"repo": "owner/repo", "labels": "bug"}
        )

        assert result["success"] is True
        assert len(result["tasks"]) == 1
        assert result["count"] == 1
        mock_service_instance.import_github_issues.assert_called_once_with(
            repo="owner/repo", labels=["bug"], state="open"
        )


@pytest.mark.asyncio
async def test_sync_task_to_github_success():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_github.GitHubSyncService") as MockService:
        mock_service_instance = MockService.return_value
        mock_service_instance.sync_task_to_github = AsyncMock(return_value={"state": "open"})

        result = await registry.call("sync_task_to_github", {"task_id": "task_123"})

        assert result["success"] is True
        assert result["task_id"] == "task_123"


@pytest.mark.asyncio
async def test_create_pr_for_task_success():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_github.GitHubSyncService") as MockService:
        mock_service_instance = MockService.return_value
        mock_service_instance.create_pr_for_task = AsyncMock(
            return_value={"number": 42, "html_url": "http://github.com/pr/42"}
        )

        result = await registry.call(
            "create_pr_for_task", {"task_id": "task_123", "head_branch": "feature-branch"}
        )

        assert result["success"] is True
        assert result["pr_number"] == 42
        assert result["pr_url"] == "http://github.com/pr/42"


@pytest.mark.asyncio
async def test_link_github_repo():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = AsyncMock()

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    result = await registry.call("link_github_repo", {"repo": "owner/new-repo"})

    assert result["success"] is True
    assert result["github_repo"] == "owner/new-repo"
    mock_project_manager.update.assert_called_with("proj_123", github_repo="owner/new-repo")


@pytest.mark.asyncio
async def test_get_github_status():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    # Mock db fetchone
    mock_task_manager.db.fetchone.return_value = {"count": 5}

    # Mock project
    mock_project = MagicMock()
    mock_project.github_repo = "owner/repo"
    mock_project_manager.get.return_value = mock_project

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.integrations.github.GitHubIntegration") as MockIntegration:
        mock_integration = MockIntegration.return_value
        mock_integration.is_available.return_value = True

        result = await registry.call("get_github_status", {})
        assert result["linked_tasks_count"] == 5


@pytest.mark.asyncio
async def test_unlink_github_repo():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    result = await registry.call("unlink_github_repo", {})

    assert result["success"] is True
    mock_project_manager.update.assert_called_with("proj_123", github_repo=None)


@pytest.mark.asyncio
async def test_import_github_issues_errors():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_github.GitHubSyncService") as MockService:
        mock_service_instance = MockService.return_value

        # Test Rate Limit Error
        mock_service_instance.import_github_issues.side_effect = GitHubRateLimitError(
            "Rate limited", reset_at=12345
        )
        result = await registry.call("import_github_issues", {"repo": "owner/repo"})
        assert result["success"] is False
        assert result["error_type"] == "rate_limit"
        assert result["reset_at"] == 12345

        # Test Not Found Error
        mock_service_instance.import_github_issues.side_effect = GitHubNotFoundError(
            "Repo not found", resource="repo"
        )
        result = await registry.call("import_github_issues", {"repo": "owner/repo"})
        assert result["error_type"] == "not_found"
        assert result["resource"] == "repo"


@pytest.mark.asyncio
async def test_sync_task_to_github_errors():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_github.GitHubSyncService") as MockService:
        mock_service_instance = MockService.return_value

        # Test Rate Limit Error
        mock_service_instance.sync_task_to_github.side_effect = GitHubRateLimitError(
            "Rate limited", reset_at=12345
        )
        result = await registry.call("sync_task_to_github", {"task_id": "task_123"})
        assert result["success"] is False
        assert result["error_type"] == "rate_limit"


@pytest.mark.asyncio
async def test_create_pr_for_task_errors():
    mock_task_manager = AsyncMock()
    mock_task_manager.db = MagicMock()
    mock_mcp_manager = AsyncMock()
    mock_project_manager = MagicMock()

    registry = create_github_sync_registry(
        task_manager=mock_task_manager,
        mcp_manager=mock_mcp_manager,
        project_manager=mock_project_manager,
        project_id="proj_123",
    )

    with patch("gobby.mcp_proxy.tools.task_github.GitHubSyncService") as MockService:
        mock_service_instance = MockService.return_value

        # Test Rate Limit Error
        mock_service_instance.create_pr_for_task.side_effect = GitHubRateLimitError(
            "Rate limited", reset_at=12345
        )
        result = await registry.call(
            "create_pr_for_task", {"task_id": "task_123", "head_branch": "feature"}
        )
        assert result["success"] is False
        assert result["error_type"] == "rate_limit"
