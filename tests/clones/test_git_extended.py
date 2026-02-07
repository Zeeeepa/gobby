from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestCloneGitManagerFullClone:
    """Tests for CloneGitManager.full_clone method."""

    @pytest.fixture
    def manager(self, tmp_path: Path):
        """Create manager with temp directory as repo path."""
        from gobby.clones.git import CloneGitManager

        return CloneGitManager(repo_path=tmp_path)

    @pytest.fixture
    def mock_run(self):
        """Mock subprocess.run."""
        with patch("subprocess.run") as mock:
            yield mock

    def test_full_clone_success(self, manager, mock_run, tmp_path: Path) -> None:
        """Full clone creates clone without depth limit."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Cloning into 'clone'...", stderr="")
        clone_path = tmp_path / "test_clone"

        result = manager.full_clone(
            remote_url="https://github.com/user/repo.git",
            clone_path=clone_path,
            branch="main",
        )

        assert result.success is True

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "clone" in cmd
        assert "--depth" not in cmd
        assert "--single-branch" not in cmd


class TestCloneGitManagerCreateClone:
    """Tests for CloneGitManager.create_clone method."""

    @pytest.fixture
    def manager(self, tmp_path: Path):
        """Create manager with temp directory as repo path."""
        from gobby.clones.git import CloneGitManager

        return CloneGitManager(repo_path=tmp_path)

    @pytest.fixture
    def mock_run(self):
        """Mock subprocess.run."""
        with patch("subprocess.run") as mock:
            yield mock

    def test_create_shallow_clone_success(self, manager, mock_run, tmp_path: Path) -> None:
        """Create clone executes shallow clone and returns success."""
        from gobby.clones.git import GitOperationResult

        # Mock get_remote_url
        with patch.object(
            manager, "get_remote_url", return_value="https://github.com/user/repo.git"
        ):
            # Mock shallow_clone
            with patch.object(manager, "shallow_clone") as mock_shallow:
                # Use real object instead of MagicMock
                mock_shallow.return_value = GitOperationResult(
                    success=True, message="Cloned", output="Cloned"
                )

                # Mock _run_git to avoid actual subprocess calls
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

                clone_path = tmp_path / "test_clone"
                result = manager.create_clone(
                    clone_path=clone_path,
                    branch_name="feature-branch",
                    base_branch="main",
                    shallow=True,
                )

                assert result.success is True
                # Should create branch if different
                assert mock_run.call_count >= 1
                cmd = mock_run.call_args[0][0]
                assert "checkout" in cmd
                assert "-b" in cmd
                assert "feature-branch" in cmd

    def test_create_full_clone_success(self, manager, mock_run, tmp_path: Path) -> None:
        """Create clone executes full clone when shallow=False."""
        with patch.object(
            manager, "get_remote_url", return_value="https://github.com/user/repo.git"
        ):
            with patch.object(manager, "full_clone") as mock_full:
                mock_full.return_value = MagicMock(success=True, output="Cloned")

                clone_path = tmp_path / "test_clone"
                result = manager.create_clone(
                    clone_path=clone_path,
                    branch_name="main",  # Same branch, so no checkout -b
                    base_branch="main",
                    shallow=False,
                )

                assert result.success is True
                mock_full.assert_called_once()
                # Should NOT call checkout -b since branches match
                mock_run.assert_not_called()


class TestCloneGitManagerMergeBranch:
    """Tests for CloneGitManager.merge_branch method."""

    @pytest.fixture
    def manager(self, tmp_path: Path):
        """Create manager with temp directory as repo path."""
        from gobby.clones.git import CloneGitManager

        return CloneGitManager(repo_path=tmp_path)

    @pytest.fixture
    def mock_run(self):
        """Mock subprocess.run."""
        with patch("subprocess.run") as mock:
            yield mock

    def test_merge_branch_success(self, manager, mock_run, tmp_path: Path) -> None:
        """Merge branch succeeds when no conflicts."""
        # Sequence: fetch, checkout, pull, merge
        mock_run.side_effect = [
            MagicMock(returncode=0),  # fetch
            MagicMock(returncode=0),  # checkout
            MagicMock(returncode=0),  # pull
            MagicMock(returncode=0, stdout="Merged", stderr=""),  # merge
        ]

        result = manager.merge_branch(
            source_branch="feature", target_branch="main", working_dir=tmp_path
        )

        assert result.success is True
        assert mock_run.call_count == 4

    def test_merge_branch_conflict(self, manager, mock_run, tmp_path: Path) -> None:
        """Merge branch handles conflicts."""
        # Sequence: fetch, checkout, pull, merge (fail), diff, abort
        mock_run.side_effect = [
            MagicMock(returncode=0),  # fetch
            MagicMock(returncode=0),  # checkout
            MagicMock(returncode=0),  # pull
            MagicMock(
                returncode=1, stdout="CONFLICT", stderr="Automatic merge failed"
            ),  # merge fail
            MagicMock(returncode=0, stdout="file.txt\n", stderr=""),  # diff U
            MagicMock(returncode=0),  # merge --abort
        ]

        result = manager.merge_branch(
            source_branch="feature", target_branch="main", working_dir=tmp_path
        )

        assert result.success is False
        assert "conflict" in result.message.lower()
        assert "file.txt" in result.output
