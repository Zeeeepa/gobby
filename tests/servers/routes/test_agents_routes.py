"""Tests for agent definition API routes - real coverage, minimal mocking.

Exercises src/gobby/servers/routes/agents.py endpoints using
create_http_server() with a real LocalAgentDefinitionManager backed by temp_db.
Only the AgentDefinitionLoader (which scans files) is mocked where needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from gobby.agents.definitions import AgentDefinition
from gobby.config.app import DaemonConfig
from gobby.storage.agent_definitions import AgentDefinitionRow, LocalAgentDefinitionManager
from gobby.storage.tasks import LocalTaskManager
from tests.servers.conftest import create_http_server

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loader_item(
    name: str,
    source: str = "built-in-file",
    source_path: str | None = None,
    **overrides: Any,
) -> MagicMock:
    """Create a mock AgentDefinitionItem for the AgentDefinitionLoader."""
    defn = MagicMock()
    defn.name = name
    defn.description = overrides.get("description", f"Agent {name}")
    defn.provider = overrides.get("provider", "claude")
    defn.model = overrides.get("model")
    defn.mode = overrides.get("mode", "headless")
    defn.terminal = overrides.get("terminal", "auto")
    defn.isolation = overrides.get("isolation")
    defn.base_branch = overrides.get("base_branch", "main")
    defn.timeout = overrides.get("timeout", 120.0)
    defn.max_turns = overrides.get("max_turns", 10)
    defn.default_workflow = overrides.get("default_workflow")
    defn.sandbox = None
    defn.skill_profile = None
    defn.workflows = None
    defn.lifecycle_variables = None
    defn.default_variables = None
    defn.role = None
    defn.goal = None
    defn.personality = None
    defn.instructions = None

    item = MagicMock()
    item.definition = defn
    item.source = source
    item.source_path = source_path
    item.to_api_dict.return_value = {
        "name": name,
        "source": source,
        "description": defn.description,
        "provider": defn.provider,
    }

    # model_dump for YAML export
    defn.model_dump.return_value = {
        "name": name,
        "provider": "claude",
        "mode": "headless",
    }

    return item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def task_manager(temp_db) -> LocalTaskManager:
    return LocalTaskManager(temp_db)


@pytest.fixture
def agent_manager(temp_db) -> LocalAgentDefinitionManager:
    return LocalAgentDefinitionManager(temp_db)


@pytest.fixture
def server(temp_db, task_manager):
    return create_http_server(
        config=DaemonConfig(),
        database=temp_db,
        task_manager=task_manager,
    )


@pytest.fixture
def client(server) -> TestClient:
    return TestClient(server.app)


# ---------------------------------------------------------------------------
# GET /api/agents/definitions  (list)
# ---------------------------------------------------------------------------


class TestListDefinitions:
    def test_list_empty_db(self, client: TestClient) -> None:
        """When no file-based or DB definitions exist, list returns empty."""
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = []
            response = client.get("/api/agents/definitions")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] == 0
        assert data["definitions"] == []

    def test_list_with_file_definitions(self, client: TestClient) -> None:
        items = [_make_loader_item("worker"), _make_loader_item("coordinator")]
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = items
            response = client.get("/api/agents/definitions")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        names = [d["name"] for d in data["definitions"]]
        assert "worker" in names
        assert "coordinator" in names

    def test_list_with_project_filter(self, client: TestClient) -> None:
        items = [_make_loader_item("scoped")]
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = items
            response = client.get("/api/agents/definitions?project_id=proj-1")
        assert response.status_code == 200
        mock_cls.return_value.list_all.assert_called_once_with(project_id="proj-1")

    def test_list_error(self, client: TestClient) -> None:
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.side_effect = RuntimeError("DB error")
            response = client.get("/api/agents/definitions")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/agents/definitions/{name}  (get single)
# ---------------------------------------------------------------------------


class TestGetDefinition:
    def test_get_existing(self, client: TestClient) -> None:
        item = _make_loader_item("worker")
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = [item]
            response = client.get("/api/agents/definitions/worker")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["definition"]["name"] == "worker"

    def test_get_not_found(self, client: TestClient) -> None:
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = []
            response = client.get("/api/agents/definitions/nonexistent")
        assert response.status_code == 404

    def test_get_with_project_id(self, client: TestClient) -> None:
        item = _make_loader_item("scoped")
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = [item]
            response = client.get("/api/agents/definitions/scoped?project_id=proj-1")
        assert response.status_code == 200

    def test_get_selects_correct_name(self, client: TestClient) -> None:
        """When multiple definitions exist, get returns the one matching name."""
        items = [_make_loader_item("alpha"), _make_loader_item("beta")]
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = items
            response = client.get("/api/agents/definitions/beta")
        assert response.status_code == 200
        assert response.json()["definition"]["name"] == "beta"

    def test_get_error(self, client: TestClient) -> None:
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.side_effect = RuntimeError("Boom")
            response = client.get("/api/agents/definitions/worker")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/agents/definitions/{name}/export
# ---------------------------------------------------------------------------


class TestExportDefinition:
    def test_export_file_based(self, client: TestClient, tmp_path: Path) -> None:
        """Export a file-based definition reads the original YAML."""
        yaml_file = tmp_path / "worker.yaml"
        yaml_content = "name: worker\nprovider: claude\n"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        item = _make_loader_item("worker", source_path=str(yaml_file))
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = [item]
            response = client.get("/api/agents/definitions/worker/export")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-yaml"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert response.text == yaml_content

    def test_export_file_based_missing_file(self, client: TestClient) -> None:
        """If source file is gone, fall back to model serialization."""
        item = _make_loader_item("worker", source_path="/nonexistent/path/worker.yaml")
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = [item]
            response = client.get("/api/agents/definitions/worker/export")
        assert response.status_code == 200
        assert "name: worker" in response.text

    def test_export_db_backed(self, client: TestClient) -> None:
        """DB-backed definitions (no source_path) serialize from model."""
        item = _make_loader_item("db-agent", source_path=None)
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = [item]
            response = client.get("/api/agents/definitions/db-agent/export")
        assert response.status_code == 200
        assert "name: db-agent" in response.text

    def test_export_not_found(self, client: TestClient) -> None:
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.return_value = []
            response = client.get("/api/agents/definitions/missing/export")
        assert response.status_code == 404

    def test_export_error(self, client: TestClient) -> None:
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.list_all.side_effect = RuntimeError("Boom")
            response = client.get("/api/agents/definitions/worker/export")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/agents/definitions  (create in DB)
# ---------------------------------------------------------------------------


class TestCreateDefinition:
    def test_create_basic(self, client: TestClient) -> None:
        """Create a minimal agent definition."""
        response = client.post(
            "/api/agents/definitions",
            json={"name": "test-agent"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["definition"]["name"] == "test-agent"
        assert "id" in data["definition"]

    def test_create_with_all_fields(self, client: TestClient) -> None:
        response = client.post(
            "/api/agents/definitions",
            json={
                "name": "full-agent",
                "description": "A fully specified agent",
                "role": "Developer",
                "goal": "Write code",
                "personality": "Helpful",
                "instructions": "Do your best",
                "provider": "claude",
                "model": "opus",
                "mode": "terminal",
                "terminal": "ghostty",
                "isolation": "clone",
                "base_branch": "develop",
                "timeout": 300.0,
                "max_turns": 20,
                "default_workflow": "worker",
                "sandbox_config": {"network": False},
                "skill_profile": {"audience": "developer"},
                "workflows": {"worker": {"file": "worker.yaml"}},
                "lifecycle_variables": {"verbose": True},
                "default_variables": {"lang": "python"},
            },
        )
        assert response.status_code == 200
        defn = response.json()["definition"]
        assert defn["name"] == "full-agent"
        assert defn["description"] == "A fully specified agent"
        assert defn["provider"] == "claude"
        assert defn["mode"] == "terminal"
        assert defn["timeout"] == 300.0
        assert defn["max_turns"] == 20

    def test_create_with_project_id(self, client: TestClient, project_manager) -> None:
        project = project_manager.create(name="agent-proj", repo_path="/tmp/agent-proj")
        response = client.post(
            "/api/agents/definitions",
            json={"name": "scoped-agent", "project_id": project.id},
        )
        assert response.status_code == 200
        assert response.json()["definition"]["project_id"] == project.id

    def test_create_duplicate_name_fails(self, client: TestClient) -> None:
        """DB enforces UNIQUE constraint on definition name."""
        resp1 = client.post("/api/agents/definitions", json={"name": "dup"})
        assert resp1.status_code == 200
        resp2 = client.post("/api/agents/definitions", json={"name": "dup"})
        assert resp2.status_code == 500


# ---------------------------------------------------------------------------
# PUT /api/agents/definitions/{definition_id}  (update)
# ---------------------------------------------------------------------------


class TestUpdateDefinition:
    def test_update_fields(self, client: TestClient) -> None:
        # Create first
        create_resp = client.post(
            "/api/agents/definitions",
            json={"name": "updatable"},
        )
        defn_id = create_resp.json()["definition"]["id"]

        response = client.put(
            f"/api/agents/definitions/{defn_id}",
            json={"name": "updated-name", "description": "Now with desc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["definition"]["name"] == "updated-name"
        assert data["definition"]["description"] == "Now with desc"

    def test_update_no_fields_returns_400(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/agents/definitions",
            json={"name": "no-update"},
        )
        defn_id = create_resp.json()["definition"]["id"]

        response = client.put(
            f"/api/agents/definitions/{defn_id}",
            json={},
        )
        assert response.status_code == 400
        assert "No fields to update" in response.json()["detail"]

    def test_update_not_found(self, client: TestClient) -> None:
        response = client.put(
            "/api/agents/definitions/nonexistent-id",
            json={"name": "new"},
        )
        assert response.status_code == 404

    def test_update_enabled_field(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/agents/definitions",
            json={"name": "toggle"},
        )
        defn_id = create_resp.json()["definition"]["id"]

        response = client.put(
            f"/api/agents/definitions/{defn_id}",
            json={"enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["definition"]["enabled"] is False

    def test_update_json_fields(self, client: TestClient) -> None:
        """Update fields that are stored as JSON (sandbox_config, etc)."""
        create_resp = client.post(
            "/api/agents/definitions",
            json={"name": "json-fields"},
        )
        defn_id = create_resp.json()["definition"]["id"]

        response = client.put(
            f"/api/agents/definitions/{defn_id}",
            json={
                "sandbox_config": {"network": True},
                "skill_profile": {"audience": "test"},
                "workflows": {"w1": {"file": "w1.yaml"}},
            },
        )
        assert response.status_code == 200
        defn = response.json()["definition"]
        assert defn["sandbox_config"] == {"network": True}
        assert defn["skill_profile"] == {"audience": "test"}


# ---------------------------------------------------------------------------
# DELETE /api/agents/definitions/{definition_id}
# ---------------------------------------------------------------------------


class TestDeleteDefinition:
    def test_delete_existing(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/agents/definitions",
            json={"name": "deletable"},
        )
        defn_id = create_resp.json()["definition"]["id"]

        response = client.delete(f"/api/agents/definitions/{defn_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["deleted"] is True

    def test_delete_not_found(self, client: TestClient) -> None:
        response = client.delete("/api/agents/definitions/nonexistent-id")
        assert response.status_code == 404

    def test_delete_idempotent(self, client: TestClient) -> None:
        """Deleting the same ID twice returns 404 on second attempt."""
        create_resp = client.post(
            "/api/agents/definitions",
            json={"name": "once-only"},
        )
        defn_id = create_resp.json()["definition"]["id"]
        client.delete(f"/api/agents/definitions/{defn_id}")
        response = client.delete(f"/api/agents/definitions/{defn_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/agents/definitions/import/{name}
# ---------------------------------------------------------------------------


class TestImportDefinition:
    def test_import_from_file(self, client: TestClient) -> None:
        """Import a file-based definition into the DB."""
        defn = AgentDefinition(name="importable", description="Imported agent")

        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.load.return_value = defn
            response = client.post("/api/agents/definitions/import/importable")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["definition"]["name"] == "importable"

    def test_import_not_found(self, client: TestClient) -> None:
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.load.return_value = None
            response = client.post("/api/agents/definitions/import/missing")
        assert response.status_code == 404

    def test_import_with_project_id(self, client: TestClient, project_manager) -> None:
        project = project_manager.create(name="import-proj", repo_path="/tmp/import-proj")
        defn = AgentDefinition(name="proj-agent")

        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.load.return_value = defn
            response = client.post(
                f"/api/agents/definitions/import/proj-agent?project_id={project.id}"
            )
        assert response.status_code == 200
        assert response.json()["definition"]["project_id"] == project.id

    def test_import_error(self, client: TestClient) -> None:
        with patch("gobby.agents.definitions.AgentDefinitionLoader") as mock_cls:
            mock_cls.return_value.load.side_effect = RuntimeError("Parse error")
            response = client.post("/api/agents/definitions/import/broken")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# CRUD round-trip
# ---------------------------------------------------------------------------


class TestCrudRoundTrip:
    def test_create_list_update_delete(self, client: TestClient) -> None:
        """Full lifecycle through the real DB."""
        # Create
        create_resp = client.post(
            "/api/agents/definitions",
            json={
                "name": "lifecycle-agent",
                "description": "Will be updated",
            },
        )
        assert create_resp.status_code == 200
        defn_id = create_resp.json()["definition"]["id"]

        # Update
        update_resp = client.put(
            f"/api/agents/definitions/{defn_id}",
            json={"description": "Updated description"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["definition"]["description"] == "Updated description"

        # Delete
        delete_resp = client.delete(f"/api/agents/definitions/{defn_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["deleted"] is True
