"""Tests for gobby install --mem0 / uninstall --mem0 commands."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from gobby.cli.installers.mem0 import DEFAULT_MEM0_URL, install_mem0, uninstall_mem0

pytestmark = pytest.mark.unit


class TestInstallMem0Local:
    """Tests for local Docker-based mem0 installation."""

    def test_checks_docker_compose(self, tmp_path: Path) -> None:
        """install_mem0 fails if docker compose is not available."""
        with patch("shutil.which", return_value=None):
            result = install_mem0(gobby_home=tmp_path)
        assert not result["success"]
        assert "docker" in result["error"].lower()

    def test_copies_compose_file(self, tmp_path: Path) -> None:
        """install_mem0 copies compose file to services/mem0/."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._wait_for_health", return_value=True),
            patch("gobby.cli.installers.mem0._update_config"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = install_mem0(gobby_home=tmp_path)

        assert result["success"]
        dest = tmp_path / "services" / "mem0" / "docker-compose.yml"
        assert dest.exists()
        # Verify it's valid YAML with expected services
        compose = yaml.safe_load(dest.read_text())
        assert "mem0" in compose["services"]

    def test_runs_docker_compose_up(self, tmp_path: Path) -> None:
        """install_mem0 runs docker compose up -d."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._wait_for_health", return_value=True),
            patch("gobby.cli.installers.mem0._update_config"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            install_mem0(gobby_home=tmp_path)

        # Find the docker compose up call
        compose_calls = [c for c in mock_run.call_args_list if "up" in str(c)]
        assert len(compose_calls) >= 1, "Expected docker compose up call"

        # Verify exact command structure
        # args[0] is the command list
        last_call_args = compose_calls[-1].args[0]
        assert "docker" in last_call_args
        assert "compose" in last_call_args
        assert "up" in last_call_args
        assert "-d" in last_call_args
        assert "--remove-orphans" in last_call_args

    def test_updates_config_on_success(self, tmp_path: Path) -> None:
        """install_mem0 updates daemon config with mem0_url."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._wait_for_health", return_value=True),
            patch("gobby.cli.installers.mem0._update_config") as mock_update,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            install_mem0(gobby_home=tmp_path)

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args
        # Should pass mem0_url
        assert DEFAULT_MEM0_URL in str(call_kwargs)

    def test_docker_compose_failure(self, tmp_path: Path) -> None:
        """install_mem0 fails when docker compose up fails."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stderr="container failed to start")
            result = install_mem0(gobby_home=tmp_path)

        assert not result["success"]
        assert "compose" in result["error"].lower() or "docker" in result["error"].lower()

    def test_health_check_timeout(self, tmp_path: Path) -> None:
        """install_mem0 fails when health check times out."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._wait_for_health", return_value=False),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = install_mem0(gobby_home=tmp_path)

        assert not result["success"]
        assert "health" in result["error"].lower()


class TestInstallMem0Remote:
    """Tests for remote mem0 installation (--remote)."""

    def test_remote_skips_docker(self, tmp_path: Path) -> None:
        """Remote mode doesn't check for Docker."""
        with (
            patch("gobby.cli.installers.mem0._check_remote_health", return_value=True),
            patch("gobby.cli.installers.mem0._update_config"),
        ):
            result = install_mem0(
                gobby_home=tmp_path,
                remote_url="http://mem0.example.com:8888",
            )

        assert result["success"]
        # No compose file should be copied
        assert not (tmp_path / "services" / "mem0").exists()

    def test_remote_verifies_url(self, tmp_path: Path) -> None:
        """Remote mode verifies the URL is reachable."""
        with patch("gobby.cli.installers.mem0._check_remote_health", return_value=False):
            result = install_mem0(
                gobby_home=tmp_path,
                remote_url="http://unreachable:8888",
            )

        assert not result["success"]
        assert "unreachable" in result["error"].lower() or "remote" in result["error"].lower()

    def test_remote_updates_config(self, tmp_path: Path) -> None:
        """Remote mode updates config with the remote URL."""
        with (
            patch("gobby.cli.installers.mem0._check_remote_health", return_value=True),
            patch("gobby.cli.installers.mem0._update_config") as mock_update,
        ):
            install_mem0(
                gobby_home=tmp_path,
                remote_url="http://mem0.example.com:8888",
            )

        mock_update.assert_called_once()
        assert "http://mem0.example.com:8888" in str(mock_update.call_args)


class TestUninstallMem0:
    """Tests for uninstalling mem0."""

    def test_runs_docker_compose_down(self, tmp_path: Path) -> None:
        """uninstall_mem0 runs docker compose down."""
        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with (
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._update_config"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = uninstall_mem0(gobby_home=tmp_path, remove_volumes=False)

        assert result["success"]
        compose_calls = [c for c in mock_run.call_args_list if "down" in str(c)]
        assert len(compose_calls) >= 1

    def test_remove_volumes_flag(self, tmp_path: Path) -> None:
        """uninstall_mem0 with remove_volumes adds -v flag."""
        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with (
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._update_config"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            uninstall_mem0(gobby_home=tmp_path, remove_volumes=True)

        # Check -v flag in docker compose down call
        down_calls = [c for c in mock_run.call_args_list if "down" in str(c)]
        assert any("-v" in str(c) for c in down_calls), "Expected -v flag for volume removal"

    def test_removes_service_directory(self, tmp_path: Path) -> None:
        """uninstall_mem0 removes the services/mem0/ directory."""
        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with (
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._update_config"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            uninstall_mem0(gobby_home=tmp_path, remove_volumes=False)

        assert not svc_dir.exists()

    def test_resets_config(self, tmp_path: Path) -> None:
        """uninstall_mem0 resets mem0_url and mem0_api_key in config."""
        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with (
            patch("subprocess.run") as mock_run,
            patch("gobby.cli.installers.mem0._update_config") as mock_update,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            uninstall_mem0(gobby_home=tmp_path, remove_volumes=False)

        mock_update.assert_called_once()
        # Should reset mem0_url to None
        assert mock_update.call_args[1].get("mem0_url") is None or "None" in str(
            mock_update.call_args
        )

    def test_graceful_when_not_installed(self, tmp_path: Path) -> None:
        """uninstall_mem0 handles case when mem0 is not installed."""
        result = uninstall_mem0(gobby_home=tmp_path, remove_volumes=False)
        assert result["success"]
        assert "not installed" in result.get("message", "").lower() or result.get(
            "already_uninstalled"
        )
