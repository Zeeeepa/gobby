from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gobby.servers.routes.admin import create_admin_router

pytestmark = pytest.mark.unit


class TestAdminRoutesExtended:
    @pytest.fixture
    def mock_server(self):
        server = MagicMock()
        server._start_time = 1234567890.0
        server._running = True
        server.port = 60887
        server.test_mode = True  # Enable test endpoints

        # Mock Daemon
        server._daemon = MagicMock()
        server._daemon.status.return_value = {"status": "running"}

        # Mock Managers
        server.mcp_manager = MagicMock()
        server.mcp_manager.server_configs = []

        server.llm_service = MagicMock()
        server.llm_service.enabled_providers = ["claude"]

        # Mock services config for models
        server.services = MagicMock()
        mock_provider_config = MagicMock()
        mock_provider_config.get_models_list.return_value = ["claude-3-opus", "claude-3-sonnet"]
        mock_provider_config.auth_mode = "api_key"
        server.services.config.llm_providers.claude = mock_provider_config

        # Mock internal manager for workflows/reload
        server._internal_manager = MagicMock()
        mock_registry = AsyncMock()
        mock_registry.name = "gobby-workflows"
        mock_registry.call.return_value = {"success": True, "count": 5}
        server._internal_manager.get_all_registries.return_value = [mock_registry]

        # Mock session manager for test endpoints
        server.session_manager = MagicMock()
        server.session_manager.db = MagicMock()  # Mock DB for project registration
        server.session_manager.update_usage.return_value = True

        return server

    @pytest.fixture
    def client(self, mock_server):
        from fastapi import FastAPI

        app = FastAPI()
        router = create_admin_router(mock_server)
        app.include_router(router)
        return TestClient(app)

    def test_models_endpoint(self, client, mock_server) -> None:
        """Test GET /models endpoint with LiteLLM discovery."""
        mock_model_cost = {
            "claude-opus-4-6": {},
            "claude-sonnet-4-5": {},
            "claude-haiku-4-5": {},
            "gpt-5": {},
            "claude-sonnet-4-5-20250929": {},  # dated variant — should be excluded
            "anthropic/claude-opus-4-6": {},  # provider-scoped — should be excluded
        }
        with patch("gobby.servers.routes.admin.litellm") as mock_litellm:
            mock_litellm.model_cost = mock_model_cost
            response = client.get("/admin/models")

        assert response.status_code == 200
        data = response.json()

        assert "claude" in data["models"]
        claude_models = data["models"]["claude"]
        assert "claude-opus-4-6" in claude_models
        assert "claude-sonnet-4-5" in claude_models
        assert "claude-haiku-4-5" in claude_models
        # Dated variant should be filtered out
        assert "claude-sonnet-4-5-20250929" not in claude_models
        assert data["default_model"] is not None

    def test_models_endpoint_provider_filter(self, client, mock_server) -> None:
        """Test GET /models?provider=claude filters to Claude only."""
        mock_model_cost = {
            "claude-opus-4-6": {},
            "claude-sonnet-4-5": {},
            "gpt-5": {},
            "gemini-2-flash": {},
        }
        with patch("gobby.servers.routes.admin.litellm") as mock_litellm:
            mock_litellm.model_cost = mock_model_cost
            response = client.get("/admin/models?provider=claude")

        assert response.status_code == 200
        data = response.json()

        assert "claude" in data["models"]
        assert "gpt" not in data["models"]
        assert "gemini" not in data["models"]

    def test_reload_workflows_endpoint(self, client, mock_server) -> None:
        """Test POST /workflows/reload endpoint."""
        response = client.post("/admin/workflows/reload")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["message"] == "Workflow cache reloaded"

        # Verify call to internal registry
        registry = mock_server._internal_manager.get_all_registries.return_value[0]
        registry.call.assert_called_with("reload_cache", {})

    def test_register_test_project(self, client, mock_server) -> None:
        """Test POST /test/register-project endpoint."""
        # Mock checking for existing project (None)
        # Patch where the class is defined since it's imported locally in the function
        with patch("gobby.storage.projects.LocalProjectManager") as MockPM:
            mock_pm_instance = MockPM.return_value
            mock_pm_instance.get.return_value = None

            payload = {"project_id": "proj-123", "name": "Test Project", "repo_path": "/tmp/test"}
            response = client.post("/admin/test/register-project", json=payload)
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "success"
            assert data["project_id"] == "proj-123"

            # Verify DB insert
            mock_server.session_manager.db.execute.assert_called()

    @patch("gobby.agents.registry.get_running_agent_registry")
    def test_register_test_agent(self, mock_get_registry, client, mock_server) -> None:
        """Test POST /test/register-agent endpoint."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry

        payload = {
            "run_id": "ar-test",
            "session_id": "sess-test",
            "parent_session_id": "parent-test",
            "mode": "terminal",
        }
        response = client.post("/admin/test/register-agent", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["agent"]["run_id"] == "ar-test"

        mock_registry.add.assert_called()

    @patch("gobby.agents.registry.get_running_agent_registry")
    def test_unregister_test_agent(self, mock_get_registry, client, mock_server) -> None:
        """Test DELETE /test/unregister-agent/{run_id} endpoint."""
        mock_registry = MagicMock()
        mock_agent = MagicMock()
        mock_registry.remove.return_value = mock_agent
        mock_get_registry.return_value = mock_registry

        response = client.delete("/admin/test/unregister-agent/ar-test")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        mock_registry.remove.assert_called_with("ar-test")

    def test_set_session_usage(self, client, mock_server) -> None:
        """Test POST /test/set-session-usage endpoint."""
        payload = {
            "session_id": "sess-123",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_cost_usd": 0.05,
        }
        response = client.post("/admin/test/set-session-usage", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["usage_set"]["input_tokens"] == 100

        mock_server.session_manager.update_usage.assert_called_with(
            session_id="sess-123",
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            total_cost_usd=0.05,
        )
