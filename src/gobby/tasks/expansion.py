"""
Task expansion module.

Handles breaking down high-level tasks into smaller, actionable subtasks
using LLM providers with MCP tool access.
"""

import json
import logging
from typing import Any

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.llm.claude import ClaudeLLMProvider
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContextGatherer
from gobby.tasks.prompts.expand import ExpansionPromptBuilder

logger = logging.getLogger(__name__)

# MCP tool pattern for task creation
CREATE_TASK_TOOL = "mcp__gobby-tasks__create_task"


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
        Expand a task into subtasks using tool-based approach.

        The expansion agent calls the create_task MCP tool directly to create
        subtasks, wiring dependencies via the 'blocks' parameter.

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
            - tool_calls: Number of create_task calls made
            - text: Agent's reasoning/explanation text
        """
        if not self.config.enabled:
            logger.info("Task expansion disabled, skipping")
            return {"subtask_ids": [], "tool_calls": 0, "text": "Expansion disabled"}

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
            # Get Claude provider (tool-based expansion requires Claude)
            provider = self.llm_service.get_provider(self.config.provider)
            if not isinstance(provider, ClaudeLLMProvider):
                logger.warning(
                    f"Provider {self.config.provider} does not support tool-based expansion, "
                    "falling back to text generation"
                )
                return await self._expand_with_text_fallback(
                    provider, prompt, task_id
                )

            # Call LLM with MCP tool access
            result = await provider.generate_with_mcp_tools(
                prompt=prompt,
                allowed_tools=[CREATE_TASK_TOOL],
                system_prompt=self.prompt_builder.get_system_prompt(
                    tdd_mode=self.config.tdd_mode
                ),
                model=self.config.model,
                max_turns=self.config.max_subtasks + 5,  # Allow extra turns for reasoning
            )

            # Extract created subtask IDs from tool call results
            subtask_ids = self._extract_subtask_ids(result.tool_calls)

            logger.info(
                f"Expansion complete for {task_id}: created {len(subtask_ids)} subtasks"
            )

            return {
                "subtask_ids": subtask_ids,
                "tool_calls": len(result.tool_calls),
                "text": result.text,
            }

        except Exception as e:
            logger.error(f"Failed to expand task {task_id}: {e}", exc_info=True)
            return {"error": str(e), "subtask_ids": [], "tool_calls": 0}

    def _extract_subtask_ids(self, tool_calls: list) -> list[str]:
        """
        Extract created subtask IDs from tool call results.

        Args:
            tool_calls: List of ToolCall objects from generate_with_mcp_tools

        Returns:
            List of task IDs created during expansion
        """
        subtask_ids = []
        for call in tool_calls:
            if call.tool_name == CREATE_TASK_TOOL and call.result:
                try:
                    # Tool result is JSON string with task details
                    result_data = json.loads(call.result)
                    if isinstance(result_data, dict) and "id" in result_data:
                        subtask_ids.append(result_data["id"])
                        logger.debug(f"Created subtask: {result_data['id']}")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse tool result: {call.result[:100]}... - {e}")
        return subtask_ids

    async def _expand_with_text_fallback(
        self,
        provider: Any,
        prompt: str,
        task_id: str,
    ) -> dict[str, Any]:
        """
        Fallback expansion using text generation (for non-Claude providers).

        This method is deprecated and will be removed once all providers
        support tool-based expansion.
        """
        logger.warning(
            f"Using text fallback for expansion of {task_id}. "
            "This approach is deprecated - use Claude provider for tool-based expansion."
        )
        response_content = await provider.generate_text(
            prompt=prompt,
            system_prompt=self.prompt_builder.get_system_prompt(
                tdd_mode=self.config.tdd_mode
            ),
            model=self.config.model,
        )
        # Return raw text - caller will need to handle manually
        return {
            "subtask_ids": [],
            "tool_calls": 0,
            "text": response_content,
            "fallback": True,
        }

