"""Tests for artifact tags junction table and CRUD methods."""

from typing import TYPE_CHECKING

import pytest

from gobby.storage.artifacts import LocalArtifactManager

if TYPE_CHECKING:
    from gobby.storage.database import LocalDatabase

pytestmark = pytest.mark.unit


@pytest.fixture
def artifact_manager(temp_db: "LocalDatabase") -> LocalArtifactManager:
    """Create an artifact manager with temp database and a test session."""
    with temp_db.transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (id, external_id, machine_id, source, project_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("sess-tags", "ext-tags", "machine-001", "claude", "00000000-0000-0000-0000-000000000000", "active"),
        )
    return LocalArtifactManager(temp_db)


@pytest.fixture
def sample_artifact(artifact_manager: LocalArtifactManager):
    """Create a sample artifact for tag tests."""
    return artifact_manager.create_artifact(
        session_id="sess-tags",
        artifact_type="code",
        content="def hello(): pass",
        title="Hello function",
    )


class TestArtifactTags:
    """Tests for artifact tag CRUD operations."""

    def test_add_tag_creates_tag(
        self, artifact_manager: LocalArtifactManager, sample_artifact
    ) -> None:
        """Test that add_tag() creates a tag for an artifact."""
        result = artifact_manager.add_tag(sample_artifact.id, "important")
        assert result is True

        tags = artifact_manager.get_tags(sample_artifact.id)
        assert "important" in tags

    def test_add_tag_is_idempotent(
        self, artifact_manager: LocalArtifactManager, sample_artifact
    ) -> None:
        """Test that adding the same tag twice doesn't error."""
        artifact_manager.add_tag(sample_artifact.id, "auth")
        result = artifact_manager.add_tag(sample_artifact.id, "auth")
        assert result is True

        tags = artifact_manager.get_tags(sample_artifact.id)
        assert tags.count("auth") == 1

    def test_remove_tag_removes_existing(
        self, artifact_manager: LocalArtifactManager, sample_artifact
    ) -> None:
        """Test that remove_tag() removes an existing tag."""
        artifact_manager.add_tag(sample_artifact.id, "temp")
        result = artifact_manager.remove_tag(sample_artifact.id, "temp")
        assert result is True

        tags = artifact_manager.get_tags(sample_artifact.id)
        assert "temp" not in tags

    def test_remove_tag_returns_false_for_nonexistent(
        self, artifact_manager: LocalArtifactManager, sample_artifact
    ) -> None:
        """Test that remove_tag() returns False for non-existent tag."""
        result = artifact_manager.remove_tag(sample_artifact.id, "nonexistent")
        assert result is False

    def test_get_tags_returns_all_tags(
        self, artifact_manager: LocalArtifactManager, sample_artifact
    ) -> None:
        """Test that get_tags() returns all tags for an artifact."""
        artifact_manager.add_tag(sample_artifact.id, "auth")
        artifact_manager.add_tag(sample_artifact.id, "refactor")
        artifact_manager.add_tag(sample_artifact.id, "v2")

        tags = artifact_manager.get_tags(sample_artifact.id)
        assert set(tags) == {"auth", "refactor", "v2"}

    def test_get_tags_empty_for_untagged(
        self, artifact_manager: LocalArtifactManager, sample_artifact
    ) -> None:
        """Test that get_tags() returns empty list for untagged artifact."""
        tags = artifact_manager.get_tags(sample_artifact.id)
        assert tags == []

    def test_list_by_tag_returns_matching_artifacts(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test that list_by_tag() returns artifacts with the given tag."""
        a1 = artifact_manager.create_artifact(
            session_id="sess-tags", artifact_type="code", content="func a()"
        )
        a2 = artifact_manager.create_artifact(
            session_id="sess-tags", artifact_type="code", content="func b()"
        )
        a3 = artifact_manager.create_artifact(
            session_id="sess-tags", artifact_type="code", content="func c()"
        )

        artifact_manager.add_tag(a1.id, "api")
        artifact_manager.add_tag(a2.id, "api")
        artifact_manager.add_tag(a3.id, "internal")

        results = artifact_manager.list_by_tag("api")
        result_ids = {a.id for a in results}
        assert a1.id in result_ids
        assert a2.id in result_ids
        assert a3.id not in result_ids

    def test_list_by_tag_empty_for_unused_tag(
        self, artifact_manager: LocalArtifactManager
    ) -> None:
        """Test that list_by_tag() returns empty for unused tag."""
        results = artifact_manager.list_by_tag("nonexistent")
        assert results == []

    def test_cascade_delete_removes_tags(
        self, artifact_manager: LocalArtifactManager, sample_artifact
    ) -> None:
        """Test that deleting an artifact cascades to delete its tags."""
        artifact_manager.add_tag(sample_artifact.id, "will-be-deleted")
        assert "will-be-deleted" in artifact_manager.get_tags(sample_artifact.id)

        artifact_manager.delete_artifact(sample_artifact.id)

        # Tags should be gone after artifact deletion
        tags = artifact_manager.get_tags(sample_artifact.id)
        assert tags == []
