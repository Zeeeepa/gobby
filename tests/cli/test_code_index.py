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


def _mock_subprocess_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestCodeIndexIndex:
    """Tests for gobby index (default subcommand)."""

    @patch("gobby.cli.code_index._gcode_bin")
    @patch("subprocess.run")
    def test_index_success(
        self, mock_run: MagicMock, mock_bin: MagicMock, runner: CliRunner, tmp_path
    ) -> None:
        mock_bin.return_value = tmp_path / "gcode"
        (tmp_path / "gcode").touch()
        mock_run.return_value = _mock_subprocess_result(stdout="Indexed 10 files")

        result = runner.invoke(cli, ["index", str(tmp_path)])

        assert result.exit_code == 0
        assert "Indexed 10 files" in result.output
        mock_run.assert_called_once()

    @patch("gobby.cli.code_index._gcode_bin")
    @patch("subprocess.run")
    def test_index_full_flag(
        self, mock_run: MagicMock, mock_bin: MagicMock, runner: CliRunner, tmp_path
    ) -> None:
        mock_bin.return_value = tmp_path / "gcode"
        (tmp_path / "gcode").touch()
        mock_run.return_value = _mock_subprocess_result()

        result = runner.invoke(cli, ["index", str(tmp_path), "--full"])

        assert result.exit_code == 0
        cmd = mock_run.call_args[0][0]
        assert "--full" in cmd

    @patch("gobby.cli.code_index._gcode_bin")
    def test_index_gcode_not_installed(
        self, mock_bin: MagicMock, runner: CliRunner, tmp_path
    ) -> None:
        mock_bin.return_value = tmp_path / "gcode"  # doesn't exist

        result = runner.invoke(cli, ["index", str(tmp_path)])

        assert result.exit_code != 0
        assert "gcode not installed" in result.output

    def test_index_invalid_path(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["index", "/nonexistent/path"])

        # Either gcode-not-installed or not-a-directory, depending on environment
        assert result.exit_code != 0

    @patch("gobby.cli.code_index._gcode_bin")
    @patch("subprocess.run")
    def test_index_gcode_failure(
        self, mock_run: MagicMock, mock_bin: MagicMock, runner: CliRunner, tmp_path
    ) -> None:
        mock_bin.return_value = tmp_path / "gcode"
        (tmp_path / "gcode").touch()
        mock_run.return_value = _mock_subprocess_result(returncode=1, stderr="parse error")

        result = runner.invoke(cli, ["index", str(tmp_path)])

        assert result.exit_code != 0
        assert "parse error" in result.output

    @patch("gobby.cli.code_index._git_repo_root", return_value="/fake/repo")
    @patch("gobby.cli.code_index._gcode_bin")
    @patch("subprocess.run")
    def test_index_default_path_uses_git_root(
        self,
        mock_run: MagicMock,
        mock_bin: MagicMock,
        mock_git: MagicMock,
        runner: CliRunner,
        tmp_path,
    ) -> None:
        mock_bin.return_value = tmp_path / "gcode"
        (tmp_path / "gcode").touch()
        mock_run.return_value = _mock_subprocess_result()

        with patch("gobby.cli.code_index.os.path.isdir", return_value=True):
            result = runner.invoke(cli, ["index"])

        assert result.exit_code == 0
        cmd = mock_run.call_args[0][0]
        assert "/fake/repo" in cmd


class TestCodeIndexStatus:
    """Tests for gobby index status."""

    @patch("gobby.cli.code_index._get_storage")
    def test_status_list_projects(self, mock_get_storage: MagicMock, runner: CliRunner) -> None:
        mock_storage = MagicMock()
        mock_proj = MagicMock()
        mock_proj.id = "proj-1"
        mock_proj.total_files = 50
        mock_proj.total_symbols = 200
        mock_proj.last_indexed_at = ""
        mock_storage.list_indexed_projects.return_value = [mock_proj]
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["index", "status"])

        assert result.exit_code == 0
        assert "proj-1" in result.output
        assert "50 files" in result.output

    @patch("gobby.cli.code_index._get_storage")
    def test_status_no_projects(self, mock_get_storage: MagicMock, runner: CliRunner) -> None:
        mock_storage = MagicMock()
        mock_storage.list_indexed_projects.return_value = []
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["index", "status"])

        assert result.exit_code == 0
        assert "No indexed projects" in result.output

    @patch("gobby.cli.code_index._get_storage")
    def test_status_specific_project(self, mock_get_storage: MagicMock, runner: CliRunner) -> None:
        mock_storage = MagicMock()
        mock_stats = MagicMock()
        mock_stats.id = "my-proj"
        mock_stats.root_path = "/home/user/project"
        mock_stats.total_files = 100
        mock_stats.total_symbols = 500
        mock_stats.last_indexed_at = "2025-01-01T00:00:00"
        mock_stats.index_duration_ms = 1200
        mock_storage.get_project_stats.return_value = mock_stats
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["index", "status", "-p", "my-proj"])

        assert result.exit_code == 0
        assert "my-proj" in result.output
        assert "Files: 100" in result.output
        assert "Symbols: 500" in result.output

    @patch("gobby.cli.code_index._get_storage")
    def test_status_project_not_indexed(
        self, mock_get_storage: MagicMock, runner: CliRunner
    ) -> None:
        mock_storage = MagicMock()
        mock_storage.get_project_stats.return_value = None
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["index", "status", "-p", "missing"])

        assert result.exit_code == 0
        assert "not indexed" in result.output


class TestCodeIndexInvalidate:
    """Tests for gobby index invalidate."""

    @patch("gobby.cli.code_index._auto_project_id", return_value="auto-proj")
    @patch("gobby.cli.code_index._get_storage")
    def test_invalidate_success(
        self, mock_get_storage: MagicMock, mock_pid: MagicMock, runner: CliRunner
    ) -> None:
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["index", "invalidate"])

        assert result.exit_code == 0
        assert "Index invalidated" in result.output
        assert "auto-proj" in result.output
        mock_storage.delete_symbols_for_project.assert_called_once_with("auto-proj")

    @patch("gobby.cli.code_index._get_storage")
    def test_invalidate_explicit_project(
        self, mock_get_storage: MagicMock, runner: CliRunner
    ) -> None:
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage

        result = runner.invoke(cli, ["index", "invalidate", "-p", "my-proj"])

        assert result.exit_code == 0
        assert "Index invalidated" in result.output
        assert "my-proj" in result.output


def test_help(runner: CliRunner) -> None:
    """index --help works and shows examples."""
    result = runner.invoke(cli, ["index", "--help"])
    assert result.exit_code == 0
    assert "Code indexing commands" in result.output
    assert "status" in result.output
    assert "invalidate" in result.output


@patch("gobby.cli.code_index._gcode_bin")
@patch("subprocess.run")
def test_default_routing_with_path(
    mock_run: MagicMock, mock_bin: MagicMock, runner: CliRunner, tmp_path
) -> None:
    """gobby index <path> routes to the index subcommand without explicit 'index'."""
    mock_bin.return_value = tmp_path / "gcode"
    (tmp_path / "gcode").touch()
    mock_run.return_value = _mock_subprocess_result(stdout="Done")

    result = runner.invoke(cli, ["index", str(tmp_path)])

    assert result.exit_code == 0
