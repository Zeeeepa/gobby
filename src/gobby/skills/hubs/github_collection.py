"""GitHub Collection provider implementation.

This module provides the GitHubCollectionProvider class which provides
access to skill collections hosted in GitHub repositories.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import httpx

from gobby.skills.hubs.base import DownloadResult, HubProvider, HubSkillDetails, HubSkillInfo
from gobby.skills.loader import GitHubRef, clone_skill_repo

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
        path: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        """Initialize the GitHub Collection provider.

        Args:
            hub_name: The configured name for this hub instance
            base_url: Not used for GitHub (kept for interface compatibility)
            repo: GitHub repository in 'owner/repo' format
            branch: Git branch to use (default: 'main')
            path: Subdirectory path within repo where skills are located
            auth_token: Optional GitHub token for private repos
        """
        super().__init__(hub_name=hub_name, base_url=base_url, auth_token=auth_token)
        self._repo = repo or ""
        self._branch = branch
        self._path = path

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

    @property
    def path(self) -> str | None:
        """Subdirectory path within repo where skills are located."""
        return self._path

    async def _fetch_skill_list(self) -> list[dict[str, Any]]:
        """Fetch the list of skills from the repository.

        Uses the GitHub API to list contents of the repository root,
        filtering for directories which represent skills.

        Returns:
            List of skill metadata dictionaries with 'slug', 'name' keys
        """
        if not self._repo or "/" not in self._repo:
            logger.warning(f"Invalid repo format: {self._repo}")
            return []

        owner, repo = self._repo.split("/", 1)
        url = f"https://api.github.com/repos/{owner}/{repo}/contents"
        if self._path:
            url = f"{url}/{self._path.strip('/')}"

        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        params: dict[str, str] = {}
        if self._branch:
            params["ref"] = self._branch

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                contents: list[dict[str, Any]] = response.json()

            # Filter for directories only (skills are directories)
            skills = []
            for item in contents:
                if item.get("type") == "dir":
                    name = item.get("name", "")
                    # Skip hidden directories
                    if name.startswith("."):
                        continue
                    skills.append(
                        {
                            "slug": name,
                            "name": name,
                            "description": "",
                        }
                    )

            return skills

        except httpx.HTTPStatusError as e:
            logger.error(f"GitHub API error: {e.response.status_code} for {url}")
            return []
        except httpx.RequestError as e:
            logger.error(f"GitHub API request failed: {e}")
            return []

    async def _clone_skill(
        self,
        slug: str,
        target_dir: str | None = None,
        version: str | None = None,
    ) -> str:
        """Clone a specific skill from the repository.

        Uses clone_skill_repo to clone the entire repository, then
        returns the path to the specific skill directory within it.
        If target_dir is specified, copies the skill directory there.

        Args:
            slug: The skill's directory name
            target_dir: Optional target directory to copy skill to
            version: Optional version/branch to checkout (overrides default branch)

        Returns:
            Path to the skill directory
        """
        # Parse repo into owner/repo
        if "/" not in self._repo:
            raise ValueError(f"Invalid repo format: {self._repo}, expected owner/repo")

        owner, repo = self._repo.split("/", 1)

        # Build skill path within repo (accounting for subdirectory)
        skill_subpath = f"{self._path.strip('/')}/{slug}" if self._path else slug

        # Build GitHubRef with optional version override
        ref = GitHubRef(
            owner=owner,
            repo=repo,
            branch=version or self._branch,
            path=skill_subpath,
        )

        # Clone/update the repository
        repo_path = clone_skill_repo(ref)

        # Path to the skill within the repo
        skill_path = repo_path / skill_subpath

        # If target_dir specified, copy skill there
        if target_dir:
            target = Path(target_dir)
            if skill_path.exists():
                # Copy skill directory contents to target
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(skill_path, target)
            return target_dir

        return str(skill_path)

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
            "path": self.path,
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
    ) -> DownloadResult:
        """Download and extract a skill from the repository.

        Args:
            slug: The skill's unique identifier
            version: Specific version (branch/tag) to download
            target_dir: Directory to extract to

        Returns:
            DownloadResult with success status, path, version, or error
        """
        try:
            path = await self._clone_skill(slug, target_dir, version)
            return DownloadResult(
                success=True,
                slug=slug,
                path=path,
                version=version or self.branch,
            )
        except Exception as e:
            logger.error(f"Failed to download skill {slug}: {e}")
            return DownloadResult(
                success=False,
                slug=slug,
                error=str(e),
            )
