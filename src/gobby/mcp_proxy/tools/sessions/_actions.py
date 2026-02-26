"""Session action tools - thin wrappers around workflow actions.

Exposes internal workflow actions as MCP tools:
- capture_baseline_dirty_files: Capture pre-session dirty files
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.workflows.git_utils import get_dirty_files

if TYPE_CHECKING:
    from gobby.mcp_proxy.tools.internal import InternalToolRegistry
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)


def register_action_tools(
    registry: InternalToolRegistry,
    session_manager: LocalSessionManager,
    llm_service: Any | None = None,
    transcript_processor: Any | None = None,
    config: Any | None = None,
    db: Any | None = None,
    worktree_manager: Any | None = None,
) -> None:
    """Register session action tools on the registry.

    Args:
        registry: The session tool registry
        session_manager: LocalSessionManager for session lookups
        llm_service: LLM service for handoff generation
        transcript_processor: Transcript processor for handoff generation
        config: DaemonConfig for settings
        db: Database for dependency injection
        worktree_manager: Worktree manager for context enrichment
    """

    @registry.tool(
        name="capture_baseline_dirty_files",
        description="Capture current dirty files as baseline for session-aware commit detection.",
    )
    async def capture_baseline_dirty_files_tool(
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Capture current dirty files as a baseline.

        Args:
            project_path: Path to the project directory for git status check
        """
        try:
            dirty_files = get_dirty_files(project_path)
            return {
                "success": True,
                "file_count": len(dirty_files),
                "files": sorted(dirty_files),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
