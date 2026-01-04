"""External validator for objective task validation.

Provides a separate validation path using a fresh LLM context,
ensuring the validator has no prior knowledge of the implementation.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from gobby.config.app import TaskValidationConfig
from gobby.llm import LLMService
from gobby.tasks.issue_extraction import parse_issues_from_response
from gobby.tasks.validation_models import Issue

logger = logging.getLogger(__name__)


@dataclass
class ExternalValidationResult:
    """Result from external validation.

    Attributes:
        status: Validation status - "valid", "invalid", "error", or "pending"
        summary: Human-readable summary of validation result
        issues: List of structured issues found
        error: Error message if status is "error"
    """

    status: str
    summary: str
    issues: list[Issue] = field(default_factory=list)
    error: str | None = None


async def run_external_validation(
    config: TaskValidationConfig,
    llm_service: LLMService,
    task: dict[str, Any],
    changes_context: str,
    force_external: bool = False,
) -> ExternalValidationResult:
    """Run external validation with a fresh LLM context.

    Creates a completely fresh prompt without any prior conversation context,
    ensuring the validator is objective and has no knowledge of the implementation
    process.

    Args:
        config: Validation configuration
        llm_service: LLM service for making requests
        task: Task dictionary with id, title, description, validation_criteria
        changes_context: Code changes to validate (typically a git diff)
        force_external: If True, run external validation even if config.use_external_validator is False

    Returns:
        ExternalValidationResult with status, summary, and any issues found
    """
    # Check if external validation should be skipped
    if not force_external and not config.use_external_validator:
        return ExternalValidationResult(
            status="skipped",
            summary="External validation skipped (disabled in config)",
            issues=[],
        )

    # Determine which model to use
    model = config.external_validator_model or config.model

    # Build the validation prompt
    prompt = _build_external_validation_prompt(task, changes_context)

    # System prompt emphasizing objectivity
    system_prompt = (
        "You are an objective QA validator reviewing code changes. "
        "You have no prior context about this task - evaluate purely based on "
        "the acceptance criteria and the changes provided. "
        "Be thorough but fair in your assessment."
    )

    try:
        provider = llm_service.get_provider(config.provider)
        response = await provider.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
        )

        return _parse_external_validation_response(response)

    except Exception as e:
        logger.error(f"External validation failed: {e}")
        return ExternalValidationResult(
            status="error",
            summary=f"External validation failed: {str(e)}",
            issues=[],
            error=str(e),
        )


def _build_external_validation_prompt(
    task: dict[str, Any],
    changes_context: str,
) -> str:
    """Build the external validation prompt.

    Args:
        task: Task dictionary
        changes_context: Code changes to validate

    Returns:
        Formatted prompt string
    """
    task_title = task.get("title", "Unknown Task")
    task_description = task.get("description", "")
    validation_criteria = task.get("validation_criteria", "")

    # Build criteria section
    if validation_criteria:
        criteria_section = f"Acceptance Criteria:\n{validation_criteria}"
    elif task_description:
        criteria_section = f"Task Description:\n{task_description}"
    else:
        criteria_section = "No specific criteria provided. Evaluate for general correctness."

    prompt = f"""You are reviewing code changes for the following task.

## Task
Title: {task_title}

{criteria_section}

## Code Changes to Validate
{changes_context}

## Instructions
1. Review each change against the acceptance criteria
2. Check for correctness, completeness, and potential issues
3. Be objective - you have no prior context about this implementation

## Output Format
Return your assessment as a JSON object:

```json
{{
  "status": "valid" | "invalid",
  "summary": "Brief assessment of the changes",
  "issues": [
    {{
      "type": "acceptance_gap|test_failure|lint_error|type_error|security",
      "severity": "blocker|major|minor",
      "title": "Brief description",
      "location": "file:line (if applicable)",
      "details": "Full explanation",
      "suggested_fix": "How to resolve (if applicable)"
    }}
  ]
}}
```

If all criteria are met, return status "valid" with an empty issues array.
If there are problems, return status "invalid" with detailed issues.
"""

    return prompt


def _parse_external_validation_response(response: str) -> ExternalValidationResult:
    """Parse the external validation response.

    Args:
        response: Raw LLM response

    Returns:
        ExternalValidationResult
    """
    if not response or not response.strip():
        return ExternalValidationResult(
            status="error",
            summary="Empty response from validator",
            issues=[],
            error="Empty response",
        )

    # Try to extract JSON from response
    content = response.strip()

    # Try code block first
    json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if json_block:
        json_str = json_block.group(1)
    else:
        # Try to find raw JSON object
        json_obj = re.search(r"(\{.*\})", content, re.DOTALL)
        if json_obj:
            json_str = json_obj.group(1)
        else:
            json_str = content

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse external validation response: {e}")
        return ExternalValidationResult(
            status="error",
            summary="Failed to parse validator response",
            issues=[],
            error=f"JSON parse error: {e}",
        )

    # Extract fields
    status = data.get("status", "pending")
    summary = data.get("summary", "")

    # Parse issues using the issue extraction module
    # Reconstruct the response with issues for parsing
    issues_response = json.dumps({"issues": data.get("issues", [])})
    issues = parse_issues_from_response(issues_response)

    return ExternalValidationResult(
        status=status,
        summary=summary,
        issues=issues,
    )
