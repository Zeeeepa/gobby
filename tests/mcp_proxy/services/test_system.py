"""Tests for the SystemService class."""

import os
from unittest.mock import MagicMock, patch

import pytest

from gobby.mcp_proxy.services.system import SystemService


class TestSystemServiceInit:
    """Tests for SystemService initialization."""

    def test_init_stores_mcp_manager(self):
        """Test that MCP manager is stored correctly."""
        mock_manager = MagicMock()
        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )
        assert service._mcp_manager is mock_manager

    def test_init_stores_port(self):
        """Test that HTTP port is stored correctly."""
        mock_manager = MagicMock()
        service = SystemService(
            mcp_manager=mock_manager,
            port=9000,
            websocket_port=9001,
            start_time=1000.0,
        )
        assert service._port == 9000

    def test_init_stores_websocket_port(self):
        """Test that WebSocket port is stored correctly."""
        mock_manager = MagicMock()
        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=9999,
            start_time=1000.0,
        )
        assert service._websocket_port == 9999

    def test_init_stores_start_time(self):
        """Test that start time is stored correctly."""
        mock_manager = MagicMock()
        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=12345.678,
        )
        assert service._start_time == 12345.678


class TestSystemServiceGetStatus:
    """Tests for SystemService.get_status method."""

    @pytest.fixture
    def mock_mcp_manager(self):
        """Create a mock MCP manager."""
        manager = MagicMock()
        manager.get_server_health.return_value = {}
        manager.get_lazy_connection_states.return_value = {}
        manager.lazy_connect = False
        return manager

    @pytest.fixture
    def system_service(self, mock_mcp_manager):
        """Create a SystemService instance with mocked dependencies."""
        return SystemService(
            mcp_manager=mock_mcp_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

    def test_get_status_returns_running_true(self, system_service):
        """Test that status always shows running as true."""
        status = system_service.get_status()
        assert status["running"] is True

    def test_get_status_returns_current_pid(self, system_service):
        """Test that status returns the current process ID."""
        status = system_service.get_status()
        assert status["pid"] == os.getpid()

    def test_get_status_returns_http_port(self, system_service):
        """Test that status returns the HTTP port."""
        status = system_service.get_status()
        assert status["http_port"] == 8080

    def test_get_status_returns_websocket_port(self, system_service):
        """Test that status returns the WebSocket port."""
        status = system_service.get_status()
        assert status["websocket_port"] == 8081

    def test_get_status_returns_lazy_mode(self, system_service, mock_mcp_manager):
        """Test that status returns lazy mode setting."""
        mock_mcp_manager.lazy_connect = True
        status = system_service.get_status()
        assert status["lazy_mode"] is True

    def test_get_status_healthy_with_no_servers(self, system_service):
        """Test that status is healthy when there are no servers."""
        status = system_service.get_status()
        assert status["healthy"] is True

    def test_get_status_healthy_with_connected_servers(
        self, system_service, mock_mcp_manager
    ):
        """Test that status is healthy when all servers are connected."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {
                "state": "connected",
                "health": "healthy",
                "last_check": None,
                "failures": 0,
                "response_time_ms": 10,
            },
            "server2": {
                "state": "connected",
                "health": "healthy",
                "last_check": None,
                "failures": 0,
                "response_time_ms": 15,
            },
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {}

        status = system_service.get_status()
        assert status["healthy"] is True

    def test_get_status_healthy_with_healthy_state(
        self, system_service, mock_mcp_manager
    ):
        """Test that status is healthy when servers report healthy state."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {
                "state": "healthy",
                "health": "healthy",
                "last_check": None,
                "failures": 0,
                "response_time_ms": 10,
            },
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {}

        status = system_service.get_status()
        assert status["healthy"] is True

    def test_get_status_healthy_with_configured_servers(
        self, system_service, mock_mcp_manager
    ):
        """Test that status is healthy with servers in configured state (lazy mode)."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {
                "state": "configured",
                "health": "unknown",
                "last_check": None,
                "failures": 0,
                "response_time_ms": None,
            },
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {}

        status = system_service.get_status()
        assert status["healthy"] is True

    def test_get_status_unhealthy_with_disconnected_server(
        self, system_service, mock_mcp_manager
    ):
        """Test that status is unhealthy when a server is disconnected."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {
                "state": "disconnected",
                "health": "unhealthy",
                "last_check": None,
                "failures": 3,
                "response_time_ms": None,
            },
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {}

        status = system_service.get_status()
        assert status["healthy"] is False

    def test_get_status_unhealthy_with_error_state(
        self, system_service, mock_mcp_manager
    ):
        """Test that status is unhealthy when a server has error state."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {
                "state": "error",
                "health": "unhealthy",
                "last_check": None,
                "failures": 5,
                "response_time_ms": None,
            },
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {}

        status = system_service.get_status()
        assert status["healthy"] is False

    def test_get_status_unhealthy_if_any_server_unhealthy(
        self, system_service, mock_mcp_manager
    ):
        """Test that status is unhealthy if any server is in bad state."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {
                "state": "connected",
                "health": "healthy",
                "last_check": None,
                "failures": 0,
                "response_time_ms": 10,
            },
            "server2": {
                "state": "failed",
                "health": "unhealthy",
                "last_check": None,
                "failures": 10,
                "response_time_ms": None,
            },
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {}

        status = system_service.get_status()
        assert status["healthy"] is False


class TestSystemServiceLazyConnectionMerge:
    """Tests for lazy connection state merging in get_status."""

    @pytest.fixture
    def mock_mcp_manager(self):
        """Create a mock MCP manager."""
        manager = MagicMock()
        manager.get_server_health.return_value = {}
        manager.get_lazy_connection_states.return_value = {}
        manager.lazy_connect = True
        return manager

    @pytest.fixture
    def system_service(self, mock_mcp_manager):
        """Create a SystemService instance with mocked dependencies."""
        return SystemService(
            mcp_manager=mock_mcp_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

    def test_lazy_info_merged_into_existing_health(
        self, system_service, mock_mcp_manager
    ):
        """Test that lazy connection info is merged into existing health data."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {
                "state": "connected",
                "health": "healthy",
                "last_check": "2024-01-01T00:00:00",
                "failures": 0,
                "response_time_ms": 10,
            },
        }
        lazy_info = {
            "is_connected": True,
            "configured_at": "2024-01-01T00:00:00",
            "connected_at": "2024-01-01T00:01:00",
            "last_attempt_at": None,
            "last_error": None,
            "connection_attempts": 1,
            "circuit_state": "closed",
            "circuit_failures": 0,
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "server1": lazy_info
        }

        status = system_service.get_status()

        assert "server1" in status["mcp_servers"]
        assert status["mcp_servers"]["server1"]["lazy_connection"] == lazy_info
        assert status["mcp_servers"]["server1"]["state"] == "connected"

    def test_lazy_only_server_creates_new_health_entry(
        self, system_service, mock_mcp_manager
    ):
        """Test that servers only in lazy state get new health entries."""
        mock_mcp_manager.get_server_health.return_value = {}
        lazy_info = {
            "is_connected": False,
            "configured_at": "2024-01-01T00:00:00",
            "connected_at": None,
            "last_attempt_at": None,
            "last_error": None,
            "connection_attempts": 0,
            "circuit_state": "closed",
            "circuit_failures": 0,
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "lazy-server": lazy_info
        }

        status = system_service.get_status()

        assert "lazy-server" in status["mcp_servers"]
        server_health = status["mcp_servers"]["lazy-server"]
        assert server_health["state"] == "configured"
        assert server_health["health"] == "unknown"
        assert server_health["last_check"] is None
        assert server_health["failures"] == 0
        assert server_health["response_time_ms"] is None
        assert server_health["lazy_connection"] == lazy_info

    def test_multiple_lazy_servers_all_added(
        self, system_service, mock_mcp_manager
    ):
        """Test that multiple lazy-only servers are all added to status."""
        mock_mcp_manager.get_server_health.return_value = {}
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "server-a": {
                "is_connected": False,
                "configured_at": "2024-01-01T00:00:00",
                "connected_at": None,
                "last_attempt_at": None,
                "last_error": None,
                "connection_attempts": 0,
                "circuit_state": "closed",
                "circuit_failures": 0,
            },
            "server-b": {
                "is_connected": False,
                "configured_at": "2024-01-01T00:00:00",
                "connected_at": None,
                "last_attempt_at": None,
                "last_error": None,
                "connection_attempts": 0,
                "circuit_state": "closed",
                "circuit_failures": 0,
            },
        }

        status = system_service.get_status()

        assert "server-a" in status["mcp_servers"]
        assert "server-b" in status["mcp_servers"]

    def test_mixed_health_and_lazy_servers(
        self, system_service, mock_mcp_manager
    ):
        """Test status with both health-tracked and lazy-only servers."""
        mock_mcp_manager.get_server_health.return_value = {
            "connected-server": {
                "state": "connected",
                "health": "healthy",
                "last_check": "2024-01-01T00:00:00",
                "failures": 0,
                "response_time_ms": 10,
            },
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "connected-server": {
                "is_connected": True,
                "configured_at": "2024-01-01T00:00:00",
                "connected_at": "2024-01-01T00:01:00",
                "last_attempt_at": None,
                "last_error": None,
                "connection_attempts": 1,
                "circuit_state": "closed",
                "circuit_failures": 0,
            },
            "lazy-server": {
                "is_connected": False,
                "configured_at": "2024-01-01T00:00:00",
                "connected_at": None,
                "last_attempt_at": None,
                "last_error": None,
                "connection_attempts": 0,
                "circuit_state": "closed",
                "circuit_failures": 0,
            },
        }

        status = system_service.get_status()

        assert "connected-server" in status["mcp_servers"]
        assert "lazy-server" in status["mcp_servers"]
        assert status["mcp_servers"]["connected-server"]["state"] == "connected"
        assert status["mcp_servers"]["lazy-server"]["state"] == "configured"


class TestSystemServiceServerCounts:
    """Tests for configured and connected server counting."""

    @pytest.fixture
    def mock_mcp_manager(self):
        """Create a mock MCP manager."""
        manager = MagicMock()
        manager.get_server_health.return_value = {}
        manager.get_lazy_connection_states.return_value = {}
        manager.lazy_connect = True
        return manager

    @pytest.fixture
    def system_service(self, mock_mcp_manager):
        """Create a SystemService instance with mocked dependencies."""
        return SystemService(
            mcp_manager=mock_mcp_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

    def test_zero_servers_counts(self, system_service):
        """Test counts with no servers."""
        status = system_service.get_status()
        assert status["configured_servers"] == 0
        assert status["connected_servers"] == 0

    def test_configured_count_from_health(
        self, system_service, mock_mcp_manager
    ):
        """Test configured count includes servers from health dict."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {"state": "connected", "health": "healthy"},
            "server2": {"state": "disconnected", "health": "unhealthy"},
        }

        status = system_service.get_status()
        assert status["configured_servers"] == 2

    def test_configured_count_from_lazy_states(
        self, system_service, mock_mcp_manager
    ):
        """Test configured count includes lazy-only servers."""
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "lazy1": {"is_connected": False},
            "lazy2": {"is_connected": False},
        }

        status = system_service.get_status()
        assert status["configured_servers"] == 2

    def test_configured_count_no_duplicates(
        self, system_service, mock_mcp_manager
    ):
        """Test that servers in both health and lazy are counted once."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {"state": "connected", "health": "healthy"},
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "server1": {"is_connected": True},
        }

        status = system_service.get_status()
        # Server1 appears in both, should only be counted once
        assert status["configured_servers"] == 1

    def test_connected_count_from_state(
        self, system_service, mock_mcp_manager
    ):
        """Test connected count based on state='connected'."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {"state": "connected", "health": "healthy"},
            "server2": {"state": "disconnected", "health": "unhealthy"},
        }

        status = system_service.get_status()
        assert status["connected_servers"] == 1

    def test_connected_count_from_lazy_is_connected(
        self, system_service, mock_mcp_manager
    ):
        """Test connected count includes servers with lazy is_connected=True."""
        mock_mcp_manager.get_server_health.return_value = {}
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "server1": {"is_connected": True},
            "server2": {"is_connected": False},
        }

        status = system_service.get_status()
        assert status["connected_servers"] == 1

    def test_connected_count_combined(
        self, system_service, mock_mcp_manager
    ):
        """Test connected count with both state and lazy info."""
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {"state": "connected", "health": "healthy"},
            "server2": {"state": "disconnected", "health": "unhealthy"},
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "server1": {"is_connected": True},
            "server2": {"is_connected": False},
            "server3": {"is_connected": True},
        }

        status = system_service.get_status()
        # server1 connected (state), server3 connected (lazy)
        # server2 in health has state=disconnected, lazy shows is_connected=False
        assert status["connected_servers"] == 2

    def test_connected_count_prefers_lazy_is_connected(
        self, system_service, mock_mcp_manager
    ):
        """Test that lazy is_connected=True counts even if state isn't 'connected'."""
        # This tests the OR condition in the connected counting logic
        mock_mcp_manager.get_server_health.return_value = {
            "server1": {"state": "configured", "health": "unknown"},
        }
        mock_mcp_manager.get_lazy_connection_states.return_value = {
            "server1": {"is_connected": True},
        }

        status = system_service.get_status()
        # state is "configured" but lazy says is_connected=True
        assert status["connected_servers"] == 1


class TestSystemServiceMCPServersOutput:
    """Tests for the mcp_servers field in status output."""

    @pytest.fixture
    def mock_mcp_manager(self):
        """Create a mock MCP manager."""
        manager = MagicMock()
        manager.get_server_health.return_value = {}
        manager.get_lazy_connection_states.return_value = {}
        manager.lazy_connect = False
        return manager

    @pytest.fixture
    def system_service(self, mock_mcp_manager):
        """Create a SystemService instance with mocked dependencies."""
        return SystemService(
            mcp_manager=mock_mcp_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

    def test_mcp_servers_empty_when_no_servers(self, system_service):
        """Test mcp_servers is empty dict when no servers configured."""
        status = system_service.get_status()
        assert status["mcp_servers"] == {}

    def test_mcp_servers_includes_all_health_fields(
        self, system_service, mock_mcp_manager
    ):
        """Test mcp_servers includes all health fields from manager."""
        mock_mcp_manager.get_server_health.return_value = {
            "test-server": {
                "state": "connected",
                "health": "healthy",
                "last_check": "2024-01-01T12:00:00",
                "failures": 2,
                "response_time_ms": 25.5,
            },
        }

        status = system_service.get_status()

        server_info = status["mcp_servers"]["test-server"]
        assert server_info["state"] == "connected"
        assert server_info["health"] == "healthy"
        assert server_info["last_check"] == "2024-01-01T12:00:00"
        assert server_info["failures"] == 2
        assert server_info["response_time_ms"] == 25.5

    def test_mcp_servers_preserves_none_values(
        self, system_service, mock_mcp_manager
    ):
        """Test mcp_servers correctly handles None values."""
        mock_mcp_manager.get_server_health.return_value = {
            "test-server": {
                "state": "configured",
                "health": "unknown",
                "last_check": None,
                "failures": 0,
                "response_time_ms": None,
            },
        }

        status = system_service.get_status()

        server_info = status["mcp_servers"]["test-server"]
        assert server_info["last_check"] is None
        assert server_info["response_time_ms"] is None


class TestSystemServicePidMocking:
    """Tests that verify os.getpid() behavior."""

    def test_get_status_uses_real_pid(self):
        """Test that get_status returns actual process ID."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {}
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        status = service.get_status()
        # Should be a positive integer
        assert isinstance(status["pid"], int)
        assert status["pid"] > 0

    def test_get_status_pid_with_mock(self):
        """Test that we can mock os.getpid for controlled testing."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {}
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        with patch("os.getpid", return_value=99999):
            status = service.get_status()
            assert status["pid"] == 99999


class TestSystemServiceEdgeCases:
    """Edge case tests for SystemService."""

    def test_empty_lazy_connection_dict_inside_health(self):
        """Test handling when lazy_connection key exists but is empty dict."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {
            "server1": {"state": "connected"},
        }
        mock_manager.get_lazy_connection_states.return_value = {
            "server1": {},  # Empty dict
        }
        mock_manager.lazy_connect = True

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        status = service.get_status()
        # Should handle empty dict gracefully
        assert status["mcp_servers"]["server1"]["lazy_connection"] == {}
        # connected_servers count should handle missing is_connected key
        assert status["connected_servers"] == 1  # From state="connected"

    def test_missing_state_key_in_health(self):
        """Test handling when health dict is missing 'state' key."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {
            "server1": {"health": "healthy"},  # Missing 'state'
        }
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        status = service.get_status()
        # Should not crash, server should be considered unhealthy
        assert status["healthy"] is False

    def test_very_large_server_count(self):
        """Test handling of many servers."""
        mock_manager = MagicMock()
        # Create 100 servers
        health = {
            f"server{i}": {"state": "connected", "health": "healthy"}
            for i in range(100)
        }
        mock_manager.get_server_health.return_value = health
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        status = service.get_status()
        assert status["configured_servers"] == 100
        assert status["connected_servers"] == 100
        assert status["healthy"] is True

    def test_special_characters_in_server_name(self):
        """Test handling of server names with special characters."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {
            "server-with-dashes": {"state": "connected"},
            "server_with_underscores": {"state": "connected"},
            "server.with.dots": {"state": "connected"},
        }
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        status = service.get_status()
        assert "server-with-dashes" in status["mcp_servers"]
        assert "server_with_underscores" in status["mcp_servers"]
        assert "server.with.dots" in status["mcp_servers"]

    def test_zero_ports(self):
        """Test handling of zero port values (edge case)."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {}
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=0,
            websocket_port=0,
            start_time=1000.0,
        )

        status = service.get_status()
        assert status["http_port"] == 0
        assert status["websocket_port"] == 0

    def test_negative_start_time(self):
        """Test handling of negative start time (edge case)."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {}
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=-1000.0,
        )

        # Service should still work
        status = service.get_status()
        assert status["running"] is True


class TestSystemServiceStatusStructure:
    """Tests verifying the complete structure of status output."""

    def test_status_has_all_required_keys(self):
        """Test that status output contains all required keys."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {}
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = False

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        status = service.get_status()

        required_keys = {
            "running",
            "pid",
            "healthy",
            "http_port",
            "websocket_port",
            "mcp_servers",
            "lazy_mode",
            "configured_servers",
            "connected_servers",
        }
        assert set(status.keys()) == required_keys

    def test_status_value_types(self):
        """Test that status values have correct types."""
        mock_manager = MagicMock()
        mock_manager.get_server_health.return_value = {}
        mock_manager.get_lazy_connection_states.return_value = {}
        mock_manager.lazy_connect = True

        service = SystemService(
            mcp_manager=mock_manager,
            port=8080,
            websocket_port=8081,
            start_time=1000.0,
        )

        status = service.get_status()

        assert isinstance(status["running"], bool)
        assert isinstance(status["pid"], int)
        assert isinstance(status["healthy"], bool)
        assert isinstance(status["http_port"], int)
        assert isinstance(status["websocket_port"], int)
        assert isinstance(status["mcp_servers"], dict)
        assert isinstance(status["lazy_mode"], bool)
        assert isinstance(status["configured_servers"], int)
        assert isinstance(status["connected_servers"], int)
