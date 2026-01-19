"""
Approval flow handling for workflow engine.

Extracted from engine.py to reduce complexity.
Handles user approval requests and responses for workflow gates.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookResponse

from .evaluator import check_approval_response

if TYPE_CHECKING:
    from .definitions import WorkflowState
    from .evaluator import ConditionEvaluator
    from .state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


def handle_approval_response(
    event: HookEvent,
    state: "WorkflowState",
    current_step: Any,
    evaluator: "ConditionEvaluator",
    state_manager: "WorkflowStateManager",
) -> HookResponse | None:
    """
    Handle user response to approval request.

    Called on BEFORE_AGENT events to check if user is responding to
    a pending approval request.

    Args:
        event: The hook event
        state: Current workflow state
        current_step: Current workflow step definition
        evaluator: Condition evaluator for checking pending approvals
        state_manager: State manager for persisting state changes

    Returns:
        HookResponse if approval was handled, None otherwise.
    """
    # Get user prompt from event
    prompt = event.data.get("prompt", "") if event.data else ""

    # Check if we're waiting for approval
    if state.approval_pending:
        response = check_approval_response(prompt)

        if response == "approved":
            # Mark approval granted
            condition_id = state.approval_condition_id
            approved_var = f"_approval_{condition_id}_granted"
            state.variables[approved_var] = True
            state.approval_pending = False
            state.approval_condition_id = None
            state.approval_prompt = None
            state.approval_requested_at = None
            state_manager.save_state(state)

            logger.info(f"User approved condition '{condition_id}' in step '{state.step}'")
            return HookResponse(
                decision="allow",
                context=f"✓ Approval granted for: {state.approval_prompt or 'action'}",
            )

        elif response == "rejected":
            # Mark approval rejected
            condition_id = state.approval_condition_id
            rejected_var = f"_approval_{condition_id}_rejected"
            state.variables[rejected_var] = True
            state.approval_pending = False
            state.approval_condition_id = None
            state.approval_prompt = None
            state.approval_requested_at = None
            state_manager.save_state(state)

            logger.info(f"User rejected condition '{condition_id}' in step '{state.step}'")
            return HookResponse(
                decision="block",
                reason="User rejected the approval request.",
            )

        else:
            # User didn't respond with approval keyword - remind them
            return HookResponse(
                decision="allow",
                context=(
                    f"⏳ **Waiting for approval:** {state.approval_prompt}\n\n"
                    f"Please respond with 'yes' or 'no' to continue."
                ),
            )

    # Check if we need to request approval
    approval_check = evaluator.check_pending_approval(current_step.exit_conditions, state)

    if approval_check and approval_check.needs_approval:
        # Set approval pending state
        state.approval_pending = True
        state.approval_condition_id = approval_check.condition_id
        state.approval_prompt = approval_check.prompt
        state.approval_requested_at = datetime.now(UTC)
        state.approval_timeout_seconds = approval_check.timeout_seconds
        state_manager.save_state(state)

        logger.info(
            f"Requesting approval for condition '{approval_check.condition_id}' "
            f"in step '{state.step}'"
        )
        return HookResponse(
            decision="allow",
            context=(
                f"🔔 **Approval Required**\n\n"
                f"{approval_check.prompt}\n\n"
                f"Please respond with 'yes' to approve or 'no' to reject."
            ),
        )

    if approval_check and approval_check.is_timed_out:
        # Timeout - treat as rejection
        condition_id = approval_check.condition_id
        rejected_var = f"_approval_{condition_id}_rejected"
        state.variables[rejected_var] = True
        state.approval_pending = False
        state.approval_condition_id = None
        state_manager.save_state(state)

        logger.info(f"Approval timed out for condition '{condition_id}'")
        return HookResponse(
            decision="block",
            reason=f"Approval request timed out after {approval_check.timeout_seconds} seconds.",
        )

    return None
