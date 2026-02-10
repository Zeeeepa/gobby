"""Tests for mem0 docker-compose bundle and lifecycle utilities."""

import yaml
import pytest
from pathlib import Path


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
