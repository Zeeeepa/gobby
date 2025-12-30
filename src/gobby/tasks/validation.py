"""
Task validation module.

Handles validating task completion against acceptance criteria
using LLM providers.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from gobby.config.app import TaskValidationConfig
from gobby.llm import LLMService

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of task validation."""

    status: Literal["valid", "invalid", "pending"]
    feedback: str | None = None


class TaskValidator:
    """Validates task completion using LLM."""

    def __init__(self, config: TaskValidationConfig, llm_service: LLMService):
        self.config = config
        self.llm_service = llm_service

    async def gather_validation_context(self, file_paths: list[str]) -> str:
        """
        Gather context for validation from files.

        Args:
            file_paths: List of absolute file paths to read.

        Returns:
            Concatenated file contents.
        """
        context: list[str] = []
        for path in file_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                    context.append(f"--- {path} ---\n{content}\n")
            except Exception as e:
                logger.warning(f"Failed to read file {path} for validation: {e}")
                context.append(f"--- {path} ---\n(Error reading file: {e})\n")
        return "\n".join(context)

    async def validate_task(
        self,
        task_id: str,
        title: str,
        original_instruction: str | None,
        changes_summary: str,
        validation_criteria: str | None = None,
        context_files: list[str] | None = None,
    ) -> ValidationResult:
        """
        Validate task completion.

        Args:
            task_id: Task ID
            title: Task title
            original_instruction: Original user instruction/request
            changes_summary: Summary of changes made (files, diffs, etc.)
            validation_criteria: Specific criteria to validate against (optional)
            context_files: List of files to read for context (optional)

        Returns:
            ValidationResult with status and feedback
        """
        if not self.config.enabled:
            return ValidationResult(status="pending", feedback="Validation disabled")

        if not original_instruction and not validation_criteria:
            logger.warning(f"Cannot validate task {task_id}: missing instruction and criteria")
            return ValidationResult(
                status="pending", feedback="Missing original instruction and criteria"
            )

        logger.info(f"Validating task {task_id}: {title}")

        # Gather context if provided
        file_context = ""
        if context_files:
            file_context = await self.gather_validation_context(context_files)

        # Build prompt
        criteria_text = (
            f"Validation Criteria:\n{validation_criteria}"
            if validation_criteria
            else f"Original Instruction:\n{original_instruction}"
        )

        base_prompt = (
            "Validate if the following changes satisfy the requirements.\n"
            "Return ONLY a valid JSON object with 'status' ('valid' or 'invalid') "
            "and 'feedback' (string explanation).\n\n"
            f"Task: {title}\n"
            f"{criteria_text}\n\n"
            f"Changes Summary:\n{changes_summary}\n\n"
        )

        if file_context:
            # Truncate file context to 50k chars to avoid exceeding LLM context limits
            base_prompt += f"File Context:\n{file_context[:50000]}\n"

        prompt = self.config.prompt or base_prompt

        try:
            provider = self.llm_service.get_provider(self.config.provider)
            response_content = await provider.generate_text(
                prompt=prompt,
                system_prompt="You are a QA engineer. Validate work strictly against requirements. Be critical.",
                model=self.config.model,
            )

            import json
            import re

            content = response_content.strip()

            # Try to find JSON in code block
            json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_block:
                content = json_block.group(1)
            else:
                # If no code block, try to find { ... }
                json_obj = re.search(r"(\{.*\})", content, re.DOTALL)
                if json_obj:
                    content = json_obj.group(1)

            result_data = json.loads(content)

            return ValidationResult(
                status=result_data.get("status", "pending"), feedback=result_data.get("feedback")
            )

        except Exception as e:
            logger.error(f"Failed to validate task {task_id}: {e}")
            return ValidationResult(status="pending", feedback=f"Validation failed: {str(e)}")

    async def generate_criteria(
        self,
        title: str,
        description: str | None = None,
    ) -> str | None:
        """
        Generate validation criteria from task title and description.

        Args:
            title: Task title
            description: Task description (optional)

        Returns:
            Generated validation criteria string, or None if generation fails
        """
        if not self.config.enabled:
            return None

        # Use custom prompt from config, or default
        if self.config.criteria_prompt:
            prompt = self.config.criteria_prompt.format(
                title=title,
                description=description or "(no description)",
            )
        else:
            prompt = (
                "Generate clear, testable acceptance criteria for the following task.\n"
                "Return a concise bulleted list of specific conditions that must be met.\n"
                "Focus on observable outcomes, not implementation details.\n\n"
                f"Task: {title}\n"
            )
            if description:
                prompt += f"Description: {description}\n"

            prompt += (
                "\nFormat your response as a simple bulleted list, e.g.:\n"
                "- Condition 1\n"
                "- Condition 2\n"
                "- Condition 3\n"
            )

        try:
            provider = self.llm_service.get_provider(self.config.provider)
            response = await provider.generate_text(
                prompt=prompt,
                system_prompt="You are a QA engineer. Generate clear, testable acceptance criteria.",
                model=self.config.model,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate validation criteria: {e}")
            return None
