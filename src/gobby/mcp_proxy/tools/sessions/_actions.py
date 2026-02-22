"""Session action tools - thin wrappers around workflow actions.

Exposes internal workflow actions as MCP tools:
- generate_handoff: Generate session summary for handoff
- extract_handoff_context: Extract structured handoff context
- capture_baseline_dirty_files: Capture pre-session dirty files
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.workflows.context_actions import (
    extract_handoff_context as extract_handoff_context_action,
)
from gobby.workflows.git_utils import get_dirty_files
from gobby.workflows.summary_actions import (
    generate_handoff as generate_handoff_action,
)

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
        name="generate_handoff",
        description="Generate a session summary for handoff. Creates an LLM-powered summary and marks session as handoff_ready.",
    )
    async def generate_handoff_tool(
        session_id: str,
        mode: str = "clear",
        write_file: bool = False,
    ) -> dict[str, Any]:
        """
        Generate a handoff summary for a session.

        Args:
            session_id: Session to generate handoff for
            mode: "clear" for session end or "compact" for compaction
            write_file: Write summary to file
        """
        if not llm_service:
            return {"success": False, "error": "LLM service not available"}
        try:
            result = await generate_handoff_action(
                session_manager=session_manager,
                session_id=session_id,
                llm_service=llm_service,
                transcript_processor=transcript_processor,
                mode=mode,
                write_file=write_file,
            )
            if result is None:
                return {"success": False, "error": "Failed to generate handoff"}
            if "error" in result:
                return {"success": False, "error": result["error"]}
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="extract_handoff_context",
        description="Extract structured handoff context from session transcript. Prefers rolling digest when available.",
    )
    def extract_handoff_context_tool(
        session_id: str,
    ) -> dict[str, Any]:
        """
        Extract handoff context from a session transcript.

        Args:
            session_id: Session to extract context from
        """
        try:
            result = extract_handoff_context_action(
                session_manager=session_manager,
                session_id=session_id,
                config=config,
                db=db,
                worktree_manager=worktree_manager,
            )
            if result is None:
                return {"success": False, "error": "No result from extraction"}
            if "error" in result:
                return {"success": False, "error": result["error"]}
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

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
