"""
Task validation module.

Handles validating task completion against acceptance criteria
using LLM providers.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import Literal

from gobby.config.app import TaskValidationConfig
from gobby.llm import LLMService

logger = logging.getLogger(__name__)


def get_last_commit_diff(max_chars: int = 50000) -> str | None:
    """Get diff from the most recent commit.

    Args:
        max_chars: Maximum characters to return (truncates if larger)

    Returns:
        Diff string from HEAD~1..HEAD, or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1..HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        diff = result.stdout
        if len(diff) > max_chars:
            diff = diff[:max_chars] + "\n\n... [diff truncated] ..."

        return diff

    except Exception as e:
        logger.debug(f"Failed to get last commit diff: {e}")
        return None


def get_git_diff(max_chars: int = 50000, fallback_to_last_commit: bool = True) -> str | None:
    """Get changes from git for validation.

    First checks for uncommitted changes (staged + unstaged).
    If none found and fallback_to_last_commit is True, returns the last commit's diff.

    Args:
        max_chars: Maximum characters to return (truncates if larger)
        fallback_to_last_commit: If True, fall back to last commit diff when no uncommitted changes

    Returns:
        Combined diff string, or None if not in git repo or no changes
    """
    try:
        # Get unstaged changes
        unstaged = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Get staged changes
        staged = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if unstaged.returncode != 0 and staged.returncode != 0:
            return None

        diff_parts = []
        if staged.stdout.strip():
            diff_parts.append("=== STAGED CHANGES ===\n" + staged.stdout)
        if unstaged.stdout.strip():
            diff_parts.append("=== UNSTAGED CHANGES ===\n" + unstaged.stdout)

        # If no uncommitted changes, try last commit
        if not diff_parts and fallback_to_last_commit:
            last_commit_diff = get_last_commit_diff(max_chars)
            if last_commit_diff:
                return f"=== LAST COMMIT ===\n{last_commit_diff}"
            return None

        if not diff_parts:
            return None

        combined = "\n".join(diff_parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n\n... [diff truncated] ..."

        return combined

    except Exception as e:
        logger.debug(f"Failed to get git diff: {e}")
        return None


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
        description: str | None,
        changes_summary: str,
        validation_criteria: str | None = None,
        context_files: list[str] | None = None,
    ) -> ValidationResult:
        """
        Validate task completion.

        Args:
            task_id: Task ID
            title: Task title
            description: Task description (used as fallback if no validation_criteria)
            changes_summary: Summary of changes made (files, diffs, etc.)
            validation_criteria: Specific criteria to validate against (optional)
            context_files: List of files to read for context (optional)

        Returns:
            ValidationResult with status and feedback
        """
        if not self.config.enabled:
            return ValidationResult(status="pending", feedback="Validation disabled")

        if not description and not validation_criteria:
            logger.warning(f"Cannot validate task {task_id}: missing description and criteria")
            return ValidationResult(
                status="pending", feedback="Missing task description and validation criteria"
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
            else f"Task Description:\n{description}"
        )

        # Detect if changes_summary is a git diff
        is_git_diff = changes_summary.startswith("Git diff") or "@@" in changes_summary

        if is_git_diff:
            changes_section = (
                "Code Changes (git diff):\n"
                "Analyze these ACTUAL code changes to verify the implementation.\n\n"
                f"{changes_summary}\n\n"
            )
        else:
            changes_section = f"Changes Summary:\n{changes_summary}\n\n"

        base_prompt = (
            "Validate if the following changes satisfy the requirements.\n\n"
            f"Task: {title}\n"
            f"{criteria_text}\n\n"
            f"{changes_section}"
            "IMPORTANT: Return ONLY a JSON object, nothing else. No explanation, no preamble.\n"
            'Format: {"status": "valid", "feedback": "..."} or {"status": "invalid", "feedback": "..."}\n'
        )

        if file_context:
            # Truncate file context to 50k chars to avoid exceeding LLM context limits
            base_prompt += f"File Context:\n{file_context[:50000]}\n"

        prompt = self.config.prompt or base_prompt

        try:
            provider = self.llm_service.get_provider(self.config.provider)
            response_content = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.config.system_prompt,
                model=self.config.model,
            )

            import json
            import re

            if not response_content or not response_content.strip():
                logger.warning(f"Empty LLM response for task {task_id} validation")
                return ValidationResult(
                    status="pending", feedback="Validation failed: Empty response from LLM"
                )

            content = response_content.strip()
            logger.debug(f"Validation LLM response for {task_id}: {content[:200]}...")

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
            prompt = f"""Generate validation criteria for the following task.

Task: {title}
Description: {description or "(no description)"}

Requirements for good criteria:
1. **Objectively verifiable** - Can be checked with a yes/no answer
2. **Specific** - Include concrete values, file paths, or behaviors (no vague terms like "appropriate" or "reasonable")
3. **Actionable** - Each criterion maps to something that can be tested or inspected
4. **Complete** - Cover the full scope of the task including edge cases and error handling
5. **Structured** - Use markdown checkboxes for easy tracking

Format your response as:
# <Task Title Summary>

## Deliverable
- [ ] Primary output (file, class, function, etc.)

## Functional Requirements
- [ ] Specific behavior 1
- [ ] Specific behavior 2

## Edge Cases / Error Handling
- [ ] How errors are handled
- [ ] Boundary conditions

## Verification
- [ ] How to verify completion (tests pass, command works, etc.)

Use concrete examples: "timeout defaults to 30 seconds" not "timeout has a reasonable default".
"""

        try:
            provider = self.llm_service.get_provider(self.config.provider)
            response = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.config.criteria_system_prompt,
                model=self.config.model,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate validation criteria: {e}")
            return None
