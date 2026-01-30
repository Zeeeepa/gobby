from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from gobby.config.skills import SkillsConfig
    from gobby.config.tasks import WorkflowConfig
    from gobby.hooks.artifact_capture import ArtifactCaptureHook
    from gobby.hooks.session_coordinator import SessionCoordinator
    from gobby.hooks.skill_manager import HookSkillManager
    from gobby.sessions.manager import SessionManager
    from gobby.sessions.summary import SummaryFileGenerator
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
    _summary_file_generator: SummaryFileGenerator | None
    _task_manager: LocalTaskManager | None
    _session_coordinator: SessionCoordinator | None
    _message_manager: LocalSessionMessageManager | None
    _skill_manager: HookSkillManager | None
    _skills_config: SkillsConfig | None
    _artifact_capture_hook: ArtifactCaptureHook | None
    _get_machine_id: Callable[[], str]
    _resolve_project_id: Callable[[str | None, str | None], str]
    logger: logging.Logger
    _handler_map: dict[HookEventType, Callable[[HookEvent], HookResponse]]

    def _auto_activate_workflow(
        self, workflow_name: str, session_id: str, project_path: str | None
    ) -> None:
        """Shared method for auto-activating workflows."""
        if not self._workflow_handler:
            return

        try:
            result = self._workflow_handler.activate_workflow(
                workflow_name=workflow_name,
                session_id=session_id,
                project_path=project_path,
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
