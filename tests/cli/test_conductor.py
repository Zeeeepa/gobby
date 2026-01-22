"""Tests for gobby.cli.conductor module.

Tests for Conductor CLI commands:
- start: Start the conductor loop
- stop: Stop the conductor loop
- restart: Restart the conductor loop
- status: Show conductor status
- chat: Send a message to the conductor
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.integration


class TestConductorStartCommand:
    """Tests for 'conductor start' command."""

    def test_start_conductor_success(self):
        """Test 'conductor start' success."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True, "message": "Conductor started"}
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["start"])

            assert result.exit_code == 0
            assert "started" in result.output.lower() or "Conductor" in result.output

    def test_start_with_interval(self):
        """Test 'conductor start --interval 60'."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["start", "--interval", "60"])

            assert result.exit_code == 0
            # Check that interval was passed
            call_json = mock_post.call_args[1]["json"]
            assert call_json.get("interval") == 60

    def test_start_with_autonomous_mode(self):
        """Test 'conductor start --autonomous'."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["start", "--autonomous"])

            assert result.exit_code == 0
            call_json = mock_post.call_args[1]["json"]
            assert call_json.get("autonomous") is True


class TestConductorStopCommand:
    """Tests for 'conductor stop' command."""

    def test_stop_conductor_success(self):
        """Test 'conductor stop' success."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True, "message": "Conductor stopped"}
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["stop"])

            assert result.exit_code == 0
            assert "stopped" in result.output.lower() or "Conductor" in result.output


class TestConductorRestartCommand:
    """Tests for 'conductor restart' command."""

    def test_restart_conductor_success(self):
        """Test 'conductor restart' success."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["restart"])

            assert result.exit_code == 0


class TestConductorStatusCommand:
    """Tests for 'conductor status' command."""

    def test_status_when_running(self):
        """Test 'conductor status' when conductor is running."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "running": True,
                "interval": 30,
                "autonomous": False,
                "last_tick": "2024-01-01T00:00:00Z",
            }
            mock_get.return_value = mock_response

            result = runner.invoke(conductor, ["status"])

            assert result.exit_code == 0
            assert "running" in result.output.lower()

    def test_status_when_stopped(self):
        """Test 'conductor status' when conductor is stopped."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "running": False,
            }
            mock_get.return_value = mock_response

            result = runner.invoke(conductor, ["status"])

            assert result.exit_code == 0
            assert "not running" in result.output.lower() or "stopped" in result.output.lower()

    def test_status_json_format(self):
        """Test 'conductor status --json'."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "running": True,
                "interval": 30,
            }
            mock_get.return_value = mock_response

            result = runner.invoke(conductor, ["status", "--json"])

            assert result.exit_code == 0
            assert '"running": true' in result.output.lower()


class TestConductorChatCommand:
    """Tests for 'conductor chat' command."""

    def test_chat_send_message(self):
        """Test 'conductor chat' sends message to conductor."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "response": "Message received",
            }
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["chat", "Check all tasks"])

            assert result.exit_code == 0
            call_json = mock_post.call_args[1]["json"]
            assert call_json.get("message") == "Check all tasks"

    def test_chat_displays_response(self):
        """Test 'conductor chat' displays the response."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "response": "Found 3 stale tasks",
            }
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["chat", "status check"])

            assert result.exit_code == 0
            assert "3 stale tasks" in result.output or "response" in result.output.lower()

    def test_chat_json_format(self):
        """Test 'conductor chat --json'."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "response": "OK",
            }
            mock_post.return_value = mock_response

            result = runner.invoke(conductor, ["chat", "--json", "ping"])

            assert result.exit_code == 0
            assert '"success": true' in result.output.lower()


class TestConductorDaemonConnection:
    """Tests for daemon connection handling."""

    def test_start_when_daemon_not_running(self):
        """Test 'conductor start' when daemon is not running."""
        from gobby.cli.conductor import conductor

        runner = CliRunner()

        with patch("gobby.cli.conductor.httpx.post") as mock_post:
            mock_post.side_effect = Exception("Connection refused")

            result = runner.invoke(conductor, ["start"])

            assert "daemon" in result.output.lower() or "connect" in result.output.lower()
