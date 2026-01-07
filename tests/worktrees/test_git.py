"""Tests for git worktree operations manager."""

import subprocess
from unittest.mock import patch

import pytest

from gobby.worktrees.git import (
    GitOperationResult,
    WorktreeGitManager,
    WorktreeInfo,
    WorktreeStatus,
)


class TestWorktreeInfo:
    """Tests for WorktreeInfo dataclass."""

    def test_create_minimal(self):
        """WorktreeInfo can be created with required fields."""
        info = WorktreeInfo(
            path="/path/to/worktree",
            branch="feature/test",
            commit="abc1234",
        )

        assert info.path == "/path/to/worktree"
        assert info.branch == "feature/test"
        assert info.commit == "abc1234"
        assert info.is_bare is False
        assert info.is_detached is False
        assert info.locked is False
        assert info.prunable is False

    def test_create_with_all_fields(self):
        """WorktreeInfo can be created with all fields."""
        info = WorktreeInfo(
            path="/path/to/worktree",
            branch=None,
            commit="abc1234",
            is_bare=True,
            is_detached=True,
            locked=True,
            prunable=True,
        )

        assert info.is_bare is True
        assert info.is_detached is True
        assert info.locked is True
        assert info.prunable is True


class TestWorktreeStatus:
    """Tests for WorktreeStatus dataclass."""

    def test_create(self):
        """WorktreeStatus can be created with all fields."""
        status = WorktreeStatus(
            has_uncommitted_changes=True,
            has_staged_changes=True,
            has_untracked_files=True,
            ahead=5,
            behind=2,
            branch="feature/test",
            commit="abc1234",
        )

        assert status.has_uncommitted_changes is True
        assert status.has_staged_changes is True
        assert status.has_untracked_files is True
        assert status.ahead == 5
        assert status.behind == 2
        assert status.branch == "feature/test"
        assert status.commit == "abc1234"

    def test_clean_status(self):
        """WorktreeStatus can represent clean working tree."""
        status = WorktreeStatus(
            has_uncommitted_changes=False,
            has_staged_changes=False,
            has_untracked_files=False,
            ahead=0,
            behind=0,
            branch="main",
            commit="def5678",
        )

        assert status.has_uncommitted_changes is False
        assert status.has_staged_changes is False
        assert status.has_untracked_files is False


class TestGitOperationResult:
    """Tests for GitOperationResult dataclass."""

    def test_success_result(self):
        """GitOperationResult can represent success."""
        result = GitOperationResult(
            success=True,
            message="Operation completed",
            output="some output",
        )

        assert result.success is True
        assert result.message == "Operation completed"
        assert result.output == "some output"
        assert result.error is None

    def test_failure_result(self):
        """GitOperationResult can represent failure."""
        result = GitOperationResult(
            success=False,
            message="Operation failed",
            error="error details",
        )

        assert result.success is False
        assert result.message == "Operation failed"
        assert result.output is None
        assert result.error == "error details"


class TestWorktreeGitManagerInit:
    """Tests for WorktreeGitManager initialization."""

    def test_init_with_valid_path(self, tmp_path):
        """Manager initializes with valid path."""
        manager = WorktreeGitManager(tmp_path)

        assert manager.repo_path == tmp_path

    def test_init_with_string_path(self, tmp_path):
        """Manager accepts string path."""
        manager = WorktreeGitManager(str(tmp_path))

        assert manager.repo_path == tmp_path

    def test_init_invalid_path_raises(self):
        """Manager raises ValueError for non-existent path."""
        with pytest.raises(ValueError, match="does not exist"):
            WorktreeGitManager("/nonexistent/path")


class TestWorktreeGitManagerRunGit:
    """Tests for WorktreeGitManager._run_git method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    @patch("subprocess.run")
    def test_run_git_success(self, mock_run, manager):
        """_run_git returns CompletedProcess on success."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="On branch main",
            stderr="",
        )

        result = manager._run_git(["status"])

        assert result.returncode == 0
        assert result.stdout == "On branch main"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_git_uses_repo_path(self, mock_run, manager):
        """_run_git uses repo_path as default cwd."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="",
            stderr="",
        )

        manager._run_git(["status"])

        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["cwd"] == manager.repo_path

    @patch("subprocess.run")
    def test_run_git_custom_cwd(self, mock_run, manager, tmp_path):
        """_run_git accepts custom cwd."""
        custom_path = tmp_path / "custom"
        custom_path.mkdir()
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="",
            stderr="",
        )

        manager._run_git(["status"], cwd=custom_path)

        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["cwd"] == custom_path

    @patch("subprocess.run")
    def test_run_git_timeout(self, mock_run, manager):
        """_run_git raises on timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)

        with pytest.raises(subprocess.TimeoutExpired):
            manager._run_git(["status"])


class TestWorktreeGitManagerCreateWorktree:
    """Tests for WorktreeGitManager.create_worktree method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    def test_create_fails_if_path_exists(self, manager, tmp_path):
        """Create fails if worktree path already exists."""
        existing_path = tmp_path / "existing"
        existing_path.mkdir()

        result = manager.create_worktree(existing_path, "feature/test")

        assert result.success is False
        assert "already exists" in result.message

    @patch("subprocess.run")
    def test_create_with_new_branch(self, mock_run, manager, tmp_path):
        """Create worktree with new branch."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "add"],
            returncode=0,
            stdout="Preparing worktree",
            stderr="",
        )

        result = manager.create_worktree(
            worktree_path, "feature/test", base_branch="main", create_branch=True
        )

        assert result.success is True
        assert "Created worktree" in result.message

    @patch("subprocess.run")
    def test_create_with_existing_branch(self, mock_run, manager, tmp_path):
        """Create worktree with existing branch."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "add"],
            returncode=0,
            stdout="Preparing worktree",
            stderr="",
        )

        result = manager.create_worktree(worktree_path, "feature/test", create_branch=False)

        assert result.success is True

    @patch("subprocess.run")
    def test_create_handles_git_failure(self, mock_run, manager, tmp_path):
        """Create handles git command failure."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        # First call is fetch (succeeds), second call is worktree add (fails)
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "fetch"],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["git", "worktree", "add"],
                returncode=128,
                stdout="",
                stderr="fatal: branch already exists",
            ),
        ]

        result = manager.create_worktree(worktree_path, "feature/test")

        assert result.success is False
        assert "Failed to create" in result.message

    @patch("subprocess.run")
    def test_create_handles_timeout(self, mock_run, manager, tmp_path):
        """Create handles git timeout."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=60)

        result = manager.create_worktree(worktree_path, "feature/test")

        assert result.success is False
        assert "timed out" in result.message


class TestWorktreeGitManagerDeleteWorktree:
    """Tests for WorktreeGitManager.delete_worktree method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    @patch("subprocess.run")
    def test_delete_success(self, mock_run, manager, tmp_path):
        """Delete worktree successfully."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "remove"],
            returncode=0,
            stdout="",
            stderr="",
        )

        result = manager.delete_worktree(worktree_path)

        assert result.success is True
        assert "Deleted worktree" in result.message

    @patch("subprocess.run")
    def test_delete_with_force(self, mock_run, manager, tmp_path):
        """Delete worktree with force option."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "remove", "--force"],
            returncode=0,
            stdout="",
            stderr="",
        )

        result = manager.delete_worktree(worktree_path, force=True)

        assert result.success is True
        # Check that --force was passed
        call_args = mock_run.call_args[0][0]
        assert "--force" in call_args

    @patch("subprocess.run")
    def test_delete_with_branch_deletion(self, mock_run, manager, tmp_path):
        """Delete worktree and associated branch."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        worktree_path.mkdir(parents=True)

        # Mock sequence: status check, worktree remove, branch delete
        mock_run.side_effect = [
            # branch --show-current
            subprocess.CompletedProcess(
                args=["git", "branch"], returncode=0, stdout="feature/test\n", stderr=""
            ),
            # rev-parse --short HEAD
            subprocess.CompletedProcess(
                args=["git", "rev-parse"], returncode=0, stdout="abc1234\n", stderr=""
            ),
            # status --porcelain
            subprocess.CompletedProcess(args=["git", "status"], returncode=0, stdout="", stderr=""),
            # rev-list (ahead/behind)
            subprocess.CompletedProcess(
                args=["git", "rev-list"], returncode=0, stdout="0\t0\n", stderr=""
            ),
            # worktree remove
            subprocess.CompletedProcess(
                args=["git", "worktree", "remove"], returncode=0, stdout="", stderr=""
            ),
            # branch -d
            subprocess.CompletedProcess(
                args=["git", "branch", "-d"], returncode=0, stdout="", stderr=""
            ),
        ]

        result = manager.delete_worktree(worktree_path, delete_branch=True)

        assert result.success is True
        assert "branch" in result.message

    @patch("subprocess.run")
    def test_delete_handles_failure(self, mock_run, manager, tmp_path):
        """Delete handles git failure."""
        worktree_path = tmp_path / "worktrees" / "feature-test"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "remove"],
            returncode=128,
            stdout="",
            stderr="error: cannot remove: dirty",
        )

        result = manager.delete_worktree(worktree_path)

        assert result.success is False
        assert "Failed to remove" in result.message


class TestWorktreeGitManagerSyncFromMain:
    """Tests for WorktreeGitManager.sync_from_main method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    def test_sync_fails_if_path_not_exists(self, manager, tmp_path):
        """Sync fails if worktree path doesn't exist."""
        worktree_path = tmp_path / "nonexistent"

        result = manager.sync_from_main(worktree_path)

        assert result.success is False
        assert "does not exist" in result.message

    @patch("subprocess.run")
    def test_sync_with_rebase(self, mock_run, manager, tmp_path):
        """Sync with rebase strategy."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        mock_run.side_effect = [
            # fetch
            subprocess.CompletedProcess(args=["git", "fetch"], returncode=0, stdout="", stderr=""),
            # rebase
            subprocess.CompletedProcess(args=["git", "rebase"], returncode=0, stdout="", stderr=""),
        ]

        result = manager.sync_from_main(worktree_path, strategy="rebase")

        assert result.success is True
        assert "rebase" in result.message

    @patch("subprocess.run")
    def test_sync_with_merge(self, mock_run, manager, tmp_path):
        """Sync with merge strategy."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        mock_run.side_effect = [
            # fetch
            subprocess.CompletedProcess(args=["git", "fetch"], returncode=0, stdout="", stderr=""),
            # merge
            subprocess.CompletedProcess(args=["git", "merge"], returncode=0, stdout="", stderr=""),
        ]

        result = manager.sync_from_main(worktree_path, strategy="merge")

        assert result.success is True
        assert "merge" in result.message

    @patch("subprocess.run")
    def test_sync_handles_conflict(self, mock_run, manager, tmp_path):
        """Sync handles merge/rebase conflicts."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        mock_run.side_effect = [
            # fetch
            subprocess.CompletedProcess(args=["git", "fetch"], returncode=0, stdout="", stderr=""),
            # rebase with conflict
            subprocess.CompletedProcess(
                args=["git", "rebase"],
                returncode=1,
                stdout="CONFLICT (content): ...",
                stderr="",
            ),
        ]

        result = manager.sync_from_main(worktree_path)

        assert result.success is False
        assert "conflicts" in result.message.lower()

    @patch("subprocess.run")
    def test_sync_handles_fetch_failure(self, mock_run, manager, tmp_path):
        """Sync handles fetch failure."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "fetch"],
            returncode=128,
            stdout="",
            stderr="fatal: could not fetch",
        )

        result = manager.sync_from_main(worktree_path)

        assert result.success is False
        assert "Failed to fetch" in result.message


class TestWorktreeGitManagerGetStatus:
    """Tests for WorktreeGitManager.get_worktree_status method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    def test_get_status_nonexistent_path(self, manager, tmp_path):
        """Get status returns None for non-existent path."""
        result = manager.get_worktree_status(tmp_path / "nonexistent")

        assert result is None

    @patch("subprocess.run")
    def test_get_status_clean(self, mock_run, manager, tmp_path):
        """Get status for clean worktree."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        mock_run.side_effect = [
            # branch --show-current
            subprocess.CompletedProcess(
                args=["git", "branch"], returncode=0, stdout="main\n", stderr=""
            ),
            # rev-parse --short HEAD
            subprocess.CompletedProcess(
                args=["git", "rev-parse"], returncode=0, stdout="abc1234\n", stderr=""
            ),
            # status --porcelain
            subprocess.CompletedProcess(args=["git", "status"], returncode=0, stdout="", stderr=""),
            # rev-list (ahead/behind)
            subprocess.CompletedProcess(
                args=["git", "rev-list"], returncode=0, stdout="0\t0\n", stderr=""
            ),
        ]

        status = manager.get_worktree_status(worktree_path)

        assert status is not None
        assert status.branch == "main"
        assert status.commit == "abc1234"
        assert status.has_uncommitted_changes is False
        assert status.has_staged_changes is False
        assert status.has_untracked_files is False
        assert status.ahead == 0
        assert status.behind == 0

    @patch("subprocess.run")
    def test_get_status_with_changes(self, mock_run, manager, tmp_path):
        """Get status for worktree with changes."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        mock_run.side_effect = [
            # branch --show-current
            subprocess.CompletedProcess(
                args=["git", "branch"], returncode=0, stdout="feature/test\n", stderr=""
            ),
            # rev-parse --short HEAD
            subprocess.CompletedProcess(
                args=["git", "rev-parse"], returncode=0, stdout="def5678\n", stderr=""
            ),
            # status --porcelain (staged, modified, untracked)
            subprocess.CompletedProcess(
                args=["git", "status"],
                returncode=0,
                stdout="M  staged.py\n M modified.py\n?? untracked.py\n",
                stderr="",
            ),
            # rev-list (ahead/behind)
            subprocess.CompletedProcess(
                args=["git", "rev-list"], returncode=0, stdout="2\t3\n", stderr=""
            ),
        ]

        status = manager.get_worktree_status(worktree_path)

        assert status is not None
        assert status.has_staged_changes is True
        assert status.has_uncommitted_changes is True
        assert status.has_untracked_files is True
        assert status.behind == 2
        assert status.ahead == 3

    @patch("subprocess.run")
    def test_get_status_handles_exception(self, mock_run, manager, tmp_path):
        """Get status handles exception gracefully."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        mock_run.side_effect = Exception("Git error")

        status = manager.get_worktree_status(worktree_path)

        assert status is None


class TestWorktreeGitManagerListWorktrees:
    """Tests for WorktreeGitManager.list_worktrees method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    @patch("subprocess.run")
    def test_list_empty(self, mock_run, manager):
        """List returns empty list when no worktrees."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "list"],
            returncode=0,
            stdout="",
            stderr="",
        )

        worktrees = manager.list_worktrees()

        assert worktrees == []

    @patch("subprocess.run")
    def test_list_single_worktree(self, mock_run, manager):
        """List returns single worktree."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "list"],
            returncode=0,
            stdout="worktree /path/to/repo\nHEAD abc1234567890\nbranch refs/heads/main\n\n",
            stderr="",
        )

        worktrees = manager.list_worktrees()

        assert len(worktrees) == 1
        assert worktrees[0].path == "/path/to/repo"
        assert worktrees[0].commit == "abc1234567890"
        assert worktrees[0].branch == "main"

    @patch("subprocess.run")
    def test_list_multiple_worktrees(self, mock_run, manager):
        """List returns multiple worktrees."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "list"],
            returncode=0,
            stdout=(
                "worktree /path/to/repo\n"
                "HEAD abc1234567890\n"
                "branch refs/heads/main\n"
                "\n"
                "worktree /path/to/worktree1\n"
                "HEAD def5678901234\n"
                "branch refs/heads/feature/one\n"
                "\n"
            ),
            stderr="",
        )

        worktrees = manager.list_worktrees()

        assert len(worktrees) == 2
        assert worktrees[0].branch == "main"
        assert worktrees[1].branch == "feature/one"

    @patch("subprocess.run")
    def test_list_with_flags(self, mock_run, manager):
        """List parses locked/prunable/detached flags."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "list"],
            returncode=0,
            stdout=(
                "worktree /path/to/worktree\n"
                "HEAD abc1234567890\n"
                "detached\n"
                "locked\n"
                "prunable\n"
                "\n"
            ),
            stderr="",
        )

        worktrees = manager.list_worktrees()

        assert len(worktrees) == 1
        assert worktrees[0].is_detached is True
        assert worktrees[0].locked is True
        assert worktrees[0].prunable is True
        assert worktrees[0].branch is None

    @patch("subprocess.run")
    def test_list_handles_failure(self, mock_run, manager):
        """List returns empty list on git failure."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "list"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )

        worktrees = manager.list_worktrees()

        assert worktrees == []


class TestWorktreeGitManagerPrune:
    """Tests for WorktreeGitManager.prune_worktrees method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    @patch("subprocess.run")
    def test_prune_success(self, mock_run, manager):
        """Prune succeeds."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "prune"],
            returncode=0,
            stdout="",
            stderr="",
        )

        result = manager.prune_worktrees()

        assert result.success is True
        assert "Pruned" in result.message

    @patch("subprocess.run")
    def test_prune_failure(self, mock_run, manager):
        """Prune handles failure."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "prune"],
            returncode=1,
            stdout="",
            stderr="error: pruning failed",
        )

        result = manager.prune_worktrees()

        assert result.success is False
        assert "Failed to prune" in result.message


class TestWorktreeGitManagerLock:
    """Tests for WorktreeGitManager.lock_worktree method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    @patch("subprocess.run")
    def test_lock_success(self, mock_run, manager, tmp_path):
        """Lock worktree successfully."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "lock"],
            returncode=0,
            stdout="",
            stderr="",
        )

        result = manager.lock_worktree(worktree_path)

        assert result.success is True
        assert "Locked" in result.message

    @patch("subprocess.run")
    def test_lock_with_reason(self, mock_run, manager, tmp_path):
        """Lock worktree with reason."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "lock"],
            returncode=0,
            stdout="",
            stderr="",
        )

        result = manager.lock_worktree(worktree_path, reason="Important work")

        assert result.success is True
        # Check that --reason was passed
        call_args = mock_run.call_args[0][0]
        assert "--reason" in call_args
        assert "Important work" in call_args

    @patch("subprocess.run")
    def test_lock_failure(self, mock_run, manager, tmp_path):
        """Lock handles failure."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "lock"],
            returncode=128,
            stdout="",
            stderr="error: already locked",
        )

        result = manager.lock_worktree(worktree_path)

        assert result.success is False
        assert "Failed to lock" in result.message


class TestWorktreeGitManagerUnlock:
    """Tests for WorktreeGitManager.unlock_worktree method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create manager with temp directory."""
        return WorktreeGitManager(tmp_path)

    @patch("subprocess.run")
    def test_unlock_success(self, mock_run, manager, tmp_path):
        """Unlock worktree successfully."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "unlock"],
            returncode=0,
            stdout="",
            stderr="",
        )

        result = manager.unlock_worktree(worktree_path)

        assert result.success is True
        assert "Unlocked" in result.message

    @patch("subprocess.run")
    def test_unlock_failure(self, mock_run, manager, tmp_path):
        """Unlock handles failure."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "worktree", "unlock"],
            returncode=128,
            stdout="",
            stderr="error: not locked",
        )

        result = manager.unlock_worktree(worktree_path)

        assert result.success is False
        assert "Failed to unlock" in result.message
