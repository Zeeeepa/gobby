"""Tests for artifacts schema enhancements: title and task_id columns."""

from typing import TYPE_CHECKING

import pytest

from gobby.storage.artifacts import Artifact, LocalArtifactManager

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

pytestmark = pytest.mark.unit


@pytest.fixture
def artifact_manager(temp_db: "LocalDatabase") -> LocalArtifactManager:
    """Create an artifact manager with temp database."""
    # Create a test session to satisfy FK constraint
    with temp_db.transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (id, external_id, machine_id, source, project_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("sess-001", "ext-001", "machine-001", "claude", "00000000-0000-0000-0000-000000000000", "active"),
        )
    return LocalArtifactManager(temp_db)


class TestArtifactTitleAndTaskId:
    """Tests for title and task_id columns on session_artifacts."""

    def test_create_artifact_with_title_and_task_id(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test creating an artifact with title and task_id stores correctly."""
        artifact = artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="code",
            content="def hello(): pass",
            title="Hello function",
            task_id="task-001",
        )

        assert artifact.title == "Hello function"
        assert artifact.task_id == "task-001"

    def test_create_artifact_without_title_defaults_to_none(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test creating artifact without title/task_id defaults to None."""
        artifact = artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="code",
            content="x = 1",
        )

        assert artifact.title is None
        assert artifact.task_id is None

    def test_artifact_from_row_handles_new_fields(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test that Artifact.from_row() reads title and task_id."""
        created = artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="error",
            content="ValueError: bad input",
            title="ValueError",
            task_id="task-002",
        )

        # Re-fetch from DB to verify from_row works
        fetched = artifact_manager.get_artifact(created.id)
        assert fetched is not None
        assert fetched.title == "ValueError"
        assert fetched.task_id == "task-002"

    def test_artifact_to_dict_includes_new_fields(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test that to_dict() includes title and task_id."""
        artifact = artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="code",
            content="print('hi')",
            title="Print statement",
            task_id="task-003",
        )

        d = artifact.to_dict()
        assert "title" in d
        assert d["title"] == "Print statement"
        assert "task_id" in d
        assert d["task_id"] == "task-003"

    def test_to_dict_with_none_fields(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test that to_dict() includes None for unset title/task_id."""
        artifact = artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="text",
            content="some text",
        )

        d = artifact.to_dict()
        assert d["title"] is None
        assert d["task_id"] is None

    def test_list_artifacts_backward_compat(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test that list_artifacts works with existing data (no title/task_id)."""
        # Create artifacts both with and without new fields
        artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="code",
            content="old style artifact",
        )
        artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="code",
            content="new style artifact",
            title="New artifact",
            task_id="task-001",
        )

        artifacts = artifact_manager.list_artifacts(session_id="sess-001")
        assert len(artifacts) == 2

        # All artifacts should have title/task_id attributes
        for a in artifacts:
            assert hasattr(a, "title")
            assert hasattr(a, "task_id")

    def test_search_artifacts_includes_new_fields(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test that search results include title and task_id."""
        artifact_manager.create_artifact(
            session_id="sess-001",
            artifact_type="code",
            content="def unique_search_test(): pass",
            title="Unique search function",
            task_id="task-004",
        )

        results = artifact_manager.search_artifacts(query_text="unique_search_test")
        assert len(results) >= 1
        found = results[0]
        assert found.title == "Unique search function"
        assert found.task_id == "task-004"
