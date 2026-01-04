"""Tests for ValidationHistoryManager."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from gobby.tasks.validation_history import ValidationHistoryManager, ValidationIteration
from gobby.tasks.validation_models import Issue, IssueSeverity, IssueType


@pytest.fixture
def history_manager(temp_db):
    """Create a ValidationHistoryManager with test database."""
    return ValidationHistoryManager(temp_db)


@pytest.fixture
def sample_project(temp_db):
    """Create a sample project for tests."""
    temp_db.execute(
        """INSERT INTO projects (id, name, created_at, updated_at)
           VALUES (?, ?, datetime('now'), datetime('now'))""",
        ("test-project", "Test Project"),
    )
    return {"id": "test-project", "name": "Test Project"}


@pytest.fixture
def sample_task(temp_db, sample_project):
    """Create a sample task for tests."""
    temp_db.execute(
        """INSERT INTO tasks (id, project_id, title, status, priority, type, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        ("gt-test123", sample_project["id"], "Test Task", "open", 2, "task"),
    )
    return {"id": "gt-test123"}


class TestValidationHistoryManager:
    """Tests for ValidationHistoryManager class."""

    def test_record_iteration_stores_data(self, history_manager, sample_task):
        """Test that record_iteration stores iteration data in database."""
        issues = [
            Issue(
                issue_type=IssueType.TEST_FAILURE,
                severity=IssueSeverity.MAJOR,
                title="Test failed",
            )
        ]

        history_manager.record_iteration(
            task_id=sample_task["id"],
            iteration=1,
            status="invalid",
            feedback="Tests are failing",
            issues=issues,
            context_type="git_diff",
            context_summary="Modified 3 files",
            validator_type="llm",
        )

        # Verify record exists in database
        history = history_manager.get_iteration_history(sample_task["id"])
        assert len(history) == 1
        assert history[0].iteration == 1
        assert history[0].status == "invalid"
        assert history[0].feedback == "Tests are failing"

    def test_record_multiple_iterations(self, history_manager, sample_task):
        """Test recording multiple iterations for same task."""
        for i in range(1, 4):
            history_manager.record_iteration(
                task_id=sample_task["id"],
                iteration=i,
                status="invalid" if i < 3 else "valid",
                feedback=f"Iteration {i}",
            )

        history = history_manager.get_iteration_history(sample_task["id"])
        assert len(history) == 3
        assert history[0].iteration == 1
        assert history[1].iteration == 2
        assert history[2].iteration == 3

    def test_get_iteration_history_returns_all_iterations(self, history_manager, sample_task):
        """Test that get_iteration_history returns all iterations for a task."""
        # Record multiple iterations with different data
        history_manager.record_iteration(
            task_id=sample_task["id"],
            iteration=1,
            status="invalid",
            feedback="First attempt",
            validator_type="llm",
        )
        history_manager.record_iteration(
            task_id=sample_task["id"],
            iteration=2,
            status="valid",
            feedback="Fixed",
            validator_type="llm",
        )

        history = history_manager.get_iteration_history(sample_task["id"])

        assert len(history) == 2
        assert all(isinstance(item, ValidationIteration) for item in history)

    def test_history_includes_issues(self, history_manager, sample_task):
        """Test that history includes serialized issues."""
        issues = [
            Issue(
                issue_type=IssueType.TEST_FAILURE,
                severity=IssueSeverity.BLOCKER,
                title="Critical test failure",
                location="tests/test_core.py:42",
            ),
            Issue(
                issue_type=IssueType.LINT_ERROR,
                severity=IssueSeverity.MINOR,
                title="Unused import",
            ),
        ]

        history_manager.record_iteration(
            task_id=sample_task["id"],
            iteration=1,
            status="invalid",
            issues=issues,
        )

        history = history_manager.get_iteration_history(sample_task["id"])
        assert len(history[0].issues) == 2
        assert history[0].issues[0].title == "Critical test failure"
        assert history[0].issues[1].title == "Unused import"

    def test_history_includes_context(self, history_manager, sample_task):
        """Test that history includes context information."""
        history_manager.record_iteration(
            task_id=sample_task["id"],
            iteration=1,
            status="invalid",
            context_type="git_diff",
            context_summary="Changed auth.py: +50/-20 lines",
        )

        history = history_manager.get_iteration_history(sample_task["id"])
        assert history[0].context_type == "git_diff"
        assert history[0].context_summary == "Changed auth.py: +50/-20 lines"

    def test_history_includes_validator_type(self, history_manager, sample_task):
        """Test that history includes validator type."""
        history_manager.record_iteration(
            task_id=sample_task["id"],
            iteration=1,
            status="invalid",
            validator_type="external_webhook",
        )

        history = history_manager.get_iteration_history(sample_task["id"])
        assert history[0].validator_type == "external_webhook"

    def test_clear_history_removes_all_iterations(self, history_manager, sample_task):
        """Test that clear_history removes all iterations for a task."""
        # Add several iterations
        for i in range(1, 4):
            history_manager.record_iteration(
                task_id=sample_task["id"],
                iteration=i,
                status="invalid",
            )

        # Verify they exist
        assert len(history_manager.get_iteration_history(sample_task["id"])) == 3

        # Clear history
        history_manager.clear_history(sample_task["id"])

        # Verify they're gone
        assert len(history_manager.get_iteration_history(sample_task["id"])) == 0

    def test_clear_history_only_affects_target_task(self, history_manager, temp_db, sample_project, sample_task):
        """Test that clear_history only affects the target task."""
        # Create a second task
        temp_db.execute(
            """INSERT INTO tasks (id, project_id, title, status, priority, type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            ("gt-other", sample_project["id"], "Other Task", "open", 2, "task"),
        )

        # Add history to both tasks
        history_manager.record_iteration(task_id=sample_task["id"], iteration=1, status="invalid")
        history_manager.record_iteration(task_id="gt-other", iteration=1, status="invalid")

        # Clear only first task
        history_manager.clear_history(sample_task["id"])

        # First task should have no history
        assert len(history_manager.get_iteration_history(sample_task["id"])) == 0
        # Second task should still have history
        assert len(history_manager.get_iteration_history("gt-other")) == 1

    def test_get_latest_iteration(self, history_manager, sample_task):
        """Test getting the latest iteration for a task."""
        history_manager.record_iteration(task_id=sample_task["id"], iteration=1, status="invalid")
        history_manager.record_iteration(task_id=sample_task["id"], iteration=2, status="invalid")
        history_manager.record_iteration(task_id=sample_task["id"], iteration=3, status="valid")

        latest = history_manager.get_latest_iteration(sample_task["id"])

        assert latest is not None
        assert latest.iteration == 3
        assert latest.status == "valid"

    def test_get_latest_iteration_empty_history(self, history_manager, sample_task):
        """Test get_latest_iteration returns None for empty history."""
        latest = history_manager.get_latest_iteration(sample_task["id"])
        assert latest is None

    def test_concurrent_iteration_recording(self, history_manager, sample_task):
        """Test that concurrent iteration recording is safe."""
        def record_iteration(iteration_num):
            history_manager.record_iteration(
                task_id=sample_task["id"],
                iteration=iteration_num,
                status="invalid",
                feedback=f"Concurrent {iteration_num}",
            )

        # Record 10 iterations concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(record_iteration, range(1, 11))

        # All should be recorded
        history = history_manager.get_iteration_history(sample_task["id"])
        assert len(history) == 10

    def test_validation_iteration_dataclass(self, history_manager, sample_task):
        """Test ValidationIteration dataclass structure."""
        issues = [
            Issue(
                issue_type=IssueType.SECURITY,
                severity=IssueSeverity.BLOCKER,
                title="SQL injection",
            )
        ]

        history_manager.record_iteration(
            task_id=sample_task["id"],
            iteration=1,
            status="invalid",
            feedback="Security issue found",
            issues=issues,
            context_type="code_review",
            context_summary="Reviewed db.py",
            validator_type="llm",
        )

        history = history_manager.get_iteration_history(sample_task["id"])
        iteration = history[0]

        # Check all expected fields exist
        assert hasattr(iteration, "id")
        assert hasattr(iteration, "task_id")
        assert hasattr(iteration, "iteration")
        assert hasattr(iteration, "status")
        assert hasattr(iteration, "feedback")
        assert hasattr(iteration, "issues")
        assert hasattr(iteration, "context_type")
        assert hasattr(iteration, "context_summary")
        assert hasattr(iteration, "validator_type")
        assert hasattr(iteration, "created_at")

        assert iteration.task_id == sample_task["id"]
        assert iteration.status == "invalid"
