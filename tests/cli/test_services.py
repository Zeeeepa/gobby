"""Tests for service lifecycle utilities."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from gobby.cli.services import get_neo4j_status, is_neo4j_healthy, is_neo4j_installed

pytestmark = pytest.mark.unit


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
