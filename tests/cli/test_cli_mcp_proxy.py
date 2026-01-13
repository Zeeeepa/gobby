import json
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner
from gobby.cli.mcp_proxy import mcp_proxy
from gobby.utils.daemon_client import DaemonClient
from gobby.config.app import DaemonConfig


@pytest.fixture
def mock_daemon_client():
    client = MagicMock(spec=DaemonClient)
    client.check_health.return_value = (True, None)
    return client


@pytest.fixture
def cli_runner(mock_daemon_client):
    runner = CliRunner()
    # Patch get_daemon_client to return our mock
    # passing obj to invoke is handled by the runner, but we need to ensure get_daemon_client uses it or is patched
    return runner


@pytest.fixture
def mock_config():
    return MagicMock(spec=DaemonConfig, daemon_port=8765)


def test_list_servers_success(cli_runner, mock_daemon_client, mock_config):
    with patch("gobby.cli.mcp_proxy.get_daemon_client", return_value=mock_daemon_client):
        mock_daemon_client.call_http_api.return_value.status_code = 200
        mock_daemon_client.call_http_api.return_value.json.return_value = {
            "servers": [
                {"name": "server1", "connected": True, "state": "connected"},
                {"name": "server2", "connected": False, "state": "disconnected"},
            ],
            "connected_count": 1,
            "total_count": 2,
        }

        result = cli_runner.invoke(mcp_proxy, ["list-servers"], obj={"config": mock_config})

        assert result.exit_code == 0
        assert "MCP Servers (1/2 connected):" in result.output
        assert "● server1 (connected)" in result.output
        assert "○ server2 (disconnected)" in result.output


def test_list_servers_json(cli_runner, mock_daemon_client, mock_config):
    with patch("gobby.cli.mcp_proxy.get_daemon_client", return_value=mock_daemon_client):
        mock_response = {"servers": [{"name": "server1"}], "connected_count": 1, "total_count": 1}
        mock_daemon_client.call_http_api.return_value.status_code = 200
        mock_daemon_client.call_http_api.return_value.json.return_value = mock_response

        result = cli_runner.invoke(
            mcp_proxy, ["list-servers", "--json"], obj={"config": mock_config}
        )

        assert result.exit_code == 0
        output_json = json.loads(result.output)
        assert output_json == mock_response


def test_list_tools_success(cli_runner, mock_daemon_client, mock_config):
    with patch("gobby.cli.mcp_proxy.get_daemon_client", return_value=mock_daemon_client):
        mock_daemon_client.call_http_api.return_value.status_code = 200
        mock_daemon_client.call_http_api.return_value.json.return_value = {
            "tools": {"server1": [{"name": "tool1", "description": "A test tool"}]}
        }

        result = cli_runner.invoke(mcp_proxy, ["list-tools"], obj={"config": mock_config})

        assert result.exit_code == 0
        assert "server1:" in result.output
        assert "• tool1" in result.output
        assert "A test tool" in result.output


def test_get_schema(cli_runner, mock_daemon_client, mock_config):
    with patch("gobby.cli.mcp_proxy.get_daemon_client", return_value=mock_daemon_client):
        mock_schema = {"name": "tool1", "inputSchema": {}}
        mock_daemon_client.call_http_api.return_value.status_code = 200
        mock_daemon_client.call_http_api.return_value.json.return_value = mock_schema

        result = cli_runner.invoke(
            mcp_proxy, ["get-schema", "server1", "tool1"], obj={"config": mock_config}
        )

        assert result.exit_code == 0
        output_json = json.loads(result.output)
        assert output_json == mock_schema

        # Verify correct endpoint called
        mock_daemon_client.call_http_api.assert_called_with(
            "/mcp/tools/schema",
            method="POST",
            json_data={"server_name": "server1", "tool_name": "tool1"},
            timeout=30.0,
        )


def test_call_tool_success(cli_runner, mock_daemon_client, mock_config):
    with patch("gobby.cli.mcp_proxy.get_daemon_client", return_value=mock_daemon_client):
        expected_result = {"result": "success"}
        mock_daemon_client.call_http_api.return_value.status_code = 200
        mock_daemon_client.call_http_api.return_value.json.return_value = {
            "success": True,
            "result": expected_result,
        }

        result = cli_runner.invoke(
            mcp_proxy,
            ["call-tool", "server1", "tool1", "-a", "arg1=val1"],
            obj={"config": mock_config},
        )

        assert result.exit_code == 0
        assert json.dumps(expected_result, indent=2) in result.output

        mock_daemon_client.call_http_api.assert_called_with(
            "/mcp/tools/call",
            method="POST",
            json_data={
                "server_name": "server1",
                "tool_name": "tool1",
                "arguments": {"arg1": "val1"},
            },
            timeout=30.0,
        )


def test_daemon_not_running(cli_runner, mock_daemon_client, mock_config):
    with patch("gobby.cli.mcp_proxy.get_daemon_client", return_value=mock_daemon_client):
        mock_daemon_client.check_health.return_value = (False, None)

        result = cli_runner.invoke(mcp_proxy, ["list-servers"], obj={"config": mock_config})

        assert result.exit_code == 1
        assert "Gobby daemon is not running" in result.output
