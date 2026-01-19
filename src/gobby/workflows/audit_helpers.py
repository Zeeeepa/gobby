"""
Audit logging helper functions for workflow engine.

Extracted from engine.py to reduce complexity.
These are pure logging functions with no side effects beyond audit.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.workflow_audit import WorkflowAuditManager

logger = logging.getLogger(__name__)


def log_tool_call(
    audit_manager: "WorkflowAuditManager | None",
    session_id: str,
    step: str,
    tool_name: str,
    result: str,
    reason: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Log a tool call permission check to the audit log."""
    if audit_manager:
        try:
            audit_manager.log_tool_call(
                session_id=session_id,
                step=step,
                tool_name=tool_name,
                result=result,
                reason=reason,
                context=context,
            )
        except Exception as e:
            logger.debug(f"Failed to log tool call audit: {e}")


def log_rule_eval(
    audit_manager: "WorkflowAuditManager | None",
    session_id: str,
    step: str,
    rule_id: str,
    condition: str,
    result: str,
    reason: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Log a rule evaluation to the audit log."""
    if audit_manager:
        try:
            audit_manager.log_rule_eval(
                session_id=session_id,
                step=step,
                rule_id=rule_id,
                condition=condition,
                result=result,
                reason=reason,
                context=context,
            )
        except Exception as e:
            logger.debug(f"Failed to log rule eval audit: {e}")


def log_transition(
    audit_manager: "WorkflowAuditManager | None",
    session_id: str,
    from_step: str,
    to_step: str,
    reason: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Log a step transition to the audit log."""
    if audit_manager:
        try:
            audit_manager.log_transition(
                session_id=session_id,
                from_step=from_step,
                to_step=to_step,
                reason=reason,
                context=context,
            )
        except Exception as e:
            logger.debug(f"Failed to log transition audit: {e}")


def log_approval(
    audit_manager: "WorkflowAuditManager | None",
    session_id: str,
    step: str,
    result: str,
    condition_id: str | None = None,
    prompt: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Log an approval gate event to the audit log."""
    if audit_manager:
        try:
            audit_manager.log_approval(
                session_id=session_id,
                step=step,
                result=result,
                condition_id=condition_id,
                prompt=prompt,
                context=context,
            )
        except Exception as e:
            logger.debug(f"Failed to log approval audit: {e}")
