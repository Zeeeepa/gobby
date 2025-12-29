"""
Task expansion module.

Handles breaking down high-level tasks into smaller, actionable subtasks
using LLM providers and gathered context.
"""

import logging
import json
from typing import Any

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.storage.tasks import Task, LocalTaskManager
from gobby.tasks.context import ExpansionContextGatherer

logger = logging.getLogger(__name__)


class TaskExpander:
    """Expands tasks into subtasks using LLM and context."""

    def __init__(
        self,
        config: TaskExpansionConfig,
        llm_service: LLMService,
        task_manager: LocalTaskManager,
    ):
        self.config = config
        self.llm_service = llm_service
        self.task_manager = task_manager
        self.context_gatherer = ExpansionContextGatherer(task_manager)

    async def expand_task(
        self,
        task_id: str,
        title: str,
        description: str | None = None,
        context: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Expand a task into subtasks.

        Args:
            task_id: ID of the task to expand
            title: Task title
            description: Task description
            context: Additional context for expansion

        Returns:
            List of subtask dictionaries with title and description
        """
        if not self.config.enabled:
            logger.info("Task expansion disabled, skipping")
            return []

        logger.info(f"Expanding task {task_id}: {title}")

        # Gather enhanced context
        task_obj = self.task_manager.get_task(task_id)
        if not task_obj:
            logger.warning(f"Task {task_id} not found for context gathering, using basic info")
            # Create a transient task object for context gathering if needed, or skip
            # For now, if task matches ID but DB lookup fails (race condition?), we proceed with limited context
            # Actually, creating a dummy task object is better for gatherer signature
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

        # Build prompt with gathered context
        prompt = self._build_expansion_prompt(
            title=title,
            description=description,
            user_context=context,
            gathered_context=expansion_ctx.to_dict(),
        )

        try:
            # Call LLM
            provider = self.llm_service.get_provider(self.config.provider)
            response_content = await provider.generate_text(
                prompt=prompt,
                system_prompt="You are a technical project manager. Break down tasks effectively.",
                model=self.config.model,
            )

            # Parse response validation logic...
            # Reuse the simple parsing from before but ideally we want JSON mode if provider supports it
            content = response_content.strip()
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content.rsplit("\n", 1)[0]
                if content.startswith("json"):
                    content = content[4:].strip()

            subtasks = json.loads(content)

            # Handle normalized format
            if isinstance(subtasks, dict) and "subtasks" in subtasks:
                subtasks = subtasks["subtasks"]

            if not isinstance(subtasks, list):
                logger.warning(f"LLM returned non-list for task expansion: {type(subtasks)}")
                return []

            return subtasks

        except Exception as e:
            logger.error(f"Failed to expand task {task_id}: {e}")
            return []

    def _build_expansion_prompt(
        self,
        title: str,
        description: str | None,
        user_context: str | None,
        gathered_context: dict[str, Any],
    ) -> str:
        """Build the prompt for task expansion."""
        prompt = self.config.prompt

        # If no default prompt in config, use our enhanced one
        if not prompt:
            prompt = f"""You are an expert technical project manager and software architect.
Your goal is to break down a high-level software task into concrete, actionable subtasks.

Task Title: {title}
Task Description: {description or "No description provided"}

"""
            if user_context:
                prompt += f"User Provided Context:\n{user_context}\n\n"

            # Add gathered context
            relevant_files = gathered_context.get("relevant_files", [])
            if relevant_files:
                prompt += f"Relevant Files:\n{', '.join(relevant_files)}\n\n"

            related_tasks = gathered_context.get("related_tasks", [])
            if related_tasks:
                prompt += "Related Tasks:\n"
                for t in related_tasks:
                    prompt += f"- {t['title']} (Status: {t['status']})\n"
                prompt += "\n"

            project_patterns = gathered_context.get("project_patterns", {})
            if project_patterns:
                prompt += "Project Patterns:\n"
                for k, v in project_patterns.items():
                    prompt += f"- {k}: {v}\n"
                prompt += "\n"

            prompt += """
Please analyze the task and break it down into 3-7 subtasks.
Each subtask should be a distinct unit of work.

Return a JSON object with a 'subtasks' key containing a list of objects, each with:
- title: Concise title for the subtask
- description: Detailed technical instructions

Example format:
{
  "subtasks": [
    {
      "title": "Create database schema",
      "description": "Create migration file for users table with id, email, password fields."
    }
  ]
}
"""
        return prompt
