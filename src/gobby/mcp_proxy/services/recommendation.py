"""Recommendation service."""

import json
import logging
from typing import Any

logger = logging.getLogger("gobby.mcp.server")


class RecommendationService:
    """Service for recommending tools."""

    def __init__(self, llm_service: Any, mcp_manager: Any):
        self._llm_service = llm_service
        self._mcp_manager = mcp_manager

    async def recommend_tools(self, task_description: str) -> dict[str, Any]:
        """Recommend tools based on task."""
        try:
            available_servers = self._mcp_manager.get_available_servers()

            prompt = f"""
You are an expert at selecting the right tools for a given task.
Task: {task_description}

Available Servers: {", ".join(available_servers)}

Please recommend which tools from these servers would be most useful for this task.
Return a JSON object with this structure:
{{
  "recommendations": [
    {{
      "server": "server_name",
      "tool": "tool_name",
      "reason": "Why this tool is useful"
    }}
  ]
}}
"""
            # Call LLM service (assuming generate returns a string response)
            # We use a lower temperature for deterministic output
            response = await self._llm_service.generate(prompt, temperature=0.1)

            # Parse response (assuming service returns raw string that might need JSON parsing)
            # In a real impl, we might use a structured output mode if available
            try:
                # Naive JSON extraction if response contains markdown code blocks
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()

                data = json.loads(response)
                recommendations = data.get("recommendations", [])
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                # Fallback if parsing fails
                recommendations = []
                logger.warning(f"Failed to parse LLM recommendation response: {e}")

            return {
                "success": True,
                "task": task_description,
                "recommendation": recommendations,  # Keep key for compatibility, though it's a list
                "recommendations": recommendations,  # Better key
                "available_servers": available_servers,
            }
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return {"success": False, "error": str(e), "task": task_description}
