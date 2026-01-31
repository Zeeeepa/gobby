"""Claude Plugins provider implementation.

This module provides the ClaudePluginsProvider class which connects to the
claude-plugins.dev REST API for skill search, listing, and download functionality.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import httpx

from gobby.skills.hubs.base import DownloadResult, HubProvider, HubSkillDetails, HubSkillInfo

logger = logging.getLogger(__name__)


class ClaudePluginsProvider(HubProvider):
    """Provider for claude-plugins.dev skill registry using REST API.

    This provider connects to the claude-plugins.dev API to provide access to
    skills indexed from various GitHub repositories.

    The API returns skills with metadata including:
    - sourceUrl: GitHub URL to the skill directory
    - metadata.rawFileUrl: Direct URL to the SKILL.md file

    Example usage:
        ```python
        provider = ClaudePluginsProvider(
            hub_name="claude-plugins",
            base_url="https://claude-plugins.dev",
        )

        results = await provider.search("frontend")
        for skill in results:
            print(f"{skill.slug}: {skill.description}")
        ```
    """

    def __init__(
        self,
        hub_name: str,
        base_url: str,
        auth_token: str | None = None,
    ) -> None:
        """Initialize the Claude Plugins provider.

        Args:
            hub_name: The configured name for this hub instance
            base_url: Base URL for the claude-plugins.dev API
            auth_token: Optional API key for authentication (not currently required)
        """
        super().__init__(hub_name=hub_name, base_url=base_url, auth_token=auth_token)

    @property
    def provider_type(self) -> str:
        """Return the provider type identifier."""
        return "claude-plugins"

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests.

        Returns:
            Dictionary of headers including Authorization if auth_token is set
        """
        headers: dict[str, str] = {
            "Accept": "application/json",
        }

        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        return headers

    async def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP GET request to the claude-plugins.dev API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            RuntimeError: If the request fails
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
            except httpx.HTTPStatusError as e:
                logger.error(f"claude-plugins.dev API error: {e.response.status_code}")
                raise RuntimeError(f"claude-plugins.dev API error: {e.response.status_code}") from e
            except httpx.RequestError as e:
                logger.error(f"claude-plugins.dev request failed: {e}")
                raise RuntimeError(f"claude-plugins.dev request failed: {e}") from e

    def _parse_skill_info(self, skill: dict[str, Any]) -> HubSkillInfo:
        """Parse a skill dict from the API into HubSkillInfo.

        Args:
            skill: Raw skill data from the API

        Returns:
            HubSkillInfo instance
        """
        return HubSkillInfo(
            slug=skill.get("name", skill.get("id", "")),
            display_name=skill.get("name", ""),
            description=skill.get("description", ""),
            hub_name=self.hub_name,
            version=None,  # API doesn't provide version info
            score=skill.get("stars"),  # Use stars as a relevance indicator
        )

    async def discover(self) -> dict[str, Any]:
        """Discover hub capabilities.

        Returns:
            Dictionary with hub info
        """
        return {
            "hub_name": self.hub_name,
            "provider_type": self.provider_type,
            "base_url": self.base_url,
            "authenticated": self.auth_token is not None,
        }

    async def search(
        self,
        query: str,
        limit: int = 20,
    ) -> list[HubSkillInfo]:
        """Search for skills matching a query.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching skills with basic info
        """
        try:
            result = await self._make_request(
                endpoint="/api/skills",
                params={"q": query, "limit": limit},
            )

            skills = result.get("skills", [])
            return [self._parse_skill_info(skill) for skill in skills]
        except RuntimeError:
            logger.warning(f"Search failed for query: {query}")
            return []

    async def list_skills(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HubSkillInfo]:
        """List available skills from the hub.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of skills with basic info
        """
        try:
            result = await self._make_request(
                endpoint="/api/skills",
                params={"limit": limit, "offset": offset},
            )

            skills = result.get("skills", [])
            return [self._parse_skill_info(skill) for skill in skills]
        except RuntimeError:
            logger.warning("Failed to list skills from claude-plugins.dev")
            return []

    async def get_skill_details(
        self,
        slug: str,
    ) -> HubSkillDetails | None:
        """Get detailed information about a specific skill.

        Args:
            slug: The skill's unique identifier (name)

        Returns:
            Detailed skill info, or None if not found
        """
        # Search for the specific skill by name
        try:
            result = await self._make_request(
                endpoint="/api/skills",
                params={"q": slug, "limit": 10},
            )

            skills = result.get("skills", [])
            for skill in skills:
                if skill.get("name") == slug:
                    return HubSkillDetails(
                        slug=skill.get("name", slug),
                        display_name=skill.get("name", slug),
                        description=skill.get("description", ""),
                        hub_name=self.hub_name,
                        version=None,
                        latest_version=None,
                        versions=[],
                    )
            return None
        except RuntimeError:
            return None

    async def download_skill(
        self,
        slug: str,
        version: str | None = None,
        target_dir: str | None = None,
    ) -> DownloadResult:
        """Download a skill from claude-plugins.dev.

        Downloads the SKILL.md file directly using the rawFileUrl from metadata.

        Args:
            slug: The skill's unique identifier (name)
            version: Not used (no versioning in this registry)
            target_dir: Directory to save to

        Returns:
            DownloadResult with success status, path, or error
        """
        # First, find the skill to get its metadata
        try:
            result = await self._make_request(
                endpoint="/api/skills",
                params={"q": slug, "limit": 10},
            )

            skills = result.get("skills", [])
            skill_data = None
            for skill in skills:
                if skill.get("name") == slug:
                    skill_data = skill
                    break

            if not skill_data:
                return DownloadResult(
                    success=False,
                    slug=slug,
                    error=f"Skill '{slug}' not found",
                )

            # Get the raw file URL from metadata
            metadata = skill_data.get("metadata", {})
            raw_url = metadata.get("rawFileUrl")

            if not raw_url:
                return DownloadResult(
                    success=False,
                    slug=slug,
                    error="No download URL available for this skill",
                )

            # Download the SKILL.md content
            async with httpx.AsyncClient() as client:
                response = await client.get(raw_url, timeout=30.0, follow_redirects=True)
                response.raise_for_status()
                content = response.text

            # Determine target directory
            if target_dir:
                extract_path = Path(target_dir)
            else:
                extract_path = Path(tempfile.mkdtemp(prefix="claude_plugins_"))

            extract_path.mkdir(parents=True, exist_ok=True)

            # Write the SKILL.md file
            skill_file = extract_path / "SKILL.md"
            skill_file.write_text(content)

            return DownloadResult(
                success=True,
                slug=slug,
                path=str(extract_path),
                version=None,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to download skill {slug}: {e.response.status_code}")
            return DownloadResult(
                success=False,
                slug=slug,
                error=f"Download failed: HTTP {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.error(f"Download request failed for skill {slug}: {e}")
            return DownloadResult(
                success=False,
                slug=slug,
                error=f"Download failed: {e}",
            )
        except RuntimeError as e:
            return DownloadResult(
                success=False,
                slug=slug,
                error=str(e),
            )
