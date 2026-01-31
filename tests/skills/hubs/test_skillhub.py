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


class TestSkillHubProviderDownloadAndExtract:
    """Tests for SkillHubProvider _download_and_extract functionality."""

    @pytest.mark.asyncio
    async def test_download_and_extract_fetches_url(self) -> None:
        """Test _download_and_extract makes GET request to download URL."""
        from io import BytesIO
        from unittest.mock import MagicMock
        from zipfile import ZipFile

        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        # Create a valid ZIP in memory
        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w") as zf:
            zf.writestr("commit-message/SKILL.md", "# Test Skill")
        zip_content = zip_buffer.getvalue()

        mock_response = MagicMock()
        mock_response.content = zip_content
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await provider._download_and_extract(
                "https://skillhub.dev/download/commit-message/1.0.0"
            )

            # Should have called GET on the download URL
            mock_client.get.assert_called_once()
            call_url = mock_client.get.call_args[0][0]
            assert "skillhub.dev" in call_url

    @pytest.mark.asyncio
    async def test_download_and_extract_extracts_to_temp(self) -> None:
        """Test _download_and_extract extracts ZIP to temp directory."""
        import os
        from io import BytesIO
        from unittest.mock import MagicMock
        from zipfile import ZipFile

        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        # Create a valid ZIP in memory
        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w") as zf:
            zf.writestr("commit-message/SKILL.md", "# Test Skill\nContent here.")
        zip_content = zip_buffer.getvalue()

        mock_response = MagicMock()
        mock_response.content = zip_content
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result_path = await provider._download_and_extract(
                "https://skillhub.dev/download/commit-message/1.0.0"
            )

            # Should return a valid path
            assert result_path is not None
            assert os.path.exists(result_path)
            # Should have extracted the skill
            assert os.path.exists(os.path.join(result_path, "commit-message", "SKILL.md"))

    @pytest.mark.asyncio
    async def test_download_and_extract_with_target_dir(self) -> None:
        """Test _download_and_extract extracts to specified target directory."""
        import tempfile
        from io import BytesIO
        from pathlib import Path
        from unittest.mock import MagicMock
        from zipfile import ZipFile

        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
        )

        # Create a valid ZIP in memory
        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w") as zf:
            zf.writestr("my-skill/SKILL.md", "# My Skill")
        zip_content = zip_buffer.getvalue()

        mock_response = MagicMock()
        mock_response.content = zip_content
        mock_response.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "target"

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result_path = await provider._download_and_extract(
                    "https://skillhub.dev/download/my-skill/1.0.0",
                    target_dir=str(target_dir),
                )

                # Should return the target directory
                assert result_path == str(target_dir)
                # Skill should be extracted there
                assert (target_dir / "my-skill" / "SKILL.md").exists()

    @pytest.mark.asyncio
    async def test_download_and_extract_handles_http_error(self) -> None:
        """Test _download_and_extract handles HTTP errors."""
        from unittest.mock import MagicMock

        import httpx

        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
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

            # Should raise RuntimeError on download failure
            with pytest.raises(RuntimeError, match="download"):
                await provider._download_and_extract(
                    "https://skillhub.dev/download/nonexistent/1.0.0"
                )


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
            with patch.object(
                provider, "_download_and_extract", return_value="/tmp/skills/commit-message"
            ):
                result = await provider.download_skill("commit-message")
                assert result["success"] is True
