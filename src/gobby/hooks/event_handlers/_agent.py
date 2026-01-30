from __future__ import annotations

from gobby.hooks.event_handlers._base import EventHandlersBase
from gobby.hooks.events import HookEvent, HookResponse, SessionSource


class AgentEventHandlerMixin(EventHandlersBase):
    """Mixin for handling agent-related events."""

    def handle_before_agent(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_AGENT event (user prompt submit)."""
        input_data = event.data
        prompt = input_data.get("prompt", "")
        transcript_path = input_data.get("transcript_path")
        session_id = event.metadata.get("_platform_session_id")

        context_parts = []

        if session_id:
            self.logger.debug(f"BEFORE_AGENT: session {session_id}, prompt_len={len(prompt)}")

            # Update status to active (unless /clear or /exit)
            prompt_lower = prompt.strip().lower()
            if prompt_lower not in ("/clear", "/exit") and self._session_manager:
                try:
                    self._session_manager.update_session_status(session_id, "active")
                    if self._session_storage:
                        self._session_storage.reset_transcript_processed(session_id)
                except Exception as e:
                    self.logger.warning(f"Failed to update session status: {e}")

            # Handle /clear command - lifecycle workflows handle handoff
            if prompt_lower in ("/clear", "/exit") and transcript_path:
                self.logger.debug(f"Detected {prompt_lower} - lifecycle workflows handle handoff")

        # Execute lifecycle workflow triggers
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.context:
                    context_parts.append(wf_response.context)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(
            decision="allow",
            context="\n\n".join(context_parts) if context_parts else None,
        )

    def handle_after_agent(self, event: HookEvent) -> HookResponse:
        """Handle AFTER_AGENT event."""
        session_id = event.metadata.get("_platform_session_id")
        cli_source = event.source.value

        context_parts = []

        if session_id:
            self.logger.debug(f"AFTER_AGENT: session {session_id}, cli={cli_source}")
            if self._session_manager:
                try:
                    self._session_manager.update_session_status(session_id, "paused")
                except Exception as e:
                    self.logger.warning(f"Failed to update session status: {e}")
        else:
            self.logger.debug(f"AFTER_AGENT: cli={cli_source}")

        # Execute lifecycle workflow triggers
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.context:
                    context_parts.append(wf_response.context)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(
            decision="allow",
            context="\n\n".join(context_parts) if context_parts else None,
        )

    def handle_stop(self, event: HookEvent) -> HookResponse:
        """Handle STOP event (Claude Code only)."""
        session_id = event.metadata.get("_platform_session_id")

        context_parts = []

        if session_id:
            self.logger.debug(f"STOP: session {session_id}")
            if self._session_manager:
                try:
                    self._session_manager.update_session_status(session_id, "paused")
                except Exception as e:
                    self.logger.warning(f"Failed to update session status: {e}")
        else:
            self.logger.debug("STOP")

        # Execute lifecycle workflow triggers
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.context:
                    context_parts.append(wf_response.context)
                if wf_response.decision != "allow":
                    return wf_response
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(
            decision="allow",
            context="\n\n".join(context_parts) if context_parts else None,
        )

    def handle_pre_compact(self, event: HookEvent) -> HookResponse:
        """Handle PRE_COMPACT event.

        Note: Gemini fires PreCompress constantly during normal operation,
        unlike Claude which fires it only when approaching context limits.
        We skip handoff logic and workflow execution for Gemini to avoid
        excessive state changes and workflow interruptions.
        """
        trigger = event.data.get("trigger", "auto")
        session_id = event.metadata.get("_platform_session_id")

        # Skip handoff logic for Gemini - it fires PreCompress too frequently
        if event.source == SessionSource.GEMINI:
            self.logger.debug(f"PRE_COMPACT ({trigger}): session {session_id} [Gemini - skipped]")
            return HookResponse(decision="allow")

        if session_id:
            self.logger.debug(f"PRE_COMPACT ({trigger}): session {session_id}")
            # Mark session as handoff_ready so it can be found as parent after compact
            if self._session_manager:
                self._session_manager.update_session_status(session_id, "handoff_ready")
        else:
            self.logger.debug(f"PRE_COMPACT ({trigger})")

        # Execute lifecycle workflows
        if self._workflow_handler:
            try:
                return self._workflow_handler.handle_all_lifecycles(event)
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(decision="allow")

    def handle_subagent_start(self, event: HookEvent) -> HookResponse:
        """Handle SUBAGENT_START event."""
        input_data = event.data
        session_id = event.metadata.get("_platform_session_id")
        agent_id = input_data.get("agent_id")
        subagent_id = input_data.get("subagent_id")

        log_msg = f"SUBAGENT_START: session {session_id}" if session_id else "SUBAGENT_START"
        if agent_id:
            log_msg += f", agent_id={agent_id}"
        if subagent_id:
            log_msg += f", subagent_id={subagent_id}"
        self.logger.debug(log_msg)

        return HookResponse(decision="allow")

    def handle_subagent_stop(self, event: HookEvent) -> HookResponse:
        """Handle SUBAGENT_STOP event."""
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"SUBAGENT_STOP: session {session_id}")
        else:
            self.logger.debug("SUBAGENT_STOP")

        return HookResponse(decision="allow")
