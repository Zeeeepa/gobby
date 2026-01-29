import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookResponse

if TYPE_CHECKING:
    from .engine import WorkflowEngine

logger = logging.getLogger(__name__)


class WorkflowHookHandler:
    """
    Integrates WorkflowEngine into the HookManager.
    Wraps the async engine to be callable from synchronous hooks.
    """

    def __init__(
        self,
        engine: "WorkflowEngine",
        loop: asyncio.AbstractEventLoop | None = None,
        timeout: float = 30.0,  # Timeout for workflow operations in seconds
        enabled: bool = True,
    ):
        self.engine = engine
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

    def handle_all_lifecycles(self, event: HookEvent) -> HookResponse:
        """
        Handle a hook event by discovering and evaluating all lifecycle workflows.

        This is the preferred method - it automatically discovers all lifecycle
        workflows and evaluates them in priority order. Replaces the need to
        call handle_lifecycle() with a specific workflow name.

        Args:
            event: The hook event to handle

        Returns:
            Merged HookResponse from all workflows
        """
        if not self._enabled:
            return HookResponse(decision="allow")

        try:
            if self._loop and self._loop.is_running():
                if threading.current_thread() is threading.main_thread():
                    return HookResponse(decision="allow")
                else:
                    future = asyncio.run_coroutine_threadsafe(
                        self.engine.evaluate_all_lifecycle_workflows(event),
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
                return asyncio.run(self.engine.evaluate_all_lifecycle_workflows(event))

        except Exception as e:
            logger.error(f"Error handling all lifecycle workflows: {e}", exc_info=True)
            return HookResponse(decision="allow")

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
            return self.engine.activate_workflow(
                workflow_name=workflow_name,
                session_id=session_id,
                project_path=path,
                variables=variables,
            )
        except Exception as e:
            logger.error(f"Error activating workflow: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
