"""Tests for SkillHubProvider."""

from unittest.mock import AsyncMock, patch

import pytest

from gobby.skills.hubs.base import HubSkillInfo
from gobby.skills.hubs.skillhub import SkillHubProvider

pytestmark = pytest.mark.unit


class TestSkillHubProvider:
    """Tests for SkillHubProvider class."""

    def test_provider_type(self) -> None:
        """Test provider_type returns 'skillhub'."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )
        assert provider.provider_type == "skillhub"

    def test_init_with_hub_name(self) -> None:
        """Test initialization with hub_name."""
        provider = SkillHubProvider(
            hub_name="my-skillhub",
            base_url="https://skillhub.dev",
        )
        assert provider.hub_name == "my-skillhub"

    def test_init_with_base_url(self) -> None:
        """Test initialization with base_url."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://custom.skillhub.io",
        )
        assert provider.base_url == "https://custom.skillhub.io"

    def test_init_with_auth_token(self) -> None:
        """Test initialization with auth_token (API key)."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
            auth_token="sk-12345",
        )
        assert provider.auth_token == "sk-12345"


class TestSkillHubProviderAuth:
    """Tests for SkillHubProvider authentication."""

    def test_get_headers_with_auth_token(self) -> None:
        """Test _get_headers returns Authorization Bearer header."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
            auth_token="sk-secret-key",
        )
        headers = provider._get_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer sk-secret-key"

    def test_get_headers_without_auth_token(self) -> None:
        """Test _get_headers without auth token."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )
        headers = provider._get_headers()
        assert "Authorization" not in headers

    def test_get_headers_includes_content_type(self) -> None:
        """Test _get_headers includes JSON content type."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )
        headers = provider._get_headers()
        assert headers.get("Content-Type") == "application/json"


class TestSkillHubProviderSearch:
    """Tests for SkillHubProvider search functionality."""

    @pytest.mark.asyncio
    async def test_search_returns_hub_skill_info_list(self) -> None:
        """Test search returns list of HubSkillInfo."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        mock_response = {
            "skills": [
                {
                    "slug": "commit-message",
                    "name": "Commit Message Generator",
                    "description": "Generate conventional commits",
                    "version": "1.0.0",
                },
                {
                    "slug": "code-review",
                    "name": "Code Review",
                    "description": "Review code for issues",
                    "version": "2.0.0",
                },
            ]
        }

        with patch.object(provider, "_make_request", return_value=mock_response):
            results = await provider.search("commit", limit=10)

            assert len(results) == 2
            assert all(isinstance(r, HubSkillInfo) for r in results)
            assert results[0].slug == "commit-message"
            assert results[0].hub_name == "skillhub"

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        """Test search with no results."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        with patch.object(provider, "_make_request", return_value={"skills": []}):
            results = await provider.search("nonexistent")
            assert results == []


class TestSkillHubProviderDiscover:
    """Tests for SkillHubProvider discover functionality."""

    @pytest.mark.asyncio
    async def test_discover_returns_hub_info(self) -> None:
        """Test discover returns hub configuration."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        result = await provider.discover()
        assert result["hub_name"] == "skillhub"
        assert result["provider_type"] == "skillhub"
        assert result["base_url"] == "https://skillhub.dev"


class TestSkillHubProviderListSkills:
    """Tests for SkillHubProvider list_skills functionality."""

    @pytest.mark.asyncio
    async def test_list_skills_returns_hub_skill_info_list(self) -> None:
        """Test list_skills returns list of HubSkillInfo."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        mock_response = {
            "skills": [
                {
                    "slug": "skill-1",
                    "name": "Skill One",
                    "description": "First skill",
                    "version": "1.0.0",
                },
            ]
        }

        with patch.object(provider, "_make_request", return_value=mock_response):
            results = await provider.list_skills(limit=10)

            assert len(results) == 1
            assert results[0].slug == "skill-1"
            assert results[0].hub_name == "skillhub"


class TestSkillHubProviderDownload:
    """Tests for SkillHubProvider download functionality."""

    @pytest.mark.asyncio
    async def test_download_skill_success(self) -> None:
        """Test successful skill download."""
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        mock_response = {
            "success": True,
            "download_url": "https://skillhub.dev/download/commit-message/1.0.0",
        }

        with patch.object(provider, "_make_request", return_value=mock_response):
            with patch.object(provider, "_download_and_extract", return_value="/tmp/skills/commit-message"):
                result = await provider.download_skill("commit-message")
                assert result["success"] is True
