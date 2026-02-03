"""Tests for task search functionality."""

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.tasks import LocalTaskManager

pytestmark = pytest.mark.unit


@pytest.fixture
def db_with_tasks(tmp_path):
    """Create a database with some tasks for testing."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(db_path)
    run_migrations(db)

    # Create project
    project_id = "test-project-id"
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, repo_path, created_at, updated_at)
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """,
            (project_id, "Test Project", str(tmp_path)),
        )

    manager = LocalTaskManager(db)

    # Create diverse tasks for search testing
    manager.create_task(
        project_id=project_id,
        title="Implement user authentication with JWT",
        description="Add JWT-based authentication to the API endpoints",
        task_type="feature",
        priority=1,
        labels=["auth", "security"],
    )

    manager.create_task(
        project_id=project_id,
        title="Fix database connection timeout",
        description="The database connection pool is timing out under load",
        task_type="bug",
        priority=1,
        labels=["database", "performance"],
    )

    manager.create_task(
        project_id=project_id,
        title="Add user profile page",
        description="Create a profile page where users can update their settings",
        task_type="feature",
        priority=2,
        labels=["ui", "user"],
    )

    manager.create_task(
        project_id=project_id,
        title="Refactor authentication middleware",
        description="Clean up the authentication middleware for better maintainability",
        task_type="task",
        priority=3,
        labels=["auth", "refactor"],
    )

    manager.create_task(
        project_id=project_id,
        title="Update documentation for API",
        description="Write comprehensive API documentation",
        task_type="task",
        priority=2,
        labels=["docs"],
    )

    return db, manager, project_id


class TestTaskSearch:
    """Tests for LocalTaskManager.search_tasks method."""

    def test_search_returns_relevant_results(self, db_with_tasks) -> None:
        """Test that search returns tasks matching the query."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks("authentication", project_id=project_id)

        assert len(results) > 0
        # Check that auth-related tasks are in results
        titles = [task.title for task, score in results]
        assert any("authentication" in t.lower() for t in titles)

    def test_search_with_status_filter(self, db_with_tasks) -> None:
        """Test search with status filter."""
        db, manager, project_id = db_with_tasks

        # All tasks are "open" by default
        results = manager.search_tasks(
            "authentication",
            project_id=project_id,
            status="open",
        )
        assert len(results) > 0

        # No tasks are "closed"
        results = manager.search_tasks(
            "authentication",
            project_id=project_id,
            status="closed",
        )
        assert len(results) == 0

    def test_search_with_status_list(self, db_with_tasks) -> None:
        """Test search with list of statuses."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks(
            "user",
            project_id=project_id,
            status=["open", "in_progress"],
        )
        assert len(results) > 0

    def test_search_with_task_type_filter(self, db_with_tasks) -> None:
        """Test search with task type filter."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks(
            "database",
            project_id=project_id,
            task_type="bug",
        )

        assert len(results) > 0
        for task, _score in results:
            assert task.task_type == "bug"

    def test_search_with_priority_filter(self, db_with_tasks) -> None:
        """Test search with priority filter."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks(
            "user",
            project_id=project_id,
            priority=2,
        )

        for task, _score in results:
            assert task.priority == 2

    def test_search_with_min_score(self, db_with_tasks) -> None:
        """Test search with minimum score threshold."""
        db, manager, project_id = db_with_tasks

        # First get all results
        all_results = manager.search_tasks(
            "user",
            project_id=project_id,
            min_score=0.0,
        )

        # Then filter by min_score
        filtered_results = manager.search_tasks(
            "user",
            project_id=project_id,
            min_score=0.1,
        )

        # Filtered should have same or fewer results
        assert len(filtered_results) <= len(all_results)

        # All filtered results should have score >= 0.1
        for _task, score in filtered_results:
            assert score >= 0.1

    def test_search_with_limit(self, db_with_tasks) -> None:
        """Test search with limit parameter."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks(
            "user",
            project_id=project_id,
            limit=2,
        )

        assert len(results) <= 2

    def test_search_empty_query_returns_empty(self, db_with_tasks) -> None:
        """Test that empty query returns empty results."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks("", project_id=project_id)
        assert len(results) == 0

    def test_search_results_include_scores(self, db_with_tasks) -> None:
        """Test that search results include similarity scores."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks("authentication", project_id=project_id)

        for _task, score in results:
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_search_results_sorted_by_score(self, db_with_tasks) -> None:
        """Test that results are sorted by score descending."""
        db, manager, project_id = db_with_tasks

        results = manager.search_tasks("user", project_id=project_id)

        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    def test_reindex_search(self, db_with_tasks) -> None:
        """Test reindex_search rebuilds the index."""
        db, manager, project_id = db_with_tasks

        # Perform initial search
        results1 = manager.search_tasks("authentication", project_id=project_id)

        # Reindex
        stats = manager.reindex_search(project_id)

        # Check stats
        assert "item_count" in stats
        assert stats["item_count"] > 0

        # Search again should work
        results2 = manager.search_tasks("authentication", project_id=project_id)
        assert len(results1) == len(results2)


class TestTaskSearcher:
    """Tests for the TaskSearcher helper class."""

    def test_build_searchable_content(self) -> None:
        """Test build_searchable_content function."""
        from gobby.storage.tasks._models import Task
        from gobby.storage.tasks._search import build_searchable_content

        # Create a mock task
        task = Task(
            id="test-id",
            project_id="project",
            seq_num=1,
            title="Test Task Title",
            description="A detailed description",
            status="open",
            priority=1,
            task_type="feature",
            category="code",
            labels=["label1", "label2"],
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )

        content = build_searchable_content(task)

        assert "Test Task Title" in content
        assert "detailed description" in content
        assert "label1" in content
        assert "label2" in content
        assert "feature" in content
        assert "code" in content

    def test_task_searcher_fit_and_search(self, db_with_tasks) -> None:
        """Test TaskSearcher fit and search."""
        from gobby.storage.tasks._search import TaskSearcher

        db, manager, project_id = db_with_tasks

        # Get tasks
        tasks = manager.list_tasks(project_id=project_id, limit=100)

        # Create and fit searcher
        searcher = TaskSearcher()
        searcher.fit(tasks)

        # Search
        results = searcher.search("authentication")

        assert len(results) > 0
        # Results should be (task_id, score) tuples
        for task_id, score in results:
            assert isinstance(task_id, str)
            assert isinstance(score, float)

    def test_task_searcher_dirty_tracking(self, db_with_tasks) -> None:
        """Test TaskSearcher dirty flag tracking."""
        from gobby.storage.tasks._search import TaskSearcher

        db, manager, project_id = db_with_tasks
        tasks = manager.list_tasks(project_id=project_id, limit=100)

        searcher = TaskSearcher()

        # Initially dirty
        assert searcher.needs_refit()

        # After fit with real tasks, not dirty
        searcher.fit(tasks)
        assert not searcher.needs_refit()

        # After mark_dirty, dirty again
        searcher.mark_dirty()
        assert searcher.needs_refit()
