"""
Comprehensive tests for src/gobby/mcp_proxy/actions.py - MCP Actions module.

This module tests:
- add_mcp_server: Adding HTTP, stdio, and websocket servers
- remove_mcp_server: Removing servers with various scenarios
- list_mcp_servers: Listing servers with different states
- Error handling and edge cases
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.mcp_proxy.actions import (
    add_mcp_server,
    list_mcp_servers,
    remove_mcp_server,
)
from gobby.mcp_proxy.manager import MCPServerConfig

pytestmark = pytest.mark.unit

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_mcp_manager():
    """Create a mock MCP client manager."""
    manager = MagicMock()
    manager.add_server = AsyncMock()
    manager.remove_server = AsyncMock()
    manager.server_configs = []
    manager.connections = {}
    manager.health = {}
    return manager


@pytest.fixture
def sample_server_config():
    """Create a sample server config for testing."""
    config = MagicMock(spec=MCPServerConfig)
    config.name = "test-server"
    config.project_id = "project-123"
    config.transport = "http"
    config.enabled = True
    config.url = "http://localhost:8080"
    config.command = None
    config.description = "Test server description"
    config.tools = [{"name": "tool1", "brief": "A tool"}]
    return config


@pytest.fixture
def sample_health_status():
    """Create a sample health status."""
    health = MagicMock()
    health.state.value = "connected"
    return health


# =============================================================================
# Tests for add_mcp_server
# =============================================================================


class TestAddMcpServer:
    """Tests for the add_mcp_server function."""

    @pytest.mark.asyncio
    async def test_add_http_server_success(self, mock_mcp_manager):
        """Test successfully adding an HTTP server."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "test-server",
            "connected": True,
            "full_tool_schemas": [],
        }

        result = await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="Test-Server",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080/mcp",
            headers={"Authorization": "Bearer token"},
        )

        assert result["success"] is True
        assert result["name"] == "test-server"
        mock_mcp_manager.add_server.assert_called_once()

        # Verify the config was created correctly
        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        assert config.name == "test-server"
        assert config.transport == "http"
        assert config.url == "http://localhost:8080/mcp"
        assert config.headers == {"Authorization": "Bearer token"}

    @pytest.mark.asyncio
    async def test_add_stdio_server_success(self, mock_mcp_manager):
        """Test successfully adding a stdio server."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "context7",
            "connected": True,
            "full_tool_schemas": [],
        }

        result = await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="context7",
            transport="stdio",
            project_id="project-456",
            command="uvx",
            args=["context7-mcp"],
            env={"DEBUG": "true"},
        )

        assert result["success"] is True
        assert result["name"] == "context7"

        # Verify the config was created correctly
        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        assert config.command == "uvx"
        assert config.args == ["context7-mcp"]
        assert config.env == {"DEBUG": "true"}

    @pytest.mark.asyncio
    async def test_add_websocket_server_success(self, mock_mcp_manager):
        """Test successfully adding a websocket server."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "ws-server",
            "connected": True,
            "full_tool_schemas": [],
        }

        result = await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="ws-server",
            transport="websocket",
            project_id="project-789",
            url="ws://localhost:8080/mcp",
        )

        assert result["success"] is True
        assert result["name"] == "ws-server"

    @pytest.mark.asyncio
    async def test_add_server_normalizes_name_to_lowercase(self, mock_mcp_manager):
        """Test that server name is normalized to lowercase."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "myserver",
            "full_tool_schemas": [],
        }

        await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="MyServer",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
        )

        # Verify the config was created with lowercase name
        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        assert config.name == "myserver"

    @pytest.mark.asyncio
    async def test_add_server_normalizes_mixed_case_name(self, mock_mcp_manager):
        """Test name normalization with mixed case."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "my-test-server",
            "full_tool_schemas": [],
        }

        await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="My-TEST-Server",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
        )

        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        assert config.name == "my-test-server"

    @pytest.mark.asyncio
    async def test_add_server_with_disabled_flag(self, mock_mcp_manager):
        """Test adding a disabled server."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "disabled-server",
            "full_tool_schemas": [],
        }

        await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="disabled-server",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
            enabled=False,
        )

        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        assert config.enabled is False

    @pytest.mark.asyncio
    async def test_add_server_failure_returns_error(self, mock_mcp_manager):
        """Test handling server add failure from manager."""
        mock_mcp_manager.add_server.return_value = {
            "success": False,
            "error": "Connection refused",
        }

        result = await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="failing-server",
            transport="http",
            project_id="project-123",
            url="http://localhost:9999",
        )

        assert result["success"] is False
        assert result.get("error") == "Connection refused"

    @pytest.mark.asyncio
    async def test_add_server_exception_returns_error_dict(self, mock_mcp_manager):
        """Test handling exception during add returns structured error."""
        mock_mcp_manager.add_server.side_effect = Exception("Network error")

        result = await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="error-server",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
        )

        assert result["success"] is False
        assert "Network error" in result["error"]
        assert result["name"] == "error-server"
        assert "Failed to add server" in result["message"]

    @pytest.mark.asyncio
    async def test_add_server_value_error_exception(self, mock_mcp_manager):
        """Test handling ValueError exception."""
        mock_mcp_manager.add_server.side_effect = ValueError("Invalid config")

        result = await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="invalid-server",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
        )

        assert result["success"] is False
        assert "Invalid config" in result["error"]

    @pytest.mark.asyncio
    async def test_add_server_generates_description_from_tools(self, mock_mcp_manager):
        """Test that description is generated when tools are returned."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "test-server",
            "full_tool_schemas": [
                {"name": "tool1", "description": "First tool"},
                {"name": "tool2", "description": "Second tool"},
            ],
        }

        with patch(
            "gobby.mcp_proxy.actions.generate_server_description",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = "Generated description"

            await add_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                transport="http",
                project_id="project-123",
                url="http://localhost:8080",
            )

            mock_gen.assert_called_once_with(
                server_name="test-server",
                tool_summaries=[
                    {"name": "tool1", "description": "First tool"},
                    {"name": "tool2", "description": "Second tool"},
                ],
            )

    @pytest.mark.asyncio
    async def test_add_server_skips_description_generation_when_provided(self, mock_mcp_manager):
        """Test that description generation is skipped when custom description is provided."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "test-server",
            "full_tool_schemas": [{"name": "tool1", "description": "A tool"}],
        }

        with patch(
            "gobby.mcp_proxy.actions.generate_server_description",
            new_callable=AsyncMock,
        ) as mock_gen:
            await add_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                transport="http",
                project_id="project-123",
                url="http://localhost:8080",
                description="My custom description",
            )

            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_server_skips_description_generation_when_no_tools(self, mock_mcp_manager):
        """Test that description generation is skipped when no tools returned."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "test-server",
            "full_tool_schemas": [],
        }

        with patch(
            "gobby.mcp_proxy.actions.generate_server_description",
            new_callable=AsyncMock,
        ) as mock_gen:
            await add_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                transport="http",
                project_id="project-123",
                url="http://localhost:8080",
            )

            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_server_handles_description_generation_failure(self, mock_mcp_manager):
        """Test that description generation failure doesn't fail the add operation."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "test-server",
            "full_tool_schemas": [{"name": "tool1", "description": "A tool"}],
        }

        with patch(
            "gobby.mcp_proxy.actions.generate_server_description",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.side_effect = Exception("AI service unavailable")

            result = await add_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                transport="http",
                project_id="project-123",
                url="http://localhost:8080",
            )

            # Add should still succeed even if description generation fails
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_add_server_with_all_optional_params(self, mock_mcp_manager):
        """Test adding server with all optional parameters."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "full-server",
            "full_tool_schemas": [],
        }

        await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="full-server",
            transport="stdio",
            project_id="project-123",
            url=None,
            headers=None,
            command="/usr/bin/server",
            args=["--verbose", "--port", "8080"],
            env={"HOME": "/home/user", "PATH": "/usr/bin"},
            enabled=True,
            description="Fully configured server",
        )

        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        assert config.command == "/usr/bin/server"
        assert config.args == ["--verbose", "--port", "8080"]
        assert config.env == {"HOME": "/home/user", "PATH": "/usr/bin"}
        assert config.description == "Fully configured server"


# =============================================================================
# Tests for remove_mcp_server
# =============================================================================


class TestRemoveMcpServer:
    """Tests for the remove_mcp_server function."""

    @pytest.mark.asyncio
    async def test_remove_server_success(self, mock_mcp_manager):
        """Test successfully removing a server."""
        mock_mcp_manager.remove_server.return_value = {"success": True}

        result = await remove_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="test-server",
            project_id="project-123",
        )

        assert result["success"] is True
        mock_mcp_manager.remove_server.assert_called_once_with(
            "test-server", project_id="project-123"
        )

    @pytest.mark.asyncio
    async def test_remove_server_not_found(self, mock_mcp_manager):
        """Test removing non-existent server."""
        mock_mcp_manager.remove_server.return_value = {
            "success": False,
            "error": "Server not found",
        }

        result = await remove_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="nonexistent",
            project_id="project-123",
        )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_remove_server_exception_returns_error_dict(self, mock_mcp_manager):
        """Test handling exception during remove."""
        mock_mcp_manager.remove_server.side_effect = Exception("Database error")

        result = await remove_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="error-server",
            project_id="project-123",
        )

        assert result["success"] is False
        assert "Database error" in result["error"]
        assert result["name"] == "error-server"
        assert "Failed to remove server" in result["message"]

    @pytest.mark.asyncio
    async def test_remove_server_value_error_exception(self, mock_mcp_manager):
        """Test handling ValueError exception during remove."""
        mock_mcp_manager.remove_server.side_effect = ValueError("Server 'test' not found")

        result = await remove_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="test",
            project_id="project-123",
        )

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_remove_server_with_different_project_ids(self, mock_mcp_manager):
        """Test removing servers from different projects."""
        mock_mcp_manager.remove_server.return_value = {"success": True}

        # Remove from project A
        await remove_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="server-a",
            project_id="project-a",
        )
        mock_mcp_manager.remove_server.assert_called_with("server-a", project_id="project-a")

        # Remove from project B
        await remove_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="server-b",
            project_id="project-b",
        )
        mock_mcp_manager.remove_server.assert_called_with("server-b", project_id="project-b")

    @pytest.mark.asyncio
    async def test_remove_server_logs_on_success(self, mock_mcp_manager, caplog):
        """Test that successful removal is logged."""
        mock_mcp_manager.remove_server.return_value = {"success": True}

        import logging

        with caplog.at_level(logging.DEBUG):
            await remove_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                project_id="project-123",
            )

        # The debug log should be present
        assert any("Removed MCP server" in record.message for record in caplog.records)


# =============================================================================
# Tests for list_mcp_servers
# =============================================================================


class TestListMcpServers:
    """Tests for the list_mcp_servers function."""

    @pytest.mark.asyncio
    async def test_list_servers_empty(self, mock_mcp_manager):
        """Test listing when no servers configured."""
        mock_mcp_manager.server_configs = []
        mock_mcp_manager.connections = {}
        mock_mcp_manager.health = {}

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is True
        assert result["servers"] == []
        assert result["total_count"] == 0
        assert result["connected_count"] == 0

    @pytest.mark.asyncio
    async def test_list_servers_with_single_server(
        self, mock_mcp_manager, sample_server_config, sample_health_status
    ):
        """Test listing a single server."""
        mock_mcp_manager.server_configs = [sample_server_config]
        mock_mcp_manager.connections = {"test-server": MagicMock()}
        mock_mcp_manager.health = {"test-server": sample_health_status}

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is True
        assert len(result["servers"]) == 1
        assert result["total_count"] == 1
        assert result["connected_count"] == 1

        server = result["servers"][0]
        assert server["name"] == "test-server"
        assert server["project_id"] == "project-123"
        assert server["transport"] == "http"
        assert server["connected"] is True
        assert server["state"] == "connected"

    @pytest.mark.asyncio
    async def test_list_servers_with_multiple_servers(self, mock_mcp_manager):
        """Test listing multiple servers."""
        config1 = MagicMock()
        config1.name = "server1"
        config1.project_id = "project-123"
        config1.transport = "http"
        config1.enabled = True
        config1.url = "http://localhost:8080"
        config1.command = None
        config1.description = "Server 1"
        config1.tools = [{"name": "tool1"}]

        config2 = MagicMock()
        config2.name = "server2"
        config2.project_id = None  # Global server
        config2.transport = "stdio"
        config2.enabled = True
        config2.url = None
        config2.command = "uvx"
        config2.description = None
        config2.tools = []

        config3 = MagicMock()
        config3.name = "server3"
        config3.project_id = "project-456"
        config3.transport = "websocket"
        config3.enabled = False
        config3.url = "ws://localhost:9090"
        config3.command = None
        config3.description = "Disabled server"
        config3.tools = []

        health1 = MagicMock()
        health1.state.value = "connected"

        health2 = MagicMock()
        health2.state.value = "disconnected"

        mock_mcp_manager.server_configs = [config1, config2, config3]
        mock_mcp_manager.connections = {"server1": MagicMock()}
        mock_mcp_manager.health = {"server1": health1, "server2": health2}

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is True
        assert len(result["servers"]) == 3
        assert result["total_count"] == 3
        assert result["connected_count"] == 1

        # Check server1 details
        server1 = next(s for s in result["servers"] if s["name"] == "server1")
        assert server1["project_id"] == "project-123"
        assert server1["transport"] == "http"
        assert server1["connected"] is True
        assert server1["state"] == "connected"

        # Check server2 details (global)
        server2 = next(s for s in result["servers"] if s["name"] == "server2")
        assert server2["project_id"] is None
        assert server2["connected"] is False
        assert server2["state"] == "disconnected"

        # Check server3 details (no health info)
        server3 = next(s for s in result["servers"] if s["name"] == "server3")
        assert server3["enabled"] is False
        assert server3["state"] == "unknown"

    @pytest.mark.asyncio
    async def test_list_servers_with_disconnected_server(self, mock_mcp_manager):
        """Test listing servers where some are disconnected."""
        config = MagicMock()
        config.name = "disconnected-server"
        config.project_id = "project-123"
        config.transport = "http"
        config.enabled = True
        config.url = "http://localhost:8080"
        config.command = None
        config.description = None
        config.tools = []

        mock_mcp_manager.server_configs = [config]
        mock_mcp_manager.connections = {}  # Not connected
        mock_mcp_manager.health = {}

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is True
        server = result["servers"][0]
        assert server["connected"] is False
        assert server["state"] == "unknown"

    @pytest.mark.asyncio
    async def test_list_servers_health_states(self, mock_mcp_manager):
        """Test various health states are properly reported."""
        config1 = MagicMock()
        config1.name = "healthy"
        config1.project_id = "project-123"
        config1.transport = "http"
        config1.enabled = True
        config1.url = "http://localhost:8080"
        config1.command = None
        config1.description = None
        config1.tools = []

        config2 = MagicMock()
        config2.name = "unhealthy"
        config2.project_id = "project-123"
        config2.transport = "http"
        config2.enabled = True
        config2.url = "http://localhost:8081"
        config2.command = None
        config2.description = None
        config2.tools = []

        health1 = MagicMock()
        health1.state.value = "connected"

        health2 = MagicMock()
        health2.state.value = "failed"

        mock_mcp_manager.server_configs = [config1, config2]
        mock_mcp_manager.connections = {"healthy": MagicMock(), "unhealthy": MagicMock()}
        mock_mcp_manager.health = {"healthy": health1, "unhealthy": health2}

        result = await list_mcp_servers(mock_mcp_manager)

        healthy_server = next(s for s in result["servers"] if s["name"] == "healthy")
        assert healthy_server["state"] == "connected"

        unhealthy_server = next(s for s in result["servers"] if s["name"] == "unhealthy")
        assert unhealthy_server["state"] == "failed"

    @pytest.mark.asyncio
    async def test_list_servers_exception_returns_error(self, mock_mcp_manager):
        """Test handling exception during list."""
        mock_mcp_manager.server_configs = MagicMock()
        mock_mcp_manager.server_configs.__iter__ = MagicMock(
            side_effect=Exception("Database error")
        )

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is False
        assert "Database error" in result["error"]
        assert result["servers"] == []

    @pytest.mark.asyncio
    async def test_list_servers_with_tools_metadata(self, mock_mcp_manager):
        """Test that tools metadata is included in listing."""
        config = MagicMock()
        config.name = "server-with-tools"
        config.project_id = "project-123"
        config.transport = "http"
        config.enabled = True
        config.url = "http://localhost:8080"
        config.command = None
        config.description = "Server with tools"
        config.tools = [
            {"name": "tool1", "brief": "First tool"},
            {"name": "tool2", "brief": "Second tool"},
        ]

        mock_mcp_manager.server_configs = [config]
        mock_mcp_manager.connections = {}
        mock_mcp_manager.health = {}

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is True
        server = result["servers"][0]
        assert server["tools"] == [
            {"name": "tool1", "brief": "First tool"},
            {"name": "tool2", "brief": "Second tool"},
        ]

    @pytest.mark.asyncio
    async def test_list_servers_with_none_tools(self, mock_mcp_manager):
        """Test listing server with None tools field returns empty list."""
        config = MagicMock()
        config.name = "server-no-tools"
        config.project_id = "project-123"
        config.transport = "http"
        config.enabled = True
        config.url = "http://localhost:8080"
        config.command = None
        config.description = None
        config.tools = None

        mock_mcp_manager.server_configs = [config]
        mock_mcp_manager.connections = {}
        mock_mcp_manager.health = {}

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is True
        server = result["servers"][0]
        # The implementation uses `config.tools or []` which converts None to []
        assert server["tools"] == []


# =============================================================================
# Edge Cases and Integration Scenarios
# =============================================================================


class TestEdgeCases:
    """Test edge cases and corner scenarios."""

    @pytest.mark.asyncio
    async def test_add_server_with_empty_name(self, mock_mcp_manager):
        """Test adding server with empty name."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "",
            "full_tool_schemas": [],
        }

        result = await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
        )

        # Empty name should still be processed (validation happens in manager)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_add_server_with_special_characters_in_name(self, mock_mcp_manager):
        """Test server name normalization handles special characters."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "my-server_v2.0",
            "full_tool_schemas": [],
        }

        await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="MY-SERVER_V2.0",
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
        )

        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        assert config.name == "my-server_v2.0"

    @pytest.mark.asyncio
    async def test_add_server_with_unicode_name(self, mock_mcp_manager):
        """Test server name normalization handles unicode."""
        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "server-\u00e9",
            "full_tool_schemas": [],
        }

        await add_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="Server-\u00c9",  # Capital E with acute
            transport="http",
            project_id="project-123",
            url="http://localhost:8080",
        )

        call_args = mock_mcp_manager.add_server.call_args
        config = call_args[0][0]
        # Should be lowercased
        assert config.name == "server-\u00e9"

    @pytest.mark.asyncio
    async def test_list_servers_with_large_number_of_servers(self, mock_mcp_manager):
        """Test listing a large number of servers."""
        configs = []
        for i in range(100):
            config = MagicMock()
            config.name = f"server-{i}"
            config.project_id = f"project-{i % 10}"
            config.transport = "http"
            config.enabled = True
            config.url = f"http://localhost:{8080 + i}"
            config.command = None
            config.description = f"Server {i}"
            config.tools = []
            configs.append(config)

        mock_mcp_manager.server_configs = configs
        mock_mcp_manager.connections = {}
        mock_mcp_manager.health = {}

        result = await list_mcp_servers(mock_mcp_manager)

        assert result["success"] is True
        assert result["total_count"] == 100
        assert len(result["servers"]) == 100

    @pytest.mark.asyncio
    async def test_remove_server_with_empty_project_id(self, mock_mcp_manager):
        """Test removing server with empty project_id."""
        mock_mcp_manager.remove_server.return_value = {"success": True}

        result = await remove_mcp_server(
            mcp_manager=mock_mcp_manager,
            name="test-server",
            project_id="",
        )

        assert result["success"] is True
        mock_mcp_manager.remove_server.assert_called_once_with("test-server", project_id="")


class TestConcurrencyScenarios:
    """Test concurrent operation scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_add_operations(self, mock_mcp_manager):
        """Test multiple concurrent add operations."""
        import asyncio

        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "test",
            "full_tool_schemas": [],
        }

        async def add_server(name: str):
            return await add_mcp_server(
                mcp_manager=mock_mcp_manager,
                name=name,
                transport="http",
                project_id="project-123",
                url="http://localhost:8080",
            )

        results = await asyncio.gather(
            add_server("server-1"),
            add_server("server-2"),
            add_server("server-3"),
        )

        assert all(r["success"] for r in results)
        assert mock_mcp_manager.add_server.call_count == 3

    @pytest.mark.asyncio
    async def test_concurrent_list_operations(self, mock_mcp_manager):
        """Test multiple concurrent list operations."""
        import asyncio

        config = MagicMock()
        config.name = "test-server"
        config.project_id = "project-123"
        config.transport = "http"
        config.enabled = True
        config.url = "http://localhost:8080"
        config.command = None
        config.description = None
        config.tools = []

        mock_mcp_manager.server_configs = [config]
        mock_mcp_manager.connections = {}
        mock_mcp_manager.health = {}

        results = await asyncio.gather(
            list_mcp_servers(mock_mcp_manager),
            list_mcp_servers(mock_mcp_manager),
            list_mcp_servers(mock_mcp_manager),
        )

        assert all(r["success"] for r in results)
        assert all(len(r["servers"]) == 1 for r in results)


class TestLogging:
    """Test logging behavior."""

    @pytest.mark.asyncio
    async def test_add_server_logs_debug_on_success(self, mock_mcp_manager, caplog):
        """Test that successful add is logged at debug level."""
        import logging

        mock_mcp_manager.add_server.return_value = {
            "success": True,
            "name": "test-server",
            "full_tool_schemas": [],
        }

        with caplog.at_level(logging.DEBUG):
            await add_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                transport="http",
                project_id="project-123",
                url="http://localhost:8080",
            )

        assert any("Added MCP server" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_add_server_logs_error_on_exception(self, mock_mcp_manager, caplog):
        """Test that exception is logged at error level."""
        import logging

        mock_mcp_manager.add_server.side_effect = Exception("Connection failed")

        with caplog.at_level(logging.ERROR):
            await add_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                transport="http",
                project_id="project-123",
                url="http://localhost:8080",
            )

        assert any("Failed to add MCP server" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_remove_server_logs_error_on_exception(self, mock_mcp_manager, caplog):
        """Test that remove exception is logged at error level."""
        import logging

        mock_mcp_manager.remove_server.side_effect = Exception("Delete failed")

        with caplog.at_level(logging.ERROR):
            await remove_mcp_server(
                mcp_manager=mock_mcp_manager,
                name="test-server",
                project_id="project-123",
            )

        assert any("Failed to remove MCP server" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_list_servers_logs_error_on_exception(self, mock_mcp_manager, caplog):
        """Test that list exception is logged at error level."""
        import logging

        mock_mcp_manager.server_configs = MagicMock()
        mock_mcp_manager.server_configs.__iter__ = MagicMock(side_effect=Exception("Query failed"))

        with caplog.at_level(logging.ERROR):
            await list_mcp_servers(mock_mcp_manager)

        assert any("Failed to list MCP servers" in record.message for record in caplog.records)
