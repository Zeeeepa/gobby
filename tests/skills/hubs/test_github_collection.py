"""Tests for GitHubCollectionProvider."""

from unittest.mock import AsyncMock, patch

import pytest

from gobby.skills.hubs.base import HubSkillInfo
from gobby.skills.hubs.github_collection import GitHubCollectionProvider

pytestmark = pytest.mark.unit


class TestGitHubCollectionProvider:
    """Tests for GitHubCollectionProvider class."""

    def test_provider_type(self) -> None:
        """Test provider_type returns 'github-collection'."""
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",
            repo="user/my-skills",
        )
        assert provider.provider_type == "github-collection"

    def test_init_with_hub_name(self) -> None:
        """Test initialization with hub_name."""
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",
            repo="user/skills",
        )
        assert provider.hub_name == "my-collection"

    def test_init_with_repo(self) -> None:
        """Test initialization with repo."""
        provider = GitHubCollectionProvider(
            hub_name="collection",
            base_url="",
            repo="anthropics/skills",
        )
        assert provider.repo == "anthropics/skills"

    def test_init_with_branch(self) -> None:
        """Test initialization with branch."""
        provider = GitHubCollectionProvider(
            hub_name="collection",
            base_url="",
            repo="user/skills",
            branch="develop",
        )
        assert provider.branch == "develop"

    def test_init_default_branch(self) -> None:
        """Test default branch is 'main'."""
        provider = GitHubCollectionProvider(
            hub_name="collection",
            base_url="",
            repo="user/skills",
        )
        assert provider.branch == "main"

    def test_init_with_auth_token(self) -> None:
        """Test initialization with auth_token."""
        provider = GitHubCollectionProvider(
            hub_name="collection",
            base_url="",
            repo="user/skills",
            auth_token="ghp_token123",
        )
        assert provider.auth_token == "ghp_token123"


class TestGitHubCollectionProviderDiscover:
    """Tests for GitHubCollectionProvider discover functionality."""

    @pytest.mark.asyncio
    async def test_discover_returns_hub_info(self) -> None:
        """Test discover returns hub configuration."""
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",
            repo="user/my-skills",
            branch="main",
        )

        result = await provider.discover()
        assert result["hub_name"] == "my-collection"
        assert result["provider_type"] == "github-collection"
        assert result["repo"] == "user/my-skills"
        assert result["branch"] == "main"


class TestGitHubCollectionProviderListSkills:
    """Tests for GitHubCollectionProvider list_skills functionality."""

    @pytest.mark.asyncio
    async def test_list_skills_returns_hub_skill_info_list(self) -> None:
        """Test list_skills returns list of HubSkillInfo."""
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",
            repo="user/my-skills",
        )

        mock_skills = [
            {
                "slug": "commit-message",
                "name": "Commit Message Generator",
                "description": "Generate conventional commits",
            },
            {
                "slug": "code-review",
                "name": "Code Review",
                "description": "Review code for issues",
            },
        ]

        with patch.object(provider, "_fetch_skill_list", return_value=mock_skills):
            results = await provider.list_skills(limit=10)

            assert len(results) == 2
            assert all(isinstance(r, HubSkillInfo) for r in results)
            assert results[0].slug == "commit-message"
            assert results[0].hub_name == "my-collection"


class TestGitHubCollectionProviderSearch:
    """Tests for GitHubCollectionProvider search functionality."""

    @pytest.mark.asyncio
    async def test_search_filters_by_query(self) -> None:
        """Test search filters skills by query string."""
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",
            repo="user/my-skills",
        )

        mock_skills = [
            HubSkillInfo(
                slug="commit-message",
                display_name="Commit Message Generator",
                description="Generate conventional commits",
                hub_name="my-collection",
            ),
            HubSkillInfo(
                slug="code-review",
                display_name="Code Review",
                description="Review code for issues",
                hub_name="my-collection",
            ),
        ]

        with patch.object(provider, "list_skills", return_value=mock_skills):
            results = await provider.search("commit")

            assert len(results) == 1
            assert results[0].slug == "commit-message"

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self) -> None:
        """Test search is case insensitive."""
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",
            repo="user/my-skills",
        )

        mock_skills = [
            HubSkillInfo(
                slug="commit-message",
                display_name="Commit Message Generator",
                description="Generate conventional commits",
                hub_name="my-collection",
            ),
        ]

        with patch.object(provider, "list_skills", return_value=mock_skills):
            results = await provider.search("COMMIT")

            assert len(results) == 1
            assert results[0].slug == "commit-message"


class TestGitHubCollectionProviderDownload:
    """Tests for GitHubCollectionProvider download functionality."""

    @pytest.mark.asyncio
    async def test_download_skill_success(self) -> None:
        """Test successful skill download."""
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",
            repo="user/my-skills",
        )

        with patch.object(
            provider, "_clone_skill", return_value="/tmp/skills/commit-message"
        ):
            result = await provider.download_skill("commit-message")
            assert result["success"] is True
            assert result["path"] == "/tmp/skills/commit-message"
