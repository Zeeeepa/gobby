from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gobby.servers.routes.admin import create_admin_router

pytestmark = pytest.mark.unit

class TestAdminRoutes:
    @pytest.fixture
    def mock_server(self):
        server = MagicMock()
        server._start_time = 1234567890.0
        server._running = True
        server.port = 60887
        server.test_mode = False

        # Mock Daemon
        server._daemon = MagicMock()
        server._daemon.status.return_value = {"status": "running"}
        server._daemon.uptime = 100.0

        # Mock Managers
        server.mcp_manager = MagicMock()
        server.mcp_manager.server_configs = []
        server.mcp_manager.health = {}
        server.mcp_manager.connections = {}

        server._internal_manager = MagicMock()
        server._internal_manager.get_all_registries.return_value = []

        server.session_manager = MagicMock()
        server.session_manager.count_by_status.return_value = {"active": 1, "paused": 0}

        server.task_manager = MagicMock()
        server.task_manager.count_by_status.return_value = {"open": 2}
        server.task_manager.count_ready_tasks.return_value = 1
        server.task_manager.count_blocked_tasks.return_value = 0

        server.memory_manager = MagicMock()
        server.memory_manager.get_stats.return_value = {"total_count": 10, "avg_importance": 0.5}

        server._background_tasks = set()

        # Shutdown support
        server._process_shutdown = AsyncMock()

        return server

    @pytest.fixture
    def client(self, mock_server):
        from fastapi import FastAPI

        app = FastAPI()
        router = create_admin_router(mock_server)
        app.include_router(router)
        return TestClient(app)

    @patch("gobby.servers.routes.admin.psutil")
    @patch("gobby.servers.routes.admin.asyncio.to_thread")
    def test_status_endpoint(self, mock_to_thread, mock_psutil, client, mock_server) -> None:
        # Mock psutil
        mock_process = MagicMock()
        mock_process.memory_info.return_value = MagicMock(
            rss=1024 * 1024 * 100, vms=1024 * 1024 * 200
        )
        mock_process.num_threads.return_value = 10
        mock_psutil.Process.return_value = mock_process

        # Mock asyncio.to_thread for cpu_percent (awaitable)
        mock_to_thread.return_value = 1.5

        # Mock MCP servers config
        mock_config = MagicMock()
        mock_config.name = "test-server"
        mock_config.enabled = True
        mock_config.transport = "stdio"
        mock_server.mcp_manager.server_configs = [mock_config]
        mock_server.mcp_manager.connections = ["test-server"]

        response = client.get("/admin/status")
        assert response.status_code == 200
        data = response.json()

        assert data["daemon"]["status"] == "running"
        assert data["process"]["cpu_percent"] == 1.5
        assert data["process"]["memory_rss_mb"] == 100.0
        assert "test-server" in data["mcp_servers"]
        assert data["mcp_servers"]["test-server"]["connected"] is True

    @patch("gobby.servers.routes.admin.get_metrics_collector")
    @patch("gobby.servers.routes.admin.psutil")
    def test_metrics_endpoint(self, mock_psutil, mock_get_collector, client) -> None:
        mock_collector = MagicMock()
        mock_collector.export_prometheus.return_value = "metric_name 1.0\n"
        mock_get_collector.return_value = mock_collector

        # Mock psutil for daemon metrics
        mock_process = MagicMock()
        mock_process.memory_info.return_value = MagicMock(rss=1000)
        mock_process.cpu_percent.return_value = 0.5
        mock_psutil.Process.return_value = mock_process

        response = client.get("/admin/metrics")
        assert response.status_code == 200
        assert response.text == "metric_name 1.0\n"
        assert "text/plain" in response.headers["content-type"]

    @patch("gobby.servers.routes.admin.get_version")
    def test_config_endpoint(self, mock_get_version, client) -> None:
        mock_get_version.return_value = "1.0.0"

        response = client.get("/admin/config")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["config"]["server"]["version"] == "1.0.0"
        assert data["config"]["features"]["session_manager"] is True

    def test_shutdown_endpoint(self, client, mock_server) -> None:
        # We don't need to patch shutdown_event, admin.py calls server._process_shutdown()

        response = client.post("/admin/shutdown")
        assert response.status_code == 200
        assert response.json() == {
            "status": "shutting_down",
            "message": "Graceful shutdown initiated",
            "response_time_ms": response.json()["response_time_ms"],  # ignore value
        }

        # Verify shutdown was initiated
        # Note: TestClient runs synchronous, but create_task might loop issues.
        # But endpoints call asyncio.create_task.
        # Since we use TestClient, it might not actually run the task loop unless we handle it,
        # but the endpoint function itself executed up to return.

        # Verify shutdown was initiated
        # Instead of checking background_tasks (which might clear quickly via callback),
        # verify the method was called.
        mock_server._process_shutdown.assert_called()
