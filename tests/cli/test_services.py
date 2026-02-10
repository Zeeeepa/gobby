"""Tests for mem0 docker-compose bundle and lifecycle utilities."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml

from gobby.cli.services import get_mem0_status, is_mem0_healthy, is_mem0_installed


COMPOSE_FILE = Path(__file__).resolve().parents[2] / "src" / "gobby" / "data" / "docker-compose.mem0.yml"


class TestDockerComposeMem0:
    """Tests for the bundled docker-compose.mem0.yml file."""

    def test_compose_file_exists(self) -> None:
        assert COMPOSE_FILE.exists(), f"Missing {COMPOSE_FILE}"

    @pytest.fixture()
    def compose(self) -> dict:
        return yaml.safe_load(COMPOSE_FILE.read_text())

    def test_valid_yaml(self, compose: dict) -> None:
        assert isinstance(compose, dict)

    def test_has_services(self, compose: dict) -> None:
        assert "services" in compose
        services = compose["services"]
        assert "mem0" in services
        assert "postgres" in services
        assert "neo4j" in services

    def test_mem0_port(self, compose: dict) -> None:
        mem0 = compose["services"]["mem0"]
        ports = mem0["ports"]
        # Should expose 8888
        assert any("8888" in str(p) for p in ports)

    def test_postgres_port(self, compose: dict) -> None:
        pg = compose["services"]["postgres"]
        ports = pg["ports"]
        # Should expose 8432 (non-standard to avoid conflicts)
        assert any("8432" in str(p) for p in ports)

    def test_neo4j_ports(self, compose: dict) -> None:
        neo4j = compose["services"]["neo4j"]
        ports = neo4j["ports"]
        port_str = " ".join(str(p) for p in ports)
        assert "8474" in port_str, "Neo4j HTTP port 8474 not found"
        assert "8687" in port_str, "Neo4j Bolt port 8687 not found"

    def test_restart_policy(self, compose: dict) -> None:
        for name, svc in compose["services"].items():
            assert svc.get("restart") == "unless-stopped", (
                f"Service {name} missing restart: unless-stopped"
            )

    def test_volumes_defined(self, compose: dict) -> None:
        # Top-level volumes section should exist for persistence
        assert "volumes" in compose, "No top-level volumes section"
        volumes = compose["volumes"]
        assert len(volumes) >= 2, "Expected at least 2 volumes (postgres, neo4j)"

    def test_mem0_depends_on_postgres(self, compose: dict) -> None:
        mem0 = compose["services"]["mem0"]
        deps = mem0.get("depends_on", {})
        # depends_on can be a list or dict
        if isinstance(deps, list):
            assert "postgres" in deps
        else:
            assert "postgres" in deps

    def test_postgres_uses_pgvector(self, compose: dict) -> None:
        pg = compose["services"]["postgres"]
        image = pg["image"]
        assert "pgvector" in image, f"Postgres image should use pgvector, got: {image}"

    def test_neo4j_image(self, compose: dict) -> None:
        neo4j = compose["services"]["neo4j"]
        image = neo4j["image"]
        assert "neo4j" in image

    def test_package_data_registered(self) -> None:
        """Verify the data directory is in pyproject.toml package-data."""
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        content = pyproject.read_text()
        assert "data/" in content or "data/*" in content or "data/**" in content, (
            "data/ not registered in pyproject.toml package-data"
        )


class TestIsMem0Installed:
    """Tests for is_mem0_installed()."""

    def test_installed_when_dir_exists(self, tmp_path: Path) -> None:
        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        assert is_mem0_installed(gobby_home=tmp_path) is True

    def test_not_installed_when_dir_missing(self, tmp_path: Path) -> None:
        assert is_mem0_installed(gobby_home=tmp_path) is False


class TestIsMem0Healthy:
    """Tests for is_mem0_healthy()."""

    def test_healthy_when_reachable(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_get.return_value = httpx.Response(200)
            assert is_mem0_healthy("http://localhost:8888") is True

    def test_unhealthy_when_unreachable(self) -> None:
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert is_mem0_healthy("http://localhost:8888") is False

    def test_unhealthy_when_server_error(self) -> None:
        with patch("httpx.get") as mock_get:
            mock_get.return_value = httpx.Response(500)
            assert is_mem0_healthy("http://localhost:8888") is False

    def test_unhealthy_when_no_url(self) -> None:
        assert is_mem0_healthy(None) is False


class TestGetMem0Status:
    """Tests for get_mem0_status()."""

    def test_status_installed_and_healthy(self, tmp_path: Path) -> None:
        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        with patch("httpx.get") as mock_get:
            mock_get.return_value = httpx.Response(200)
            status = get_mem0_status(
                gobby_home=tmp_path, mem0_url="http://localhost:8888"
            )
        assert status["installed"] is True
        assert status["healthy"] is True
        assert status["url"] == "http://localhost:8888"

    def test_status_not_installed(self, tmp_path: Path) -> None:
        status = get_mem0_status(gobby_home=tmp_path, mem0_url=None)
        assert status["installed"] is False
        assert status["healthy"] is False
        assert status["url"] is None

    def test_status_installed_but_unhealthy(self, tmp_path: Path) -> None:
        svc_dir = tmp_path / "services" / "mem0"
        svc_dir.mkdir(parents=True)
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            status = get_mem0_status(
                gobby_home=tmp_path, mem0_url="http://localhost:8888"
            )
        assert status["installed"] is True
        assert status["healthy"] is False
