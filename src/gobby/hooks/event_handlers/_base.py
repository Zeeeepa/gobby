from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from gobby.config.skills import SkillsConfig
    from gobby.config.tasks import WorkflowConfig
    from gobby.hooks.session_coordinator import SessionCoordinator
    from gobby.hooks.skill_manager import HookSkillManager
    from gobby.sessions.manager import SessionManager
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.session_tasks import SessionTaskManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.hooks import WorkflowHookHandler


class EventHandlersBase:
    """Base class for EventHandlers mixins with type hints for shared state."""

    _session_manager: SessionManager | None
    _workflow_handler: WorkflowHookHandler | None
    _workflow_config: WorkflowConfig | None
    _session_storage: LocalSessionManager | None
    _session_task_manager: SessionTaskManager | None
    _message_processor: Any | None
    _task_manager: LocalTaskManager | None
    _session_coordinator: SessionCoordinator | None
    _message_manager: LocalSessionMessageManager | None
    _skill_manager: HookSkillManager | None
    _skills_config: SkillsConfig | None
    _get_machine_id: Callable[[], str]
    _resolve_project_id: Callable[[str | None, str | None], str]
    logger: logging.Logger
    _handler_map: dict[HookEventType, Callable[[HookEvent], HookResponse]]

    def _evaluate_workflows(self, event: HookEvent) -> HookResponse:
        """Evaluate lifecycle workflows for an event.

        Consolidates the try/except workflow handler pattern used across
        all event handler call sites. Returns allow-default when no handler
        is configured or on error.
        """
        if not self._workflow_handler:
            return HookResponse(decision="allow")
        try:
            return self._workflow_handler.evaluate(event)
        except Exception as e:
            self.logger.error(f"Failed to evaluate workflows: {e}", exc_info=True)
            return HookResponse(decision="allow")

    def _apply_debug_echo(self, response: HookResponse, wf_response: HookResponse) -> None:
        """Append additionalContext to system_message when debug_echo_context is enabled.

        Reads the flag from workflow variables (priority) or WorkflowConfig (fallback).
        Mutates ``response`` in place (HookResponse is a non-frozen dataclass).
        """
        debug_echo = False
        workflow_vars = (wf_response.metadata or {}).get("workflow_variables", {})
        if workflow_vars.get("debug_echo_context") is not None:
            debug_echo = bool(workflow_vars["debug_echo_context"])
        elif self._workflow_config and self._workflow_config.debug_echo_context:
            debug_echo = True

        if not debug_echo or not response.context:
            self.logger.debug(
                f"debug_echo_context: enabled={debug_echo}, "
                f"context_len={len(response.context) if response.context else 0}"
            )
            return

        echo_block = f"\n\n[DEBUG additionalContext]\n{response.context}"
        if response.system_message:
            response.system_message += echo_block
        else:
            response.system_message = echo_block

        self.logger.debug(
            f"debug_echo_context: appended {len(response.context)} chars to system_message"
        )

    def _auto_activate_workflow(
        self,
        workflow_name: str,
        session_id: str,
        project_path: str | None,
        variables: dict[str, Any] | None = None,
    ) -> None:
        """Shared method for auto-activating workflows."""
        if not self._workflow_handler:
            return

        try:
            result = self._workflow_handler.activate_workflow(
                workflow_name=workflow_name,
                session_id=session_id,
                project_path=project_path,
                variables=variables,
            )
            if result.get("success"):
                self.logger.info(
                    "Auto-activated workflow for session",
                    extra={
                        "workflow_name": workflow_name,
                        "session_id": session_id,
                        "project_path": project_path,
                    },
                )
            else:
                self.logger.warning(
                    "Failed to auto-activate workflow",
                    extra={
                        "workflow_name": workflow_name,
                        "session_id": session_id,
                        "project_path": project_path,
                        "error": result.get("error"),
                    },
                )
        except Exception as e:
            self.logger.warning(
                "Failed to auto-activate workflow",
                extra={
                    "workflow_name": workflow_name,
                    "session_id": session_id,
                    "project_path": project_path,
                    "error": str(e),
                },
                exc_info=True,
            )
