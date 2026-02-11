"""Tests for --mem0 flag on daemon commands and mem0 status display."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from gobby.utils.status import format_status_message

import pytest

pytestmark = pytest.mark.unit


class TestStatusMem0Display:
    """Tests for mem0 status in format_status_message."""

    def test_status_shows_mem0_installed_healthy(self) -> None:
        msg = format_status_message(
            running=True,
            pid=123,
            mem0_installed=True,
            mem0_healthy=True,
            mem0_url="http://localhost:8888",
        )
        assert "Mem0" in msg
        assert "Healthy" in msg or "healthy" in msg
        assert "localhost:8888" in msg

    def test_status_shows_mem0_installed_unhealthy(self) -> None:
        msg = format_status_message(
            running=True,
            pid=123,
            mem0_installed=True,
            mem0_healthy=False,
            mem0_url="http://localhost:8888",
        )
        assert "Mem0" in msg
        assert "Unhealthy" in msg or "unhealthy" in msg or "Not responding" in msg

    def test_status_shows_mem0_not_installed(self) -> None:
        msg = format_status_message(
            running=True,
            pid=123,
            mem0_installed=False,
            mem0_healthy=False,
        )
        assert "Mem0" in msg
        assert "Not installed" in msg or "not installed" in msg

    def test_status_omits_mem0_when_no_data(self) -> None:
        """When no mem0 params are passed, no Mem0 section appears."""
        msg = format_status_message(running=True, pid=123)
        assert "Mem0" not in msg


class TestDaemonMem0Flag:
    """Tests for --mem0 flag on start/stop/restart."""

    def test_start_mem0_runs_compose_up(self, tmp_path: Path) -> None:
        """start --mem0 should run docker compose up for mem0."""
        from gobby.cli.daemon import _mem0_start

        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _mem0_start(tmp_path)

        compose_calls = [c for c in mock_run.call_args_list if "up" in str(c)]
        assert len(compose_calls) >= 1

    def test_start_mem0_skips_when_not_installed(self, tmp_path: Path) -> None:
        """start --mem0 does nothing when mem0 is not installed."""
        from gobby.cli.daemon import _mem0_start

        with patch("subprocess.run") as mock_run:
            _mem0_start(tmp_path)

        mock_run.assert_not_called()

    def test_stop_mem0_runs_compose_down(self, tmp_path: Path) -> None:
        """stop --mem0 should run docker compose down."""
        from gobby.cli.daemon import _mem0_stop

        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _mem0_stop(tmp_path)

        compose_calls = [c for c in mock_run.call_args_list if "down" in str(c)]
        assert len(compose_calls) >= 1

    def test_stop_mem0_skips_when_not_installed(self, tmp_path: Path) -> None:
        """stop --mem0 does nothing when mem0 is not installed."""
        from gobby.cli.daemon import _mem0_stop

        with patch("subprocess.run") as mock_run:
            _mem0_stop(tmp_path)

        mock_run.assert_not_called()
