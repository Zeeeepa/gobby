"""Tests for artifacts REST API routes."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gobby.app_context import ServiceContainer
from gobby.servers.http import HTTPServer
from gobby.storage.artifacts import Artifact, LocalArtifactManager
from gobby.storage.database import LocalDatabase
from gobby.storage.sessions import LocalSessionManager

pytestmark = pytest.mark.unit


@pytest.fixture
def session_storage(temp_db: LocalDatabase) -> LocalSessionManager:
    """Create session storage."""
    return LocalSessionManager(temp_db)


@pytest.fixture
def artifact_manager(temp_db: LocalDatabase) -> LocalArtifactManager:
    """Create an artifact manager for testing."""
    return LocalArtifactManager(temp_db)


@pytest.fixture
def http_server(
    session_storage: LocalSessionManager,
    temp_dir: Path,
) -> HTTPServer:
    """Create an HTTP server instance for testing."""
    services = ServiceContainer(
        config=None,
        database=session_storage.db,
        session_manager=session_storage,
        task_manager=MagicMock(),
    )
    return HTTPServer(
        services=services,
        port=60887,
        test_mode=True,
    )


@pytest.fixture
def sample_session_id(temp_db: LocalDatabase) -> str:
    """Create a test session and return its ID."""
    session_id = "sess-art-test-001"
    with temp_db.transaction() as conn:
        # Create project first (sessions FK references projects)
        conn.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            ("proj-001", "test-project", "/tmp/test"),
        )
        conn.execute(
            "INSERT INTO sessions (id, external_id, machine_id, source, project_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, "ext-001", "machine-001", "claude", "proj-001", "active"),
        )
    return session_id


@pytest.fixture
def sample_artifacts(artifact_manager: LocalArtifactManager, sample_session_id: str) -> list[Artifact]:
    """Create sample artifacts and return them."""
    a1 = artifact_manager.create_artifact(
        session_id=sample_session_id,
        artifact_type="code",
        content="def hello(): pass",
        title="Hello function",
    )
    a2 = artifact_manager.create_artifact(
        session_id=sample_session_id,
        artifact_type="error",
        content="TypeError: cannot add str and int",
        title="Type error",
        task_id="task-001",
    )
    a3 = artifact_manager.create_artifact(
        session_id=sample_session_id,
        artifact_type="code",
        content="class Foo:\n    pass",
        title="Foo class",
    )
    return [a1, a2, a3]


@pytest.fixture
def client(http_server: HTTPServer, artifact_manager: LocalArtifactManager) -> Iterator[TestClient]:
    """Create a test client with artifact manager pre-initialized."""
    # Pre-set the artifact manager so _get_manager() finds it
    http_server._artifact_manager = artifact_manager

    with patch("gobby.servers.http.HookManager") as MockHM:
        mock_instance = MockHM.return_value
        mock_instance._stop_registry = MagicMock()
        mock_instance._workflow_handler = MagicMock()
        mock_instance.shutdown = MagicMock()
        with TestClient(http_server.app) as c:
            yield c


class TestListArtifacts:
    """Tests for GET /artifacts."""

    def test_list_empty(self, client: TestClient) -> None:
        response = client.get("/artifacts")
        assert response.status_code == 200
        data = response.json()
        assert data["artifacts"] == []
        assert data["count"] == 0

    def test_list_with_artifacts(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert len(data["artifacts"]) == 3

    def test_list_filter_by_session(
        self, client: TestClient, sample_artifacts, sample_session_id: str
    ) -> None:
        response = client.get(f"/artifacts?session_id={sample_session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3

    def test_list_filter_by_type(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts?artifact_type=code")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert all(a["artifact_type"] == "code" for a in data["artifacts"])

    def test_list_filter_by_task_id(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts?task_id=task-001")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["artifacts"][0]["task_id"] == "task-001"

    def test_list_with_tag_filter(
        self, client: TestClient, sample_artifacts, artifact_manager: LocalArtifactManager
    ) -> None:
        artifact_manager.add_tag(sample_artifacts[0].id, "important")
        response = client.get("/artifacts?tag=important")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    def test_list_pagination(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2

    def test_list_pagination_offset(self, client: TestClient, sample_artifacts) -> None:
        """Verify offset produces disjoint results from first page."""
        page1 = client.get("/artifacts?limit=2&offset=0").json()
        page2 = client.get("/artifacts?limit=2&offset=2").json()
        page1_ids = {a["id"] for a in page1["artifacts"]}
        page2_ids = {a["id"] for a in page2["artifacts"]}
        assert page1_ids.isdisjoint(page2_ids)
        assert page2["count"] == 1  # 3 total, offset=2 gives 1

    def test_list_includes_tags(
        self, client: TestClient, sample_artifacts, artifact_manager: LocalArtifactManager
    ) -> None:
        artifact_manager.add_tag(sample_artifacts[0].id, "tagged")
        response = client.get("/artifacts")
        assert response.status_code == 200
        data = response.json()
        tagged = [a for a in data["artifacts"] if a["id"] == sample_artifacts[0].id]
        assert len(tagged) == 1
        assert "tagged" in tagged[0]["tags"]


class TestSearchArtifacts:
    """Tests for GET /artifacts/search."""

    def test_search(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts/search?q=hello")
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "hello"
        assert data["count"] >= 1

    def test_search_with_type_filter(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts/search?q=def&artifact_type=code")
        assert response.status_code == 200
        data = response.json()
        assert all(a["artifact_type"] == "code" for a in data["artifacts"])

    def test_search_with_task_filter(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts/search?q=TypeError&task_id=task-001")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        assert all(a["task_id"] == "task-001" for a in data["artifacts"])


class TestGetArtifact:
    """Tests for GET /artifacts/{artifact_id}."""

    def test_get_artifact(self, client: TestClient, sample_artifacts) -> None:
        artifact = sample_artifacts[0]
        response = client.get(f"/artifacts/{artifact.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == artifact.id
        assert data["content"] == "def hello(): pass"
        assert "tags" in data

    def test_get_artifact_not_found(self, client: TestClient) -> None:
        response = client.get("/artifacts/nonexistent-id")
        assert response.status_code == 404


class TestDeleteArtifact:
    """Tests for DELETE /artifacts/{artifact_id}."""

    def test_delete_artifact(self, client: TestClient, sample_artifacts) -> None:
        artifact = sample_artifacts[0]
        response = client.delete(f"/artifacts/{artifact.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True

        # Verify it's gone
        response = client.get(f"/artifacts/{artifact.id}")
        assert response.status_code == 404

    def test_delete_artifact_not_found(self, client: TestClient) -> None:
        response = client.delete("/artifacts/nonexistent-id")
        assert response.status_code == 404


class TestArtifactTags:
    """Tests for POST/DELETE /artifacts/{artifact_id}/tags."""

    def test_add_tag(self, client: TestClient, sample_artifacts) -> None:
        artifact = sample_artifacts[0]
        response = client.post(
            f"/artifacts/{artifact.id}/tags",
            json={"tag": "reviewed"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["tag"] == "reviewed"

    def test_add_tag_artifact_not_found(self, client: TestClient) -> None:
        response = client.post(
            "/artifacts/nonexistent-id/tags",
            json={"tag": "test"},
        )
        assert response.status_code == 404

    def test_remove_tag(
        self, client: TestClient, sample_artifacts, artifact_manager: LocalArtifactManager
    ) -> None:
        artifact = sample_artifacts[0]
        artifact_manager.add_tag(artifact.id, "to-remove")
        response = client.delete(f"/artifacts/{artifact.id}/tags/to-remove")
        assert response.status_code == 200
        data = response.json()
        assert data["removed"] is True

    def test_remove_tag_not_found(self, client: TestClient, sample_artifacts) -> None:
        artifact = sample_artifacts[0]
        response = client.delete(f"/artifacts/{artifact.id}/tags/nonexistent")
        assert response.status_code == 404


class TestArtifactStats:
    """Tests for GET /artifacts/stats."""

    def test_stats_empty(self, client: TestClient) -> None:
        response = client.get("/artifacts/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0

    def test_stats_with_artifacts(self, client: TestClient, sample_artifacts) -> None:
        response = client.get("/artifacts/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 3
        assert data["by_type"]["code"] == 2
        assert data["by_type"]["error"] == 1


class TestTimeline:
    """Tests for GET /artifacts/timeline/{session_id}."""

    def test_timeline(self, client: TestClient, sample_artifacts, sample_session_id: str) -> None:
        response = client.get(f"/artifacts/timeline/{sample_session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == sample_session_id
        assert data["count"] == 3
        # Timeline should be chronological (oldest first)
        timestamps = [a["created_at"] for a in data["artifacts"]]
        assert timestamps == sorted(timestamps)

    def test_timeline_filter_by_type(
        self, client: TestClient, sample_artifacts, sample_session_id: str
    ) -> None:
        response = client.get(
            f"/artifacts/timeline/{sample_session_id}?artifact_type=error"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["artifacts"][0]["artifact_type"] == "error"
