"""GitHub Collection provider implementation.

This module provides the GitHubCollectionProvider class which provides
access to skill collections hosted in GitHub repositories.
"""

from __future__ import annotations

import logging
from typing import Any

from gobby.skills.hubs.base import HubProvider, HubSkillDetails, HubSkillInfo

logger = logging.getLogger(__name__)


class GitHubCollectionProvider(HubProvider):
    """Provider for GitHub-hosted skill collections.

    This provider accesses skills stored in a GitHub repository,
    typically organized as a collection of skill directories.

    The repository structure is expected to be:
    ```
    repo/
    ├── skill-1/
    │   └── SKILL.md
    ├── skill-2/
    │   └── SKILL.md
    └── ...
    ```

    Example usage:
        ```python
        provider = GitHubCollectionProvider(
            hub_name="my-collection",
            base_url="",  # Not used for GitHub
            repo="user/my-skills",
            branch="main",
            auth_token="ghp_your_token",  # Optional, for private repos
        )

        skills = await provider.list_skills()
        for skill in skills:
            print(f"{skill.slug}: {skill.description}")
        ```
    """

    def __init__(
        self,
        hub_name: str,
        base_url: str,
        repo: str | None = None,
        branch: str = "main",
        auth_token: str | None = None,
    ) -> None:
        """Initialize the GitHub Collection provider.

        Args:
            hub_name: The configured name for this hub instance
            base_url: Not used for GitHub (kept for interface compatibility)
            repo: GitHub repository in 'owner/repo' format
            branch: Git branch to use (default: 'main')
            auth_token: Optional GitHub token for private repos
        """
        super().__init__(hub_name=hub_name, base_url=base_url, auth_token=auth_token)
        self._repo = repo or ""
        self._branch = branch

    @property
    def provider_type(self) -> str:
        """Return the provider type identifier."""
        return "github-collection"

    @property
    def repo(self) -> str:
        """GitHub repository in 'owner/repo' format."""
        return self._repo

    @property
    def branch(self) -> str:
        """Git branch to use."""
        return self._branch

    async def _fetch_skill_list(self) -> list[dict[str, Any]]:
        """Fetch the list of skills from the repository.

        Returns:
            List of skill metadata dictionaries
        """
        # TODO: Implement actual GitHub API call or git ls-tree
        # For now, return empty list - will be implemented with actual git ops
        return []

    async def _clone_skill(
        self,
        slug: str,
        target_dir: str | None = None,
    ) -> str:
        """Clone a specific skill from the repository.

        Args:
            slug: The skill's directory name
            target_dir: Optional target directory

        Returns:
            Path to the cloned skill
        """
        # TODO: Implement actual git clone/sparse checkout
        return target_dir or f"/tmp/skills/{slug}"

    async def discover(self) -> dict[str, Any]:
        """Discover hub capabilities.

        Returns:
            Dictionary with hub info
        """
        return {
            "hub_name": self.hub_name,
            "provider_type": self.provider_type,
            "repo": self.repo,
            "branch": self.branch,
            "authenticated": self.auth_token is not None,
        }

    async def search(
        self,
        query: str,
        limit: int = 20,
    ) -> list[HubSkillInfo]:
        """Search for skills matching a query.

        This performs client-side filtering of the skill list.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching skills with basic info
        """
        # Get all skills and filter locally
        all_skills = await self.list_skills(limit=1000)

        query_lower = query.lower()
        matching = [
            skill
            for skill in all_skills
            if query_lower in skill.slug.lower()
            or query_lower in skill.display_name.lower()
            or query_lower in skill.description.lower()
        ]

        return matching[:limit]

    async def list_skills(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HubSkillInfo]:
        """List available skills from the repository.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of skills with basic info
        """
        skills_data = await self._fetch_skill_list()

        skills = [
            HubSkillInfo(
                slug=skill.get("slug", skill.get("name", "")),
                display_name=skill.get("name", skill.get("slug", "")),
                description=skill.get("description", ""),
                hub_name=self.hub_name,
                version=skill.get("version"),
            )
            for skill in skills_data
        ]

        return skills[offset : offset + limit]

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
        # Find the skill in the list
        all_skills = await self.list_skills(limit=1000)
        for skill in all_skills:
            if skill.slug == slug:
                return HubSkillDetails(
                    slug=skill.slug,
                    display_name=skill.display_name,
                    description=skill.description,
                    hub_name=self.hub_name,
                    version=skill.version,
                    latest_version=skill.version,
                    versions=[skill.version] if skill.version else [],
                )
        return None

    async def download_skill(
        self,
        slug: str,
        version: str | None = None,
        target_dir: str | None = None,
    ) -> dict[str, Any]:
        """Download and extract a skill from the repository.

        Args:
            slug: The skill's unique identifier
            version: Specific version (branch/tag) to download
            target_dir: Directory to extract to

        Returns:
            Dictionary with download result including path
        """
        try:
            path = await self._clone_skill(slug, target_dir)
            return {
                "success": True,
                "path": path,
                "version": version or self.branch,
                "slug": slug,
            }
        except Exception as e:
            logger.error(f"Failed to download skill {slug}: {e}")
            return {
                "success": False,
                "error": str(e),
                "slug": slug,
            }
