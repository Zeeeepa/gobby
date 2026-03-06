"""Tests for the code-index CLI module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli import cli

pytestmark = pytest.mark.unit


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCodeIndexIndex:
    """Tests for gobby code-index index."""

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_index_success(self, mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (True, None)
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "files_indexed": 10,
            "files_skipped": 5,
            "symbols_found": 42,
            "duration_ms": 150,
            "errors": [],
        }
        mock_client.call_http_api.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "index", str(tmp_path)])

        assert result.exit_code == 0
        assert "Files indexed: 10" in result.output
        assert "Symbols found: 42" in result.output
        mock_client.call_http_api.assert_called_once()
        call_args = mock_client.call_http_api.call_args
        assert call_args[0][0] == "/api/code-index/index"
        assert call_args[1]["json_data"]["incremental"] is True

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_index_full_flag(self, mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (True, None)
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "files_indexed": 10,
            "files_skipped": 0,
            "symbols_found": 42,
            "duration_ms": 300,
            "errors": [],
        }
        mock_client.call_http_api.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "index", str(tmp_path), "--full"])

        assert result.exit_code == 0
        call_args = mock_client.call_http_api.call_args
        assert call_args[1]["json_data"]["incremental"] is False

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_index_daemon_not_running(self, mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (False, "Connection refused")
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "index", str(tmp_path)])

        assert result.exit_code != 0
        assert "Daemon not running" in result.output

    def test_index_invalid_path(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["code-index", "index", "/nonexistent/path"])

        assert result.exit_code != 0
        assert "Not a directory" in result.output

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_index_http_error(self, mock_get_client: MagicMock, runner: CliRunner, tmp_path) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (True, None)
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_client.call_http_api.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "index", str(tmp_path)])

        assert result.exit_code != 0
        assert "Indexing failed" in result.output


class TestCodeIndexStatus:
    """Tests for gobby code-index status."""

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_status_list_projects(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (True, None)
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "projects": [
                {"id": "proj-1", "total_files": 50, "total_symbols": 200},
            ]
        }
        mock_client.call_http_api.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "status"])

        assert result.exit_code == 0
        assert "proj-1" in result.output
        assert "50 files" in result.output

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_status_no_projects(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (True, None)
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"projects": []}
        mock_client.call_http_api.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "status"])

        assert result.exit_code == 0
        assert "No indexed projects" in result.output

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_status_specific_project(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (True, None)
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "indexed": True,
            "id": "my-proj",
            "root_path": "/home/user/project",
            "total_files": 100,
            "total_symbols": 500,
            "last_indexed_at": "2025-01-01T00:00:00",
            "index_duration_ms": 1200,
        }
        mock_client.call_http_api.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "status", "-p", "my-proj"])

        assert result.exit_code == 0
        assert "my-proj" in result.output
        assert "Files: 100" in result.output
        assert "Symbols: 500" in result.output


class TestCodeIndexInvalidate:
    """Tests for gobby code-index invalidate."""

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_invalidate_success(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (True, None)
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"status": "ok", "project_id": "my-proj"}
        mock_client.call_http_api.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "invalidate", "-p", "my-proj"])

        assert result.exit_code == 0
        assert "Index invalidated" in result.output
        assert "my-proj" in result.output

    @patch("gobby.cli.code_index._get_daemon_client")
    def test_invalidate_daemon_not_running(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.check_health.return_value = (False, "Connection refused")
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["code-index", "invalidate", "-p", "test"])

        assert result.exit_code != 0
        assert "Daemon not running" in result.output


def test_help(runner: CliRunner) -> None:
    """code-index --help works."""
    result = runner.invoke(cli, ["code-index", "--help"])
    assert result.exit_code == 0
    assert "Code indexing commands" in result.output


def test_index_help(runner: CliRunner) -> None:
    """code-index index --help works."""
    result = runner.invoke(cli, ["code-index", "index", "--help"])
    assert result.exit_code == 0
    assert "Index a directory" in result.output
