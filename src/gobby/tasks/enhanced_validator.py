"""Enhanced task validator with retry and escalation logic.

Provides the core validation loop for Task System V2.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

from gobby.tasks.validation_models import Issue

if TYPE_CHECKING:
    from gobby.tasks.validation_history import ValidationHistoryManager

logger = logging.getLogger(__name__)


class EscalationReason(Enum):
    """Reasons for escalating a validation failure."""

    MAX_ITERATIONS = "max_iterations"
    CONSECUTIVE_ERRORS = "consecutive_errors"
    RECURRING_ISSUES = "recurring_issues"


@dataclass
class ValidationResult:
    """Result of a validation attempt.

    Attributes:
        valid: Whether the task passed validation.
        iterations: Number of validation iterations performed.
        feedback: Human-readable feedback from the validator.
        escalated: Whether the validation was escalated.
        escalation_reason: Reason for escalation if escalated.
        issues: List of issues found during validation.
    """

    valid: bool
    iterations: int
    feedback: str
    escalated: bool = False
    escalation_reason: EscalationReason | None = None
    issues: list[Issue] = field(default_factory=list)


class LLMValidator(Protocol):
    """Protocol for LLM-based validators."""

    async def validate(
        self,
        task: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate a task.

        Args:
            task: The task to validate.
            context: Optional context for validation.

        Returns:
            Dictionary with keys:
                - valid: bool
                - feedback: str
                - issues: list[dict]
        """
        ...


class TaskManager(Protocol):
    """Protocol for task managers."""

    def get_task(self, task_id: str) -> Any:
        """Get a task by ID."""
        ...


class EnhancedTaskValidator:
    """Enhanced task validator with retry and escalation logic.

    Implements a validation loop that:
    - Retries validation up to max_iterations
    - Tracks validation history
    - Detects recurring issues
    - Escalates when thresholds are exceeded
    """

    def __init__(
        self,
        task_manager: TaskManager,
        history_manager: "ValidationHistoryManager",
        llm_validator: LLMValidator,
        max_iterations: int = 3,
        error_threshold: int = 2,
    ):
        """Initialize EnhancedTaskValidator.

        Args:
            task_manager: Manager for task CRUD operations.
            history_manager: Manager for validation history.
            llm_validator: LLM-based validator for task validation.
            max_iterations: Maximum validation attempts before escalation.
            error_threshold: Consecutive errors before escalation.
        """
        self.task_manager = task_manager
        self.history_manager = history_manager
        self.llm_validator = llm_validator
        self.max_iterations = max_iterations
        self.error_threshold = error_threshold

    async def validate_with_retry(
        self,
        task_id: str,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate a task with retry logic.

        Attempts validation up to max_iterations times. Escalates if:
        - max_iterations is exceeded
        - Consecutive errors exceed error_threshold
        - Recurring issues are detected

        Args:
            task_id: ID of the task to validate.
            context: Optional context for validation (e.g., git diff).

        Returns:
            ValidationResult with validation status and details.
        """
        task = self.task_manager.get_task(task_id)
        consecutive_errors = 0
        last_feedback = ""
        last_issues: list[Issue] = []

        for iteration in range(1, self.max_iterations + 1):
            try:
                # Attempt validation
                result = await self.llm_validator.validate(task, context=context)

                valid = result.get("valid", False)
                feedback = result.get("feedback", "")
                issues_data = result.get("issues", [])

                # Parse issues
                issues = []
                for issue_dict in issues_data:
                    if isinstance(issue_dict, dict):
                        issues.append(Issue.from_dict(issue_dict))
                    elif isinstance(issue_dict, Issue):
                        issues.append(issue_dict)

                last_feedback = feedback
                last_issues = issues

                # Record this iteration
                status = "valid" if valid else "invalid"
                self.history_manager.record_iteration(
                    task_id=task_id,
                    iteration=iteration,
                    status=status,
                    feedback=feedback,
                    issues=issues if issues else None,
                )

                # Reset consecutive errors on success
                consecutive_errors = 0

                if valid:
                    # Validation passed
                    return ValidationResult(
                        valid=True,
                        iterations=iteration,
                        feedback=feedback,
                        issues=issues,
                    )

                # Check for recurring issues after recording
                if self.history_manager.has_recurring_issues(task_id):
                    logger.info(f"Recurring issues detected for task {task_id}, escalating")
                    return ValidationResult(
                        valid=False,
                        iterations=iteration,
                        feedback=feedback,
                        escalated=True,
                        escalation_reason=EscalationReason.RECURRING_ISSUES,
                        issues=issues,
                    )

            except Exception as e:
                logger.warning(f"Validation error on iteration {iteration}: {e}")
                consecutive_errors += 1

                # Record error iteration
                self.history_manager.record_iteration(
                    task_id=task_id,
                    iteration=iteration,
                    status="error",
                    feedback=str(e),
                )

                if consecutive_errors >= self.error_threshold:
                    logger.info(
                        f"Consecutive error threshold reached for task {task_id}, "
                        f"escalating after {consecutive_errors} errors"
                    )
                    return ValidationResult(
                        valid=False,
                        iterations=iteration,
                        feedback=f"Validation failed with {consecutive_errors} consecutive errors",
                        escalated=True,
                        escalation_reason=EscalationReason.CONSECUTIVE_ERRORS,
                    )

        # Max iterations exceeded
        logger.info(
            f"Max iterations ({self.max_iterations}) exceeded for task {task_id}, escalating"
        )
        return ValidationResult(
            valid=False,
            iterations=self.max_iterations,
            feedback=last_feedback,
            escalated=True,
            escalation_reason=EscalationReason.MAX_ITERATIONS,
            issues=last_issues,
        )
