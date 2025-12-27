"""Recommendation service."""

import logging
from typing import Any

logger = logging.getLogger("gobby.mcp.server")


class RecommendationService:
    """Service for recommending tools."""

    def __init__(self, llm_service: Any, mcp_manager: Any):
        self._llm_service = llm_service
        self._mcp_manager = mcp_manager

    async def recommend_tools(
        self, task_description: str, agent_id: str | None = None
    ) -> dict[str, Any]:
        """Recommend tools based on task."""
        # Logic extracted from recommend_tools
        return {
            "success": True,
            "task": task_description,
            "recommendation": "Stubbed recommendation",
            "available_servers": list(self._mcp_manager._configs.keys()),
        }
