import asyncio
import concurrent.futures
import logging
import threading
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from .engine import WorkflowEngine
    from .rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class WorkflowHookHandler:
    """
    Integrates WorkflowEngine into the HookManager.
    Wraps the async engine to be callable from synchronous hooks.

    Supports dual evaluation: RuleEngine (new) runs first, then legacy
    lifecycle workflows. Rule blocks short-circuit legacy evaluation.
    """

    def __init__(
        self,
        engine: "WorkflowEngine",
        loop: asyncio.AbstractEventLoop | None = None,
        timeout: float = 30.0,  # Timeout for workflow operations in seconds
        enabled: bool = True,
        rule_engine: "RuleEngine | None" = None,
    ):
        self.engine = engine
        self.rule_engine = rule_engine
        self._loop = loop
        # Convert 0 to None for asyncio (0 means no timeout)
        self.timeout = timeout if timeout > 0 else None
        self._enabled = enabled

        # If no loop provided, try to get one or create one for this thread
        if not self._loop:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def _handle_cancelled(self, event: HookEvent) -> HookResponse:
        """Handle CancelledError by logging and returning appropriate response."""
        logger.warning("Workflow evaluation cancelled for %s", event.event_type)
        if event.event_type == HookEventType.STOP:
            return HookResponse(
                decision="block",
                reason="Workflow evaluation was cancelled; blocking stop for safety.",
            )
        return HookResponse(decision="allow")

    async def _dual_evaluate(self, event: HookEvent) -> HookResponse:
        """Run RuleEngine first, then legacy lifecycle evaluation.

        If the rule engine blocks/denies, short-circuit (skip legacy).
        Otherwise, run legacy and merge results. Logs disagreements.
        """
        # Step 1: Evaluate rules (if rule engine is available)
        rule_response: HookResponse | None = None
        if self.rule_engine is not None:
            try:
                session_id = (
                    event.metadata.get("_platform_session_id") or event.session_id or ""
                )
                rule_response = await self.rule_engine.evaluate(
                    event=event,
                    session_id=session_id,
                    variables={},
                )
            except Exception as e:
                logger.error(f"RuleEngine evaluation failed: {e}", exc_info=True)
                rule_response = None

        # Step 2: If rules block/deny, short-circuit
        if rule_response and rule_response.decision in ("block", "deny"):
            return rule_response

        # Step 3: Run legacy lifecycle evaluation
        legacy_response = await self.engine.evaluate_all_lifecycle_workflows(event)

        # Step 4: If no rule engine or rules had no opinion, return legacy as-is
        if rule_response is None:
            return legacy_response

        # Step 5: Merge rule + legacy responses
        return self._merge_responses(rule_response, legacy_response, event)

    def _merge_responses(
        self,
        rule_response: HookResponse,
        legacy_response: HookResponse,
        event: HookEvent,
    ) -> HookResponse:
        """Merge rule engine and legacy responses.

        - Context accumulates (rule first, then legacy)
        - First non-allow decision wins (legacy, since rules already allowed)
        - Metadata merges (rule mcp_calls + legacy metadata)
        - Disagreements are logged
        """
        # Merge context
        context_parts: list[str] = []
        if rule_response.context:
            context_parts.append(rule_response.context)
        if legacy_response.context:
            context_parts.append(legacy_response.context)
        merged_context = "\n\n".join(context_parts) if context_parts else None

        # Decision: legacy wins (rules already returned allow)
        decision = legacy_response.decision
        reason = legacy_response.reason

        # Log disagreement: legacy blocks but rules allowed
        if legacy_response.decision in ("block", "deny") and rule_response.decision == "allow":
            logger.warning(
                "Rule/legacy disagreement on %s: rules allowed but legacy returned %s "
                "(reason: %s). Consider adding a rule to cover this case.",
                event.event_type.name,
                legacy_response.decision,
                legacy_response.reason,
            )

        # Merge metadata (rule mcp_calls + legacy metadata)
        merged_metadata = {**legacy_response.metadata}
        if rule_response.metadata.get("mcp_calls"):
            merged_metadata["mcp_calls"] = rule_response.metadata["mcp_calls"]

        return HookResponse(
            decision=decision,
            reason=reason,
            context=merged_context,
            system_message=legacy_response.system_message,
            metadata=merged_metadata,
        )

    def evaluate(self, event: HookEvent) -> HookResponse:
        """Evaluate rules and lifecycle workflows for a hook event.

        Runs RuleEngine first (if available), then legacy lifecycle workflows.
        Rule blocks short-circuit legacy evaluation. This is the primary
        entry point for workflow evaluation.

        Args:
            event: The hook event to handle

        Returns:
            Merged HookResponse from rule engine and legacy workflows
        """
        if not self._enabled:
            return HookResponse(decision="allow")

        try:
            if self._loop and self._loop.is_running():
                if threading.current_thread() is threading.main_thread():
                    return HookResponse(decision="allow")
                else:
                    future = asyncio.run_coroutine_threadsafe(
                        self._dual_evaluate(event),
                        self._loop,
                    )
                    return future.result(timeout=self.timeout)

            try:
                asyncio.get_running_loop()
                # If we get here, a loop is running
                logger.warning("Could not run workflow engine: Event loop is already running.")
                return HookResponse(decision="allow")
            except RuntimeError:
                # No loop running, safe to use asyncio.run
                return asyncio.run(self._dual_evaluate(event))

        except concurrent.futures.CancelledError:
            return self._handle_cancelled(event)
        except Exception as e:
            logger.error(f"Error handling all lifecycle workflows: {e}", exc_info=True)
            return HookResponse(decision="allow")

    # Backward-compatible alias
    handle_all_lifecycles = evaluate

    def handle(self, event: HookEvent) -> HookResponse:
        """
        Handle a hook event by delegating to the workflow engine.
        Handles the sync/async bridge.
        """
        if not self._enabled:
            return HookResponse(decision="allow")

        try:
            # We need to run the async self.engine.handle_event(event) synchronously

            # Case 1: We have a captured loop (main loop) and we are likely in a thread
            # This is the common case for FastAPI sync endpoints
            if self._loop and self._loop.is_running():
                if threading.current_thread() is threading.main_thread():
                    # We are on the main thread and the loop is running.
                    # We cannot block here without deadlock if we use run_until_complete.
                    # But HookManager.handle is synchronous, so this is a tricky spot.
                    # Ideally, HookManager should await, but it's not async.
                    # For now, we return allow and log a warning if we can't run.
                    # OR we create a task and return allow (fire and forget), but we need the result.

                    # Actually, if we are here, we are blocking the event loop!
                    # This implementation assumes HookManager.handle is run in a threadpool (def handle vs async def handle).
                    # Pydantic/FastAPI runs sync def routes in threadpool.
                    pass
                else:
                    # We are in a thread, loop is in another thread.
                    # Safe to block this thread waiting for loop.
                    future = asyncio.run_coroutine_threadsafe(
                        self.engine.handle_event(event), self._loop
                    )
                    return future.result(timeout=self.timeout)

            # Case 2: No loop running, or we just want to run it.
            # Create a new loop or use asyncio.run if appropriate
            try:
                asyncio.get_running_loop()
                # If we get here, a loop is running
                logger.warning(
                    "Could not run workflow engine: Event loop is already running and we are blocking it."
                )
                return HookResponse(decision="allow")
            except RuntimeError:
                # No loop running, safe to use asyncio.run
                return asyncio.run(self.engine.handle_event(event))

        except concurrent.futures.CancelledError:
            return self._handle_cancelled(event)
        except Exception as e:
            logger.error(f"Error handling workflow hook: {e}", exc_info=True)
            return HookResponse(decision="allow")

    def handle_lifecycle(
        self, workflow_name: str, event: HookEvent, context_data: dict[str, Any] | None = None
    ) -> HookResponse:
        """
        Handle a lifecycle workflow event.
        """
        if not self._enabled:
            return HookResponse(decision="allow")

        logger.debug(
            f"handle_lifecycle called: workflow={workflow_name}, event_type={event.event_type}"
        )
        try:
            if self._loop and self._loop.is_running():
                if threading.current_thread() is threading.main_thread():
                    # See comment in handle() about blocking main thread loop
                    return HookResponse(decision="allow")
                else:
                    future = asyncio.run_coroutine_threadsafe(
                        self.engine.evaluate_lifecycle_triggers(workflow_name, event, context_data),
                        self._loop,
                    )
                    return future.result(timeout=self.timeout)

            try:
                asyncio.get_running_loop()
                # If we get here, a loop is running
                logger.warning("Could not run workflow engine: Event loop is already running.")
                return HookResponse(decision="allow")
            except RuntimeError:
                # No loop running, safe to use asyncio.run
                return asyncio.run(
                    self.engine.evaluate_lifecycle_triggers(workflow_name, event, context_data)
                )

        except concurrent.futures.CancelledError:
            return self._handle_cancelled(event)
        except Exception as e:
            logger.error(f"Error handling lifecycle workflow: {e}", exc_info=True)
            return HookResponse(decision="allow")

    def activate_workflow(
        self,
        workflow_name: str,
        session_id: str,
        project_path: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Activate a step-based workflow for a session.

        This is used during session startup for terminal-mode agents that have
        a workflow_name set. It's a synchronous wrapper around the engine's
        activate_workflow method.

        Args:
            workflow_name: Name of the workflow to activate
            session_id: Session ID to activate for
            project_path: Optional project path for workflow discovery
            variables: Optional initial variables to merge with workflow defaults

        Returns:
            Dict with success status and workflow info
        """
        if not self._enabled:
            return {"success": False, "error": "Workflow engine is disabled"}

        from pathlib import Path

        path = Path(project_path) if project_path else None

        try:
            if self._loop and self._loop.is_running():
                if threading.current_thread() is threading.main_thread():
                    return {"success": False, "error": "Event loop conflict"}
                future = asyncio.run_coroutine_threadsafe(
                    self.engine.activate_workflow(
                        workflow_name=workflow_name,
                        session_id=session_id,
                        project_path=path,
                        variables=variables,
                    ),
                    self._loop,
                )
                return future.result(timeout=self.timeout)

            try:
                asyncio.get_running_loop()
                return {"success": False, "error": "Event loop conflict"}
            except RuntimeError:
                return asyncio.run(
                    self.engine.activate_workflow(
                        workflow_name=workflow_name,
                        session_id=session_id,
                        project_path=path,
                        variables=variables,
                    )
                )
        except concurrent.futures.CancelledError:
            logger.warning("Workflow activation cancelled")
            return {"success": False, "error": "Workflow activation was cancelled"}
        except Exception as e:
            logger.error(f"Error activating workflow: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
