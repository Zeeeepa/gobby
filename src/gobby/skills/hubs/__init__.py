"""Skill hub providers for searching and installing skills from registries."""

from gobby.skills.hubs.base import (
    DownloadResult,
    HubProvider,
    HubSkillDetails,
    HubSkillInfo,
)
from gobby.skills.hubs.clawdhub import ClawdHubProvider
from gobby.skills.hubs.github_collection import GitHubCollectionProvider
from gobby.skills.hubs.manager import HubManager
from gobby.skills.hubs.skillhub import SkillHubProvider

__all__ = [
    "ClawdHubProvider",
    "DownloadResult",
    "GitHubCollectionProvider",
    "HubManager",
    "HubProvider",
    "HubSkillDetails",
    "HubSkillInfo",
    "SkillHubProvider",
]
