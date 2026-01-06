"""
Event handlers module for hook event processing.

This module is extracted from hook_manager.py using Strangler Fig pattern.
It provides centralized event handler registration and dispatch.

Classes:
    EventHandlers: Manages event handler registration and dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from gobby.hooks.session_coordinator import SessionCoordinator
    from gobby.sessions.manager import SessionManager
    from gobby.sessions.summary import SummaryFileGenerator
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.hooks import WorkflowHookHandler


class EventHandlers:
    """
    Manages event handler registration and dispatch.

    Provides handler methods for all HookEventType values and a registration
    mechanism for looking up handlers by event type.

    Extracted from HookManager to separate event handling concerns.
    """

    def __init__(
        self,
        session_manager: "SessionManager | None" = None,
        workflow_handler: "WorkflowHookHandler | None" = None,
        session_storage: "LocalSessionManager | None" = None,
        message_processor: Any | None = None,
        summary_file_generator: "SummaryFileGenerator | None" = None,
        task_manager: "LocalTaskManager | None" = None,
        session_coordinator: "SessionCoordinator | None" = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """
        Initialize EventHandlers.

        Args:
            session_manager: SessionManager for session operations
            workflow_handler: WorkflowHookHandler for lifecycle workflows
            session_storage: LocalSessionManager for session storage
            message_processor: SessionMessageProcessor for message handling
            summary_file_generator: SummaryFileGenerator for summaries
            task_manager: LocalTaskManager for task operations
            session_coordinator: SessionCoordinator for session tracking
            logger: Optional logger instance
        """
        self._session_manager = session_manager
        self._workflow_handler = workflow_handler
        self._session_storage = session_storage
        self._message_processor = message_processor
        self._summary_file_generator = summary_file_generator
        self._task_manager = task_manager
        self._session_coordinator = session_coordinator
        self.logger = logger or logging.getLogger(__name__)

        # Build handler map
        self._handler_map: dict[HookEventType, Callable[[HookEvent], HookResponse]] = {
            HookEventType.SESSION_START: self.handle_session_start,
            HookEventType.SESSION_END: self.handle_session_end,
            HookEventType.BEFORE_AGENT: self.handle_before_agent,
            HookEventType.AFTER_AGENT: self.handle_after_agent,
            HookEventType.BEFORE_TOOL: self.handle_before_tool,
            HookEventType.AFTER_TOOL: self.handle_after_tool,
            HookEventType.PRE_COMPACT: self.handle_pre_compact,
            HookEventType.SUBAGENT_START: self.handle_subagent_start,
            HookEventType.SUBAGENT_STOP: self.handle_subagent_stop,
            HookEventType.NOTIFICATION: self.handle_notification,
            HookEventType.BEFORE_TOOL_SELECTION: self.handle_before_tool_selection,
            HookEventType.BEFORE_MODEL: self.handle_before_model,
            HookEventType.AFTER_MODEL: self.handle_after_model,
            HookEventType.PERMISSION_REQUEST: self.handle_permission_request,
            HookEventType.STOP: self.handle_stop,
        }

    def get_handler(
        self, event_type: HookEventType | str
    ) -> Callable[[HookEvent], HookResponse] | None:
        """
        Get handler for an event type.

        Args:
            event_type: The event type to get handler for

        Returns:
            Handler callable or None if not found
        """
        if isinstance(event_type, str):
            try:
                event_type = HookEventType(event_type)
            except ValueError:
                return None
        return self._handler_map.get(event_type)

    def get_handler_map(self) -> dict[HookEventType, Callable[[HookEvent], HookResponse]]:
        """
        Get a copy of the handler map.

        Returns:
            Copy of handler map (modifications don't affect internal state)
        """
        return dict(self._handler_map)

    # ==================== SESSION HANDLERS ====================

    def handle_session_start(self, event: HookEvent) -> HookResponse:
        """Handle SESSION_START event."""
        session_id = event.session_id
        self.logger.debug(f"SESSION_START: {session_id}")

        context = ""

        # Register session if session_manager available
        if self._session_manager:
            try:
                self._session_manager.register_session(
                    external_id=session_id,
                    source=event.source.value if hasattr(event.source, "value") else str(event.source),
                )
            except Exception as e:
                self.logger.warning(f"Failed to register session: {e}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.context:
                    context = wf_response.context
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow", context=context)

    def handle_session_end(self, event: HookEvent) -> HookResponse:
        """Handle SESSION_END event."""
        session_id = event.metadata.get("_platform_session_id", event.session_id)
        self.logger.debug(f"SESSION_END: {session_id}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== AGENT HANDLERS ====================

    def handle_before_agent(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_AGENT event (user prompt submit)."""
        session_id = event.metadata.get("_platform_session_id", event.session_id)
        self.logger.debug(f"BEFORE_AGENT: {session_id}")

        context = ""

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.context:
                    context = wf_response.context
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow", context=context)

    def handle_after_agent(self, event: HookEvent) -> HookResponse:
        """Handle AFTER_AGENT event."""
        session_id = event.metadata.get("_platform_session_id", event.session_id)
        self.logger.debug(f"AFTER_AGENT: {session_id}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== TOOL HANDLERS ====================

    def handle_before_tool(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_TOOL event."""
        tool_name = event.data.get("tool_name", "unknown")
        self.logger.debug(f"BEFORE_TOOL: {tool_name}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    def handle_after_tool(self, event: HookEvent) -> HookResponse:
        """Handle AFTER_TOOL event."""
        tool_name = event.data.get("tool_name", "unknown")
        self.logger.debug(f"AFTER_TOOL: {tool_name}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== STOP HANDLER ====================

    def handle_stop(self, event: HookEvent) -> HookResponse:
        """Handle STOP event (Claude Code only)."""
        session_id = event.metadata.get("_platform_session_id", event.session_id)
        self.logger.debug(f"STOP: {session_id}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== COMPACT HANDLER ====================

    def handle_pre_compact(self, event: HookEvent) -> HookResponse:
        """Handle PRE_COMPACT event."""
        session_id = event.metadata.get("_platform_session_id", event.session_id)
        self.logger.debug(f"PRE_COMPACT: {session_id}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== SUBAGENT HANDLERS ====================

    def handle_subagent_start(self, event: HookEvent) -> HookResponse:
        """Handle SUBAGENT_START event."""
        subagent_id = event.data.get("subagent_id", "unknown")
        self.logger.debug(f"SUBAGENT_START: {subagent_id}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    def handle_subagent_stop(self, event: HookEvent) -> HookResponse:
        """Handle SUBAGENT_STOP event."""
        subagent_id = event.data.get("subagent_id", "unknown")
        self.logger.debug(f"SUBAGENT_STOP: {subagent_id}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== NOTIFICATION HANDLER ====================

    def handle_notification(self, event: HookEvent) -> HookResponse:
        """Handle NOTIFICATION event."""
        message = event.data.get("message", "")
        self.logger.debug(f"NOTIFICATION: {message[:50]}...")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== PERMISSION HANDLER ====================

    def handle_permission_request(self, event: HookEvent) -> HookResponse:
        """Handle PERMISSION_REQUEST event (Claude Code only)."""
        permission = event.data.get("permission", "unknown")
        self.logger.debug(f"PERMISSION_REQUEST: {permission}")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    # ==================== GEMINI-ONLY HANDLERS ====================

    def handle_before_tool_selection(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_TOOL_SELECTION event (Gemini only)."""
        self.logger.debug("BEFORE_TOOL_SELECTION")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    def handle_before_model(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_MODEL event (Gemini only)."""
        self.logger.debug("BEFORE_MODEL")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")

    def handle_after_model(self, event: HookEvent) -> HookResponse:
        """Handle AFTER_MODEL event (Gemini only)."""
        self.logger.debug("AFTER_MODEL")

        # Execute workflows if handler available
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return HookResponse(decision="allow")


__all__ = ["EventHandlers"]
