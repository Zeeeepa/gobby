"""Tests for ClaudePluginsProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gobby.skills.hubs.base import HubSkillInfo
from gobby.skills.hubs.claude_plugins import ClaudePluginsProvider

pytestmark = pytest.mark.unit


class TestClaudePluginsProvider:
    """Tests for ClaudePluginsProvider class."""

    def test_provider_type(self) -> None:
        """Test provider_type returns 'claude-plugins'."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )
        assert provider.provider_type == "claude-plugins"

    def test_init_with_hub_name(self) -> None:
        """Test initialization with hub_name."""
        provider = ClaudePluginsProvider(
            hub_name="my-plugins",
            base_url="https://claude-plugins.dev",
        )
        assert provider.hub_name == "my-plugins"

    def test_init_with_base_url(self) -> None:
        """Test initialization with base_url."""
        provider = ClaudePluginsProvider(
            hub_name="plugins",
            base_url="https://custom.plugins.dev",
        )
        assert provider.base_url == "https://custom.plugins.dev"

    def test_init_with_auth_token(self) -> None:
        """Test initialization with auth_token."""
        provider = ClaudePluginsProvider(
            hub_name="plugins",
            base_url="https://claude-plugins.dev",
            auth_token="secret-token",
        )
        assert provider.auth_token == "secret-token"


class TestClaudePluginsProviderDiscover:
    """Tests for ClaudePluginsProvider discover functionality."""

    @pytest.mark.asyncio
    async def test_discover_returns_hub_info(self) -> None:
        """Test discover returns hub configuration."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        result = await provider.discover()
        assert result["hub_name"] == "claude-plugins"
        assert result["provider_type"] == "claude-plugins"
        assert result["base_url"] == "https://claude-plugins.dev"


class TestClaudePluginsProviderListSkills:
    """Tests for ClaudePluginsProvider list_skills functionality."""

    @pytest.mark.asyncio
    async def test_list_skills_returns_hub_skill_info_list(self) -> None:
        """Test list_skills returns list of HubSkillInfo."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        mock_response = {
            "skills": [
                {
                    "id": "uuid-1",
                    "name": "frontend-design",
                    "description": "Create distinctive frontend interfaces",
                    "stars": 52420,
                },
                {
                    "id": "uuid-2",
                    "name": "code-review",
                    "description": "Review code for issues",
                    "stars": 1000,
                },
            ],
            "total": 2,
        }

        with patch.object(provider, "_make_request", return_value=mock_response):
            results = await provider.list_skills(limit=10)

            assert len(results) == 2
            assert all(isinstance(r, HubSkillInfo) for r in results)
            assert results[0].slug == "frontend-design"
            assert results[0].hub_name == "claude-plugins"

    @pytest.mark.asyncio
    async def test_list_skills_handles_empty_response(self) -> None:
        """Test list_skills handles empty response."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        mock_response: dict = {"skills": [], "total": 0}

        with patch.object(provider, "_make_request", return_value=mock_response):
            results = await provider.list_skills()
            assert results == []


class TestClaudePluginsProviderSearch:
    """Tests for ClaudePluginsProvider search functionality."""

    @pytest.mark.asyncio
    async def test_search_returns_matching_skills(self) -> None:
        """Test search returns skills matching query."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        mock_response = {
            "skills": [
                {
                    "name": "frontend-design",
                    "description": "Create distinctive frontend interfaces",
                    "stars": 52420,
                },
            ],
        }

        with patch.object(provider, "_make_request", return_value=mock_response):
            results = await provider.search("frontend")

            assert len(results) == 1
            assert results[0].slug == "frontend-design"

    @pytest.mark.asyncio
    async def test_search_passes_query_parameter(self) -> None:
        """Test search passes query to API."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        with patch.object(provider, "_make_request", return_value={"skills": []}) as mock_request:
            await provider.search("test-query", limit=5)

            mock_request.assert_called_once_with(
                endpoint="/api/skills",
                params={"q": "test-query", "limit": 5},
            )


class TestClaudePluginsProviderDownload:
    """Tests for ClaudePluginsProvider download functionality."""

    @pytest.mark.asyncio
    async def test_download_skill_success(self) -> None:
        """Test successful skill download."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        mock_api_response = {
            "skills": [
                {
                    "name": "frontend-design",
                    "description": "Test skill",
                    "metadata": {
                        "rawFileUrl": "https://raw.githubusercontent.com/test/SKILL.md",
                    },
                },
            ],
        }

        mock_file_response = MagicMock()
        mock_file_response.text = "# Frontend Design\n\nTest content"
        mock_file_response.raise_for_status = MagicMock()

        with (
            patch.object(provider, "_make_request", return_value=mock_api_response),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_file_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await provider.download_skill("frontend-design")

            assert result.success is True
            assert result.path is not None

    @pytest.mark.asyncio
    async def test_download_skill_not_found(self) -> None:
        """Test download when skill is not found."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        mock_response: dict = {"skills": []}

        with patch.object(provider, "_make_request", return_value=mock_response):
            result = await provider.download_skill("nonexistent-skill")

            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_download_skill_no_raw_url(self) -> None:
        """Test download when skill has no rawFileUrl."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        mock_response = {
            "skills": [
                {
                    "name": "broken-skill",
                    "description": "No download URL",
                    "metadata": {},
                },
            ],
        }

        with patch.object(provider, "_make_request", return_value=mock_response):
            result = await provider.download_skill("broken-skill")

            assert result.success is False
            assert "no download url" in result.error.lower()


class TestClaudePluginsProviderMakeRequest:
    """Tests for ClaudePluginsProvider _make_request functionality."""

    @pytest.mark.asyncio
    async def test_make_request_builds_correct_url(self) -> None:
        """Test _make_request builds correct URL."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"skills": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await provider._make_request("/api/skills", params={"limit": 10})

            mock_client.get.assert_called_once()
            # URL is passed as first positional argument
            call_args = mock_client.get.call_args
            call_url = call_args[1].get("url") or call_args[0][0]
            assert call_url == "https://claude-plugins.dev/api/skills"

    @pytest.mark.asyncio
    async def test_make_request_handles_api_error(self) -> None:
        """Test _make_request handles API errors."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Not Found",
                    request=MagicMock(),
                    response=MagicMock(status_code=404),
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="API error: 404"):
                await provider._make_request("/api/skills")

    @pytest.mark.asyncio
    async def test_make_request_includes_auth_header(self) -> None:
        """Test _make_request includes auth token in headers."""
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
            auth_token="secret-token",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"skills": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await provider._make_request("/api/skills")

            call_kwargs = mock_client.get.call_args[1]
            assert "headers" in call_kwargs
            assert "Authorization" in call_kwargs["headers"]
            assert "secret-token" in call_kwargs["headers"]["Authorization"]
