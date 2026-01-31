"""Skill hub providers for searching and installing skills from registries."""

from gobby.skills.hubs.base import (
    HubProvider,
    HubSkillDetails,
    HubSkillInfo,
)
from gobby.skills.hubs.manager import HubManager

__all__ = [
    "HubManager",
    "HubProvider",
    "HubSkillDetails",
    "HubSkillInfo",
]
