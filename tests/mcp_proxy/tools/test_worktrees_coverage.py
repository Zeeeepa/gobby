from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.tools.worktrees import (
    _copy_project_json_to_worktree,
    _generate_worktree_path,
    _get_worktree_base_dir,
    _install_provider_hooks,
    _resolve_project_context,
    create_worktrees_registry,
)
from gobby.storage.worktrees import Worktree


@pytest.fixture
def mock_worktree_storage():
    return MagicMock()


@pytest.fixture
def mock_git_manager():
    manager = MagicMock()
    manager.repo_path = "/tmp/repo"
    return manager


@pytest.fixture
def mock_agent_runner():
    runner = MagicMock()
    runner._child_session_manager.max_agent_depth = 3
    return runner


@pytest.fixture
def registry(mock_worktree_storage, mock_git_manager, mock_agent_runner):
    return create_worktrees_registry(
        worktree_storage=mock_worktree_storage,
        git_manager=mock_git_manager,
        project_id="proj-1",
        agent_runner=mock_agent_runner,
    )


@pytest.mark.asyncio
async def test_create_worktree_success(registry, mock_worktree_storage, mock_git_manager):
    mock_git_manager.create_worktree.return_value.success = True
    mock_worktree_storage.get_by_branch.return_value = None
    mock_worktree_storage.create.return_value = Worktree(
        id="wt-123",
        project_id="proj-1",
        task_id=None,
        branch_name="feature/test",
        worktree_path="/tmp/wt/feature-test",
        base_branch="main",
        agent_session_id=None,
        status="active",
        created_at="now",
        updated_at="now",
        merged_at=None,
    )
    result = await registry.call(
        "create_worktree", {"branch_name": "feature/test", "worktree_path": "/tmp/wt/feature-test"}
    )
    assert result["success"] is True
    assert result["worktree_path"] == "/tmp/wt/feature-test"
    mock_git_manager.create_worktree.assert_called_once_with(
        worktree_path="/tmp/wt/feature-test",
        branch_name="feature/test",
        base_branch="main",
        create_branch=True,
    )
    mock_worktree_storage.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_worktree_failure(registry, mock_worktree_storage, mock_git_manager):
    mock_git_manager.create_worktree.return_value.success = False
    mock_git_manager.create_worktree.return_value.error = "Git error"
    mock_worktree_storage.get_by_branch.return_value = None
    result = await registry.call(
        "create_worktree",
        {
            "branch_name": "feature/fail",
        },
    )
    assert result["success"] is False
    assert "Git error" in result["error"]
    mock_worktree_storage.create.assert_not_called()


@pytest.mark.asyncio
async def test_create_worktree_existing(registry, mock_worktree_storage):
    existing = Worktree(
        id="wt-123",
        project_id="proj-1",
        branch_name="feature/exists",
        worktree_path="/tmp/exists",
        base_branch="main",
        status="active",
        created_at="2024-01-01",
        updated_at="2024-01-01",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get_by_branch.return_value = existing
    result = await registry.call(
        "create_worktree",
        {
            "branch_name": "feature/exists",
        },
    )
    assert result["success"] is False
    assert "already exists" in result["error"]


@pytest.mark.asyncio
async def test_create_worktree_auto_path(registry, mock_git_manager, mock_worktree_storage):
    mock_git_manager.create_worktree.return_value.success = True
    mock_worktree_storage.get_by_branch.return_value = None
    mock_worktree_storage.create.return_value = Worktree(
        id="wt-auto",
        project_id="proj-1",
        task_id=None,
        branch_name="feature/auto",
        worktree_path="/tmp/gobby-worktrees/feature-auto",
        base_branch="main",
        agent_session_id=None,
        status="active",
        created_at="now",
        updated_at="now",
        merged_at=None,
    )
    with patch(
        "gobby.mcp_proxy.tools.worktrees._get_worktree_base_dir",
        return_value=Path("/tmp/gobby-worktrees"),
    ):
        result = await registry.call(
            "create_worktree",
            {
                "branch_name": "feature/auto",
            },
        )
        assert result["success"] is True
        args, kwargs = mock_git_manager.create_worktree.call_args
        assert "feature-auto" in kwargs["worktree_path"]


@pytest.mark.asyncio
async def test_get_worktree_found(registry, mock_worktree_storage, mock_git_manager):
    wt = Worktree(
        id="wt-123",
        project_id="proj-1",
        branch_name="feat/1",
        worktree_path="/tmp/wt1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_status = MagicMock()
    mock_status.has_uncommitted_changes = True
    mock_status.ahead = 1
    mock_status.behind = 2
    mock_status.branch = "feat/1"
    mock_git_manager.get_worktree_status.return_value = mock_status
    with patch("pathlib.Path.exists", return_value=True):
        result = await registry.call("get_worktree", {"worktree_id": "wt-123"})
        assert result["success"] is True
        assert result["worktree"]["id"] == "wt-123"
        assert result["git_status"]["has_uncommitted_changes"] is True


@pytest.mark.asyncio
async def test_get_worktree_not_found(registry, mock_worktree_storage):
    mock_worktree_storage.get.return_value = None
    result = await registry.call("get_worktree", {"worktree_id": "missing"})
    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_list_worktrees(registry, mock_worktree_storage):
    wt1 = Worktree(
        id="1",
        project_id="p1",
        branch_name="b1",
        worktree_path="p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.list_worktrees.return_value = [wt1]
    result = await registry.call("list_worktrees", {"status": "active"})
    assert result["success"] is True
    assert len(result["worktrees"]) == 1
    mock_worktree_storage.list_worktrees.assert_called_with(
        project_id="proj-1", status="active", agent_session_id=None, limit=50
    )


@pytest.mark.asyncio
async def test_claim_worktree_success(registry, mock_worktree_storage):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        agent_session_id=None,
        task_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_worktree_storage.claim.return_value = True
    result = await registry.call("claim_worktree", {"worktree_id": "wt-1", "session_id": "sess-1"})
    assert result == {}
    mock_worktree_storage.claim.assert_called_with("wt-1", "sess-1")


@pytest.mark.asyncio
async def test_claim_worktree_already_claimed(registry, mock_worktree_storage):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        agent_session_id="other-session",
        task_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    result = await registry.call("claim_worktree", {"worktree_id": "wt-1", "session_id": "sess-1"})
    assert result["success"] is False
    assert "already claimed" in result["error"]


@pytest.mark.asyncio
async def test_release_worktree(registry, mock_worktree_storage):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        agent_session_id="sess-1",
        task_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_worktree_storage.release.return_value = True
    result = await registry.call("release_worktree", {"worktree_id": "wt-1"})
    assert result == {}
    mock_worktree_storage.release.assert_called_with("wt-1")


@pytest.mark.asyncio
async def test_delete_worktree_success(registry, mock_worktree_storage, mock_git_manager):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="/tmp/p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_git_manager.get_worktree_status.return_value.has_uncommitted_changes = False
    mock_git_manager.delete_worktree.return_value.success = True
    mock_worktree_storage.delete.return_value = True
    with patch("pathlib.Path.exists", return_value=True):
        result = await registry.call("delete_worktree", {"worktree_id": "wt-1"})
        assert result == {}
        mock_git_manager.delete_worktree.assert_called_with(
            "/tmp/p1", force=False, delete_branch=True, branch_name="b1"
        )
        mock_worktree_storage.delete.assert_called_with("wt-1")


@pytest.mark.asyncio
async def test_delete_worktree_uncommitted_changes(
    registry, mock_worktree_storage, mock_git_manager
):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="/tmp/p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_git_manager.get_worktree_status.return_value.has_uncommitted_changes = True
    with patch("pathlib.Path.exists", return_value=True):
        result = await registry.call("delete_worktree", {"worktree_id": "wt-1"})
        assert result["success"] is False
        assert "uncommitted changes" in result["error"]

        mock_git_manager.delete_worktree.return_value.success = True
        mock_worktree_storage.delete.return_value = True
        result_force = await registry.call(
            "delete_worktree", {"worktree_id": "wt-1", "force": True}
        )
        assert result_force == {}
        mock_git_manager.delete_worktree.assert_called_with(
            "/tmp/p1", force=True, delete_branch=True, branch_name="b1"
        )


@pytest.mark.asyncio
async def test_sync_worktree(registry, mock_worktree_storage, mock_git_manager):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="/tmp/p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_git_manager.sync_from_main.return_value.success = True
    mock_git_manager.sync_from_main.return_value.message = "Synced"
    result = await registry.call("sync_worktree", {"worktree_id": "wt-1", "strategy": "merge"})
    assert result["success"] is True
    mock_git_manager.sync_from_main.assert_called_with(
        "/tmp/p1", base_branch="main", strategy="merge"
    )


@pytest.mark.asyncio
async def test_detect_stale_worktrees(registry, mock_worktree_storage):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="p1",
        base_branch="main",
        status="active",
        created_at="old",
        updated_at="old",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.find_stale.return_value = [wt]
    result = await registry.call("detect_stale_worktrees", {"hours": 48})
    assert result["success"] is True
    assert result["count"] == 1
    mock_worktree_storage.find_stale.assert_called_with(project_id="proj-1", hours=48, limit=50)


@pytest.mark.asyncio
async def test_cleanup_stale_worktrees(registry, mock_worktree_storage, mock_git_manager):
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="/tmp/p1",
        base_branch="main",
        status="active",
        created_at="old",
        updated_at="old",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.cleanup_stale.return_value = [wt]
    mock_git_manager.delete_worktree.return_value.success = True

    # Dry run
    result = await registry.call("cleanup_stale_worktrees", {"hours": 24, "dry_run": True})
    assert result["success"] is True
    assert result["count"] == 1
    assert result["cleaned"][0]["marked_abandoned"] is False
    mock_worktree_storage.cleanup_stale.assert_called_with(
        project_id="proj-1", hours=24, dry_run=True
    )

    # Actual run with delete_git
    result = await registry.call(
        "cleanup_stale_worktrees", {"hours": 24, "dry_run": False, "delete_git": True}
    )
    assert result["success"] is True
    assert result["cleaned"][0]["marked_abandoned"] is True
    assert result["cleaned"][0]["git_deleted"] is True
    mock_git_manager.delete_worktree.assert_called_with(
        "/tmp/p1", force=True, delete_branch=True, branch_name="b1"
    )


@pytest.mark.asyncio
async def test_spawn_agent_in_worktree(
    registry, mock_worktree_storage, mock_git_manager, mock_agent_runner
):
    """Test spawn_agent_in_worktree delegates to spawn_agent_impl with isolation='worktree'."""
    # Setup mock for spawn_agent_impl (the unified implementation)
    from gobby.agents.isolation import IsolationContext
    from gobby.agents.spawn_executor import SpawnResult

    # Configure mock_agent_runner.can_spawn to return proper tuple
    mock_agent_runner.can_spawn.return_value = (True, None, 1)

    mock_spawn_result = SpawnResult(
        success=True,
        run_id="run-123",
        child_session_id="child-sess-1",
        status="pending",
        pid=123,
        terminal_type="test-term",
        message="Agent spawned in test-term (PID: 123)",
    )

    mock_isolation_ctx = MagicMock(spec=IsolationContext)
    mock_isolation_ctx.cwd = "/tmp/new"
    mock_isolation_ctx.branch_name = "feat/new"
    mock_isolation_ctx.worktree_id = "wt-new"
    mock_isolation_ctx.clone_id = None

    mock_handler = MagicMock()
    mock_handler.prepare_environment = AsyncMock(return_value=mock_isolation_ctx)
    mock_handler.build_context_prompt.return_value = "enhanced prompt"

    with (
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.get_project_context",
            return_value={"id": "proj-1", "project_path": "/tmp/repo"},
        ),
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler",
            return_value=mock_handler,
        ),
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.execute_spawn",
            AsyncMock(return_value=mock_spawn_result),
        ),
    ):
        result = await registry.call(
            "spawn_agent_in_worktree",
            {
                "prompt": "do work",
                "branch_name": "feat/new",
                "parent_session_id": "parent-1",
                "provider": "claude",
            },
        )

        assert result["success"] is True
        assert result["worktree_id"] == "wt-new"
        assert result["pid"] == 123
        assert result["isolation"] == "worktree"


# ========== Helper function tests ==========


class TestGetWorktreeBaseDir:
    """Tests for _get_worktree_base_dir helper."""

    def test_unix_path(self):
        """Test Unix path generation."""
        with patch("gobby.mcp_proxy.tools.worktrees.platform.system", return_value="Darwin"):
            path = _get_worktree_base_dir()
            assert "gobby-worktrees" in str(path)
            # On macOS, /tmp resolves to /private/tmp
            assert path.exists() or str(path).startswith("/")

    def test_windows_path(self, tmp_path):
        """Test Windows path generation uses tempdir."""
        with (
            patch("gobby.mcp_proxy.tools.worktrees.platform.system", return_value="Windows"),
            patch("gobby.mcp_proxy.tools.worktrees.tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            path = _get_worktree_base_dir()
            assert "gobby-worktrees" in str(path)
            assert str(tmp_path) in str(path)


class TestGenerateWorktreePath:
    """Tests for _generate_worktree_path helper."""

    def test_with_project_name(self, tmp_path):
        """Test path generation with project name."""
        with patch(
            "gobby.mcp_proxy.tools.worktrees._get_worktree_base_dir", return_value=tmp_path
        ):
            path = _generate_worktree_path("feature/test", project_name="myproject")
            assert "myproject" in path
            assert "feature-test" in path

    def test_without_project_name(self, tmp_path):
        """Test path generation without project name."""
        with patch(
            "gobby.mcp_proxy.tools.worktrees._get_worktree_base_dir", return_value=tmp_path
        ):
            path = _generate_worktree_path("feature/test")
            # No project subdirectory
            assert path == str(tmp_path / "feature-test")


class TestResolveProjectContext:
    """Tests for _resolve_project_context helper."""

    def test_project_path_not_exists(self):
        """Test with non-existent project path."""
        git_manager, project_id, error = _resolve_project_context(
            project_path="/nonexistent/path",
            default_git_manager=None,
            default_project_id=None,
        )
        assert error is not None
        assert "does not exist" in error
        assert git_manager is None
        assert project_id is None

    def test_project_path_no_gobby(self, tmp_path):
        """Test with path that has no .gobby/project.json."""
        with patch(
            "gobby.mcp_proxy.tools.worktrees.get_project_context", return_value=None
        ):
            git_manager, project_id, error = _resolve_project_context(
                project_path=str(tmp_path),
                default_git_manager=None,
                default_project_id=None,
            )
            assert error is not None
            assert "No .gobby/project.json" in error

    def test_project_path_invalid_git_repo(self, tmp_path):
        """Test with path that's not a valid git repo."""
        with (
            patch(
                "gobby.mcp_proxy.tools.worktrees.get_project_context",
                return_value={"id": "proj-1", "project_path": str(tmp_path)},
            ),
            patch(
                "gobby.mcp_proxy.tools.worktrees.WorktreeGitManager",
                side_effect=ValueError("Not a git repo"),
            ),
        ):
            git_manager, project_id, error = _resolve_project_context(
                project_path=str(tmp_path),
                default_git_manager=None,
                default_project_id=None,
            )
            assert error is not None
            assert "Invalid git repository" in error

    def test_no_project_path_no_defaults(self):
        """Test with no project path and no defaults."""
        git_manager, project_id, error = _resolve_project_context(
            project_path=None,
            default_git_manager=None,
            default_project_id=None,
        )
        assert error is not None
        assert "No project_path provided" in error

    def test_no_project_path_no_project_id(self):
        """Test with no project path and no project ID default."""
        git_manager, project_id, error = _resolve_project_context(
            project_path=None,
            default_git_manager=MagicMock(),
            default_project_id=None,
        )
        assert error is not None
        assert "no default project ID" in error

    def test_with_defaults(self):
        """Test with valid defaults."""
        mock_manager = MagicMock()
        git_manager, project_id, error = _resolve_project_context(
            project_path=None,
            default_git_manager=mock_manager,
            default_project_id="proj-123",
        )
        assert error is None
        assert git_manager is mock_manager
        assert project_id == "proj-123"


class TestCopyProjectJsonToWorktree:
    """Tests for _copy_project_json_to_worktree helper."""

    def test_copies_project_json(self, tmp_path):
        """Test that project.json is copied with parent reference."""
        # Setup source
        repo_path = tmp_path / "repo"
        repo_gobby = repo_path / ".gobby"
        repo_gobby.mkdir(parents=True)
        (repo_gobby / "project.json").write_text('{"id": "proj-1", "name": "test"}')

        # Setup target
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        _copy_project_json_to_worktree(repo_path, worktree_path)

        # Verify copy exists with parent reference
        worktree_project = worktree_path / ".gobby" / "project.json"
        assert worktree_project.exists()
        import json

        data = json.loads(worktree_project.read_text())
        assert data["id"] == "proj-1"
        assert "parent_project_path" in data

    def test_skips_if_no_source(self, tmp_path):
        """Test that nothing happens if source doesn't exist."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        # Should not raise
        _copy_project_json_to_worktree(repo_path, worktree_path)

        assert not (worktree_path / ".gobby" / "project.json").exists()

    def test_skips_if_target_exists(self, tmp_path):
        """Test that existing project.json is not overwritten."""
        # Setup source
        repo_path = tmp_path / "repo"
        repo_gobby = repo_path / ".gobby"
        repo_gobby.mkdir(parents=True)
        (repo_gobby / "project.json").write_text('{"id": "proj-1"}')

        # Setup target with existing file
        worktree_path = tmp_path / "worktree"
        worktree_gobby = worktree_path / ".gobby"
        worktree_gobby.mkdir(parents=True)
        (worktree_gobby / "project.json").write_text('{"id": "existing"}')

        _copy_project_json_to_worktree(repo_path, worktree_path)

        # Verify original is preserved
        import json

        data = json.loads((worktree_gobby / "project.json").read_text())
        assert data["id"] == "existing"


class TestInstallProviderHooks:
    """Tests for _install_provider_hooks helper."""

    def test_none_provider(self, tmp_path):
        """Test with None provider returns False."""
        result = _install_provider_hooks(None, tmp_path)
        assert result is False

    def test_claude_hooks_success(self, tmp_path):
        """Test Claude hooks installation success."""
        with patch("gobby.cli.installers.claude.install_claude") as mock_install:
            mock_install.return_value = {"success": True}
            result = _install_provider_hooks("claude", tmp_path)
            assert result is True
            mock_install.assert_called_once()

    def test_claude_hooks_failure(self, tmp_path, caplog):
        """Test Claude hooks installation failure."""
        with patch("gobby.cli.installers.claude.install_claude") as mock_install:
            mock_install.return_value = {"success": False, "error": "Install failed"}
            result = _install_provider_hooks("claude", tmp_path)
            assert result is False

    def test_gemini_hooks_success(self, tmp_path):
        """Test Gemini hooks installation success."""
        with patch("gobby.cli.installers.gemini.install_gemini") as mock_install:
            mock_install.return_value = {"success": True}
            result = _install_provider_hooks("gemini", tmp_path)
            assert result is True

    def test_gemini_hooks_failure(self, tmp_path):
        """Test Gemini hooks installation failure."""
        with patch("gobby.cli.installers.gemini.install_gemini") as mock_install:
            mock_install.return_value = {"success": False, "error": "Failed"}
            result = _install_provider_hooks("gemini", tmp_path)
            assert result is False

    def test_antigravity_hooks_success(self, tmp_path):
        """Test Antigravity hooks installation success."""
        with patch("gobby.cli.installers.antigravity.install_antigravity") as mock_install:
            mock_install.return_value = {"success": True}
            result = _install_provider_hooks("antigravity", tmp_path)
            assert result is True

    def test_hooks_install_exception(self, tmp_path, caplog):
        """Test hooks installation handles exceptions."""
        with patch("gobby.cli.installers.claude.install_claude") as mock_install:
            mock_install.side_effect = Exception("Import error")
            result = _install_provider_hooks("claude", tmp_path)
            assert result is False


# ========== Additional tool tests for coverage ==========


@pytest.mark.asyncio
async def test_get_worktree_path_not_exists(registry, mock_worktree_storage, mock_git_manager):
    """Test get_worktree when path doesn't exist on disk."""
    wt = Worktree(
        id="wt-123",
        project_id="proj-1",
        branch_name="feat/1",
        worktree_path="/nonexistent/path",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    with patch("pathlib.Path.exists", return_value=False):
        result = await registry.call("get_worktree", {"worktree_id": "wt-123"})
        assert result["success"] is True
        # git_status should be None or missing when path doesn't exist
        assert result.get("git_status") is None or "git_status" not in result


@pytest.mark.asyncio
async def test_claim_worktree_not_found(registry, mock_worktree_storage):
    """Test claim_worktree when worktree not found."""
    mock_worktree_storage.get.return_value = None
    result = await registry.call(
        "claim_worktree", {"worktree_id": "nonexistent", "session_id": "sess-1"}
    )
    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_release_worktree_not_found(registry, mock_worktree_storage):
    """Test release_worktree when worktree not found."""
    mock_worktree_storage.get.return_value = None
    result = await registry.call("release_worktree", {"worktree_id": "nonexistent"})
    # release_worktree returns {"error": "..."} without "success" key on error
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_delete_worktree_not_found(registry, mock_worktree_storage):
    """Test delete_worktree when worktree not found."""
    mock_worktree_storage.get.return_value = None
    result = await registry.call("delete_worktree", {"worktree_id": "nonexistent"})
    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_delete_worktree_path_not_exists(registry, mock_worktree_storage, mock_git_manager):
    """Test delete_worktree when path doesn't exist."""
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="/nonexistent",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_worktree_storage.delete.return_value = True
    # Git delete is still called (git worktree remove handles non-existent paths)
    mock_git_manager.delete_worktree.return_value.success = True
    with patch("pathlib.Path.exists", return_value=False):
        result = await registry.call("delete_worktree", {"worktree_id": "wt-1"})
        # Should succeed - deletes both git worktree and DB record
        assert result == {}
        # Git delete IS called - the path check only controls uncommitted changes check
        mock_git_manager.delete_worktree.assert_called_once()


@pytest.mark.asyncio
async def test_delete_worktree_git_failure(registry, mock_worktree_storage, mock_git_manager):
    """Test delete_worktree when git delete fails."""
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="/tmp/p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_git_manager.get_worktree_status.return_value.has_uncommitted_changes = False
    mock_git_manager.delete_worktree.return_value.success = False
    mock_git_manager.delete_worktree.return_value.error = "Git delete failed"
    with patch("pathlib.Path.exists", return_value=True):
        result = await registry.call("delete_worktree", {"worktree_id": "wt-1"})
        assert result["success"] is False
        assert "Git delete failed" in result["error"]


@pytest.mark.asyncio
async def test_sync_worktree_not_found(registry, mock_worktree_storage):
    """Test sync_worktree when worktree not found."""
    mock_worktree_storage.get.return_value = None
    result = await registry.call("sync_worktree", {"worktree_id": "nonexistent"})
    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_sync_worktree_failure(registry, mock_worktree_storage, mock_git_manager):
    """Test sync_worktree when sync fails."""
    wt = Worktree(
        id="wt-1",
        project_id="p1",
        branch_name="b1",
        worktree_path="/tmp/p1",
        base_branch="main",
        status="active",
        created_at="",
        updated_at="",
        task_id=None,
        agent_session_id=None,
        merged_at=None,
    )
    mock_worktree_storage.get.return_value = wt
    mock_git_manager.sync_from_main.return_value.success = False
    mock_git_manager.sync_from_main.return_value.error = "Sync failed"
    result = await registry.call("sync_worktree", {"worktree_id": "wt-1"})
    assert result["success"] is False
    assert "Sync failed" in result["error"]


@pytest.mark.asyncio
async def test_spawn_agent_depth_exceeded(
    registry, mock_worktree_storage, mock_git_manager, mock_agent_runner
):
    """Test spawn_agent_in_worktree when depth is exceeded."""
    mock_agent_runner.can_spawn.return_value = (False, "Max depth exceeded", 4)

    result = await registry.call(
        "spawn_agent_in_worktree",
        {
            "prompt": "do work",
            "branch_name": "feat/new",
            "parent_session_id": "parent-1",
        },
    )

    assert result["success"] is False
    assert "Max depth exceeded" in result["error"]


@pytest.mark.asyncio
async def test_spawn_agent_create_worktree_fails(
    registry, mock_worktree_storage, mock_git_manager, mock_agent_runner
):
    """Test spawn_agent_in_worktree when worktree creation fails."""
    mock_agent_runner.can_spawn.return_value = (True, None, 1)
    mock_worktree_storage.get_by_branch.return_value = None
    mock_git_manager.create_worktree.return_value.success = False
    mock_git_manager.create_worktree.return_value.error = "Branch already exists"

    with patch(
        "gobby.mcp_proxy.tools.worktrees._generate_worktree_path", return_value="/tmp/wt"
    ):
        result = await registry.call(
            "spawn_agent_in_worktree",
            {
                "prompt": "do work",
                "branch_name": "existing-branch",
                "parent_session_id": "parent-1",
            },
        )

    assert result["success"] is False
    assert "Branch already exists" in result["error"]


@pytest.mark.asyncio
async def test_spawn_agent_in_worktree_deprecation_warning(
    registry, mock_worktree_storage, mock_git_manager, mock_agent_runner, caplog
):
    """Test that spawn_agent_in_worktree logs a deprecation warning."""
    import logging
    import warnings

    from gobby.agents.isolation import IsolationContext
    from gobby.agents.spawn_executor import SpawnResult

    # Setup
    mock_agent_runner.can_spawn.return_value = (True, None, 1)

    mock_spawn_result = SpawnResult(
        success=True,
        run_id="run-123",
        child_session_id="child-sess-1",
        status="pending",
        pid=789,
        terminal_type="test-term",
        message="Agent spawned",
    )

    mock_isolation_ctx = MagicMock(spec=IsolationContext)
    mock_isolation_ctx.cwd = "/tmp/deprecation"
    mock_isolation_ctx.branch_name = "feat/deprecation"
    mock_isolation_ctx.worktree_id = "wt-deprecation"
    mock_isolation_ctx.clone_id = None

    mock_handler = MagicMock()
    mock_handler.prepare_environment = AsyncMock(return_value=mock_isolation_ctx)
    mock_handler.build_context_prompt.return_value = "enhanced prompt"

    with (
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.get_project_context",
            return_value={"id": "proj-1", "project_path": "/tmp/repo"},
        ),
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler",
            return_value=mock_handler,
        ),
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.execute_spawn",
            AsyncMock(return_value=mock_spawn_result),
        ),
        caplog.at_level(logging.WARNING),
        warnings.catch_warnings(record=True) as w,
    ):
        warnings.simplefilter("always")

        result = await registry.call(
            "spawn_agent_in_worktree",
            {
                "prompt": "do work",
                "branch_name": "feat/deprecation",
                "parent_session_id": "parent-1",
                "provider": "claude",
            },
        )

    # Should still succeed (backwards compatibility)
    assert result["success"] is True

    # Should log deprecation warning
    assert any(
        "deprecated" in record.message.lower() and "spawn_agent_in_worktree" in record.message
        for record in caplog.records
    ), f"Expected deprecation warning for spawn_agent_in_worktree, got: {[r.message for r in caplog.records]}"

    # Should emit DeprecationWarning
    deprecation_warnings = [
        warning for warning in w
        if issubclass(warning.category, DeprecationWarning)
        and "spawn_agent_in_worktree" in str(warning.message)
    ]
    assert len(deprecation_warnings) >= 1, (
        f"Expected DeprecationWarning for spawn_agent_in_worktree, got: {[str(x.message) for x in w]}"
    )


@pytest.mark.asyncio
async def test_spawn_agent_default_workflow(
    registry, mock_worktree_storage, mock_git_manager, mock_agent_runner
):
    """Test that spawn_agent_in_worktree defaults to 'worktree-agent' workflow."""
    from gobby.agents.isolation import IsolationContext
    from gobby.agents.spawn_executor import SpawnResult

    # Setup
    mock_agent_runner.can_spawn.return_value = (True, None, 1)

    mock_spawn_result = SpawnResult(
        success=True,
        run_id="run-123",
        child_session_id="child-sess-1",
        status="pending",
        pid=456,
        terminal_type="test-term",
        message="Agent spawned",
    )

    mock_isolation_ctx = MagicMock(spec=IsolationContext)
    mock_isolation_ctx.cwd = "/tmp/default"
    mock_isolation_ctx.branch_name = "feat/default"
    mock_isolation_ctx.worktree_id = "wt-default"
    mock_isolation_ctx.clone_id = None

    mock_handler = MagicMock()
    mock_handler.prepare_environment = AsyncMock(return_value=mock_isolation_ctx)
    mock_handler.build_context_prompt.return_value = "enhanced prompt"

    with (
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.get_project_context",
            return_value={"id": "proj-1", "project_path": "/tmp/repo"},
        ),
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.get_isolation_handler",
            return_value=mock_handler,
        ),
        patch(
            "gobby.mcp_proxy.tools.spawn_agent.execute_spawn",
            AsyncMock(return_value=mock_spawn_result),
        ) as mock_execute_spawn,
    ):
        # Call WITHOUT specifying workflow
        result = await registry.call(
            "spawn_agent_in_worktree",
            {
                "prompt": "do work",
                "branch_name": "feat/default",
                "parent_session_id": "parent-1",
                "provider": "claude",
            },
        )

        assert result["success"] is True

        # Verify execute_spawn was called with workflow='worktree-agent'
        mock_execute_spawn.assert_called_once()
        spawn_request = mock_execute_spawn.call_args[0][0]
        assert spawn_request.workflow == "worktree-agent", (
            f"Expected workflow='worktree-agent', got workflow={spawn_request.workflow!r}"
        )
