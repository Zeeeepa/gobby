"""Tests for GitHubSyncService class.

Tests verify the sync service correctly orchestrates between gobby tasks
and GitHub via the official GitHub MCP server.

TDD Red Phase: Tests should fail initially since GitHubSyncService class does not exist.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.sync.github import GitHubSyncService


@pytest.fixture
def mock_mcp_manager():
    """Create a mock MCPClientManager."""
    manager = MagicMock()
    manager.has_server = MagicMock(return_value=True)
    manager.health = {"github": MagicMock(state="connected")}
    manager.call_tool = AsyncMock()
    return manager


@pytest.fixture
def mock_task_manager():
    """Create a mock LocalTaskManager."""
    manager = MagicMock()
    manager.create_task = MagicMock()
    manager.update_task = MagicMock()
    manager.get_task = MagicMock()
    manager.list_tasks = MagicMock(return_value=[])
    return manager


@pytest.fixture
def sync_service(mock_mcp_manager, mock_task_manager):
    """Create a GitHubSyncService with mock dependencies."""
    return GitHubSyncService(
        mcp_manager=mock_mcp_manager,
        task_manager=mock_task_manager,
        project_id="test-project-id",
    )


class TestGitHubSyncServiceInit:
    """Test GitHubSyncService initialization."""

    def test_init_with_dependencies(self, mock_mcp_manager, mock_task_manager):
        """GitHubSyncService initializes with mcp_manager and task_manager."""
        service = GitHubSyncService(
            mcp_manager=mock_mcp_manager,
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        assert service.mcp_manager is mock_mcp_manager
        assert service.task_manager is mock_task_manager
        assert service.project_id == "test-project"

    def test_init_creates_github_integration(self, mock_mcp_manager, mock_task_manager):
        """GitHubSyncService creates GitHubIntegration for availability checks."""
        service = GitHubSyncService(
            mcp_manager=mock_mcp_manager,
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        assert hasattr(service, "github")
        # Should be a GitHubIntegration instance
        from gobby.integrations.github import GitHubIntegration

        assert isinstance(service.github, GitHubIntegration)

    def test_init_default_repo_is_none(self, mock_mcp_manager, mock_task_manager):
        """Default github_repo is None if not specified."""
        service = GitHubSyncService(
            mcp_manager=mock_mcp_manager,
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        assert service.github_repo is None

    def test_init_with_github_repo(self, mock_mcp_manager, mock_task_manager):
        """GitHubSyncService accepts github_repo parameter."""
        service = GitHubSyncService(
            mcp_manager=mock_mcp_manager,
            task_manager=mock_task_manager,
            project_id="test-project",
            github_repo="owner/repo",
        )
        assert service.github_repo == "owner/repo"


class TestGitHubSyncServiceAvailability:
    """Test availability checking."""

    def test_requires_github_available(self, mock_mcp_manager, mock_task_manager):
        """Operations should check GitHub availability first."""
        mock_mcp_manager.has_server.return_value = False

        service = GitHubSyncService(
            mcp_manager=mock_mcp_manager,
            task_manager=mock_task_manager,
            project_id="test-project",
        )

        assert service.github.is_available() is False

    def test_is_available_proxies_to_integration(
        self, mock_mcp_manager, mock_task_manager
    ):
        """is_available() delegates to GitHubIntegration."""
        service = GitHubSyncService(
            mcp_manager=mock_mcp_manager,
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        assert service.is_available() == service.github.is_available()


class TestGitHubSyncServiceImport:
    """Test import_github_issues method."""

    @pytest.mark.asyncio
    async def test_import_issues_calls_github_mcp(self, sync_service, mock_mcp_manager):
        """import_github_issues calls GitHub MCP list_issues tool."""
        mock_mcp_manager.call_tool.return_value = {"issues": []}

        await sync_service.import_github_issues(repo="owner/repo")

        mock_mcp_manager.call_tool.assert_called()
        # Verify GitHub MCP was called
        calls = mock_mcp_manager.call_tool.call_args_list
        assert any("github" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_import_issues_creates_tasks(
        self, sync_service, mock_mcp_manager, mock_task_manager
    ):
        """import_github_issues creates gobby tasks from GitHub issues."""
        mock_mcp_manager.call_tool.return_value = {
            "issues": [
                {"number": 1, "title": "Issue 1", "body": "Description 1"},
                {"number": 2, "title": "Issue 2", "body": "Description 2"},
            ]
        }

        await sync_service.import_github_issues(repo="owner/repo")

        # Should create tasks for each issue
        assert mock_task_manager.create_task.call_count >= 2

    @pytest.mark.asyncio
    async def test_import_issues_links_github_fields(
        self, sync_service, mock_mcp_manager, mock_task_manager
    ):
        """import_github_issues sets github_issue_number and github_repo on tasks."""
        mock_mcp_manager.call_tool.return_value = {
            "issues": [{"number": 42, "title": "Test Issue", "body": "Test body"}]
        }

        await sync_service.import_github_issues(repo="owner/repo")

        # Verify task created with GitHub fields
        create_call = mock_task_manager.create_task.call_args
        assert create_call is not None
        kwargs = create_call.kwargs if create_call.kwargs else {}
        args_dict = dict(zip(["project_id", "title"], create_call.args)) if create_call.args else {}
        all_args = {**args_dict, **kwargs}

        assert all_args.get("github_issue_number") == 42 or "github_issue_number" in str(create_call)

    @pytest.mark.asyncio
    async def test_import_issues_raises_when_unavailable(
        self, mock_mcp_manager, mock_task_manager
    ):
        """import_github_issues raises RuntimeError when GitHub unavailable."""
        mock_mcp_manager.has_server.return_value = False

        service = GitHubSyncService(
            mcp_manager=mock_mcp_manager,
            task_manager=mock_task_manager,
            project_id="test-project",
        )

        with pytest.raises(RuntimeError, match="GitHub"):
            await service.import_github_issues(repo="owner/repo")


class TestGitHubSyncServiceSync:
    """Test sync_task_to_github method."""

    @pytest.mark.asyncio
    async def test_sync_task_calls_github_mcp(self, sync_service, mock_mcp_manager):
        """sync_task_to_github calls GitHub MCP to update issue."""
        mock_task = MagicMock()
        mock_task.github_issue_number = 42
        mock_task.github_repo = "owner/repo"
        mock_task.title = "Updated Title"
        mock_task.description = "Updated description"

        sync_service.task_manager.get_task.return_value = mock_task
        mock_mcp_manager.call_tool.return_value = {"success": True}

        await sync_service.sync_task_to_github(task_id="test-task-id")

        mock_mcp_manager.call_tool.assert_called()

    @pytest.mark.asyncio
    async def test_sync_task_raises_when_no_issue_number(
        self, sync_service, mock_task_manager
    ):
        """sync_task_to_github raises ValueError when task has no github_issue_number."""
        mock_task = MagicMock()
        mock_task.github_issue_number = None

        mock_task_manager.get_task.return_value = mock_task

        with pytest.raises(ValueError, match="issue"):
            await sync_service.sync_task_to_github(task_id="test-task-id")


class TestGitHubSyncServicePR:
    """Test create_pr_for_task method."""

    @pytest.mark.asyncio
    async def test_create_pr_calls_github_mcp(self, sync_service, mock_mcp_manager):
        """create_pr_for_task calls GitHub MCP create_pull_request."""
        mock_task = MagicMock()
        mock_task.title = "Feature: Add new thing"
        mock_task.description = "Adds a cool feature"
        mock_task.github_repo = "owner/repo"
        mock_task.id = "test-task-id"

        sync_service.task_manager.get_task.return_value = mock_task
        mock_mcp_manager.call_tool.return_value = {"number": 123, "url": "https://github.com/owner/repo/pull/123"}

        result = await sync_service.create_pr_for_task(
            task_id="test-task-id",
            head_branch="feature/new-thing",
            base_branch="main",
        )

        mock_mcp_manager.call_tool.assert_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_pr_updates_task_pr_number(
        self, sync_service, mock_mcp_manager, mock_task_manager
    ):
        """create_pr_for_task updates task with github_pr_number."""
        mock_task = MagicMock()
        mock_task.title = "Feature"
        mock_task.description = "Description"
        mock_task.github_repo = "owner/repo"
        mock_task.id = "test-task-id"

        mock_task_manager.get_task.return_value = mock_task
        mock_mcp_manager.call_tool.return_value = {"number": 456}

        await sync_service.create_pr_for_task(
            task_id="test-task-id",
            head_branch="feature/thing",
            base_branch="main",
        )

        # Should update task with PR number
        mock_task_manager.update_task.assert_called()
        update_call = mock_task_manager.update_task.call_args
        assert update_call is not None


class TestLabelMapping:
    """Test label mapping functions."""

    def test_map_gobby_labels_to_github_basic(self, sync_service):
        """map_gobby_labels_to_github converts internal labels to GitHub format."""
        gobby_labels = ["bug", "high-priority", "backend"]
        github_labels = sync_service.map_gobby_labels_to_github(gobby_labels)

        assert isinstance(github_labels, list)
        assert len(github_labels) == 3

    def test_map_gobby_labels_to_github_empty(self, sync_service):
        """map_gobby_labels_to_github handles empty labels."""
        github_labels = sync_service.map_gobby_labels_to_github([])
        assert github_labels == []

    def test_map_gobby_labels_to_github_with_prefix(self, sync_service):
        """map_gobby_labels_to_github can add prefix to labels."""
        gobby_labels = ["bug"]
        github_labels = sync_service.map_gobby_labels_to_github(
            gobby_labels, prefix="gobby:"
        )
        assert "gobby:bug" in github_labels

    def test_map_github_labels_to_gobby_basic(self, sync_service):
        """map_github_labels_to_gobby parses GitHub labels to internal format."""
        github_labels = ["bug", "enhancement", "documentation"]
        gobby_labels = sync_service.map_github_labels_to_gobby(github_labels)

        assert isinstance(gobby_labels, list)
        assert len(gobby_labels) == 3

    def test_map_github_labels_to_gobby_empty(self, sync_service):
        """map_github_labels_to_gobby handles empty labels."""
        gobby_labels = sync_service.map_github_labels_to_gobby([])
        assert gobby_labels == []

    def test_map_github_labels_to_gobby_strips_prefix(self, sync_service):
        """map_github_labels_to_gobby strips gobby: prefix."""
        github_labels = ["gobby:bug", "gobby:feature"]
        gobby_labels = sync_service.map_github_labels_to_gobby(
            github_labels, strip_prefix="gobby:"
        )
        assert "bug" in gobby_labels
        assert "feature" in gobby_labels

    def test_map_labels_special_characters(self, sync_service):
        """Label mapping handles special characters in label names."""
        gobby_labels = ["feature/new-ui", "p0:critical"]
        github_labels = sync_service.map_gobby_labels_to_github(gobby_labels)

        # Should preserve special characters
        assert len(github_labels) == 2
