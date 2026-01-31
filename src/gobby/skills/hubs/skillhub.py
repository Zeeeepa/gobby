"""SkillHub provider implementation.

This module provides the SkillHubProvider class which connects to the
SkillHub REST API for skill search, listing, and download functionality.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from gobby.skills.hubs.base import HubProvider, HubSkillDetails, HubSkillInfo

logger = logging.getLogger(__name__)


class SkillHubProvider(HubProvider):
    """Provider for SkillHub skill registry using REST API.

    This provider connects to the SkillHub API to provide access to
    skills in the SkillHub registry.

    Authentication is via Bearer token in the Authorization header.

    Example usage:
        ```python
        provider = SkillHubProvider(
            hub_name="skillhub",
            base_url="https://skillhub.dev",
            auth_token="sk-your-api-key",
        )

        results = await provider.search("commit message")
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
        """Initialize the SkillHub provider.

        Args:
            hub_name: The configured name for this hub instance
            base_url: Base URL for the SkillHub API
            auth_token: Optional API key for authentication
        """
        super().__init__(hub_name=hub_name, base_url=base_url, auth_token=auth_token)

    @property
    def provider_type(self) -> str:
        """Return the provider type identifier."""
        return "skillhub"

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests.

        Returns:
            Dictionary of headers including Authorization if auth_token is set
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the SkillHub API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data for POST requests

        Returns:
            Parsed JSON response

        Raises:
            RuntimeError: If the request fails
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=json_data,
                    timeout=30.0,
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
            except httpx.HTTPStatusError as e:
                logger.error(f"SkillHub API error: {e.response.status_code}")
                raise RuntimeError(f"SkillHub API error: {e.response.status_code}") from e
            except httpx.RequestError as e:
                logger.error(f"SkillHub request failed: {e}")
                raise RuntimeError(f"SkillHub request failed: {e}") from e

    async def _download_and_extract(
        self,
        download_url: str,
        target_dir: str | None = None,
    ) -> str:
        """Download and extract a skill from a URL.

        Args:
            download_url: URL to download the skill from
            target_dir: Optional target directory

        Returns:
            Path to the extracted skill
        """
        # TODO: Implement actual download and extraction
        # For now, return a placeholder
        return target_dir or "/tmp/skills"

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
        result = await self._make_request(
            method="POST",
            endpoint="/skills/search",
            json_data={"query": query, "limit": limit},
        )

        skills = result.get("skills", [])
        return [
            HubSkillInfo(
                slug=skill.get("slug", skill.get("name", "")),
                display_name=skill.get("name", skill.get("slug", "")),
                description=skill.get("description", ""),
                hub_name=self.hub_name,
                version=skill.get("version"),
                score=skill.get("score"),
            )
            for skill in skills
        ]

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
        result = await self._make_request(
            method="GET",
            endpoint="/skills/catalog",
            params={"limit": limit, "offset": offset},
        )

        skills = result.get("skills", [])
        return [
            HubSkillInfo(
                slug=skill.get("slug", skill.get("name", "")),
                display_name=skill.get("name", skill.get("slug", "")),
                description=skill.get("description", ""),
                hub_name=self.hub_name,
                version=skill.get("version"),
            )
            for skill in skills
        ]

    async def get_skill_details(
        self,
        slug: str,
    ) -> HubSkillDetails | None:
        """Get detailed information about a specific skill.

        Args:
            slug: The skill's unique identifier

        Returns:
            Detailed skill info, or None if not found
        """
        try:
            result = await self._make_request(
                method="GET",
                endpoint=f"/skills/{slug}",
            )

            if not result:
                return None

            return HubSkillDetails(
                slug=result.get("slug", slug),
                display_name=result.get("name", slug),
                description=result.get("description", ""),
                hub_name=self.hub_name,
                version=result.get("version"),
                latest_version=result.get("latest_version", result.get("version")),
                versions=result.get("versions", []),
            )
        except RuntimeError:
            return None

    async def download_skill(
        self,
        slug: str,
        version: str | None = None,
        target_dir: str | None = None,
    ) -> dict[str, Any]:
        """Download and extract a skill from the hub.

        Args:
            slug: The skill's unique identifier
            version: Specific version to download (None for latest)
            target_dir: Directory to extract to

        Returns:
            Dictionary with download result including path
        """
        # Get download URL from API
        params: dict[str, Any] = {}
        if version:
            params["version"] = version

        result = await self._make_request(
            method="GET",
            endpoint=f"/skills/{slug}/download",
            params=params if params else None,
        )

        download_url = result.get("download_url", "")

        if download_url:
            path = await self._download_and_extract(download_url, target_dir)
            return {
                "success": True,
                "path": path,
                "version": result.get("version", version),
                "slug": slug,
            }

        return {
            "success": False,
            "error": "No download URL provided",
            "slug": slug,
        }
