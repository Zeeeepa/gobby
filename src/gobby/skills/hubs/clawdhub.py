"""ClawdHub provider implementation.

This module provides the ClawdHubProvider class which wraps the official
`clawdhub` CLI tool to provide skill search, listing, and download functionality.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from gobby.skills.hubs.base import HubProvider, HubSkillDetails, HubSkillInfo

logger = logging.getLogger(__name__)


class ClawdHubProvider(HubProvider):
    """Provider for ClawdHub skill registry using the CLI tool.

    This provider wraps the official `clawdhub` CLI tool (installed via
    `npm i -g clawdhub`) to provide access to the ClawdHub skill registry.

    The CLI provides commands for:
    - search: Search for skills by query
    - list: List available skills
    - install: Download/install a skill
    - info: Get detailed skill information

    Example usage:
        ```python
        provider = ClawdHubProvider(
            hub_name="clawdhub",
            base_url="https://clawdhub.com",
        )

        # Check if CLI is available
        info = await provider.discover()
        if info["cli_available"]:
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
        """Initialize the ClawdHub provider.

        Args:
            hub_name: The configured name for this hub instance
            base_url: Base URL for ClawdHub (used for reference)
            auth_token: Optional authentication token for private skills
        """
        super().__init__(hub_name=hub_name, base_url=base_url, auth_token=auth_token)
        self._cli_available: bool | None = None

    @property
    def provider_type(self) -> str:
        """Return the provider type identifier."""
        return "clawdhub"

    async def _check_cli_available(self) -> bool:
        """Check if the clawdhub CLI is available.

        Returns:
            True if CLI is installed and accessible, False otherwise
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "clawdhub",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                version = stdout.decode().strip()
                logger.debug(f"ClawdHub CLI version: {version}")
                return True
            return False
        except FileNotFoundError:
            logger.warning("ClawdHub CLI not found. Install with: npm i -g clawdhub")
            return False
        except Exception as e:
            logger.error(f"Error checking ClawdHub CLI: {e}")
            return False

    async def _run_cli_command(
        self,
        command: str,
        args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run a clawdhub CLI command and return parsed JSON output.

        Args:
            command: The CLI command (search, list, install, info, etc.)
            args: Additional arguments for the command

        Returns:
            Parsed JSON output from the CLI

        Raises:
            RuntimeError: If CLI is not available or command fails
        """
        cmd_args = ["clawdhub", command, "--json"]
        if args:
            cmd_args.extend(args)

        # Add auth token if available
        if self.auth_token:
            cmd_args.extend(["--token", self.auth_token])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                logger.error(f"ClawdHub CLI error: {error_msg}")
                raise RuntimeError(f"ClawdHub CLI command failed: {error_msg}")

            output = stdout.decode().strip()
            if not output:
                return {}

            parsed: dict[str, Any] = json.loads(output)
            return parsed
        except FileNotFoundError as e:
            raise RuntimeError("ClawdHub CLI not found. Install with: npm i -g clawdhub") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CLI output: {e}")
            raise RuntimeError(f"Invalid JSON from ClawdHub CLI: {e}") from e

    async def discover(self) -> dict[str, Any]:
        """Discover hub capabilities and check CLI availability.

        Returns:
            Dictionary with hub info and CLI availability status
        """
        cli_available = await self._check_cli_available()
        self._cli_available = cli_available

        return {
            "hub_name": self.hub_name,
            "provider_type": self.provider_type,
            "cli_available": cli_available,
            "base_url": self.base_url,
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
        result = await self._run_cli_command("search", [query, "--limit", str(limit)])

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
        args = ["--limit", str(limit)]
        if offset > 0:
            args.extend(["--offset", str(offset)])

        result = await self._run_cli_command("list", args)

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
            result = await self._run_cli_command("info", [slug])

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
        args = [slug]

        if version:
            args.extend(["--version", version])

        if target_dir:
            args.extend(["--output", target_dir])

        result = await self._run_cli_command("install", args)

        return {
            "success": result.get("success", True),
            "path": result.get("path", target_dir),
            "version": result.get("version", version),
            "slug": slug,
        }
