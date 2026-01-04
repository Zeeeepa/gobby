"""
Task expansion module.

Handles breaking down high-level tasks into smaller, actionable subtasks
using LLM providers with structured JSON output.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContext, ExpansionContextGatherer
from gobby.tasks.prompts.expand import ExpansionPromptBuilder

logger = logging.getLogger(__name__)


@dataclass
class SubtaskSpec:
    """Parsed subtask specification from LLM output."""

    title: str
    description: str | None = None
    priority: int = 2
    task_type: str = "task"
    test_strategy: str | None = None
    depends_on: list[int] | None = None


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
        enable_web_research: bool = False,
        enable_code_context: bool = True,
    ) -> dict[str, Any]:
        """
        Expand a task into subtasks using structured JSON output.

        The LLM returns a JSON object with subtask specifications, which are
        then parsed and created as tasks with proper dependency wiring.

        Args:
            task_id: ID of the task to expand
            title: Task title
            description: Task description
            context: Additional context for expansion
            enable_web_research: Whether to enable web research (default: False)
            enable_code_context: Whether to enable code context gathering (default: True)

        Returns:
            Dictionary with:
            - subtask_ids: List of created subtask IDs
            - subtask_count: Number of subtasks created
            - raw_response: The raw LLM response (for debugging)
        """
        if not self.config.enabled:
            logger.info("Task expansion disabled, skipping")
            return {"subtask_ids": [], "subtask_count": 0, "raw_response": "Expansion disabled"}

        logger.info(f"Expanding task {task_id}: {title}")

        # Apply overall timeout for entire expansion
        timeout_seconds = self.config.timeout
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._expand_task_impl(
                    task_id=task_id,
                    title=title,
                    description=description,
                    context=context,
                    enable_web_research=enable_web_research,
                    enable_code_context=enable_code_context,
                )
        except TimeoutError:
            error_msg = (
                f"Task expansion timed out after {timeout_seconds} seconds. "
                f"Consider increasing task_expansion.timeout in config or simplifying the task."
            )
            logger.error(f"Expansion timeout for {task_id}: {error_msg}")
            return {"error": error_msg, "subtask_ids": [], "subtask_count": 0, "timeout": True}

    async def _expand_task_impl(
        self,
        task_id: str,
        title: str,
        description: str | None = None,
        context: str | None = None,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
    ) -> dict[str, Any]:
        """Internal implementation of expand_task (called within timeout context)."""
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

        expansion_ctx = await self.context_gatherer.gather_context(
            task_obj,
            enable_web_research=enable_web_research,
            enable_code_context=enable_code_context,
        )

        # Build prompt using builder
        prompt = self.prompt_builder.build_user_prompt(
            task=task_obj,
            context=expansion_ctx,
            user_instructions=context,
        )

        try:
            # Get provider and generate text response
            provider = self.llm_service.get_provider(self.config.provider)

            # Disable TDD mode for epics - their closing condition is "all children closed"
            # so they don't need test pairs
            tdd_mode = self.config.tdd_mode and task_obj.task_type != "epic"

            response = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.prompt_builder.get_system_prompt(tdd_mode=tdd_mode),
                model=self.config.model,
            )

            logger.debug(f"LLM response (first 500 chars): {response[:500]}")

            # Parse JSON from response
            subtask_specs = self._parse_subtasks(response)
            logger.debug(f"Parsed {len(subtask_specs)} subtask specs")

            if not subtask_specs:
                logger.warning(f"No subtasks parsed from response for {task_id}")
                return {
                    "subtask_ids": [],
                    "subtask_count": 0,
                    "raw_response": response,
                    "error": "No subtasks found in response",
                }

            # Create tasks with dependency wiring
            subtask_ids = await self._create_subtasks(
                parent_task_id=task_id,
                project_id=task_obj.project_id,
                subtask_specs=subtask_specs,
            )

            # Save expansion context to the parent task for audit/reuse
            self._save_expansion_context(task_id, expansion_ctx)

            logger.info(f"Expansion complete for {task_id}: created {len(subtask_ids)} subtasks")

            return {
                "subtask_ids": subtask_ids,
                "subtask_count": len(subtask_ids),
                "raw_response": response,
            }

        except Exception as e:
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            logger.error(f"Failed to expand task {task_id}: {error_msg}", exc_info=True)
            return {"error": error_msg, "subtask_ids": [], "subtask_count": 0}

    def _parse_subtasks(self, response: str) -> list[SubtaskSpec]:
        """
        Parse subtask specifications from LLM JSON response.

        Args:
            response: Raw LLM response text (should be JSON)

        Returns:
            List of SubtaskSpec objects parsed from the response
        """
        # Try to extract JSON from the response
        json_str = self._extract_json(response)
        if not json_str:
            logger.warning("No JSON found in response")
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return []

        # Extract subtasks array
        subtasks_data = data.get("subtasks", [])
        if not isinstance(subtasks_data, list):
            logger.warning(f"Expected 'subtasks' to be a list, got {type(subtasks_data)}")
            return []

        # Parse each subtask
        subtask_specs = []
        for i, item in enumerate(subtasks_data):
            if not isinstance(item, dict):
                logger.warning(f"Subtask {i} is not a dict, skipping")
                continue

            if "title" not in item:
                logger.warning(f"Subtask {i} missing title, skipping")
                continue

            spec = SubtaskSpec(
                title=item["title"],
                description=item.get("description"),
                priority=item.get("priority", 2),
                task_type=item.get("task_type", "task"),
                test_strategy=item.get("test_strategy"),
                depends_on=item.get("depends_on"),
            )
            subtask_specs.append(spec)

        return subtask_specs

    def _extract_json(self, text: str) -> str | None:
        """
        Extract JSON from text, handling markdown code blocks.

        Args:
            text: Raw text that may contain JSON

        Returns:
            Extracted JSON string, or None if not found
        """
        # Try to find JSON in code blocks first
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches: list[str] = re.findall(code_block_pattern, text)
        for match in matches:
            stripped: str = match.strip()
            if stripped.startswith("{"):
                return stripped

        # Try to find raw JSON object
        # Look for { ... } pattern
        brace_start = text.find("{")
        if brace_start == -1:
            return None

        # Find matching closing brace
        depth = 0
        for i, char in enumerate(text[brace_start:], brace_start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[brace_start : i + 1]

        return None

    async def _create_subtasks(
        self,
        parent_task_id: str,
        project_id: str,
        subtask_specs: list[SubtaskSpec],
    ) -> list[str]:
        """
        Create tasks from parsed subtask specifications.

        Handles dependency wiring by mapping depends_on indices to task IDs.

        Args:
            parent_task_id: ID of the parent task
            project_id: Project ID for the new tasks
            subtask_specs: List of parsed subtask specifications

        Returns:
            List of created task IDs
        """
        created_ids: list[str] = []
        dep_manager = TaskDependencyManager(self.task_manager.db)

        for i, spec in enumerate(subtask_specs):
            # Build description with test strategy if present
            description = spec.description or ""
            if spec.test_strategy:
                if description:
                    description += f"\n\n**Test Strategy:** {spec.test_strategy}"
                else:
                    description = f"**Test Strategy:** {spec.test_strategy}"

            # Create the task
            task = self.task_manager.create_task(
                title=spec.title,
                description=description if description else None,
                project_id=project_id,
                priority=spec.priority,
                task_type=spec.task_type,
                parent_task_id=parent_task_id,
                test_strategy=spec.test_strategy,
            )

            created_ids.append(task.id)
            logger.debug(f"Created subtask {task.id}: {spec.title}")

            # Add dependencies (depends_on indices -> this task is blocked by those)
            if spec.depends_on:
                for dep_idx in spec.depends_on:
                    if (
                        0 <= dep_idx < len(created_ids) - 1
                    ):  # -1 because current task is already added
                        blocker_id = created_ids[dep_idx]
                        try:
                            dep_manager.add_dependency(task.id, blocker_id, "blocks")
                            logger.debug(f"Added dependency: {task.id} blocked by {blocker_id}")
                        except Exception as e:
                            logger.warning(f"Failed to add dependency: {e}")
                    else:
                        logger.warning(
                            f"Subtask {i} references invalid index {dep_idx}, skipping dependency"
                        )

        return created_ids

    def _save_expansion_context(
        self,
        task_id: str,
        context: "ExpansionContext",
    ) -> None:
        """
        Save expansion context to the task for audit and reuse.

        Stores web research results and other context in the task's
        expansion_context field as JSON.

        Args:
            task_id: ID of the task to update
            context: The expansion context to save
        """
        try:
            # Build a slim context dict focused on web research
            context_data: dict[str, Any] = {}

            if context.web_research:
                context_data["web_research"] = context.web_research

            if context.agent_findings:
                context_data["agent_findings"] = context.agent_findings

            if context.relevant_files:
                context_data["relevant_files"] = context.relevant_files

            if not context_data:
                logger.debug(f"No expansion context to save for {task_id}")
                return

            # Serialize and update the task
            context_json = json.dumps(context_data)
            self.task_manager.update_task(task_id, expansion_context=context_json)
            logger.info(f"Saved expansion context for {task_id} ({len(context_json)} bytes)")

        except Exception as e:
            logger.warning(f"Failed to save expansion context for {task_id}: {e}")
