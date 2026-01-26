"""
Isolation Handlers for Unified spawn_agent API.

This module provides the abstraction layer for different isolation modes:
- current: Work in the current directory (no isolation)
- worktree: Create/reuse a git worktree for isolated work
- clone: Create a shallow clone for full isolation

Each handler implements the IsolationHandler ABC to provide:
- Environment preparation (worktree/clone creation)
- Context prompt building (adding isolation warnings)
- Branch name generation
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class IsolationContext:
    """Result of environment preparation."""

    cwd: str
    branch_name: str | None = None
    worktree_id: str | None = None
    clone_id: str | None = None
    isolation_type: Literal["current", "worktree", "clone"] = "current"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpawnConfig:
    """Configuration passed to isolation handlers."""

    prompt: str
    task_id: str | None
    task_title: str | None
    task_seq_num: int | None
    branch_name: str | None
    branch_prefix: str | None
    base_branch: str
    project_id: str
    project_path: str
    provider: str
    parent_session_id: str


def generate_branch_name(config: SpawnConfig) -> str:
    """
    Auto-generate branch name from task or fallback to prefix+timestamp.

    Priority:
    1. Explicit branch_name if provided
    2. task-{seq_num}-{slugified_title} if task info available
    3. {branch_prefix}{timestamp} as fallback (default prefix: "agent/")
    """
    if config.branch_name:
        return config.branch_name

    if config.task_seq_num and config.task_title:
        # Generate slug from task title
        slug = config.task_title.lower().replace(" ", "-")
        # Keep only alphanumeric and hyphens
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        # Truncate to 40 chars
        slug = slug[:40]
        return f"task-{config.task_seq_num}-{slug}"

    # Fallback to prefix + timestamp
    prefix = config.branch_prefix or "agent/"
    return f"{prefix}{int(time.time())}"


class IsolationHandler(ABC):
    """Abstract base class for isolation handlers."""

    @abstractmethod
    async def prepare_environment(self, config: SpawnConfig) -> IsolationContext:
        """
        Prepare isolated environment (worktree/clone creation).

        Args:
            config: Spawn configuration with project and task info

        Returns:
            IsolationContext with cwd and isolation metadata
        """

    @abstractmethod
    def build_context_prompt(self, original_prompt: str, ctx: IsolationContext) -> str:
        """
        Build prompt with isolation context warnings.

        Args:
            original_prompt: The original user prompt
            ctx: Isolation context from prepare_environment

        Returns:
            Enhanced prompt with isolation context (or unchanged for current)
        """


class CurrentIsolationHandler(IsolationHandler):
    """
    No isolation - work in current directory.

    This is the simplest handler that just returns the project path
    as the working directory without any git branch changes.
    """

    async def prepare_environment(self, config: SpawnConfig) -> IsolationContext:
        """Return project path as working directory."""
        return IsolationContext(
            cwd=config.project_path,
            isolation_type="current",
        )

    def build_context_prompt(self, original_prompt: str, ctx: IsolationContext) -> str:
        """Return prompt unchanged - no additional context needed."""
        return original_prompt
