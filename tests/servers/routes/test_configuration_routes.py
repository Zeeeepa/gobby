"""Tests for configuration routes - real coverage, minimal mocking.

Exercises src/gobby/servers/routes/configuration.py endpoints using
create_http_server() with a real DaemonConfig and real SecretStore
backed by a real temp_db.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from gobby.config.app import DaemonConfig
from gobby.storage.config_store import ConfigStore
from gobby.storage.secrets import SecretStore
from gobby.storage.tasks import LocalTaskManager
from tests.servers.conftest import create_http_server

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def real_config() -> DaemonConfig:
    """A real DaemonConfig with defaults."""
    return DaemonConfig()


@pytest.fixture
def task_manager(temp_db):
    return LocalTaskManager(temp_db)


@pytest.fixture
def server(temp_db, real_config, task_manager):
    """Create an HTTPServer with real config and database."""
    return create_http_server(
        config=real_config,
        database=temp_db,
        task_manager=task_manager,
    )


@pytest.fixture
def client(server) -> TestClient:
    return TestClient(server.app)


# ---------------------------------------------------------------------------
# GET /api/config/schema
# ---------------------------------------------------------------------------


class TestGetConfigSchema:
    def test_returns_json_schema(self, client: TestClient) -> None:
        response = client.get("/api/config/schema")
        assert response.status_code == 200
        data = response.json()
        # Real DaemonConfig schema has these
        assert data["type"] == "object"
        assert "properties" in data
        assert "daemon_port" in data["properties"]

    def test_schema_is_stable(self, client: TestClient) -> None:
        """Calling twice returns the same schema."""
        r1 = client.get("/api/config/schema")
        r2 = client.get("/api/config/schema")
        assert r1.json() == r2.json()


# ---------------------------------------------------------------------------
# GET /api/config/values
# ---------------------------------------------------------------------------


class TestGetConfigValues:
    def test_returns_current_config(self, client: TestClient) -> None:
        response = client.get("/api/config/values")
        assert response.status_code == 200
        data = response.json()
        assert data["daemon_port"] == 60887
        assert "websocket" in data

    def test_values_match_model_dump(self, client: TestClient, real_config: DaemonConfig) -> None:
        response = client.get("/api/config/values")
        expected = real_config.model_dump(mode="json", exclude_none=True)
        assert response.json() == expected


# ---------------------------------------------------------------------------
# PUT /api/config/values
# ---------------------------------------------------------------------------


class TestSaveConfigValues:
    def test_save_valid_values(self, client: TestClient) -> None:
        """Valid partial update succeeds (save_config is patched by conftest)."""
        response = client.put(
            "/api/config/values",
            json={"values": {"daemon_port": 9999}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["requires_restart"] is True

    def test_save_deep_merge(self, client: TestClient) -> None:
        """Deep merge should merge nested dicts, not replace them."""
        response = client.put(
            "/api/config/values",
            json={"values": {"websocket": {"port": 61000}}},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_save_invalid_values_returns_400(self, client: TestClient) -> None:
        """Invalid config values cause a 400."""
        response = client.put(
            "/api/config/values",
            json={"values": {"ui": {"port": 99999, "mode": "invalid"}}},
        )
        assert response.status_code == 400
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# POST /api/config/values/validate
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config(self, client: TestClient) -> None:
        response = client.post(
            "/api/config/values/validate",
            json={"values": {"daemon_port": 9999}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_invalid_config(self, client: TestClient) -> None:
        response = client.post(
            "/api/config/values/validate",
            json={"values": {"ui": {"port": 99999, "mode": "invalid"}}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_empty_values_is_valid(self, client: TestClient) -> None:
        response = client.post(
            "/api/config/values/validate",
            json={"values": {}},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True


# ---------------------------------------------------------------------------
# POST /api/config/values/reset
# ---------------------------------------------------------------------------


class TestResetConfig:
    def test_reset_success(self, client: TestClient, temp_db) -> None:
        """Reset clears config_store and sets in-memory config to defaults."""
        # Seed some config in DB
        store = ConfigStore(temp_db)
        store.set("daemon_port", 9999)
        response = client.post("/api/config/values/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["requires_restart"] is True
        # Verify DB was cleared
        assert store.get_all() == {}

    def test_reset_failure(self, client: TestClient) -> None:
        """Reset failure returns 500."""
        with patch(
            "gobby.servers.routes.configuration.ConfigStore.delete_all",
            side_effect=OSError("Permission denied"),
        ):
            response = client.post("/api/config/values/reset")
        assert response.status_code == 500
        assert "Permission denied" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/config/template
# ---------------------------------------------------------------------------


class TestGetTemplate:
    def test_returns_yaml_with_defaults(self, client: TestClient) -> None:
        response = client.get("/api/config/template")
        assert response.status_code == 200
        content = response.json()["content"]
        assert "daemon_port" in content
        assert isinstance(content, str)

    def test_includes_db_overrides(self, client: TestClient, temp_db) -> None:
        """DB overrides are merged into the template."""
        store = ConfigStore(temp_db)
        store.set("daemon_port", 9999)
        response = client.get("/api/config/template")
        assert response.status_code == 200
        assert "9999" in response.json()["content"]


# ---------------------------------------------------------------------------
# PUT /api/config/template
# ---------------------------------------------------------------------------


class TestSaveTemplate:
    def test_save_valid_yaml(self, client: TestClient, temp_db) -> None:
        response = client.put(
            "/api/config/template",
            json={"content": "daemon_port: 9999\n"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["requires_restart"] is True
        # Verify the DB has the non-default value
        store = ConfigStore(temp_db)
        assert store.get("daemon_port") == 9999

    def test_save_empty_yaml_treated_as_empty_dict(self, client: TestClient) -> None:
        """Empty YAML (parsed as None) is treated as empty dict."""
        response = client.put(
            "/api/config/template",
            json={"content": ""},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_save_invalid_yaml_syntax(self, client: TestClient) -> None:
        response = client.put(
            "/api/config/template",
            json={"content": ":\n  :\n    - [invalid"},
        )
        assert response.status_code == 400
        assert "Invalid YAML" in response.json()["detail"]

    def test_save_yaml_not_a_dict(self, client: TestClient) -> None:
        response = client.put(
            "/api/config/template",
            json={"content": "- item1\n- item2\n"},
        )
        assert response.status_code == 400
        assert "mapping" in response.json()["detail"]

    def test_save_yaml_invalid_config(self, client: TestClient) -> None:
        """Valid YAML but invalid DaemonConfig values."""
        response = client.put(
            "/api/config/template",
            json={"content": "ui:\n  port: 99999\n  mode: invalid\n"},
        )
        assert response.status_code == 400

    def test_only_stores_non_defaults(self, client: TestClient, temp_db) -> None:
        """Template save should only store values that differ from defaults."""
        # Save with all defaults except one change
        response = client.put(
            "/api/config/template",
            json={"content": "daemon_port: 7777\nbind_host: localhost\n"},
        )
        assert response.status_code == 200
        store = ConfigStore(temp_db)
        keys = store.list_keys()
        # Only daemon_port should be stored (bind_host is default)
        assert "daemon_port" in keys
        assert "bind_host" not in keys


# ---------------------------------------------------------------------------
# Secrets endpoints  (GET, POST, DELETE /api/config/secrets)
# ---------------------------------------------------------------------------


class TestSecretsEndpoints:
    def test_list_secrets_empty(self, client: TestClient) -> None:
        with patch("gobby.servers.routes.configuration.SecretStore") as mock_cls:
            mock_store = MagicMock(spec=SecretStore)
            mock_store.list.return_value = []
            mock_cls.return_value = mock_store
            response = client.get("/api/config/secrets")
        assert response.status_code == 200
        data = response.json()
        assert data["secrets"] == []
        assert "categories" in data

    def test_list_secrets_with_data(self, client: TestClient, temp_db, mock_machine_id) -> None:
        """Use a real SecretStore on the temp_db."""
        store = SecretStore(temp_db)
        store.set(name="MY_KEY", plaintext_value="secret123", category="llm", description="Test")
        response = client.get("/api/config/secrets")
        assert response.status_code == 200
        data = response.json()
        assert len(data["secrets"]) >= 1
        names = [s["name"] for s in data["secrets"]]
        assert "MY_KEY" in names

    def test_create_secret(self, client: TestClient, mock_machine_id) -> None:
        response = client.post(
            "/api/config/secrets",
            json={
                "name": "TEST_SECRET",
                "value": "super-secret",
                "category": "general",
                "description": "A test secret",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["secret"]["name"] == "TEST_SECRET"

    def test_create_secret_default_category(self, client: TestClient, mock_machine_id) -> None:
        response = client.post(
            "/api/config/secrets",
            json={"name": "KEY2", "value": "val"},
        )
        assert response.status_code == 200
        assert response.json()["secret"]["category"] == "general"

    def test_create_secret_invalid_category(self, client: TestClient, mock_machine_id) -> None:
        response = client.post(
            "/api/config/secrets",
            json={"name": "KEY3", "value": "val", "category": "bogus"},
        )
        assert response.status_code == 400
        assert "Invalid category" in response.json()["detail"]

    def test_delete_secret_success(self, client: TestClient, temp_db, mock_machine_id) -> None:
        store = SecretStore(temp_db)
        store.set(name="TO_DELETE", plaintext_value="x")
        response = client.delete("/api/config/secrets/TO_DELETE")
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_delete_secret_not_found(self, client: TestClient, mock_machine_id) -> None:
        response = client.delete("/api/config/secrets/NONEXISTENT")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_secret_internal_error(self, client: TestClient) -> None:
        with patch("gobby.servers.routes.configuration.SecretStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.delete.side_effect = RuntimeError("DB error")
            mock_cls.return_value = mock_store
            response = client.delete("/api/config/secrets/MY_SECRET")
        assert response.status_code == 500
        assert "DB error" in response.json()["detail"]

    def test_list_secrets_internal_error(self, client: TestClient) -> None:
        with patch("gobby.servers.routes.configuration.SecretStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.list.side_effect = RuntimeError("Boom")
            mock_cls.return_value = mock_store
            response = client.get("/api/config/secrets")
        assert response.status_code == 500

    def test_create_secret_internal_error(self, client: TestClient) -> None:
        with patch("gobby.servers.routes.configuration.SecretStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.set.side_effect = RuntimeError("Encryption failed")
            mock_cls.return_value = mock_store
            response = client.post(
                "/api/config/secrets",
                json={"name": "KEY", "value": "val"},
            )
        assert response.status_code == 500

    def test_database_not_available(self, real_config) -> None:
        """When database is not a LocalDatabase, _get_secret_store raises 503."""
        server = create_http_server(
            config=real_config,
            database="not-a-database",
        )
        c = TestClient(server.app)
        response = c.get("/api/config/secrets")
        # The 503 from _get_secret_store is caught by the handler's except block
        assert response.status_code == 500
        assert "Database not available" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Prompts endpoints  (GET, GET detail, PUT, DELETE)
# ---------------------------------------------------------------------------


class TestPromptsEndpoints:
    def test_list_prompts(self, client: TestClient) -> None:
        """Lists bundled prompts from real PromptLoader."""
        response = client.get("/api/config/prompts")
        assert response.status_code == 200
        data = response.json()
        assert "prompts" in data
        assert "categories" in data
        assert "total" in data
        assert isinstance(data["total"], int)

    def test_list_prompts_has_categories(self, client: TestClient) -> None:
        """Category counts are populated from listed prompts."""
        response = client.get("/api/config/prompts")
        data = response.json()
        if data["total"] > 0:
            assert len(data["categories"]) > 0
            # Sum of category counts should equal total
            assert sum(data["categories"].values()) == data["total"]

    def test_list_prompts_source_is_bundled(self, client: TestClient, tmp_path: Path) -> None:
        """Without overrides, all sources should be 'bundled'."""
        # Point GLOBAL_PROMPTS_DIR to empty tmp dir so no overrides are found
        empty_prompts = tmp_path / "empty_prompts"
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", empty_prompts
        ):
            response = client.get("/api/config/prompts")
        for p in response.json()["prompts"]:
            assert p["source"] == "bundled"
            assert p["has_override"] is False

    def test_get_prompt_detail(self, client: TestClient) -> None:
        """Get detail of a prompt that exists."""
        # First, list to find a valid prompt path
        list_resp = client.get("/api/config/prompts")
        prompts = list_resp.json()["prompts"]
        if not prompts:
            pytest.skip("No bundled prompts found")
        path = prompts[0]["path"]
        response = client.get(f"/api/config/prompts/{path}")
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == path
        assert "content" in data
        assert "variables" in data
        assert data["source"] == "bundled"

    def test_get_prompt_not_found(self, client: TestClient) -> None:
        response = client.get("/api/config/prompts/nonexistent/prompt")
        assert response.status_code == 404

    def test_list_prompts_error(self, client: TestClient) -> None:
        with patch(
            "gobby.servers.routes.configuration.PromptLoader",
            side_effect=RuntimeError("Loader broke"),
        ):
            response = client.get("/api/config/prompts")
        assert response.status_code == 500

    def test_save_and_delete_prompt_override(self, client: TestClient, tmp_path: Path) -> None:
        """Save an override, then delete it."""
        prompts_dir = tmp_path / "prompts"
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", prompts_dir
        ):
            # Save
            response = client.put(
                "/api/config/prompts/test/prompt",
                json={"content": "# Custom override\nHello world"},
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True
            # Verify file exists
            assert (prompts_dir / "test" / "prompt.md").exists()

            # Delete
            response = client.delete("/api/config/prompts/test/prompt")
            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert not (prompts_dir / "test" / "prompt.md").exists()

    def test_delete_prompt_override_not_found(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", prompts_dir
        ):
            response = client.delete("/api/config/prompts/no/such/prompt")
        assert response.status_code == 404
        assert "No override" in response.json()["detail"]

    def test_save_prompt_override_error(self, client: TestClient) -> None:
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR",
            new_callable=lambda: MagicMock(
                __truediv__=MagicMock(
                    return_value=MagicMock(
                        parent=MagicMock(
                            mkdir=MagicMock(side_effect=OSError("No space"))
                        )
                    )
                )
            ),
        ):
            response = client.put(
                "/api/config/prompts/test/prompt",
                json={"content": "# Fail"},
            )
        assert response.status_code == 500

    def test_delete_prompt_override_error(self, client: TestClient, tmp_path: Path) -> None:
        prompts_dir = tmp_path / "prompts"
        override_file = prompts_dir / "test" / "prompt.md"
        override_file.parent.mkdir(parents=True, exist_ok=True)
        override_file.write_text("# Override", encoding="utf-8")
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", prompts_dir
        ):
            # Make unlink fail
            with patch.object(Path, "unlink", side_effect=OSError("Locked")):
                response = client.delete("/api/config/prompts/test/prompt")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------


class TestExportImport:
    def test_export_config(self, client: TestClient, tmp_path: Path, mock_machine_id) -> None:
        prompts_dir = tmp_path / "prompts"
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", prompts_dir
        ):
            response = client.post("/api/config/export")
        assert response.status_code == 200
        data = response.json()
        assert "exported_at" in data
        assert "config_store" in data
        assert isinstance(data["config_store"], dict)
        assert isinstance(data["prompts"], dict)
        assert isinstance(data["secrets"], list)

    def test_export_config_with_prompt_overrides(
        self, client: TestClient, tmp_path: Path, mock_machine_id
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "expansion").mkdir(parents=True)
        (prompts_dir / "expansion" / "system.md").write_text("# Custom")
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", prompts_dir
        ):
            response = client.post("/api/config/export")
        data = response.json()
        assert "expansion/system.md" in data["prompts"]
        assert data["prompts"]["expansion/system.md"] == "# Custom"

    def test_import_config_store(self, client: TestClient, temp_db) -> None:
        """Import flat config_store dict writes to DB."""
        response = client.post(
            "/api/config/import",
            json={"config_store": {"daemon_port": 9999}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "config restored" in data["summary"]
        assert data["requires_restart"] is True
        # Verify DB
        store = ConfigStore(temp_db)
        assert store.get("daemon_port") == 9999

    def test_import_legacy_config(self, client: TestClient, temp_db) -> None:
        """Legacy nested config dict is flattened and stored to DB."""
        response = client.post(
            "/api/config/import",
            json={"config": {"daemon_port": 8888}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "config restored" in data["summary"]
        assert data["requires_restart"] is True

    def test_import_config_with_prompts(self, client: TestClient, tmp_path: Path) -> None:
        prompts_dir = tmp_path / "prompts"
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", prompts_dir
        ):
            response = client.post(
                "/api/config/import",
                json={
                    "prompts": {"expansion/system.md": "# Custom prompt override"},
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "1 prompt override(s) restored" in data["summary"]
        assert data["requires_restart"] is False
        assert (prompts_dir / "expansion/system.md").read_text() == "# Custom prompt override"

    def test_import_nothing(self, client: TestClient) -> None:
        response = client.post("/api/config/import", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["summary"] == "nothing to import"
        assert data["requires_restart"] is False

    def test_import_invalid_config(self, client: TestClient) -> None:
        response = client.post(
            "/api/config/import",
            json={"config": {"ui": {"port": 99999, "mode": "invalid"}}},
        )
        assert response.status_code == 400

    def test_import_config_and_prompts_together(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        prompts_dir = tmp_path / "prompts"
        with patch(
            "gobby.servers.routes.configuration.GLOBAL_PROMPTS_DIR", prompts_dir
        ):
            response = client.post(
                "/api/config/import",
                json={
                    "config_store": {"daemon_port": 7777},
                    "prompts": {"test/foo.md": "# Foo"},
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert "config restored" in data["summary"]
        assert "1 prompt override(s) restored" in data["summary"]
        assert data["requires_restart"] is True


# ---------------------------------------------------------------------------
# _deep_merge helper
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_deep_merge_basic(self) -> None:
        from gobby.config.app import deep_merge

        base = {"a": 1, "b": {"c": 2, "d": 3}}
        updates = {"b": {"c": 99, "e": 5}, "f": 6}
        deep_merge(base, updates)
        assert base == {"a": 1, "b": {"c": 99, "d": 3, "e": 5}, "f": 6}

    def test_deep_merge_replace_non_dict(self) -> None:
        from gobby.config.app import deep_merge

        base = {"a": {"b": 1}}
        updates = {"a": "string"}
        deep_merge(base, updates)
        assert base == {"a": "string"}

    def test_deep_merge_empty_updates(self) -> None:
        from gobby.config.app import deep_merge

        base = {"a": 1}
        deep_merge(base, {})
        assert base == {"a": 1}

    def test_deep_merge_nested_three_levels(self) -> None:
        from gobby.config.app import deep_merge

        base = {"a": {"b": {"c": 1, "d": 2}}}
        updates = {"a": {"b": {"c": 99}}}
        deep_merge(base, updates)
        assert base == {"a": {"b": {"c": 99, "d": 2}}}
