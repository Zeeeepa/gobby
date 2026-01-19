import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from gobby.storage.tasks import LocalTaskManager
from gobby.sync.tasks import TaskSyncManager


@pytest.fixture
def sync_manager(temp_db, tmp_path):
    export_path = tmp_path / ".gobby" / "tasks.jsonl"
    task_manager = LocalTaskManager(temp_db)
    manager = TaskSyncManager(task_manager, str(export_path))
    yield manager
    manager.stop()


@pytest.fixture
def task_manager(temp_db):
    return LocalTaskManager(temp_db)


class TestTaskSyncManager:
    @pytest.mark.integration
    @pytest.mark.slow
    def test_export_to_jsonl(self, sync_manager, task_manager, sample_project):
        # Create tasks
        t1 = task_manager.create_task(sample_project["id"], "Task 1")
        t2 = task_manager.create_task(sample_project["id"], "Task 2")

        # Add dependency: Task 2 depends on Task 1
        # task_id = t2.id (the one with dependency), depends_on = t1.id (the dependency)
        # Note: In schema, unique constraint includes dep_type
        now = "2023-01-01T00:00:00"
        sync_manager.db.execute(
            "INSERT INTO task_dependencies (task_id, depends_on, dep_type, created_at) VALUES (?, ?, ?, ?)",
            (t2.id, t1.id, "blocking", now),
        )

        sync_manager.export_to_jsonl()

        assert sync_manager.export_path.exists()

        lines = sync_manager.export_path.read_text().strip().split("\n")
        assert len(lines) == 2

        data = [json.loads(line) for line in lines]

        # Verify Task 1
        task1_data = next(d for d in data if d["id"] == t1.id)
        assert task1_data["title"] == "Task 1"
        assert task1_data["deps_on"] == []

        # Verify Task 2
        task2_data = next(d for d in data if d["id"] == t2.id)
        assert task2_data["title"] == "Task 2"
        assert task2_data["deps_on"] == [t1.id]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_trigger_export_debounced(self, sync_manager):
        """Test that multiple rapid trigger_export calls result in single debounced export."""
        # Reduce interval for test
        sync_manager._debounce_interval = 0.1

        with patch.object(sync_manager, "export_to_jsonl") as mock_export:
            # Trigger multiple times in quick succession
            sync_manager.trigger_export()
            sync_manager.trigger_export()
            sync_manager.trigger_export()

            # With async debounce, the task should be pending
            assert sync_manager._export_task is not None

            # Wait for debounce + execution
            await asyncio.sleep(0.3)

            # Should have been called exactly once (debounced)
            assert mock_export.call_count == 1

    @pytest.mark.integration
    def test_mutation_triggers_export(self, task_manager, tmp_path, sample_project):
        """Test that task mutations trigger export."""
        export_path = tmp_path / "tasks.jsonl"
        sync_manager = TaskSyncManager(task_manager, str(export_path))

        try:
            # Mock trigger_export to verify call
            sync_manager.trigger_export = MagicMock()

            # Wire up listener
            task_manager.add_change_listener(sync_manager.trigger_export)

            # Create task -> should trigger
            task = task_manager.create_task(sample_project["id"], "Task 1")
            assert sync_manager.trigger_export.call_count == 1

            # Update task -> should trigger
            task_manager.update_task(task.id, title="Updated Task 1")
            assert sync_manager.trigger_export.call_count == 2

            # Close task -> should trigger
            task_manager.close_task(task.id)
            assert sync_manager.trigger_export.call_count == 3

            # Delete task -> should trigger
            task_manager.delete_task(task.id)
            assert sync_manager.trigger_export.call_count == 4
        finally:
            sync_manager.stop()

    @pytest.mark.integration
    def test_import_from_jsonl(self, sync_manager, task_manager, sample_project):
        """Test importing tasks from JSONL."""
        # Create JSONL file content
        now = "2023-01-02T00:00:00+00:00"
        later = "2023-01-03T00:00:00+00:00"

        tasks_data = [
            {
                "id": "task-imported-1",
                "title": "Imported Task",
                "description": "Desc",
                "status": "todo",
                "created_at": now,
                "updated_at": now,
                "project_id": sample_project["id"],
                "parent_id": None,
                "deps_on": [],
            },
            {
                "id": "task-imported-2",
                "title": "Imported Task with Dep",
                "description": "Desc",
                "status": "todo",
                "created_at": now,
                "updated_at": later,
                "project_id": sample_project["id"],
                "parent_id": None,
                "deps_on": ["task-imported-1"],
            },
        ]

        # Write export file
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            for task in tasks_data:
                f.write(json.dumps(task) + "\n")

        # Run import
        sync_manager.import_from_jsonl()

        # Verify tasks in DB
        t1 = task_manager.get_task("task-imported-1")
        assert t1 is not None
        assert t1.title == "Imported Task"

        t2 = task_manager.get_task("task-imported-2")
        assert t2 is not None
        assert t2.title == "Imported Task with Dep"

        # Verify Dependency
        deps = task_manager.db.fetchall(
            "SELECT * FROM task_dependencies WHERE task_id = ?", (t2.id,)
        )
        assert len(deps) == 1
        assert deps[0]["depends_on"] == t1.id

    @pytest.mark.integration
    def test_import_conflict_resolution(self, sync_manager, task_manager, sample_project):
        """Test LWW conflict resolution during import."""
        # 1. Local Task is NEWER (should keep local)
        t1 = task_manager.create_task(sample_project["id"], "Local Newer")
        # Force updated_at to future
        future = "2025-01-01T00:00:00+00:00"
        task_manager.db.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (future, t1.id))

        # File has older version
        past = "2020-01-01T00:00:00+00:00"
        file_data = {
            "id": t1.id,
            "title": "File Older",
            "description": "",
            "status": "todo",
            "created_at": past,
            "updated_at": past,
            "project_id": sample_project["id"],
            "parent_id": None,
            "deps_on": [],
        }

        # Write file
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(file_data) + "\n")

        sync_manager.import_from_jsonl()

        # Verify DB unchanged
        t1_fresh = task_manager.get_task(t1.id)
        assert t1_fresh.title == "Local Newer"

        # 2. File is NEWER (should overwrite local)
        t2 = task_manager.create_task(sample_project["id"], "Local Older")
        task_manager.db.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (past, t2.id))

        file_data_2 = {
            "id": t2.id,
            "title": "File Newer",
            "description": "",
            "status": "todo",
            "created_at": past,
            "updated_at": future,
            "project_id": sample_project["id"],
            "parent_id": None,
            "deps_on": [],
        }

        # Append to file
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(file_data_2) + "\n")

        sync_manager.import_from_jsonl()

        # Verify DB updated
        t2_fresh = task_manager.get_task(t2.id)
        assert t2_fresh.title == "File Newer"

    @pytest.mark.integration
    def test_export_skips_when_unchanged(self, sync_manager, task_manager, sample_project):
        """Test that export doesn't update meta file when content unchanged."""
        # Create a task and export
        task_manager.create_task(sample_project["id"], "Task 1")
        sync_manager.export_to_jsonl()

        meta_path = sync_manager.export_path.parent / "tasks_meta.json"
        assert meta_path.exists()

        # Read initial meta
        with open(meta_path) as f:
            initial_meta = json.load(f)
        initial_timestamp = initial_meta["last_exported"]

        # Wait a bit to ensure timestamp would differ
        time.sleep(0.1)

        # Export again without changes
        sync_manager.export_to_jsonl()

        # Meta file should NOT have been updated (timestamp unchanged)
        with open(meta_path) as f:
            final_meta = json.load(f)

        assert final_meta["last_exported"] == initial_timestamp
        assert final_meta["content_hash"] == initial_meta["content_hash"]


class TestGetSyncStatus:
    """Tests for the get_sync_status method."""

    @pytest.mark.integration
    def test_get_sync_status_no_file(self, sync_manager):
        """Test sync status when export file doesn't exist."""
        result = sync_manager.get_sync_status()

        assert result["status"] == "no_file"
        assert result["synced"] is False

    @pytest.mark.integration
    def test_get_sync_status_no_meta_file(self, sync_manager):
        """Test sync status when export file exists but meta file doesn't."""
        # Create export file without meta
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        sync_manager.export_path.write_text("{}\n")

        result = sync_manager.get_sync_status()

        assert result["status"] == "no_meta"
        assert result["synced"] is False

    @pytest.mark.integration
    def test_get_sync_status_available(self, sync_manager, task_manager, sample_project):
        """Test sync status when both files exist."""
        # Create and export a task
        task_manager.create_task(sample_project["id"], "Test Task")
        sync_manager.export_to_jsonl()

        result = sync_manager.get_sync_status()

        assert result["status"] == "available"
        assert result["synced"] is True
        assert "last_exported" in result
        assert "hash" in result
        assert result["hash"] is not None

    @pytest.mark.integration
    def test_get_sync_status_error_on_corrupt_meta(self, sync_manager):
        """Test sync status when meta file is corrupted."""
        # Create export file
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        sync_manager.export_path.write_text("{}\n")

        # Create corrupted meta file
        meta_path = sync_manager.export_path.parent / "tasks_meta.json"
        meta_path.write_text("not valid json{{{")

        result = sync_manager.get_sync_status()

        assert result["status"] == "error"
        assert result["synced"] is False


class TestImportEdgeCases:
    """Tests for import edge cases and error handling."""

    @pytest.mark.integration
    def test_import_no_file_exists(self, sync_manager):
        """Test import when file doesn't exist - should just return."""
        # Ensure file doesn't exist
        assert not sync_manager.export_path.exists()

        # Should not raise
        sync_manager.import_from_jsonl()

    @pytest.mark.integration
    def test_import_with_empty_lines(self, sync_manager, task_manager, sample_project):
        """Test import handles empty lines in JSONL file."""
        now = "2023-01-02T00:00:00+00:00"

        tasks_data = {
            "id": "task-empty-lines",
            "title": "Test Task",
            "description": "Desc",
            "status": "todo",
            "created_at": now,
            "updated_at": now,
            "project_id": sample_project["id"],
            "parent_id": None,
            "deps_on": [],
        }

        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write("\n")  # Empty line at start
            f.write(json.dumps(tasks_data) + "\n")
            f.write("\n")  # Empty line in middle
            f.write("   \n")  # Whitespace-only line

        sync_manager.import_from_jsonl()

        task = task_manager.get_task("task-empty-lines")
        assert task is not None
        assert task.title == "Test Task"

    @pytest.mark.integration
    def test_import_with_validation_data(self, sync_manager, task_manager, sample_project):
        """Test import handles validation object."""
        now = "2023-01-02T00:00:00+00:00"

        tasks_data = {
            "id": "task-validation",
            "title": "Task with Validation",
            "description": "Desc",
            "status": "todo",
            "created_at": now,
            "updated_at": now,
            "project_id": sample_project["id"],
            "parent_id": None,
            "deps_on": [],
            "validation": {
                "status": "valid",  # Must be 'pending', 'valid', or 'invalid'
                "feedback": "All tests passed",
                "fail_count": 0,
                "criteria": "Must pass unit tests",
                "override_reason": None,
            },
        }

        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(tasks_data) + "\n")

        sync_manager.import_from_jsonl()

        task = task_manager.get_task("task-validation")
        assert task is not None
        assert task.validation_status == "valid"
        assert task.validation_feedback == "All tests passed"
        assert task.validation_criteria == "Must pass unit tests"

    @pytest.mark.integration
    def test_import_with_commits(self, sync_manager, task_manager, sample_project):
        """Test import handles commits array."""
        now = "2023-01-02T00:00:00+00:00"

        tasks_data = {
            "id": "task-commits",
            "title": "Task with Commits",
            "description": "Desc",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "project_id": sample_project["id"],
            "parent_id": None,
            "deps_on": [],
            "commits": ["abc123", "def456"],
        }

        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(tasks_data) + "\n")

        sync_manager.import_from_jsonl()

        task = task_manager.get_task("task-commits")
        assert task is not None
        assert task.commits == ["abc123", "def456"]

    @pytest.mark.integration
    def test_import_with_escalation_data(self, sync_manager, task_manager, sample_project):
        """Test import handles escalation fields."""
        now = "2023-01-02T00:00:00+00:00"

        tasks_data = {
            "id": "task-escalated",
            "title": "Escalated Task",
            "description": "Desc",
            "status": "todo",
            "created_at": now,
            "updated_at": now,
            "project_id": sample_project["id"],
            "parent_id": None,
            "deps_on": [],
            "escalated_at": now,
            "escalation_reason": "Blocked by external dependency",
        }

        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(tasks_data) + "\n")

        sync_manager.import_from_jsonl()

        task = task_manager.get_task("task-escalated")
        assert task is not None
        assert task.escalated_at == now
        assert task.escalation_reason == "Blocked by external dependency"

    @pytest.mark.integration
    def test_import_with_null_validation(self, sync_manager, task_manager, sample_project):
        """Test import handles null validation object."""
        now = "2023-01-02T00:00:00+00:00"

        tasks_data = {
            "id": "task-null-validation",
            "title": "Task without Validation",
            "description": "Desc",
            "status": "todo",
            "created_at": now,
            "updated_at": now,
            "project_id": sample_project["id"],
            "parent_id": None,
            "deps_on": [],
            "validation": None,
        }

        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write(json.dumps(tasks_data) + "\n")

        sync_manager.import_from_jsonl()

        task = task_manager.get_task("task-null-validation")
        assert task is not None
        assert task.validation_status is None

    @pytest.mark.integration
    def test_import_error_handling(self, sync_manager, task_manager, sample_project):
        """Test import raises exception on invalid JSON."""
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sync_manager.export_path, "w") as f:
            f.write("invalid json {{{")

        with pytest.raises(json.JSONDecodeError):
            sync_manager.import_from_jsonl()


class TestExportEdgeCases:
    """Tests for export edge cases and error handling."""

    @pytest.mark.integration
    def test_export_multiple_dependencies(self, sync_manager, task_manager, sample_project):
        """Test export with task having multiple dependencies."""
        t1 = task_manager.create_task(sample_project["id"], "Dependency 1")
        t2 = task_manager.create_task(sample_project["id"], "Dependency 2")
        t3 = task_manager.create_task(sample_project["id"], "Task with multiple deps")

        # Add multiple dependencies to t3
        now = "2023-01-01T00:00:00"
        sync_manager.db.execute(
            "INSERT INTO task_dependencies (task_id, depends_on, dep_type, created_at) VALUES (?, ?, ?, ?)",
            (t3.id, t1.id, "blocking", now),
        )
        sync_manager.db.execute(
            "INSERT INTO task_dependencies (task_id, depends_on, dep_type, created_at) VALUES (?, ?, ?, ?)",
            (t3.id, t2.id, "blocking", now),
        )

        sync_manager.export_to_jsonl()

        lines = sync_manager.export_path.read_text().strip().split("\n")
        data = [json.loads(line) for line in lines]

        task3_data = next(d for d in data if d["id"] == t3.id)
        # deps_on should be sorted
        assert sorted(task3_data["deps_on"]) == sorted([t1.id, t2.id])

    @pytest.mark.integration
    def test_export_with_validation_data(self, sync_manager, task_manager, sample_project):
        """Test export includes validation data."""
        task = task_manager.create_task(sample_project["id"], "Task with validation")

        # Add validation data directly to DB (status must be 'pending', 'valid', or 'invalid')
        sync_manager.db.execute(
            """UPDATE tasks SET
                validation_status = ?,
                validation_feedback = ?,
                validation_fail_count = ?,
                validation_criteria = ?
            WHERE id = ?""",
            ("invalid", "Test failed", 2, "Must pass CI", task.id),
        )

        sync_manager.export_to_jsonl()

        lines = sync_manager.export_path.read_text().strip().split("\n")
        data = json.loads(lines[0])

        assert data["validation"] is not None
        assert data["validation"]["status"] == "invalid"
        assert data["validation"]["feedback"] == "Test failed"
        assert data["validation"]["fail_count"] == 2
        assert data["validation"]["criteria"] == "Must pass CI"

    @pytest.mark.integration
    def test_export_with_commits(self, sync_manager, task_manager, sample_project):
        """Test export includes commits array."""
        task = task_manager.create_task(sample_project["id"], "Task with commits")

        # Link commits
        commits_json = json.dumps(["commit1", "commit2"])
        sync_manager.db.execute(
            "UPDATE tasks SET commits = ? WHERE id = ?",
            (commits_json, task.id),
        )

        sync_manager.export_to_jsonl()

        lines = sync_manager.export_path.read_text().strip().split("\n")
        data = json.loads(lines[0])

        assert data["commits"] == ["commit1", "commit2"]

    @pytest.mark.integration
    def test_export_with_corrupted_meta_file(self, sync_manager, task_manager, sample_project):
        """Test export handles corrupted meta file."""
        task_manager.create_task(sample_project["id"], "Task 1")

        # Create corrupted meta file first
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path = sync_manager.export_path.parent / "tasks_meta.json"
        meta_path.write_text("not valid json{{{")

        # Export should work despite corrupted meta
        sync_manager.export_to_jsonl()

        assert sync_manager.export_path.exists()

        # Meta should now be valid
        with open(meta_path) as f:
            meta = json.load(f)
        assert "content_hash" in meta
        assert "last_exported" in meta

    @pytest.mark.integration
    def test_export_error_propagates(self, sync_manager, task_manager, sample_project):
        """Test that export errors are propagated."""
        task_manager.create_task(sample_project["id"], "Task 1")

        # Make the export path a directory to cause write error
        sync_manager.export_path.parent.mkdir(parents=True, exist_ok=True)
        sync_manager.export_path.mkdir()

        with pytest.raises(IsADirectoryError):
            sync_manager.export_to_jsonl()

    @pytest.mark.integration
    def test_export_empty_tasks(self, sync_manager):
        """Test export with no tasks creates empty file."""
        sync_manager.export_to_jsonl()

        assert sync_manager.export_path.exists()
        content = sync_manager.export_path.read_text()
        assert content == ""


class TestStopMethod:
    """Tests for the stop method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stop_cancels_export_task(self, sync_manager):
        """Test stop cancels pending export task."""
        sync_manager._debounce_interval = 10  # Long interval

        with patch.object(sync_manager, "export_to_jsonl") as mock_export:
            sync_manager.trigger_export()
            assert sync_manager._export_task is not None

            sync_manager.stop()

            # Wait a bit to ensure task would have fired if not cancelled
            await asyncio.sleep(0.1)

            # Export should not have been called because task was cancelled
            assert mock_export.call_count == 0
            assert sync_manager._shutdown_requested is True

    @pytest.mark.integration
    def test_stop_without_export_task(self, sync_manager):
        """Test stop when no export task is running."""
        assert sync_manager._export_task is None

        # Should not raise
        sync_manager.stop()
        assert sync_manager._shutdown_requested is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_shutdown_graceful(self, sync_manager):
        """Test graceful async shutdown."""
        sync_manager._debounce_interval = 0.05

        with patch.object(sync_manager, "export_to_jsonl") as mock_export:
            sync_manager.trigger_export()

            # Graceful shutdown waits for task completion
            await sync_manager.shutdown()

            # Task should complete and export called
            assert sync_manager._export_task is None
            assert mock_export.call_count == 1


class TestImportFromGitHubIssues:
    """Tests for import_from_github_issues async method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_invalid_github_url(self, sync_manager):
        """Test import with invalid GitHub URL."""
        result = await sync_manager.import_from_github_issues("not-a-url")

        assert result["success"] is False
        assert "Invalid GitHub URL" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_github_url_with_git_suffix(self, sync_manager):
        """Test import handles .git suffix in URL."""
        with patch("subprocess.run") as mock_run:
            # Mock gh --version check
            mock_run.side_effect = [
                MagicMock(returncode=0),  # gh --version
                MagicMock(returncode=0, stdout="[]"),  # gh issue list
            ]

            result = await sync_manager.import_from_github_issues(
                "https://github.com/owner/repo.git"
            )

            assert result["success"] is True
            assert result["count"] == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_gh_not_installed(self, sync_manager):
        """Test import when gh CLI is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await sync_manager.import_from_github_issues("https://github.com/owner/repo")

            assert result["success"] is False
            assert "GitHub CLI (gh) not found" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_gh_command_fails(self, sync_manager):
        """Test import when gh command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # gh --version
                MagicMock(returncode=1, stderr="auth required"),  # gh issue list
            ]

            result = await sync_manager.import_from_github_issues("https://github.com/owner/repo")

            assert result["success"] is False
            assert "gh command failed" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_no_open_issues(self, sync_manager):
        """Test import when there are no open issues."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # gh --version
                MagicMock(returncode=0, stdout="[]"),  # gh issue list
            ]

            result = await sync_manager.import_from_github_issues("https://github.com/owner/repo")

            assert result["success"] is True
            assert result["count"] == 0
            assert result["imported"] == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_without_project_context(self, sync_manager):
        """Test import fails without project context."""
        issues_json = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Issue 1",
                    "body": "Body 1",
                    "labels": [],
                    "createdAt": "2023-01-01T00:00:00Z",
                }
            ]
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # gh --version
                MagicMock(returncode=0, stdout=issues_json),  # gh issue list
            ]

            with patch("gobby.utils.project_context.get_project_context", return_value=None):
                result = await sync_manager.import_from_github_issues(
                    "https://github.com/owner/repo"
                )

        assert result["success"] is False
        assert "Could not determine project ID" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_with_project_id(self, sync_manager, sample_project):
        """Test import with explicit project_id."""
        issues_json = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Issue 1",
                    "body": "Body 1",
                    "labels": [],
                    "createdAt": "2023-01-01T00:00:00Z",
                },
                {
                    "number": 2,
                    "title": "Issue 2",
                    "body": None,
                    "labels": [{"name": "bug"}],
                    "createdAt": "2023-01-02T00:00:00Z",
                },
            ]
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # gh --version
                MagicMock(returncode=0, stdout=issues_json),  # gh issue list
            ]

            result = await sync_manager.import_from_github_issues(
                "https://github.com/owner/repo",
                project_id=sample_project["id"],
            )

        assert result["success"] is True
        assert result["count"] == 2
        assert "gh-1" in result["imported"]
        assert "gh-2" in result["imported"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_updates_existing(self, sync_manager, sample_project):
        """Test import updates existing issues."""
        # First import
        issues_json = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Issue 1",
                    "body": "Original body",
                    "labels": [],
                    "createdAt": "2023-01-01T00:00:00Z",
                }
            ]
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout=issues_json),
            ]

            result1 = await sync_manager.import_from_github_issues(
                "https://github.com/owner/repo",
                project_id=sample_project["id"],
            )

        assert result1["count"] == 1

        # Second import with updated issue
        issues_json_updated = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Updated Title",
                    "body": "Updated body",
                    "labels": [{"name": "enhancement"}],
                    "createdAt": "2023-01-01T00:00:00Z",
                }
            ]
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout=issues_json_updated),
            ]

            result2 = await sync_manager.import_from_github_issues(
                "https://github.com/owner/repo",
                project_id=sample_project["id"],
            )

        # Should update, not import
        assert result2["count"] == 0
        assert "gh-1" in result2["imported"]
        assert "updated 1 existing" in result2["message"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_skip_no_number(self, sync_manager, sample_project):
        """Test import skips issues without number."""
        issues_json = json.dumps(
            [
                {
                    "title": "Issue without number",
                    "body": "Body",
                    "labels": [],
                    "createdAt": "2023-01-01T00:00:00Z",
                }
            ]
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout=issues_json),
            ]

            result = await sync_manager.import_from_github_issues(
                "https://github.com/owner/repo",
                project_id=sample_project["id"],
            )

        assert result["success"] is True
        assert result["count"] == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_json_decode_error(self, sync_manager):
        """Test import handles invalid JSON from gh."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout="not valid json"),
            ]

            result = await sync_manager.import_from_github_issues("https://github.com/owner/repo")

        assert result["success"] is False
        assert "Failed to parse GitHub response" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_finds_project_by_url(self, sync_manager, sample_project):
        """Test import finds project by matching github_url."""
        issues_json = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Issue 1",
                    "body": "Body",
                    "labels": [],
                    "createdAt": "2023-01-01T00:00:00Z",
                }
            ]
        )

        # The sample_project fixture has github_url set
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout=issues_json),
            ]

            result = await sync_manager.import_from_github_issues(
                repo_url=sample_project["github_url"],
            )

        assert result["success"] is True
        assert result["count"] == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_general_exception(self, sync_manager):
        """Test import handles general exceptions."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                Exception("Unexpected error"),
            ]

            result = await sync_manager.import_from_github_issues("https://github.com/owner/repo")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_issues_with_project_context(self, sync_manager, sample_project):
        """Test import uses project context when project_id not provided."""
        issues_json = json.dumps(
            [
                {
                    "number": 1,
                    "title": "Issue 1",
                    "body": "Body",
                    "labels": [],
                    "createdAt": "2023-01-01T00:00:00Z",
                }
            ]
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout=issues_json),
            ]

            # Mock project context to return sample project
            with patch("gobby.utils.project_context.get_project_context") as mock_ctx:
                mock_ctx.return_value = {"id": sample_project["id"]}

                result = await sync_manager.import_from_github_issues(
                    "https://github.com/different/repo"
                )

        assert result["success"] is True
        assert result["count"] == 1
