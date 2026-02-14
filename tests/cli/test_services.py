"""Tests for docker-compose bundles and service lifecycle utilities."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml

from gobby.cli.services import get_neo4j_status, is_neo4j_healthy, is_neo4j_installed

pytestmark = pytest.mark.unit


COMPOSE_FILE = (
    Path(__file__).resolve().parents[2] / "src" / "gobby" / "data" / "docker-compose.mem0.yml"
)


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


class TestIsNeo4jInstalled:
    """Tests for is_neo4j_installed()."""

    def test_installed_when_dir_exists(self, tmp_path: Path) -> None:
        svc_dir = tmp_path / "services" / "neo4j"
        svc_dir.mkdir(parents=True)
        assert is_neo4j_installed(gobby_home=tmp_path) is True

    def test_not_installed_when_dir_missing(self, tmp_path: Path) -> None:
        assert is_neo4j_installed(gobby_home=tmp_path) is False


@pytest.fixture
def mock_async_client() -> AsyncMock:
    """Create a reusable async HTTP client mock with context-manager support."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


class TestIsNeo4jHealthy:
    """Tests for is_neo4j_healthy()."""

    @pytest.mark.asyncio
    async def test_healthy_when_reachable(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.get = AsyncMock(return_value=httpx.Response(200))
        with patch("gobby.cli.services.httpx.AsyncClient", return_value=mock_async_client):
            assert await is_neo4j_healthy("http://localhost:8474") is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_unreachable(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("gobby.cli.services.httpx.AsyncClient", return_value=mock_async_client):
            assert await is_neo4j_healthy("http://localhost:8474") is False

    @pytest.mark.asyncio
    async def test_unhealthy_when_server_error(self, mock_async_client: AsyncMock) -> None:
        mock_async_client.get = AsyncMock(return_value=httpx.Response(500))
        with patch("gobby.cli.services.httpx.AsyncClient", return_value=mock_async_client):
            assert await is_neo4j_healthy("http://localhost:8474") is False

    @pytest.mark.asyncio
    async def test_unhealthy_when_no_url(self) -> None:
        assert await is_neo4j_healthy(None) is False


class TestGetNeo4jStatus:
    """Tests for get_neo4j_status()."""

    @pytest.mark.asyncio
    async def test_status_installed_and_healthy(self, tmp_path: Path, mock_async_client: AsyncMock) -> None:
        svc_dir = tmp_path / "services" / "neo4j"
        svc_dir.mkdir(parents=True)
        mock_async_client.get = AsyncMock(return_value=httpx.Response(200))
        with patch("gobby.cli.services.httpx.AsyncClient", return_value=mock_async_client):
            status = await get_neo4j_status(gobby_home=tmp_path, neo4j_url="http://localhost:8474")
        assert status["installed"] is True
        assert status["healthy"] is True
        assert status["url"] == "http://localhost:8474"

    @pytest.mark.asyncio
    async def test_status_not_installed(self, tmp_path: Path) -> None:
        status = await get_neo4j_status(gobby_home=tmp_path, neo4j_url=None)
        assert status["installed"] is False
        assert status["healthy"] is False
        assert status["url"] is None

    @pytest.mark.asyncio
    async def test_status_installed_but_unhealthy(self, tmp_path: Path, mock_async_client: AsyncMock) -> None:
        svc_dir = tmp_path / "services" / "neo4j"
        svc_dir.mkdir(parents=True)
        mock_async_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("gobby.cli.services.httpx.AsyncClient", return_value=mock_async_client):
            status = await get_neo4j_status(gobby_home=tmp_path, neo4j_url="http://localhost:8474")
        assert status["installed"] is True
        assert status["healthy"] is False
