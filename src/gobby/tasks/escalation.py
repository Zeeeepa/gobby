"""Task escalation management for Task System V2.

Provides escalation and de-escalation functionality for tasks.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from gobby.tasks.enhanced_validator import EscalationReason

if TYPE_CHECKING:
    from gobby.tasks.validation_history import ValidationHistoryManager

logger = logging.getLogger(__name__)


class TaskManager(Protocol):
    """Protocol for task managers."""

    def get_task(self, task_id: str) -> Any:
        """Get a task by ID."""
        ...

    def update_task(self, task_id: str, **kwargs: Any) -> Any:
        """Update a task."""
        ...


class WebhookClient(Protocol):
    """Protocol for webhook clients."""

    async def send_escalation(
        self,
        task_id: str,
        reason: str,
        summary: "EscalationSummary",
    ) -> bool:
        """Send escalation notification via webhook."""
        ...


@dataclass
class EscalationSummary:
    """Summary of an escalated task.

    Attributes:
        title: Task title.
        reason: Escalation reason.
        total_iterations: Number of validation iterations.
        recurring_issues: List of recurring issue summaries.
        feedback: Optional feedback message.
    """

    title: str
    reason: str
    total_iterations: int = 0
    recurring_issues: list[dict[str, Any]] = field(default_factory=list)
    feedback: str | None = None

    def to_markdown(self) -> str:
        """Render summary as markdown.

        Returns:
            Markdown-formatted escalation summary.
        """
        lines = [
            "# Escalation Summary",
            "",
            f"**Task:** {self.title}",
            f"**Reason:** {self.reason}",
            f"**Iterations:** {self.total_iterations}",
            "",
        ]

        if self.feedback:
            lines.extend(
                [
                    "## Feedback",
                    "",
                    self.feedback,
                    "",
                ]
            )

        if self.recurring_issues:
            lines.extend(
                [
                    "## Recurring Issues",
                    "",
                ]
            )
            for issue in self.recurring_issues:
                lines.append(
                    f"- **{issue.get('title', 'Unknown')}** (seen {issue.get('count', 0)} times)"
                )
            lines.append("")

        return "\n".join(lines)


@dataclass
class EscalationResult:
    """Result of an escalation operation.

    Attributes:
        task_id: ID of the escalated task.
        reason: Escalation reason.
        feedback: Optional feedback message.
        escalated_at: Timestamp of escalation.
    """

    task_id: str
    reason: str
    feedback: str | None = None
    escalated_at: str | None = None


class EscalationManager:
    """Manages task escalation and de-escalation.

    Handles:
    - Escalating tasks that exceed validation thresholds
    - De-escalating tasks back to open status
    - Generating escalation summaries
    - Sending webhook notifications
    """

    def __init__(
        self,
        task_manager: TaskManager,
        history_manager: "ValidationHistoryManager",
        webhook_client: WebhookClient | None = None,
    ):
        """Initialize EscalationManager.

        Args:
            task_manager: Manager for task CRUD operations.
            history_manager: Manager for validation history.
            webhook_client: Optional webhook client for notifications.
        """
        self.task_manager = task_manager
        self.history_manager = history_manager
        self.webhook_client = webhook_client

    def escalate(
        self,
        task_id: str,
        reason: EscalationReason,
        feedback: str | None = None,
    ) -> EscalationResult:
        """Escalate a task.

        Sets task status to 'escalated' and records the reason and timestamp.

        Args:
            task_id: ID of the task to escalate.
            reason: Reason for escalation.
            feedback: Optional feedback message.

        Returns:
            EscalationResult with escalation details.
        """
        escalated_at = datetime.now(UTC).isoformat()

        self.task_manager.update_task(
            task_id,
            status="escalated",
            escalated_at=escalated_at,
            escalation_reason=reason.value,
        )

        logger.info(f"Escalated task {task_id}: {reason.value}")

        return EscalationResult(
            task_id=task_id,
            reason=reason.value,
            feedback=feedback,
            escalated_at=escalated_at,
        )

    async def escalate_async(
        self,
        task_id: str,
        reason: EscalationReason,
        feedback: str | None = None,
    ) -> EscalationResult:
        """Escalate a task with async webhook notification.

        Sets task status to 'escalated' and sends webhook if configured.

        Args:
            task_id: ID of the task to escalate.
            reason: Reason for escalation.
            feedback: Optional feedback message.

        Returns:
            EscalationResult with escalation details.
        """
        result = self.escalate(task_id, reason, feedback)

        # Send webhook notification if configured
        if self.webhook_client:
            try:
                summary = self.generate_escalation_summary(task_id)
                await self.webhook_client.send_escalation(
                    task_id=task_id,
                    reason=reason.value,
                    summary=summary,
                )
                logger.debug(f"Sent escalation webhook for task {task_id}")
            except Exception as e:
                logger.warning(f"Failed to send escalation webhook: {e}")
                # Don't fail the escalation if webhook fails

        return result

    def de_escalate(self, task_id: str) -> None:
        """De-escalate a task back to open status.

        Clears escalation fields and returns task to open status.

        Args:
            task_id: ID of the task to de-escalate.

        Raises:
            ValueError: If task is not escalated.
        """
        task = self.task_manager.get_task(task_id)

        if task.status != "escalated":
            raise ValueError(f"Task {task_id} is not escalated (status: {task.status})")

        self.task_manager.update_task(
            task_id,
            status="open",
            escalated_at=None,
            escalation_reason=None,
        )

        logger.info(f"De-escalated task {task_id}")

    def generate_escalation_summary(self, task_id: str) -> EscalationSummary:
        """Generate a summary of an escalated task.

        Args:
            task_id: ID of the task to summarize.

        Returns:
            EscalationSummary with task and issue details.
        """
        task = self.task_manager.get_task(task_id)

        # Get recurring issue summary from history
        issue_summary = self.history_manager.get_recurring_issue_summary(task_id)

        return EscalationSummary(
            title=task.title,
            reason=task.escalation_reason or "unknown",
            total_iterations=issue_summary.get("total_iterations", 0),
            recurring_issues=issue_summary.get("recurring_issues", []),
        )
