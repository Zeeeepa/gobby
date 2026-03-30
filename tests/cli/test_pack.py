"""Tests for gobby pack and unpack CLI commands."""

import json
import os
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gobby.cli.pack import pack, unpack, _human_size

pytestmark = pytest.mark.unit


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestPackHelpers:
    def test_human_size(self) -> None:
        assert _human_size(500) == "500B"
        assert _human_size(1024) == "1.0KB"
        assert _human_size(1048576) == "1.0MB"
        assert _human_size(1073741824) == "1.0GB"
        assert _human_size(1099511627776) == "1.0TB"


class TestPackCommand:
    @patch("gobby.cli.pack.GOBBY_HOME")
    def test_pack_no_gobby_home(self, mock_home, runner: CliRunner) -> None:
        mock_home.exists.return_value = False
        result = runner.invoke(pack, [])
        assert result.exit_code == 1
        assert "No ~/.gobby directory found" in result.output

    @patch("gobby.cli.pack.GOBBY_HOME")
    @patch("gobby.cli.pack._daemon_is_running", return_value=False)
    @patch("gobby.cli.pack._docker_available", return_value=False)
    def test_pack_dry_run(
        self, mock_docker, mock_daemon, mock_home, tmp_path, runner: CliRunner
    ) -> None:
        # Setup fake GOBBY_HOME structure
        fake_home = tmp_path / ".gobby"
        fake_home.mkdir()
        (fake_home / "gobby-hub.db").write_text("fake db")
        (fake_home / "session_transcripts").mkdir()
        (fake_home / "session_transcripts" / "1.txt").write_text("ts")

        mock_home.__truediv__.side_effect = lambda x: fake_home / x
        mock_home.exists.return_value = True

        result = runner.invoke(pack, ["--dry-run"])
        assert result.exit_code == 0
        assert "Pack contents (dry run):" in result.output
        assert "gobby/gobby-hub.db" in result.output
        assert "gobby/session_transcripts/" in result.output

    @patch("gobby.cli.pack.GOBBY_HOME")
    @patch("gobby.cli.pack._daemon_is_running", return_value=False)
    @patch("gobby.cli.pack._docker_available", return_value=False)
    def test_pack_success(
        self, mock_docker, mock_daemon, mock_home, tmp_path, runner: CliRunner
    ) -> None:
        fake_home = tmp_path / ".gobby"
        fake_home.mkdir()
        (fake_home / "gobby-hub.db").write_text("db content")

        mock_home.__truediv__.side_effect = lambda x: fake_home / x
        mock_home.exists.return_value = True

        out_path = tmp_path / "out.tar.gz"
        result = runner.invoke(pack, [str(out_path)])
        assert result.exit_code == 0
        assert "Packing Gobby data" in result.output
        assert out_path.exists()

        # Verify tarball
        with tarfile.open(out_path, "r:gz") as tar:
            names = tar.getnames()
            assert "gobby/manifest.json" in names
            assert "gobby/gobby-hub.db" in names

    @patch("gobby.cli.pack.GOBBY_HOME")
    @patch("gobby.cli.pack._daemon_is_running", return_value=True)
    @patch("gobby.cli.pack.stop_daemon")
    @patch("gobby.cli.pack._start_daemon")
    @patch("gobby.cli.pack._docker_available", return_value=False)
    def test_pack_daemon_lifecycle(
        self,
        mock_docker,
        mock_start,
        mock_stop,
        mock_daemon,
        mock_home,
        tmp_path,
        runner: CliRunner,
    ) -> None:
        fake_home = tmp_path / ".gobby"
        fake_home.mkdir()

        mock_home.__truediv__.side_effect = lambda x: fake_home / x
        mock_home.exists.return_value = True

        out_path = tmp_path / "out.tar.gz"
        result = runner.invoke(pack, [str(out_path)])

        assert result.exit_code == 0
        mock_stop.assert_called_once()
        mock_start.assert_called_once()


class TestUnpackCommand:
    def _create_fake_archive(self, tmp_path: Path) -> Path:
        out_path = tmp_path / "testpack.tar.gz"
        with tarfile.open(out_path, "w:gz") as tar:
            # manifest
            m_path = tmp_path / "manifest.json"
            m_path.write_text(json.dumps({"version": 1}))
            tar.add(str(m_path), arcname="gobby/manifest.json")

            # db
            db_path = tmp_path / "gobby-hub.db"
            db_path.write_text("restored db")
            tar.add(str(db_path), arcname="gobby/gobby-hub.db")
        return out_path

    @patch("gobby.cli.pack.GOBBY_HOME")
    def test_unpack_dry_run(self, mock_home, tmp_path, runner: CliRunner) -> None:
        archive = self._create_fake_archive(tmp_path)

        result = runner.invoke(unpack, [str(archive), "--dry-run"])
        assert result.exit_code == 0
        assert "Contents:" in result.output
        assert "gobby/gobby-hub.db" in result.output

    @patch("gobby.cli.pack.GOBBY_HOME")
    @patch("gobby.cli.pack._daemon_is_running", return_value=False)
    @patch("gobby.cli.pack._docker_available", return_value=False)
    @patch("gobby.cli.pack.install_git_hooks", return_value={"success": True, "installed": []})
    def test_unpack_success(
        self, mock_hooks, mock_docker, mock_daemon, mock_home, tmp_path, runner: CliRunner
    ) -> None:
        archive = self._create_fake_archive(tmp_path)

        fake_home = tmp_path / ".gobby"
        # don't exist yet to avoid safety check block
        mock_home.exists.return_value = False
        mock_home.__truediv__.side_effect = lambda x: fake_home / x
        mock_home.mkdir = fake_home.mkdir

        result = runner.invoke(unpack, [str(archive)])
        assert result.exit_code == 0

        assert (fake_home / "gobby-hub.db").exists()
        assert (fake_home / "gobby-hub.db").read_text() == "restored db"

    @patch("gobby.cli.pack.GOBBY_HOME")
    def test_unpack_aborts_if_exists(self, mock_home, tmp_path, runner: CliRunner) -> None:
        archive = self._create_fake_archive(tmp_path)

        fake_db = MagicMock()
        fake_db.exists.return_value = True

        mock_home.exists.return_value = True
        mock_home.__truediv__.return_value = fake_db

        # Answer NO to confirmation
        result = runner.invoke(unpack, [str(archive)], input="N\n")
        assert result.exit_code == 0  # Aborted prints, then sys.exit(0)
        assert "Aborted" in result.output

    @patch("gobby.cli.pack.GOBBY_HOME")
    @patch("gobby.cli.pack._daemon_is_running", return_value=False)
    @patch("gobby.cli.pack._docker_available", return_value=False)
    @patch("gobby.cli.pack.install_git_hooks", return_value={"success": True, "installed": []})
    def test_unpack_force(
        self, mock_hooks, mock_docker, mock_daemon, mock_home, tmp_path, runner: CliRunner
    ) -> None:
        archive = self._create_fake_archive(tmp_path)

        fake_home = tmp_path / ".gobby"
        fake_home.mkdir()
        (fake_home / "gobby-hub.db").write_text("old")

        mock_home.exists.return_value = True
        mock_home.__truediv__.side_effect = lambda x: fake_home / x
        mock_home.mkdir = fake_home.mkdir

        # Note we pass --force to bypass confirmation
        result = runner.invoke(unpack, [str(archive), "--force"])
        assert result.exit_code == 0

        assert (fake_home / "gobby-hub.db").read_text() == "restored db"
