"""Tests for task enforcement actions."""

import subprocess
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.enforcement import (
    capture_baseline_dirty_files,
    require_active_task,
    require_commit_before_stop,
    require_task_complete,
    require_task_review_or_close_before_stop,
    validate_session_task_scope,
)
from gobby.workflows.git_utils import get_dirty_files

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_config():
    """Create mock config with task enforcement enabled."""
    config = MagicMock()
    config.workflow.require_task_before_edit = True
    config.workflow.protected_tools = ["Edit", "Write", "Bash"]
    return config


@pytest.fixture
def mock_task_manager():
    """Create mock task manager."""
    return MagicMock()


@pytest.fixture
def workflow_state():
    """Create a workflow state with empty variables."""
    return WorkflowState(
        session_id="test-session",
        workflow_name="test-workflow",
        step="test-step",
        step_entered_at=datetime.now(UTC),
        variables={},
    )


# =============================================================================
# Tests for _get_dirty_files helper
# =============================================================================


class TestGetDirtyFiles:
    """Tests for get_dirty_files helper function."""

    def test_parses_git_status_output(self, monkeypatch) -> None:
        """Parse git status --porcelain output correctly."""
        import gobby.workflows.git_utils as git_utils

        mock_result = MagicMock(
            returncode=0,
            stdout=" M src/file.py\n?? new_file.py\nA  staged.py",
            stderr="",
        )
        monkeypatch.setattr(git_utils.subprocess, "run", lambda *a, **k: mock_result)

        result = get_dirty_files("/test/path")
        assert result == {"src/file.py", "new_file.py", "staged.py"}

    def test_excludes_gobby_directory(self, monkeypatch) -> None:
        """Files in .gobby/ are excluded from dirty files."""
        import gobby.workflows.git_utils as git_utils

        mock_result = MagicMock(
            returncode=0,
            stdout=" M src/file.py\n M .gobby/tasks.jsonl\n?? .gobby/new.json",
            stderr="",
        )
        monkeypatch.setattr(git_utils.subprocess, "run", lambda *a, **k: mock_result)

        result = get_dirty_files("/test/path")

        assert result == {"src/file.py"}
        assert ".gobby/tasks.jsonl" not in result
        assert ".gobby/new.json" not in result

    def test_handles_renames(self, monkeypatch) -> None:
        """Parse rename format correctly (old -> new)."""
        import gobby.workflows.git_utils as git_utils

        mock_result = MagicMock(
            returncode=0,
            stdout="R  old_name.py -> new_name.py",
            stderr="",
        )
        monkeypatch.setattr(git_utils.subprocess, "run", lambda *a, **k: mock_result)

        result = get_dirty_files("/test/path")
        # Should capture the old name (source of rename)
        assert result == {"old_name.py"}

    def test_returns_empty_set_on_no_changes(self, monkeypatch) -> None:
        """Empty output returns empty set."""
        import gobby.workflows.git_utils as git_utils

        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        monkeypatch.setattr(git_utils.subprocess, "run", lambda *a, **k: mock_result)

        result = get_dirty_files("/test/path")
        assert result == set()

    def test_returns_empty_set_on_git_failure(self, monkeypatch) -> None:
        """Git failure returns empty set."""
        import gobby.workflows.git_utils as git_utils

        mock_result = MagicMock(returncode=128, stdout="", stderr="fatal: not a git repository")
        monkeypatch.setattr(git_utils.subprocess, "run", lambda *a, **k: mock_result)

        result = get_dirty_files("/test/path")
        assert result == set()

    def test_returns_empty_set_on_timeout(self, monkeypatch) -> None:
        """Timeout returns empty set."""
        import gobby.workflows.git_utils as git_utils

        def raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=10)

        monkeypatch.setattr(git_utils.subprocess, "run", raise_timeout)

        result = get_dirty_files("/test/path")
        assert result == set()

    def test_returns_empty_set_on_file_not_found(self, monkeypatch) -> None:
        """Git not found returns empty set."""
        import gobby.workflows.git_utils as git_utils

        def raise_fnf(*a, **k):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(git_utils.subprocess, "run", raise_fnf)

        result = get_dirty_files("/test/path")
        assert result == set()

    def test_returns_empty_set_on_generic_error(self, monkeypatch) -> None:
        """Generic error returns empty set."""
        import gobby.workflows.git_utils as git_utils

        def raise_oserror(*a, **k):
            raise OSError("Unexpected error")

        monkeypatch.setattr(git_utils.subprocess, "run", raise_oserror)

        result = get_dirty_files("/test/path")
        assert result == set()


# =============================================================================
# Tests for capture_baseline_dirty_files
# =============================================================================


class TestCaptureBaselineDirtyFiles:
    """Tests for capture_baseline_dirty_files action."""

    async def test_no_workflow_state_returns_none(self):
        """When no workflow_state, return None."""
        result = await capture_baseline_dirty_files(
            workflow_state=None,
            project_path="/test/path",
        )
        assert result is None

    async def test_captures_dirty_files_as_baseline(self, workflow_state):
        """Captures current dirty files and stores in workflow_state."""
        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"src/file1.py", "src/file2.py"}

            result = await capture_baseline_dirty_files(
                workflow_state=workflow_state,
                project_path="/test/path",
            )

        assert result is not None
        assert result["baseline_captured"] is True
        assert result["file_count"] == 2
        assert set(result["files"]) == {"src/file1.py", "src/file2.py"}

        # Check stored in workflow_state (as list, not set)
        baseline = workflow_state.variables["baseline_dirty_files"]
        assert isinstance(baseline, list)
        assert set(baseline) == {"src/file1.py", "src/file2.py"}

    async def test_captures_empty_baseline(self, workflow_state):
        """Captures empty baseline when no dirty files."""
        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = set()

            result = await capture_baseline_dirty_files(
                workflow_state=workflow_state,
                project_path="/test/path",
            )

        assert result is not None
        assert result["baseline_captured"] is True
        assert result["file_count"] == 0
        assert result["files"] == []
        assert workflow_state.variables["baseline_dirty_files"] == []


# =============================================================================
# Tests for require_commit_before_stop
# =============================================================================


class TestRequireCommitBeforeStop:
    """Tests for require_commit_before_stop action."""

    async def test_no_workflow_state_allows(self):
        """When no workflow_state, allow stop."""
        result = await require_commit_before_stop(
            workflow_state=None,
            project_path="/test/path",
            task_manager=MagicMock(),
        )
        assert result is None

    async def test_no_claimed_task_allows(self, workflow_state):
        """When no claimed_task_id, allow stop."""
        result = await require_commit_before_stop(
            workflow_state=workflow_state,
            project_path="/test/path",
            task_manager=MagicMock(),
        )
        assert result is None

    async def test_task_no_longer_in_progress_clears_state(self, workflow_state, mock_task_manager):
        """When task status changed, clear workflow state and allow."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["task_claimed"] = True

        # Task exists but is now closed
        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task

        result = await require_commit_before_stop(
            workflow_state=workflow_state,
            project_path="/test/path",
            task_manager=mock_task_manager,
        )

        assert result is None
        # State should be cleared
        assert workflow_state.variables["claimed_task_id"] is None
        assert workflow_state.variables["task_claimed"] is False

    async def test_task_not_found_clears_state(self, workflow_state, mock_task_manager):
        """When task no longer exists, clear workflow state and allow."""
        workflow_state.variables["claimed_task_id"] = "gt-deleted"
        workflow_state.variables["task_claimed"] = True

        mock_task_manager.get_task.return_value = None

        result = await require_commit_before_stop(
            workflow_state=workflow_state,
            project_path="/test/path",
            task_manager=mock_task_manager,
        )

        assert result is None
        assert workflow_state.variables["claimed_task_id"] is None
        assert workflow_state.variables["task_claimed"] is False

    async def test_no_uncommitted_changes_allows(self, workflow_state, mock_task_manager):
        """When git status shows no changes, allow stop."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = set()

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is None

    async def test_uncommitted_changes_blocks(self, workflow_state, mock_task_manager):
        """When git status shows NEW changes (not in baseline), block stop."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["baseline_dirty_files"] = []  # No baseline files

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"src/file.py", "new_file.py"}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is not None
        assert result["decision"] == "block"
        assert "gt-abc123" in result["reason"]
        assert "uncommitted" in result["reason"]
        assert "close_task" in result["reason"]

    async def test_preexisting_dirty_files_allows(self, workflow_state, mock_task_manager):
        """Pre-existing dirty files (in baseline) are ignored."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        # Baseline captured at session start
        workflow_state.variables["baseline_dirty_files"] = [
            "src/preexisting.py",
            "config.yaml",
        ]

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            # Same files as baseline - no NEW changes
            mock_get_dirty.return_value = {"src/preexisting.py", "config.yaml"}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is None

    async def test_new_changes_with_baseline_blocks(self, workflow_state, mock_task_manager):
        """New changes beyond baseline are blocked."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        # Some files were already dirty at session start
        workflow_state.variables["baseline_dirty_files"] = ["src/preexisting.py"]

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            # New files added during session
            mock_get_dirty.return_value = {
                "src/preexisting.py",  # In baseline
                "src/new_file.py",  # NEW - should trigger block
            }

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is not None
        assert result["decision"] == "block"
        # Should only mention the NEW file
        assert "src/new_file.py" in result["reason"]

    async def test_no_baseline_treats_all_as_new(self, workflow_state, mock_task_manager):
        """When no baseline, all dirty files are treated as new."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        # No baseline captured (e.g., workflow activated after session started)

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"src/file.py"}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is not None
        assert result["decision"] == "block"

    async def test_block_reason_lists_new_dirty_files(self, workflow_state, mock_task_manager):
        """Block reason includes list of new dirty files."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["baseline_dirty_files"] = []

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"src/a.py", "src/b.py", "src/c.py"}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is not None
        assert "3 uncommitted" in result["reason"]
        assert "src/a.py" in result["reason"]
        assert "src/b.py" in result["reason"]
        assert "src/c.py" in result["reason"]

    async def test_block_reason_truncates_long_file_list(self, workflow_state, mock_task_manager):
        """Block reason truncates file list if more than 10 files."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["baseline_dirty_files"] = []

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            # 15 files
            mock_get_dirty.return_value = {f"src/file{i}.py" for i in range(15)}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is not None
        assert "15 uncommitted" in result["reason"]
        assert "and 5 more files" in result["reason"]

    async def test_max_block_count_allows(self, workflow_state, mock_task_manager):
        """After 3 blocks, allow to prevent infinite loop."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["_commit_block_count"] = 3  # Already at max

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"src/file.py"}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is None

    async def test_block_count_increments(self, workflow_state, mock_task_manager):
        """Block count increments on each block."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["baseline_dirty_files"] = []

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"src/file.py"}

            # First block
            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

            assert result is not None
            assert workflow_state.variables["_commit_block_count"] == 1

            # Second block
            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

            assert result is not None
            assert workflow_state.variables["_commit_block_count"] == 2

    async def test_no_task_manager_skips_status_check(self, workflow_state):
        """When no task_manager, skip task status check but still check git."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["baseline_dirty_files"] = []

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"src/file.py"}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=None,  # No task manager
            )

        # Should still block because git shows changes
        assert result is not None
        assert result["decision"] == "block"

    async def test_block_reason_includes_instructions(self, workflow_state, mock_task_manager):
        """Block reason includes commit and close instructions."""
        workflow_state.variables["claimed_task_id"] = "gt-xyz789"
        workflow_state.variables["baseline_dirty_files"] = []

        mock_task = MagicMock()
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        with patch("gobby.workflows.enforcement.commit_policy.get_dirty_files") as mock_get_dirty:
            mock_get_dirty.return_value = {"file.txt"}

            result = await require_commit_before_stop(
                workflow_state=workflow_state,
                project_path="/test/path",
                task_manager=mock_task_manager,
            )

        assert result is not None
        assert "[gt-xyz789]" in result["reason"]
        assert 'close_task(task_id="gt-xyz789"' in result["reason"]


# =============================================================================
# Tests for require_task_review_or_close_before_stop
# =============================================================================


class TestRequireTaskReviewOrCloseBeforeStop:
    """Tests for require_task_review_or_close_before_stop action."""

    async def test_no_workflow_state_allows(self):
        """When no workflow_state, allow stop."""
        result = await require_task_review_or_close_before_stop(
            workflow_state=None,
            task_manager=MagicMock(),
        )
        assert result is None

    async def test_no_claimed_task_allows(self, workflow_state):
        """When no claimed_task_id, allow stop."""
        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=MagicMock(),
        )
        assert result is None

    async def test_no_task_manager_allows(self, workflow_state):
        """When no task_manager, allow stop."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=None,
        )
        assert result is None

    async def test_task_not_found_clears_state(self, workflow_state, mock_task_manager):
        """When task no longer exists, clear workflow state and allow."""
        workflow_state.variables["claimed_task_id"] = "gt-deleted"
        workflow_state.variables["task_claimed"] = True

        mock_task_manager.get_task.return_value = None

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is None
        assert workflow_state.variables["claimed_task_id"] is None
        assert workflow_state.variables["task_claimed"] is False

    async def test_task_closed_clears_state(self, workflow_state, mock_task_manager):
        """When task is closed, clear workflow state and allow."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["task_claimed"] = True

        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is None
        assert workflow_state.variables["claimed_task_id"] is None
        assert workflow_state.variables["task_claimed"] is False

    async def test_task_in_review_clears_state(self, workflow_state, mock_task_manager):
        """When task is in review, clear workflow state and allow."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"
        workflow_state.variables["task_claimed"] = True

        mock_task = MagicMock()
        mock_task.status = "review"
        mock_task_manager.get_task.return_value = mock_task

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is None
        assert workflow_state.variables["claimed_task_id"] is None
        assert workflow_state.variables["task_claimed"] is False

    async def test_task_in_progress_blocks(self, workflow_state, mock_task_manager):
        """When task is in_progress, block stop."""
        task_id = "01234567-89ab-cdef-0123-456789abcdef"
        workflow_state.variables["claimed_task_id"] = task_id

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.seq_num = 42
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "#42" in result["reason"]
        assert "still in_progress" in result["reason"]
        assert "close_task()" in result["reason"]
        assert result["task_id"] == task_id
        assert result["task_status"] == "in_progress"

    async def test_exception_allows(self, workflow_state, mock_task_manager):
        """When exception occurs, allow stop to avoid blocking."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"

        mock_task_manager.get_task.side_effect = Exception("Database error")

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is None

    async def test_accepts_extra_kwargs(self, workflow_state, mock_task_manager):
        """Function accepts extra kwargs for compatibility."""
        workflow_state.variables["claimed_task_id"] = "gt-abc123"

        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task

        # Should not raise even with extra kwargs
        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
            project_path="/some/path",  # Extra kwarg for compatibility
            extra_arg="ignored",
        )

        assert result is None

    # -------------------------------------------------------------------------
    # Tests for session_task fallback (when claimed_task_id is not set)
    # -------------------------------------------------------------------------

    async def test_session_task_string_blocks_when_in_progress(
        self, workflow_state, mock_task_manager
    ):
        """When session_task is set (string) and task is in_progress, block stop."""
        task_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        workflow_state.variables["session_task"] = task_id
        # No claimed_task_id set

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.seq_num = 101
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "#101" in result["reason"]
        assert "still in_progress" in result["reason"]

    async def test_session_task_list_blocks_when_any_in_progress(
        self, workflow_state, mock_task_manager
    ):
        """When session_task is a list and any task is in_progress, block stop."""
        task1_id = "11111111-1111-1111-1111-111111111111"
        task2_id = "22222222-2222-2222-2222-222222222222"
        workflow_state.variables["session_task"] = [task1_id, task2_id]
        # No claimed_task_id set

        mock_task1 = MagicMock()
        mock_task1.id = task1_id
        mock_task1.seq_num = 1
        mock_task1.status = "closed"

        mock_task2 = MagicMock()
        mock_task2.id = task2_id
        mock_task2.seq_num = 2
        mock_task2.status = "in_progress"

        # Return different tasks for each get_task call
        mock_task_manager.get_task.side_effect = [mock_task1, mock_task2, mock_task2]
        mock_task_manager.list_tasks.return_value = []

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "#2" in result["reason"]

    async def test_session_task_allows_when_all_closed(self, workflow_state, mock_task_manager):
        """When session_task is set but all tasks are closed, allow stop."""
        workflow_state.variables["session_task"] = "gt-closed-task"
        # No claimed_task_id set

        mock_task = MagicMock()
        mock_task.id = "gt-closed-task"
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        # Should allow since no in_progress task found
        assert result is None

    async def test_session_task_subtask_in_progress_blocks(self, workflow_state, mock_task_manager):
        """When session_task has subtask in_progress, block stop."""
        parent_id = "33333333-3333-3333-3333-333333333333"
        subtask_id = "44444444-4444-4444-4444-444444444444"
        workflow_state.variables["session_task"] = parent_id
        # No claimed_task_id set

        mock_parent = MagicMock()
        mock_parent.id = parent_id
        mock_parent.seq_num = 10
        mock_parent.status = "open"  # Parent is open, not in_progress

        mock_subtask = MagicMock()
        mock_subtask.id = subtask_id
        mock_subtask.seq_num = 11
        mock_subtask.status = "in_progress"

        # First call for parent, second call for subtask verification
        mock_task_manager.get_task.side_effect = [mock_parent, mock_subtask]
        mock_task_manager.list_tasks.return_value = [mock_subtask]

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "#11" in result["reason"]

    async def test_session_task_wildcard_allows(self, workflow_state, mock_task_manager):
        """When session_task='*', don't check tasks (wildcard means all)."""
        workflow_state.variables["session_task"] = "*"
        # No claimed_task_id set

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        # Wildcard means we don't check specific tasks
        assert result is None
        mock_task_manager.get_task.assert_not_called()

    async def test_session_task_no_task_manager_allows(self, workflow_state):
        """When session_task is set but no task_manager, allow stop."""
        workflow_state.variables["session_task"] = "gt-task"
        # No claimed_task_id set

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=None,
        )

        assert result is None

    async def test_claimed_task_takes_precedence_over_session_task(
        self, workflow_state, mock_task_manager
    ):
        """claimed_task_id is checked first, session_task is fallback."""
        claimed_id = "55555555-5555-5555-5555-555555555555"
        session_id = "66666666-6666-6666-6666-666666666666"
        workflow_state.variables["claimed_task_id"] = claimed_id
        workflow_state.variables["session_task"] = session_id

        mock_claimed_task = MagicMock()
        mock_claimed_task.id = claimed_id
        mock_claimed_task.seq_num = 99
        mock_claimed_task.status = "in_progress"

        # Only return the claimed task
        mock_task_manager.get_task.return_value = mock_claimed_task

        result = await require_task_review_or_close_before_stop(
            workflow_state=workflow_state,
            task_manager=mock_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        # Should block on claimed_task, not session_task
        assert "#99" in result["reason"]


# =============================================================================
# Tests for require_task_complete
# =============================================================================


class TestRequireTaskComplete:
    """Tests for require_task_complete action."""

    async def test_no_task_ids_allows(self):
        """When no task_ids specified, allow stop."""
        result = await require_task_complete(
            task_manager=MagicMock(),
            session_id="test-session",
            task_ids=None,
        )
        assert result is None

    async def test_empty_task_ids_allows(self):
        """When empty task_ids list, allow stop."""
        result = await require_task_complete(
            task_manager=MagicMock(),
            session_id="test-session",
            task_ids=[],
        )
        assert result is None

    async def test_no_task_manager_allows(self):
        """When no task_manager available, allow stop."""
        result = await require_task_complete(
            task_manager=None,
            session_id="test-session",
            task_ids=["gt-abc123"],
        )
        assert result is None

    async def test_max_block_count_allows(self, workflow_state):
        """After 5 blocks, allow to prevent infinite loop."""
        workflow_state.variables["_task_block_count"] = 5

        result = await require_task_complete(
            task_manager=MagicMock(),
            session_id="test-session",
            task_ids=["gt-abc123"],
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_task_not_found_skipped(self, mock_task_manager):
        """When task not found, skip it and continue."""
        mock_task_manager.get_task.return_value = None

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-nonexistent"],
        )

        assert result is None

    async def test_closed_task_skipped(self, mock_task_manager):
        """When task is closed, skip it."""
        mock_task = MagicMock()
        mock_task.status = "closed"
        mock_task_manager.get_task.return_value = mock_task

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-closed"],
        )

        assert result is None

    async def test_all_tasks_closed_allows(self, mock_task_manager):
        """When all specified tasks are closed, allow stop."""
        mock_task1 = MagicMock()
        mock_task1.status = "closed"
        mock_task2 = MagicMock()
        mock_task2.status = "closed"

        mock_task_manager.get_task.side_effect = [mock_task1, mock_task2]

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-task1", "gt-task2"],
        )

        assert result is None

    async def test_leaf_task_not_closed_blocks(self, mock_task_manager):
        """Task with no subtasks but not closed should block with close reminder."""
        mock_task = MagicMock()
        mock_task.id = "gt-leaf"
        mock_task.title = "Leaf Task"
        mock_task.status = "in_progress"

        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []  # No subtasks

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-leaf"],
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "ready to close" in result["reason"]
        assert "close_task" in result["reason"]
        assert "gt-leaf" in result["reason"]

    async def test_incomplete_subtasks_no_claimed_task_blocks(
        self, mock_task_manager, workflow_state
    ):
        """Incomplete subtasks with no claimed task should suggest next task."""
        mock_parent = MagicMock()
        mock_parent.id = "gt-parent"
        mock_parent.title = "Parent Feature"
        mock_parent.status = "open"

        mock_subtask1 = MagicMock()
        mock_subtask1.id = "gt-sub1"
        mock_subtask1.status = "open"

        mock_subtask2 = MagicMock()
        mock_subtask2.id = "gt-sub2"
        mock_subtask2.status = "open"

        mock_task_manager.get_task.return_value = mock_parent
        mock_task_manager.list_tasks.return_value = [mock_subtask1, mock_subtask2]

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-parent"],
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "2 incomplete subtask(s)" in result["reason"]
        assert "suggest_next_task()" in result["reason"]

    async def test_incomplete_subtasks_with_claimed_task_under_parent(
        self, mock_task_manager, workflow_state
    ):
        """Claimed task under parent should remind to finish it."""
        workflow_state.variables["task_claimed"] = True
        workflow_state.variables["claimed_task_id"] = "gt-sub1"

        mock_parent = MagicMock()
        mock_parent.id = "gt-parent"
        mock_parent.title = "Parent Feature"
        mock_parent.status = "open"

        mock_subtask1 = MagicMock()
        mock_subtask1.id = "gt-sub1"
        mock_subtask1.status = "in_progress"

        mock_subtask2 = MagicMock()
        mock_subtask2.id = "gt-sub2"
        mock_subtask2.status = "open"

        # Return correct task based on task_id (needed for claimed_task_id resolution)
        def get_task_side_effect(task_id):
            if task_id == "gt-sub1":
                return mock_subtask1
            elif task_id == "gt-parent":
                return mock_parent
            return None

        mock_task_manager.get_task.side_effect = get_task_side_effect
        mock_task_manager.list_tasks.return_value = [mock_subtask1, mock_subtask2]

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-parent"],
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "current task is not yet complete" in result["reason"]
        assert 'close_task(task_id="gt-sub1")' in result["reason"]

    async def test_incomplete_subtasks_with_claimed_task_not_under_parent(
        self, mock_task_manager, workflow_state
    ):
        """Claimed task not under parent should redirect to parent work."""
        workflow_state.variables["task_claimed"] = True
        workflow_state.variables["claimed_task_id"] = "gt-other"  # Different task

        mock_parent = MagicMock()
        mock_parent.id = "gt-parent"
        mock_parent.title = "Parent Feature"
        mock_parent.status = "open"

        mock_subtask1 = MagicMock()
        mock_subtask1.id = "gt-sub1"
        mock_subtask1.status = "open"

        mock_task_manager.get_task.return_value = mock_parent
        mock_task_manager.list_tasks.return_value = [mock_subtask1]

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-parent"],
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "1 incomplete subtask(s)" in result["reason"]
        assert "suggest_next_task()" in result["reason"]

    async def test_multiple_tasks_shows_count(self, mock_task_manager):
        """Multiple incomplete tasks shows remaining count."""
        mock_task1 = MagicMock()
        mock_task1.id = "gt-task1"
        mock_task1.title = "Task 1"
        mock_task1.status = "open"

        mock_task2 = MagicMock()
        mock_task2.id = "gt-task2"
        mock_task2.title = "Task 2"
        mock_task2.status = "open"

        mock_task_manager.get_task.side_effect = [mock_task1, mock_task2]
        mock_task_manager.list_tasks.return_value = []  # No subtasks

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-task1", "gt-task2"],
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "2 tasks remaining in total" in result["reason"]

    async def test_block_count_increments(self, mock_task_manager, workflow_state):
        """Block count increments on each block."""
        mock_task = MagicMock()
        mock_task.id = "gt-task"
        mock_task.title = "Test Task"
        mock_task.status = "open"

        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []

        # First block
        await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-task"],
            workflow_state=workflow_state,
        )

        assert workflow_state.variables["_task_block_count"] == 1

        # Second block
        await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-task"],
            workflow_state=workflow_state,
        )

        assert workflow_state.variables["_task_block_count"] == 2

    async def test_error_handling_allows(self, mock_task_manager):
        """On exception, allow stop to avoid blocking legitimate work."""

        mock_task_manager.get_task.side_effect = Exception("Database error")

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-abc123"],
        )

        assert result is None

    async def test_all_subtasks_closed_parent_not_closed_allows(self, mock_task_manager):
        """All subtasks closed allows stop (parent completion tracked elsewhere).

        The require_task_complete function only blocks when there are incomplete
        subtasks OR no subtasks. If all subtasks are complete, the parent is
        considered complete for enforcement purposes.
        """
        mock_parent = MagicMock()
        mock_parent.id = "gt-parent"
        mock_parent.title = "Parent Feature"
        mock_parent.status = "in_progress"  # Not closed, but subtasks are

        mock_subtask1 = MagicMock()
        mock_subtask1.id = "gt-sub1"
        mock_subtask1.status = "closed"

        mock_subtask2 = MagicMock()
        mock_subtask2.id = "gt-sub2"
        mock_subtask2.status = "closed"

        mock_task_manager.get_task.return_value = mock_parent
        mock_task_manager.list_tasks.return_value = [mock_subtask1, mock_subtask2]

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-parent"],
        )

        # All subtasks closed = parent considered complete for enforcement
        assert result is None

    async def test_mixed_complete_incomplete_tasks(self, mock_task_manager):
        """Mix of complete and incomplete tasks blocks on first incomplete."""
        mock_task1 = MagicMock()
        mock_task1.id = "gt-task1"
        mock_task1.status = "closed"

        mock_task2 = MagicMock()
        mock_task2.id = "gt-task2"
        mock_task2.title = "Incomplete Task"
        mock_task2.status = "open"

        mock_task_manager.get_task.side_effect = [mock_task1, mock_task2]
        mock_task_manager.list_tasks.return_value = []

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-task1", "gt-task2"],
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "Incomplete Task" in result["reason"]

    async def test_without_workflow_state_no_block_count(self, mock_task_manager):
        """Without workflow state, block count is not tracked."""
        mock_task = MagicMock()
        mock_task.id = "gt-task"
        mock_task.title = "Test Task"
        mock_task.status = "open"

        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.list_tasks.return_value = []

        # Multiple blocks without workflow state
        for _ in range(10):
            result = await require_task_complete(
                task_manager=mock_task_manager,
                session_id="test-session",
                task_ids=["gt-task"],
                workflow_state=None,
            )
            # Should still block (no max count check without state)
            assert result is not None


# =============================================================================
# Tests for require_active_task
# =============================================================================


class TestRequireActiveTask:
    """Tests for require_active_task action."""

    async def test_task_claimed_allows_immediately(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed=True, tool is allowed without DB query."""
        workflow_state.variables["task_claimed"] = True

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None  # None means allow
        # Verify DB was NOT queried
        mock_task_manager.list_tasks.assert_not_called()

    async def test_no_task_claimed_blocks_protected_tool(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed=False, protected tool is blocked."""
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "No task claimed for this session" in result["reason"]

    async def test_no_task_claimed_with_project_task_shows_hint(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed=False but project has in_progress task, show hint."""
        mock_task = MagicMock()
        mock_task.id = "gt-existing"
        mock_task.title = "Existing task"
        mock_task_manager.list_tasks.return_value = [mock_task]

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "gt-existing" in result["reason"]
        assert "appears unattended" in result["reason"]

    async def test_unprotected_tool_always_allowed(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Unprotected tools are allowed without any checks."""
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Read"},  # Not in protected_tools
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None
        mock_task_manager.list_tasks.assert_not_called()

    async def test_feature_disabled_allows_all(self, mock_task_manager, workflow_state):
        """When feature is disabled, all tools are allowed."""
        config = MagicMock()
        config.workflow.require_task_before_edit = False

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_no_workflow_state_falls_back_to_db_check(self, mock_config, mock_task_manager):
        """When workflow_state is None, falls back to DB check."""
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=None,  # No workflow state
        )

        assert result is not None
        assert result["decision"] == "block"
        mock_task_manager.list_tasks.assert_called_once()

    async def test_task_claimed_false_explicitly_blocks(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When task_claimed is explicitly False, tool is blocked."""
        workflow_state.variables["task_claimed"] = False
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Write"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"

    async def test_no_config_allows_all(self, mock_task_manager, workflow_state):
        """When config is None, all tools are allowed."""
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=None,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_inject_context_explains_session_scope(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Blocking message explains session-scoped requirement."""
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Bash"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert "inject_context" in result
        assert "claim a task for this session" in result["inject_context"]
        assert "Each session must explicitly" in result["inject_context"]

    async def test_new_session_starts_without_task_claimed(self, mock_config, mock_task_manager):
        """New sessions start without task_claimed variable (blocks protected tools).

        This verifies session isolation - a fresh session has no task_claimed
        and cannot use protected tools until it claims a task.
        """
        # Simulate a fresh session with new WorkflowState
        fresh_state = WorkflowState(
            session_id="new-session-123",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={},  # Empty - no task_claimed
        )
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="new-session-123",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=fresh_state,
        )

        # New session should be blocked from protected tools
        assert result is not None
        assert result["decision"] == "block"
        # Verify task_claimed is not in variables
        assert "task_claimed" not in fresh_state.variables

    async def test_error_shown_once_then_short_reminder(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """First block shows full error, subsequent blocks show short reminder."""
        mock_task_manager.list_tasks.return_value = []

        # First call - should get full error
        result1 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result1 is not None
        assert result1["decision"] == "block"
        assert "Each session must explicitly" in result1["inject_context"]
        assert workflow_state.variables.get("task_error_shown") is True

        # Second call - should get short reminder
        result2 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Write"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result2 is not None
        assert result2["decision"] == "block"
        assert "see previous error" in result2["inject_context"]
        assert "Each session must explicitly" not in result2["inject_context"]

    async def test_error_dedup_without_workflow_state(self, mock_config, mock_task_manager):
        """Error dedup gracefully handles missing workflow_state (no dedup)."""
        mock_task_manager.list_tasks.return_value = []

        # First call without workflow_state
        result1 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=None,
        )

        assert result1 is not None
        assert result1["decision"] == "block"
        # Should get full error since we can't track state
        assert "Each session must explicitly" in result1["inject_context"]

        # Second call also without workflow_state - still gets full error
        result2 = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Write"},
            project_id="proj-123",
            workflow_state=None,
        )

        assert result2 is not None
        assert result2["decision"] == "block"
        # Without state, each call shows full error
        assert "Each session must explicitly" in result2["inject_context"]

    async def test_no_event_data_allows(self, mock_config, mock_task_manager, workflow_state):
        """When no event_data provided, allow."""
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data=None,
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_no_tool_name_in_event_data_allows(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When tool_name not in event_data, allow."""
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"other_field": "value"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_db_query_error_allows(self, mock_config, mock_task_manager, workflow_state):
        """When DB query fails, allow to avoid blocking legitimate work."""
        mock_task_manager.list_tasks.side_effect = Exception("Database error")

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None

    async def test_no_task_manager_skips_fallback(self, mock_config, workflow_state):
        """When task_manager is None, skip fallback DB check."""
        result = await require_active_task(
            task_manager=None,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        # Should still block, but without project task hint
        assert result is not None
        assert result["decision"] == "block"
        assert "wasn't claimed" not in result["reason"]

    async def test_workflow_variable_takes_precedence_over_config(
        self, mock_task_manager, workflow_state
    ):
        """Workflow variable require_task_before_edit takes precedence over config.yaml."""
        # Config has it enabled
        mock_config = MagicMock()
        mock_config.workflow.require_task_before_edit = True
        mock_config.workflow.protected_tools = ["Edit", "Write"]

        # But workflow variable disables it
        workflow_state.variables["require_task_before_edit"] = False

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        # Should allow because workflow variable takes precedence
        assert result is None

    async def test_workflow_variable_can_enable_when_config_disabled(
        self, mock_task_manager, workflow_state
    ):
        """Workflow variable can enable feature even when config.yaml has it disabled."""
        # Config has it disabled
        mock_config = MagicMock()
        mock_config.workflow.require_task_before_edit = False
        mock_config.workflow.protected_tools = ["Edit", "Write"]

        # But workflow variable enables it
        workflow_state.variables["require_task_before_edit"] = True
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        # Should block because workflow variable takes precedence
        assert result is not None
        assert result["decision"] == "block"

    async def test_claude_plan_file_allows_without_task(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Writing to Claude Code plan file is allowed without a task.

        Claude stores plan files in ~/.claude/plans/ directory. This allows
        plan mode to work even when no task is claimed.
        """
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={
                "tool_name": "Write",
                "tool_input": {"file_path": "/Users/josh/.claude/plans/my-plan-abc123.md"},
            },
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None  # Allowed
        mock_task_manager.list_tasks.assert_not_called()

    async def test_claude_plan_file_edit_allows_without_task(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Editing Claude Code plan file is allowed without a task."""
        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={
                "tool_name": "Edit",
                "tool_input": {"file_path": "/Users/josh/.claude/plans/plan-12345.md"},
            },
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None  # Allowed

    async def test_non_plan_file_still_requires_task(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Writing to non-plan file still requires a task."""
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={
                "tool_name": "Write",
                "tool_input": {"file_path": "/Users/josh/project/src/main.py"},
            },
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"

    async def test_plan_mode_variable_allows_without_task(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When plan_mode=True, protected tools are allowed."""
        workflow_state.variables["plan_mode"] = True

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={
                "tool_name": "Edit",
                "tool_input": {"file_path": "/Users/josh/project/src/some_file.py"},
            },
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is None  # Allowed
        mock_task_manager.list_tasks.assert_not_called()

    async def test_plan_mode_false_still_requires_task(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """When plan_mode=False, task is still required."""
        workflow_state.variables["plan_mode"] = False
        mock_task_manager.list_tasks.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="test-session",
            config=mock_config,
            event_data={
                "tool_name": "Write",
                "tool_input": {"file_path": "/Users/josh/project/src/main.py"},
            },
            project_id="proj-123",
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"


# =============================================================================
# Tests for validate_session_task_scope
# =============================================================================


class TestValidateSessionTaskScope:
    """Tests for validate_session_task_scope action."""

    @pytest.fixture
    def workflow_state_with_session_task(self):
        """Create a workflow state with session_task set."""
        return WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": "epic-1"},
        )

    async def test_no_session_task_allows_all(self, mock_task_manager, workflow_state):
        """When no session_task is set, any task can be claimed."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state,
            event_data=event_data,
        )

        assert result is None  # Allowed

    async def test_descendant_task_allowed(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Task that is descendant of session_task is allowed."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "child-1", "status": "in_progress"}},
        }

        # Mock is_descendant_of to return True
        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = True

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state_with_session_task,
                event_data=event_data,
            )

        assert result is None  # Allowed
        mock_descendant.assert_called_once_with(mock_task_manager, "child-1", "epic-1")

    async def test_non_descendant_task_blocked(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Task outside session_task hierarchy is blocked."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "other-task", "status": "in_progress"}},
        }

        # Mock is_descendant_of to return False
        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = False

            # Mock get_task for error message
            mock_session_task = MagicMock()
            mock_session_task.title = "My Epic"
            mock_task_manager.get_task.return_value = mock_session_task

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state_with_session_task,
                event_data=event_data,
            )

        assert result is not None
        assert result["decision"] == "block"
        assert "not within the session_task scope" in result["reason"]
        assert "epic-1" in result["reason"]
        assert "suggest_next_task" in result["reason"]

    async def test_non_update_task_tool_allowed(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Non-update_task tool calls are not affected."""
        event_data = {
            "tool_name": "create_task",
            "tool_input": {"arguments": {"title": "New task"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None  # Allowed - not an update_task call

    async def test_non_in_progress_status_allowed(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """Setting status to something other than in_progress is allowed."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "blocked"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None  # Allowed - not claiming (in_progress)

    async def test_no_workflow_state_allows(self, mock_task_manager):
        """When no workflow state, scope check is skipped."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=None,
            event_data=event_data,
        )

        assert result is None  # Allowed - no workflow state to check

    async def test_no_task_manager_allows(self, workflow_state_with_session_task):
        """When no task manager, scope check is skipped."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=None,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None  # Allowed - no task manager to check

    async def test_wildcard_allows_all(self, mock_task_manager):
        """When session_task='*', all tasks are allowed."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": "*"},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state,
            event_data=event_data,
        )

        assert result is None  # Allowed - wildcard means all tasks

    async def test_array_allows_descendant_of_any(self, mock_task_manager):
        """When session_task is array, task must be descendant of ANY."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": ["epic-1", "epic-2"]},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "child-of-epic-2", "status": "in_progress"}},
        }

        # Mock is_descendant_of: False for epic-1, True for epic-2
        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.side_effect = [False, True]  # Not under epic-1, but under epic-2

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is None  # Allowed - descendant of epic-2
        assert mock_descendant.call_count == 2

    async def test_array_blocks_if_not_descendant_of_any(self, mock_task_manager):
        """When session_task is array, blocks if not descendant of any."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": ["epic-1", "epic-2"]},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "unrelated-task", "status": "in_progress"}},
        }

        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = False  # Not under any

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is not None
        assert result["decision"] == "block"
        assert "epic-1" in result["reason"]
        assert "epic-2" in result["reason"]

    async def test_empty_array_allows_all(self, mock_task_manager):
        """Empty session_task array means no scope restriction."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": []},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state,
            event_data=event_data,
        )

        assert result is None  # Allowed - empty list means no restriction

    async def test_no_event_data_allows(self, mock_task_manager, workflow_state_with_session_task):
        """When no event_data provided, allow."""
        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=None,
        )

        assert result is None

    async def test_no_status_in_arguments_allows(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """When no status in arguments, allow (not claiming)."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "title": "New Title"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None

    async def test_no_task_id_in_arguments_allows(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """When no task_id in arguments, allow."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"status": "in_progress"}},  # Missing task_id
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None

    async def test_invalid_session_task_type_allows(self, mock_task_manager):
        """When session_task is invalid type (not str/list), allow with warning."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": 12345},  # Invalid type
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "any-task", "status": "in_progress"}},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state,
            event_data=event_data,
        )

        assert result is None

    async def test_empty_arguments_allows(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """When arguments is empty or None, allow."""
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": None},
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None

    async def test_missing_tool_input_allows(
        self, mock_task_manager, workflow_state_with_session_task
    ):
        """When tool_input is missing, allow."""
        event_data = {
            "tool_name": "update_task",
        }

        result = await validate_session_task_scope(
            task_manager=mock_task_manager,
            workflow_state=workflow_state_with_session_task,
            event_data=event_data,
        )

        assert result is None

    async def test_blocked_message_includes_single_task_title(self, mock_task_manager):
        """When single session_task, error message includes task title."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": "epic-main"},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "wrong-task", "status": "in_progress"}},
        }

        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = False

            mock_session_task = MagicMock()
            mock_session_task.title = "Main Epic Feature"
            mock_task_manager.get_task.return_value = mock_session_task

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is not None
        assert "Main Epic Feature" in result["reason"]
        assert "epic-main" in result["reason"]
        assert 'suggest_next_task(parent_id="epic-main")' in result["reason"]

    async def test_blocked_message_for_array_session_task(self, mock_task_manager):
        """When multiple session_tasks, error message lists all IDs."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": ["epic-1", "epic-2", "epic-3"]},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "wrong-task", "status": "in_progress"}},
        }

        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = False

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is not None
        assert "epic-1, epic-2, epic-3" in result["reason"]
        assert "one of the scoped parent IDs" in result["reason"]

    async def test_session_task_not_found_still_shows_id(self, mock_task_manager):
        """When session_task doesn't exist, still show its ID in error."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": "gt-deleted"},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "wrong-task", "status": "in_progress"}},
        }

        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = False

            mock_task_manager.get_task.return_value = None  # Task not found

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is not None
        assert "gt-deleted" in result["reason"]


# =============================================================================
# Additional edge case tests for coverage
# =============================================================================


class TestRequireTaskCompleteEdgeCases:
    """Edge case tests for require_task_complete."""

    async def test_fallback_block_for_edge_case(self, mock_task_manager, workflow_state):
        """Test the fallback block case for incomplete subtasks.

        This covers line 288-289 which is a defensive fallback.
        The code path happens when has_claimed_task is False and incomplete exists.
        """
        # This is actually covered by test_incomplete_subtasks_no_claimed_task_blocks
        # The fallback at lines 288-289 is truly unreachable in current code
        # since all conditions are exhaustively handled above it.
        # Leaving this test as documentation.
        pass

    async def test_parent_with_some_closed_subtasks(self, mock_task_manager):
        """Parent with mix of closed and open subtasks blocks."""
        mock_parent = MagicMock()
        mock_parent.id = "gt-parent"
        mock_parent.title = "Parent Task"
        mock_parent.status = "open"

        mock_closed_subtask = MagicMock()
        mock_closed_subtask.id = "gt-sub1"
        mock_closed_subtask.status = "closed"

        mock_open_subtask = MagicMock()
        mock_open_subtask.id = "gt-sub2"
        mock_open_subtask.status = "open"

        mock_task_manager.get_task.return_value = mock_parent
        mock_task_manager.list_tasks.return_value = [mock_closed_subtask, mock_open_subtask]

        result = await require_task_complete(
            task_manager=mock_task_manager,
            session_id="test-session",
            task_ids=["gt-parent"],
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "1 incomplete subtask(s)" in result["reason"]


class TestValidateSessionTaskScopeEdgeCases:
    """Edge case tests for validate_session_task_scope."""

    async def test_string_session_task_as_single_item_list(self, mock_task_manager):
        """String session_task gets normalized to single-item list internally."""
        workflow_state = WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={"session_task": "single-epic"},
        )
        event_data = {
            "tool_name": "update_task",
            "tool_input": {"arguments": {"task_id": "child-task", "status": "in_progress"}},
        }

        with patch("gobby.workflows.enforcement.task_policy.is_descendant_of") as mock_descendant:
            mock_descendant.return_value = True

            result = await validate_session_task_scope(
                task_manager=mock_task_manager,
                workflow_state=workflow_state,
                event_data=event_data,
            )

        assert result is None
        mock_descendant.assert_called_once_with(mock_task_manager, "child-task", "single-epic")


# =============================================================================
# Tests for session liveness in require_active_task
# =============================================================================


class TestRequireActiveTaskLiveness:
    """Tests for session liveness checks in require_active_task."""

    async def test_require_active_task_with_active_session_on_other_task(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Warn about other active session when suggesting task."""
        workflow_state.variables["task_claimed"] = False
        workflow_state.variables["task_error_shown"] = False

        # Mock an in_progress task in the project
        mock_task = MagicMock()
        mock_task.id = "gt-active"
        mock_task.title = "Active Task"
        mock_task.status = "in_progress"
        mock_task_manager.list_tasks.return_value = [mock_task]

        # Mock session manager and session task manager
        mock_session_manager = MagicMock()
        mock_session_task_manager = MagicMock()

        # Mock active session linked to this task
        mock_link = {"session_id": "other-session", "task_id": "gt-active"}
        mock_session_task_manager.get_task_sessions.return_value = [mock_link]

        mock_session = MagicMock()
        mock_session.id = "other-session"
        mock_session.status = "active"
        mock_session_manager.get.return_value = mock_session

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="current-session",
            config=mock_config,
            event_data={"tool_name": "Edit", "tool_input": {"file_path": "src/file.py"}},
            project_id="test-project",
            workflow_state=workflow_state,
            session_manager=mock_session_manager,
            session_task_manager=mock_session_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        # msg should warn about active session
        assert "**currently being worked on by another active session**" in result["inject_context"]
        assert "create a new task" in result["inject_context"]
        assert "claim it" not in result["inject_context"]

    async def test_require_active_task_with_inactive_session_on_other_task(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Suggest claiming task if linked session is inactive."""
        workflow_state.variables["task_claimed"] = False
        workflow_state.variables["task_error_shown"] = False

        # Mock an in_progress task in the project
        mock_task = MagicMock()
        mock_task.id = "gt-abandoned"
        mock_task.title = "Abandoned Task"
        mock_task.status = "in_progress"
        mock_task_manager.list_tasks.return_value = [mock_task]

        # Mock session manager and session task manager
        mock_session_manager = MagicMock()
        mock_session_task_manager = MagicMock()

        # Mock inactive/expired session linked to this task
        mock_link = {"session_id": "old-session", "task_id": "gt-abandoned"}
        mock_session_task_manager.get_task_sessions.return_value = [mock_link]

        mock_session = MagicMock()
        mock_session.id = "old-session"
        mock_session.status = "expired"  # Not active
        mock_session_manager.get.return_value = mock_session

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="current-session",
            config=mock_config,
            event_data={"tool_name": "Edit", "tool_input": {"file_path": "src/file.py"}},
            project_id="test-project",
            workflow_state=workflow_state,
            session_manager=mock_session_manager,
            session_task_manager=mock_session_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        # msg should suggest claiming
        assert "appears unattended" in result["inject_context"]
        assert "claim it" in result["inject_context"]

    async def test_require_active_task_no_linked_sessions(
        self, mock_config, mock_task_manager, workflow_state
    ):
        """Suggest claiming task if no sessions linked at all."""
        workflow_state.variables["task_claimed"] = False
        workflow_state.variables["task_error_shown"] = False

        # Mock an in_progress task
        mock_task = MagicMock()
        mock_task.id = "gt-orphan"
        mock_task.title = "Orphan Task"
        mock_task.status = "in_progress"
        mock_task_manager.list_tasks.return_value = [mock_task]

        # Mock session manager and session task manager
        mock_session_manager = MagicMock()
        mock_session_task_manager = MagicMock()

        # No linked sessions
        mock_session_task_manager.get_task_sessions.return_value = []

        result = await require_active_task(
            task_manager=mock_task_manager,
            session_id="current-session",
            config=mock_config,
            event_data={"tool_name": "Edit"},
            project_id="test-project",
            workflow_state=workflow_state,
            session_manager=mock_session_manager,
            session_task_manager=mock_session_task_manager,
        )

        assert result is not None
        assert result["decision"] == "block"
        # msg should suggest claiming
        assert "appears unattended" in result["inject_context"]
        assert "claim it" in result["inject_context"]


# =============================================================================
# Tests for block_tools action (unified tool blocking)
# =============================================================================


class TestBlockTools:
    """Tests for block_tools action."""

    @pytest.fixture
    def workflow_state(self):
        """Create a workflow state with empty variables."""
        return WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

    @pytest.mark.asyncio
    async def test_block_tools_no_rules(self, workflow_state):
        """Returns None when no rules are provided."""
        from gobby.workflows.enforcement import block_tools

        result = await block_tools(
            rules=None,
            event_data={"tool_name": "Edit"},
            workflow_state=workflow_state,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_block_tools_no_event_data(self, workflow_state):
        """Returns None when no event_data is provided."""
        from gobby.workflows.enforcement import block_tools

        result = await block_tools(
            rules=[{"tools": ["Edit"], "reason": "Blocked"}],
            event_data=None,
            workflow_state=workflow_state,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_block_tools_blocks_matching_tool(self, workflow_state):
        """Blocks tool when it matches a rule."""
        from gobby.workflows.enforcement import block_tools

        rules = [
            {
                "tools": ["TaskCreate", "TaskUpdate"],
                "reason": "CC native task tools are disabled.",
            }
        ]

        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "TaskCreate"},
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "CC native task tools are disabled" in result["reason"]

    @pytest.mark.asyncio
    async def test_block_tools_allows_non_matching_tool(self, workflow_state):
        """Allows tool when it doesn't match any rule."""
        from gobby.workflows.enforcement import block_tools

        rules = [
            {
                "tools": ["TaskCreate", "TaskUpdate"],
                "reason": "CC native task tools are disabled.",
            }
        ]

        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "Edit"},
            workflow_state=workflow_state,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_block_tools_with_condition_true(self, workflow_state):
        """Blocks tool when condition evaluates to true."""
        from gobby.workflows.enforcement import block_tools

        workflow_state.variables["task_claimed"] = False
        workflow_state.variables["plan_mode"] = False

        rules = [
            {
                "tools": ["Edit", "Write"],
                "when": "not task_claimed and not plan_mode",
                "reason": "Task Required: Claim a task before editing.",
            }
        ]

        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "Edit"},
            workflow_state=workflow_state,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "Task Required" in result["reason"]

    @pytest.mark.asyncio
    async def test_block_tools_with_condition_false(self, workflow_state):
        """Allows tool when condition evaluates to false."""
        from gobby.workflows.enforcement import block_tools

        workflow_state.variables["task_claimed"] = True
        workflow_state.variables["plan_mode"] = False

        rules = [
            {
                "tools": ["Edit", "Write"],
                "when": "not task_claimed and not plan_mode",
                "reason": "Task Required: Claim a task before editing.",
            }
        ]

        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "Edit"},
            workflow_state=workflow_state,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_block_tools_plan_mode_allows_edit(self, workflow_state):
        """Allows edit tools when in plan mode."""
        from gobby.workflows.enforcement import block_tools

        workflow_state.variables["task_claimed"] = False
        workflow_state.variables["plan_mode"] = True

        rules = [
            {
                "tools": ["Edit", "Write"],
                "when": "not task_claimed and not plan_mode",
                "reason": "Task Required: Claim a task before editing.",
            }
        ]

        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "Edit"},
            workflow_state=workflow_state,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_block_tools_multiple_rules(self, workflow_state):
        """First matching rule blocks the tool."""
        from gobby.workflows.enforcement import block_tools

        workflow_state.variables["task_claimed"] = False
        workflow_state.variables["plan_mode"] = False

        rules = [
            {
                "tools": ["TaskCreate"],
                "reason": "CC task tools disabled.",
            },
            {
                "tools": ["Edit", "Write"],
                "when": "not task_claimed",
                "reason": "Task required for edits.",
            },
        ]

        # Test TaskCreate matches first rule
        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "TaskCreate"},
            workflow_state=workflow_state,
        )
        assert result is not None
        assert "CC task tools disabled" in result["reason"]

        # Test Edit matches second rule
        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "Edit"},
            workflow_state=workflow_state,
        )
        assert result is not None
        assert "Task required for edits" in result["reason"]

    @pytest.mark.asyncio
    async def test_block_tools_invalid_condition(self, workflow_state):
        """Invalid condition blocks tool (fail-closed security behavior)."""
        from gobby.workflows.enforcement import block_tools

        rules = [
            {
                "tools": ["Edit"],
                "when": "invalid_syntax[[[",
                "reason": "Block on invalid condition.",
            }
        ]

        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "Edit"},
            workflow_state=workflow_state,
        )

        # Invalid condition triggers fail-closed: block the tool to prevent bypass
        assert result is not None
        assert result["decision"] == "block"

    @pytest.mark.asyncio
    async def test_block_tools_no_workflow_state(self):
        """Works without workflow state (condition always matches if no condition)."""
        from gobby.workflows.enforcement import block_tools

        rules = [
            {
                "tools": ["TaskCreate"],
                "reason": "Blocked without condition.",
            }
        ]

        result = await block_tools(
            rules=rules,
            event_data={"tool_name": "TaskCreate"},
            workflow_state=None,
        )

        assert result is not None
        assert result["decision"] == "block"


class TestEvaluateBlockCondition:
    """Tests for _evaluate_block_condition helper."""

    @pytest.fixture
    def workflow_state(self):
        """Create a workflow state."""
        return WorkflowState(
            session_id="test-session",
            workflow_name="test-workflow",
            step="test-step",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

    def test_empty_condition_returns_true(self, workflow_state) -> None:
        """Empty condition means always match (block)."""
        from gobby.workflows.enforcement.blocking import _evaluate_block_condition

        assert _evaluate_block_condition("", workflow_state) is True
        assert _evaluate_block_condition(None, workflow_state) is True

    def test_task_claimed_shorthand(self, workflow_state) -> None:
        """task_claimed shorthand works."""
        from gobby.workflows.enforcement.blocking import _evaluate_block_condition

        workflow_state.variables["task_claimed"] = True
        assert _evaluate_block_condition("task_claimed", workflow_state) is True

        workflow_state.variables["task_claimed"] = False
        assert _evaluate_block_condition("task_claimed", workflow_state) is False

    def test_not_operator(self, workflow_state) -> None:
        """not operator works."""
        from gobby.workflows.enforcement.blocking import _evaluate_block_condition

        workflow_state.variables["task_claimed"] = False
        assert _evaluate_block_condition("not task_claimed", workflow_state) is True

        workflow_state.variables["task_claimed"] = True
        assert _evaluate_block_condition("not task_claimed", workflow_state) is False

    def test_variables_get_access(self, workflow_state) -> None:
        """variables.get() works."""
        from gobby.workflows.enforcement.blocking import _evaluate_block_condition

        workflow_state.variables["custom_var"] = True
        assert _evaluate_block_condition("variables.get('custom_var')", workflow_state) is True

        workflow_state.variables["custom_var"] = False
        assert _evaluate_block_condition("variables.get('custom_var')", workflow_state) is False

    def test_combined_conditions(self, workflow_state) -> None:
        """Combined conditions work."""
        from gobby.workflows.enforcement.blocking import _evaluate_block_condition

        workflow_state.variables["task_claimed"] = False
        workflow_state.variables["plan_mode"] = False
        assert (
            _evaluate_block_condition("not task_claimed and not plan_mode", workflow_state) is True
        )

        workflow_state.variables["plan_mode"] = True
        assert (
            _evaluate_block_condition("not task_claimed and not plan_mode", workflow_state) is False
        )
