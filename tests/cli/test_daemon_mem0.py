"""Tests for --neo4j flag on daemon commands and Neo4j status display.

NOTE: This file was updated from mem0 → neo4j as part of the
knowledge graph migration (epic #8239, task #8265).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.utils.status import format_status_message

pytestmark = pytest.mark.unit


class TestStatusNeo4jDisplay:
    """Tests for Neo4j status in format_status_message."""

    def test_status_shows_neo4j_installed_healthy(self) -> None:
        msg = format_status_message(
            running=True,
            pid=123,
            neo4j_installed=True,
            neo4j_healthy=True,
            neo4j_url="http://localhost:8474",
        )
        assert "Neo4j" in msg
        assert "Healthy" in msg or "healthy" in msg
        assert "localhost:8474" in msg

    def test_status_shows_neo4j_installed_unhealthy(self) -> None:
        msg = format_status_message(
            running=True,
            pid=123,
            neo4j_installed=True,
            neo4j_healthy=False,
            neo4j_url="http://localhost:8474",
        )
        assert "Neo4j" in msg
        assert "Unhealthy" in msg or "unhealthy" in msg or "Not responding" in msg

    def test_status_shows_neo4j_not_installed(self) -> None:
        msg = format_status_message(
            running=True,
            pid=123,
            neo4j_installed=False,
            neo4j_healthy=False,
        )
        assert "Neo4j" in msg
        assert "Not installed" in msg or "not installed" in msg

    def test_status_omits_neo4j_when_no_data(self) -> None:
        """When no neo4j params are passed, no Neo4j section appears."""
        msg = format_status_message(running=True, pid=123)
        assert "Neo4j" not in msg


class TestDaemonNeo4jFlag:
    """Tests for --neo4j flag on start/stop/restart."""

    def test_start_neo4j_runs_compose_up(self, tmp_path: Path) -> None:
        """start --neo4j should run docker compose up for neo4j."""
        from gobby.cli.daemon import _neo4j_start

        svc_dir = tmp_path / "services" / "neo4j"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with patch("gobby.cli.daemon.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _neo4j_start(tmp_path)

        compose_calls = [c for c in mock_run.call_args_list if "up" in str(c)]
        assert len(compose_calls) >= 1

    def test_start_neo4j_skips_when_not_installed(self, tmp_path: Path) -> None:
        """start --neo4j does nothing when neo4j is not installed."""
        from gobby.cli.daemon import _neo4j_start

        with patch("gobby.cli.daemon.subprocess.run") as mock_run:
            _neo4j_start(tmp_path)

        mock_run.assert_not_called()

    def test_stop_neo4j_runs_compose_down(self, tmp_path: Path) -> None:
        """stop --neo4j should run docker compose down."""
        from gobby.cli.daemon import _neo4j_stop

        svc_dir = tmp_path / "services" / "neo4j"
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}")

        with patch("gobby.cli.daemon.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _neo4j_stop(tmp_path)

        compose_calls = [c for c in mock_run.call_args_list if "down" in str(c)]
        assert len(compose_calls) >= 1

    def test_stop_neo4j_skips_when_not_installed(self, tmp_path: Path) -> None:
        """stop --neo4j does nothing when neo4j is not installed."""
        from gobby.cli.daemon import _neo4j_stop

        with patch("gobby.cli.daemon.subprocess.run") as mock_run:
            _neo4j_stop(tmp_path)

        mock_run.assert_not_called()
