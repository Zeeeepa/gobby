"""Session end event handler."""

from __future__ import annotations

from gobby.hooks.event_handlers._base import EventHandlersBase
from gobby.hooks.events import HookEvent, HookResponse


class SessionEndMixin(EventHandlersBase):
    """Mixin for handling SESSION_END events."""

    def handle_session_end(self, event: HookEvent) -> HookResponse:
        """Handle SESSION_END event."""
        from gobby.tasks.commits import auto_link_commits

        external_id = event.session_id
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"SESSION_END: session {session_id}")
        else:
            self.logger.warning(f"SESSION_END: session_id not found for external_id={external_id}")

        # If not in mapping, query database
        if not session_id and external_id and self._session_manager:
            self.logger.debug(f"external_id {external_id} not in mapping, querying database")
            # Resolve context for lookup
            machine_id = self._get_machine_id()
            cwd = event.data.get("cwd")
            project_id = self._resolve_project_id(event.data.get("project_id"), cwd)
            # Lookup with full composite key
            session_id = self._session_manager.lookup_session_id(
                external_id,
                source=event.source.value,
                machine_id=machine_id,
                project_id=project_id,
            )

        # Ensure session_id is available in event metadata for workflow actions
        if session_id and not event.metadata.get("_platform_session_id"):
            event.metadata["_platform_session_id"] = session_id

        # Auto-link commits made during this session to tasks
        if session_id and self._session_storage and self._task_manager:
            try:
                session = self._session_storage.get(session_id)
                if session:
                    cwd = event.data.get("cwd")
                    link_result = auto_link_commits(
                        task_manager=self._task_manager,
                        since=session.created_at,
                        cwd=cwd,
                    )
                    if link_result.total_linked > 0:
                        self.logger.info(
                            f"Auto-linked {link_result.total_linked} commits to tasks: "
                            f"{list(link_result.linked_tasks.keys())}"
                        )
            except Exception as e:
                self.logger.warning(f"Failed to auto-link session commits: {e}")

        # Complete agent run if this is a terminal-mode agent session
        if session_id and self._session_storage and self._session_coordinator:
            try:
                session = self._session_storage.get(session_id)
                if session and session.agent_run_id:
                    self._session_coordinator.complete_agent_run(session)
            except Exception as e:
                self.logger.warning(f"Failed to complete agent run: {e}")

        # Unregister from message processor
        if self._message_processor and (session_id or external_id):
            try:
                target_id = session_id or external_id
                self._message_processor.unregister_session(target_id)
            except Exception as e:
                self.logger.warning(f"Failed to unregister session from message processor: {e}")

        # Notify pane monitor to prevent double-fire
        if session_id:
            try:
                from gobby.agents.tmux import get_tmux_pane_monitor

                monitor = get_tmux_pane_monitor()
                if monitor:
                    monitor.mark_recently_ended(session_id)
            except Exception as e:
                self.logger.debug(f"Failed to notify pane monitor for session {session_id}: {e}")

        # Mark as handoff_ready if session is ending due to /clear or /compact,
        # so the new session can find this parent and generate handoff summaries.
        # Claude Code session-end uses 'reason' field (not 'source').
        if session_id and self._session_storage:
            try:
                end_status = "expired"
                end_reason = event.data.get("reason")
                if end_reason in ("clear", "compact"):
                    end_status = "handoff_ready"
                # Don't downgrade handoff_ready -> expired (PRE_COMPACT may have
                # already set handoff_ready before SESSION_END fires)
                if end_status == "expired":
                    current = self._session_storage.get(session_id)
                    if current and current.status == "handoff_ready":
                        end_status = "handoff_ready"
                self._session_storage.update_status(session_id, end_status)
            except Exception as e:
                self.logger.warning(f"Failed to update session status on end: {e}")

        return HookResponse(decision="allow")
