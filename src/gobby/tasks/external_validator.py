"""External validator for objective task validation.

Provides a separate validation path using either:
1. A fresh LLM context (direct API calls) - mode: "llm"
2. A spawned agent instance with tools - mode: "agent"

Both modes ensure the validator has no prior knowledge of the implementation.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from gobby.config.app import TaskValidationConfig
from gobby.llm import LLMService
from gobby.tasks.issue_extraction import parse_issues_from_response
from gobby.tasks.validation_models import Issue
from gobby.utils.json_helpers import extract_json_object

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner

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
    agent_runner: "AgentRunner | None" = None,
) -> ExternalValidationResult:
    """Run external validation with a fresh LLM context or agent.

    Creates a completely fresh validation context without any prior conversation,
    ensuring the validator is objective and has no knowledge of the implementation
    process.

    Two modes are supported:
    - "llm": Direct LLM API calls (default, backwards compatible)
    - "agent": Spawns a full agent instance with tools for validation

    Args:
        config: Validation configuration
        llm_service: LLM service for making requests (used in llm mode)
        task: Task dictionary with id, title, description, validation_criteria
        changes_context: Code changes to validate (typically a git diff)
        force_external: If True, run external validation even if config.use_external_validator is False
        agent_runner: Agent runner for spawning validation agent (required for agent mode)

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

    # Dispatch based on mode
    mode = getattr(config, "external_validator_mode", "llm")

    if mode == "agent":
        return await _run_agent_validation(
            config=config,
            task=task,
            changes_context=changes_context,
            agent_runner=agent_runner,
        )
    else:
        return await _run_llm_validation(
            config=config,
            llm_service=llm_service,
            task=task,
            changes_context=changes_context,
        )


async def _run_llm_validation(
    config: TaskValidationConfig,
    llm_service: LLMService,
    task: dict[str, Any],
    changes_context: str,
) -> ExternalValidationResult:
    """Run validation using direct LLM API calls.

    Args:
        config: Validation configuration
        llm_service: LLM service for making requests
        task: Task dictionary
        changes_context: Code changes to validate

    Returns:
        ExternalValidationResult
    """
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


async def _run_agent_validation(
    config: TaskValidationConfig,
    task: dict[str, Any],
    changes_context: str,
    agent_runner: "AgentRunner | None" = None,
) -> ExternalValidationResult:
    """Run validation by spawning an agent instance.

    Spawns a headless agent that can use tools to validate the implementation.
    This provides more thorough validation as the agent can read files,
    run commands, etc.

    Args:
        config: Validation configuration
        task: Task dictionary
        changes_context: Code changes to validate
        agent_runner: Agent runner for spawning agents

    Returns:
        ExternalValidationResult
    """
    if not agent_runner:
        logger.warning("Agent validation requested but no agent runner available")
        return ExternalValidationResult(
            status="error",
            summary="Agent validation not available (no agent runner)",
            issues=[],
            error="Agent runner required for agent mode",
        )

    try:
        from gobby.agents.runner import AgentConfig

        # Build prompt for validation agent
        prompt = _build_agent_validation_prompt(task, changes_context)

        # Create agent config for in-process execution
        agent_config = AgentConfig(
            prompt=prompt,
            mode="in_process",  # Run in-process for direct result access
            max_turns=20,
            timeout=120.0,
            source="external_validator",
            model=config.external_validator_model or config.model,
            provider=config.provider,
        )

        # Run the agent directly
        result = await agent_runner.run(agent_config)

        # Parse the agent's output
        if result.status == "error":
            return ExternalValidationResult(
                status="error",
                summary=f"Validation agent failed: {result.error or 'Unknown error'}",
                issues=[],
                error=result.error,
            )

        # Parse the agent's response for validation verdict
        return _parse_external_validation_response(result.output or "")

    except Exception as e:
        logger.error(f"Agent validation failed: {e}")
        return ExternalValidationResult(
            status="error",
            summary=f"Agent validation failed: {str(e)}",
            issues=[],
            error=str(e),
        )


def _build_agent_validation_prompt(
    task: dict[str, Any],
    changes_context: str,
) -> str:
    """Build the validation prompt for agent mode.

    The agent prompt is more comprehensive as the agent can use tools.

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

    prompt = f"""You are an objective QA validator. You have NO prior context about this task.

## Your Role
Validate whether the code changes satisfy the acceptance criteria. You have access to tools to:
- Read files to verify implementation details
- Run tests if needed
- Check for common issues

## Task Being Validated
Title: {task_title}

{criteria_section}

## Code Changes to Validate
{changes_context}

## Instructions
1. Review the changes against the acceptance criteria
2. Use tools if needed to verify specific requirements
3. Check for correctness, completeness, and potential issues
4. Be objective and thorough

## Required Output
After your analysis, provide your verdict as a JSON object:

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

Begin your validation now.
"""

    return prompt


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

    # Extract JSON from response using shared utility
    data = extract_json_object(response)
    if data is None:
        logger.warning("Failed to parse external validation response")
        return ExternalValidationResult(
            status="error",
            summary="Failed to parse validator response",
            issues=[],
            error="No valid JSON found in response",
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
