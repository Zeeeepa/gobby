"""
Task expansion module.

Handles breaking down high-level tasks into smaller, actionable subtasks
using LLM providers and gathered context.
"""

import json
import logging
from typing import Any

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContextGatherer
from gobby.tasks.prompts.expand import ExpansionPromptBuilder

logger = logging.getLogger(__name__)


class TaskExpander:
    """Expands tasks into subtasks using LLM and context."""

    def __init__(
        self,
        config: TaskExpansionConfig,
        llm_service: LLMService,
        task_manager: LocalTaskManager,
        mcp_manager: Any | None = None,
    ):
        self.config = config
        self.llm_service = llm_service
        self.task_manager = task_manager
        self.mcp_manager = mcp_manager
        self.context_gatherer = ExpansionContextGatherer(
            task_manager=task_manager,
            llm_service=llm_service,
            config=config,
            mcp_manager=mcp_manager,
        )
        self.prompt_builder = ExpansionPromptBuilder(config)

    async def expand_task(
        self,
        task_id: str,
        title: str,
        description: str | None = None,
        context: str | None = None,
    ) -> dict[str, Any]:
        """
        Expand a task into subtasks using prompt builder and schema validation.

        Args:
            task_id: ID of the task to expand
            title: Task title
            description: Task description
            context: Additional context for expansion

        Returns:
            Dictionary matching the expansion schema (complexity_analysis, phases)
        """
        if not self.config.enabled:
            logger.info("Task expansion disabled, skipping")
            return {}

        logger.info(f"Expanding task {task_id}: {title}")

        # Gather enhanced context
        task_obj = self.task_manager.get_task(task_id)
        if not task_obj:
            logger.warning(f"Task {task_id} not found for context gathering, using basic info")
            task_obj = Task(
                id=task_id,
                project_id="unknown",
                title=title,
                status="open",
                priority=2,
                task_type="task",
                created_at="",
                updated_at="",
                description=description,
            )

        expansion_ctx = await self.context_gatherer.gather_context(task_obj)

        # Build prompt using builder
        prompt = self.prompt_builder.build_user_prompt(
            task=task_obj,
            context=expansion_ctx,
            user_instructions=context,
        )

        try:
            # Call LLM
            provider = self.llm_service.get_provider(self.config.provider)
            response_content = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.prompt_builder.get_system_prompt(),
                model=self.config.model,
            )

            # Parse and validate response
            return self._parse_and_validate_response(response_content)

        except Exception as e:
            logger.error(f"Failed to expand task {task_id}: {e}", exc_info=True)
            return {"error": str(e)}

    def _parse_and_validate_response(self, content: str) -> dict[str, Any]:
        """
        Parse LLM response and validate against schema.
        Handles markdown blocks and loose JSON.
        """
        content = content.strip()

        # Handle markdown blocks
        if "```" in content:
            # Find the JSON block
            import re

            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)
            else:
                # Fallback: try to find start/end of JSON object
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1:
                    content = content[start : end + 1]

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode output as JSON: {content[:100]}...")
            raise ValueError(f"Invalid JSON response from LLM: {e}")

        # Basic schema validation (we rely on prompt for structure mostly)
        if "complexity_analysis" not in data or "phases" not in data:
            # Attempt to normalize if LLM returned just a list of subtasks (legacy behavior fallback)
            if "subtasks" in data:
                return {
                    "complexity_analysis": {
                        "score": 1,
                        "reasoning": "Legacy format normalized",
                        "recommended_subtasks": len(data["subtasks"]),
                    },
                    "phases": [
                        {
                            "name": "Phase 1",
                            "description": "Auto-generated phase",
                            "subtasks": data["subtasks"],
                        }
                    ],
                }
            raise ValueError("Response missing 'complexity_analysis' or 'phases' fields")

        return data
