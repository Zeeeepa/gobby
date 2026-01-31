"""Tests for ClawdHubProvider."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from gobby.skills.hubs.base import HubSkillInfo
from gobby.skills.hubs.clawdhub import ClawdHubProvider

pytestmark = pytest.mark.unit


class TestClawdHubProvider:
    """Tests for ClawdHubProvider class."""

    def test_provider_type(self) -> None:
        """Test provider_type returns 'clawdhub'."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )
        assert provider.provider_type == "clawdhub"

    def test_init_with_hub_name(self) -> None:
        """Test initialization with hub_name."""
        provider = ClawdHubProvider(
            hub_name="my-clawdhub",
            base_url="https://clawdhub.com",
        )
        assert provider.hub_name == "my-clawdhub"

    def test_init_with_auth_token(self) -> None:
        """Test initialization with auth_token."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
            auth_token="secret123",
        )
        assert provider.auth_token == "secret123"


class TestClawdHubProviderCLI:
    """Tests for ClawdHubProvider CLI integration."""

    @pytest.mark.asyncio
    async def test_check_cli_available_success(self) -> None:
        """Test CLI availability check when clawdhub is installed."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        with patch("gobby.skills.hubs.clawdhub.asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"1.0.0\n", b"")
            mock_exec.return_value = mock_process

            result = await provider._check_cli_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_cli_available_not_installed(self) -> None:
        """Test CLI availability check when clawdhub is not installed."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        with patch("gobby.skills.hubs.clawdhub.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError("clawdhub not found")

            result = await provider._check_cli_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_run_cli_command(self) -> None:
        """Test running a CLI command."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        with patch("gobby.skills.hubs.clawdhub.asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b'{"success": true}\n', b"")
            mock_exec.return_value = mock_process

            result = await provider._run_cli_command("search", ["test"])
            assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_run_cli_command_with_json_output(self) -> None:
        """Test CLI command returns parsed JSON."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        json_output = json.dumps({"skills": [{"name": "test-skill"}]})

        with patch("gobby.skills.hubs.clawdhub.asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (json_output.encode(), b"")
            mock_exec.return_value = mock_process

            result = await provider._run_cli_command("list", [])
            assert result == {"skills": [{"name": "test-skill"}]}


class TestClawdHubProviderSearch:
    """Tests for ClawdHubProvider search functionality."""

    @pytest.mark.asyncio
    async def test_search_returns_hub_skill_info_list(self) -> None:
        """Test search returns list of HubSkillInfo."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        search_results = {
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
                    "version": "2.1.0",
                },
            ]
        }

        with patch.object(provider, "_run_cli_command", return_value=search_results):
            results = await provider.search("commit", limit=10)

            assert len(results) == 2
            assert all(isinstance(r, HubSkillInfo) for r in results)
            assert results[0].slug == "commit-message"
            assert results[0].display_name == "Commit Message Generator"
            assert results[0].hub_name == "clawdhub"

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        """Test search with no results."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        with patch.object(provider, "_run_cli_command", return_value={"skills": []}):
            results = await provider.search("nonexistent")
            assert results == []


class TestClawdHubProviderDiscover:
    """Tests for ClawdHubProvider discover functionality."""

    @pytest.mark.asyncio
    async def test_discover_returns_hub_info(self) -> None:
        """Test discover returns hub configuration."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        with patch.object(provider, "_check_cli_available", return_value=True):
            result = await provider.discover()
            assert "cli_available" in result
            assert result["cli_available"] is True
            assert result["hub_name"] == "clawdhub"


class TestClawdHubProviderListSkills:
    """Tests for ClawdHubProvider list_skills functionality."""

    @pytest.mark.asyncio
    async def test_list_skills_returns_hub_skill_info_list(self) -> None:
        """Test list_skills returns list of HubSkillInfo."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        list_results = {
            "skills": [
                {
                    "slug": "skill-1",
                    "name": "Skill One",
                    "description": "First skill",
                },
            ]
        }

        with patch.object(provider, "_run_cli_command", return_value=list_results):
            results = await provider.list_skills(limit=10)

            assert len(results) == 1
            assert results[0].slug == "skill-1"
            assert results[0].hub_name == "clawdhub"


class TestClawdHubProviderDownload:
    """Tests for ClawdHubProvider download functionality."""

    @pytest.mark.asyncio
    async def test_download_skill_success(self) -> None:
        """Test successful skill download."""
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        install_result = {
            "success": True,
            "path": "/tmp/skills/commit-message",
        }

        with patch.object(provider, "_run_cli_command", return_value=install_result):
            result = await provider.download_skill("commit-message")
            assert result.success is True
            assert result.path is not None
