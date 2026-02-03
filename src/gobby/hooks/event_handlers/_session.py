from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gobby.hooks.event_handlers._base import EventHandlersBase
from gobby.hooks.events import HookEvent, HookResponse

if TYPE_CHECKING:
    from gobby.storage.sessions import Session


class SessionEventHandlerMixin(EventHandlersBase):
    """Mixin for handling session-related events."""

    def handle_session_start(self, event: HookEvent) -> HookResponse:
        """
        Handle SESSION_START event.

        Register session and execute session-handoff workflow.
        """
        external_id = event.session_id
        input_data = event.data
        transcript_path = input_data.get("transcript_path")
        cli_source = event.source.value
        cwd = input_data.get("cwd")
        session_source = input_data.get("source", "startup")

        # Resolve project_id (auto-creates if needed)
        project_id = self._resolve_project_id(input_data.get("project_id"), cwd)
        # Always use Gobby's machine_id for cross-CLI consistency
        machine_id = self._get_machine_id()

        self.logger.debug(
            f"SESSION_START: cli={cli_source}, project={project_id}, source={session_source}"
        )

        # Step 0: Check if this is a pre-created session (terminal mode agent)
        # Two cases:
        # 1. Claude: We pass --session-id <internal_id>, so external_id IS our internal ID
        # 2. Gemini: We pass GOBBY_SESSION_ID env var, hook_dispatcher includes it in terminal_context
        existing_session = None
        terminal_context = input_data.get("terminal_context")
        gobby_session_id_from_env = (
            terminal_context.get("gobby_session_id") if terminal_context else None
        )

        if self._session_storage:
            try:
                # Try to find by internal ID first (Claude case - external_id IS internal_id)
                existing_session = self._session_storage.get(external_id)
                if existing_session:
                    return self._handle_pre_created_session(
                        existing_session=existing_session,
                        external_id=external_id,
                        transcript_path=transcript_path,
                        cli_source=cli_source,
                        event=event,
                        cwd=cwd,
                    )
            except Exception as e:
                self.logger.debug(f"No pre-created session found by external_id: {e}")

            # Gemini case: Look up by gobby_session_id from terminal_context
            if gobby_session_id_from_env and not existing_session:
                try:
                    existing_session = self._session_storage.get(gobby_session_id_from_env)
                    if existing_session:
                        self.logger.info(
                            f"Found pre-created session {gobby_session_id_from_env} via "
                            f"terminal_context, updating external_id to {external_id}"
                        )
                        # Update the session's external_id with CLI's native session_id
                        self._session_storage.update(
                            gobby_session_id_from_env,
                            external_id=external_id,
                        )
                        return self._handle_pre_created_session(
                            existing_session=existing_session,
                            external_id=external_id,
                            transcript_path=transcript_path,
                            cli_source=cli_source,
                            event=event,
                            cwd=cwd,
                        )
                except Exception as e:
                    self.logger.debug(f"No pre-created session found by gobby_session_id: {e}")

        # Step 1: Find parent session
        # Check env vars first (spawned agent case), then handoff (source='clear')
        parent_session_id = input_data.get("parent_session_id")
        workflow_name = input_data.get("workflow_name")
        agent_depth = input_data.get("agent_depth")

        if not parent_session_id and session_source == "clear" and self._session_storage:
            try:
                parent = self._session_storage.find_parent(
                    machine_id=machine_id,
                    project_id=project_id,
                    source=cli_source,
                    status="handoff_ready",
                )
                if parent:
                    parent_session_id = parent.id
                    self.logger.debug(f"Found parent session: {parent_session_id}")
            except Exception as e:
                self.logger.warning(f"Error finding parent session: {e}")

        # Step 2: Register new session with parent if found
        # terminal_context already extracted in Step 0
        # Parse agent_depth as int if provided
        agent_depth_val = 0
        if agent_depth:
            try:
                agent_depth_val = int(agent_depth)
            except (ValueError, TypeError):
                pass

        session_id = None
        if self._session_manager:
            session_id = self._session_manager.register_session(
                external_id=external_id,
                machine_id=machine_id,
                project_id=project_id,
                parent_session_id=parent_session_id,
                jsonl_path=transcript_path,
                source=cli_source,
                project_path=cwd,
                terminal_context=terminal_context,
                workflow_name=workflow_name,
                agent_depth=agent_depth_val,
            )

        # Step 2b: Mark parent session as expired after successful handoff
        if parent_session_id and self._session_manager:
            try:
                self._session_manager.mark_session_expired(parent_session_id)
                self.logger.debug(f"Marked parent session {parent_session_id} as expired")
            except Exception as e:
                self.logger.warning(f"Failed to mark parent session as expired: {e}")

        # Step 2c: Auto-activate workflow if specified (for spawned agents)
        if workflow_name and session_id:
            self._auto_activate_workflow(workflow_name, session_id, cwd)

        # Step 3: Track registered session
        if transcript_path and self._session_coordinator:
            try:
                self._session_coordinator.register_session(external_id)
            except Exception as e:
                self.logger.error(f"Failed to setup session tracking: {e}", exc_info=True)

        # Step 4: Update event metadata with the newly registered session_id
        event.metadata["_platform_session_id"] = session_id
        if parent_session_id:
            event.metadata["_parent_session_id"] = parent_session_id

        # Step 5: Register with Message Processor
        if self._message_processor and transcript_path and session_id:
            try:
                self._message_processor.register_session(
                    session_id, transcript_path, source=cli_source
                )
            except Exception as e:
                self.logger.warning(f"Failed to register session with message processor: {e}")

        # Step 6: Execute lifecycle workflows
        wf_response = HookResponse(decision="allow", context="")
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        # Build additional context (task context)
        # Note: Skill injection is now handled by workflows via inject_context action
        additional_context: list[str] = []
        if event.task_id:
            task_title = event.metadata.get("_task_title", "Unknown Task")
            additional_context.append("\n## Active Task Context\n")
            additional_context.append(f"You are working on task: {task_title} ({event.task_id})")

        # Fetch session to get seq_num for #N display
        session_obj = None
        if session_id and self._session_storage:
            session_obj = self._session_storage.get(session_id)

        return self._compose_session_response(
            session=session_obj,
            wf_response=wf_response,
            session_id=session_id,
            external_id=external_id,
            parent_session_id=parent_session_id,
            machine_id=machine_id,
            project_id=project_id,
            task_id=event.task_id,
            additional_context=additional_context,
            terminal_context=terminal_context,
        )

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

        # Execute lifecycle workflow triggers
        if self._workflow_handler:
            try:
                self._workflow_handler.handle_all_lifecycles(event)
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

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

        # Generate independent session summary file
        if self._summary_file_generator:
            try:
                summary_input = {
                    "session_id": external_id,
                    "transcript_path": event.data.get("transcript_path"),
                }
                self._summary_file_generator.generate_session_summary(
                    session_id=session_id or external_id,
                    input_data=summary_input,
                )
            except Exception as e:
                self.logger.error(f"Failed to generate failover summary: {e}")

        # Unregister from message processor
        if self._message_processor and (session_id or external_id):
            try:
                target_id = session_id or external_id
                self._message_processor.unregister_session(target_id)
            except Exception as e:
                self.logger.warning(f"Failed to unregister session from message processor: {e}")

        return HookResponse(decision="allow")

    def _handle_pre_created_session(
        self,
        existing_session: Session,
        external_id: str,
        transcript_path: str | None,
        cli_source: str,
        event: HookEvent,
        cwd: str | None,
    ) -> HookResponse:
        """Handle session start for a pre-created session (terminal mode agent).

        Args:
            existing_session: Pre-created session object
            external_id: External (CLI-native) session ID
            transcript_path: Path to transcript file
            cli_source: CLI source (e.g., "claude-code")
            event: Hook event
            cwd: Current working directory

        Returns:
            HookResponse for the pre-created session
        """
        self.logger.info(f"Found pre-created session {external_id}, updating instead of creating")

        # Update the session with actual runtime info
        if self._session_storage:
            self._session_storage.update(
                session_id=existing_session.id,
                jsonl_path=transcript_path,
                status="active",
            )

        session_id = existing_session.id
        parent_session_id = existing_session.parent_session_id
        machine_id = self._get_machine_id()

        # Track registered session
        if transcript_path and self._session_coordinator:
            try:
                self._session_coordinator.register_session(external_id)
            except Exception as e:
                self.logger.error(f"Failed to setup session tracking: {e}")

        # Start the agent run if this is a terminal-mode agent session
        if existing_session.agent_run_id and self._session_coordinator:
            try:
                self._session_coordinator.start_agent_run(existing_session.agent_run_id)
            except Exception as e:
                self.logger.warning(f"Failed to start agent run: {e}")

        # Auto-activate workflow if specified for this session
        if existing_session.workflow_name and session_id:
            self._auto_activate_workflow(
                existing_session.workflow_name,
                session_id,
                cwd,
                variables=existing_session.step_variables,
            )

        # Update event metadata
        event.metadata["_platform_session_id"] = session_id

        # Register with Message Processor
        if self._message_processor and transcript_path:
            try:
                self._message_processor.register_session(
                    session_id, transcript_path, source=cli_source
                )
            except Exception as e:
                self.logger.warning(f"Failed to register with message processor: {e}")

        # Execute lifecycle workflows
        wf_response = HookResponse(decision="allow", context="")
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        return self._compose_session_response(
            session=existing_session,
            wf_response=wf_response,
            session_id=session_id,
            external_id=external_id,
            parent_session_id=parent_session_id,
            machine_id=machine_id,
            project_id=existing_session.project_id,
            task_id=event.task_id,
            is_pre_created=True,
        )

    def _compose_session_response(
        self,
        session: Session | None,
        wf_response: HookResponse,
        session_id: str | None,
        external_id: str,
        parent_session_id: str | None,
        machine_id: str,
        project_id: str | None = None,
        task_id: str | None = None,
        additional_context: list[str] | None = None,
        is_pre_created: bool = False,
        terminal_context: dict[str, Any] | None = None,
    ) -> HookResponse:
        """Build HookResponse for session start.

        Shared helper that builds the system message, context, and metadata
        for both pre-created and newly-created sessions.

        Args:
            session: Session object (used for seq_num)
            wf_response: Response from workflow handler
            session_id: Session ID
            external_id: External (CLI-native) session ID
            parent_session_id: Parent session ID if any
            machine_id: Machine ID
            project_id: Project ID
            task_id: Task ID if any
            additional_context: Additional context strings to append (e.g., task/skill context)
            is_pre_created: Whether this is a pre-created session
            terminal_context: Terminal context dict to add to metadata

        Returns:
            HookResponse with system_message, context, and metadata
        """
        # Build context_parts
        context_parts: list[str] = []
        if wf_response.context:
            context_parts.append(wf_response.context)
        if parent_session_id:
            context_parts.append(f"Parent session: {parent_session_id}")
        if additional_context:
            context_parts.extend(additional_context)

        # Compute session_ref from session object or fallback to session_id
        session_ref = session_id
        if session and session.seq_num:
            session_ref = f"#{session.seq_num}"

        # Build system message (terminal display only)
        if session_ref and session_ref != session_id:
            system_message = f"\nGobby Session ID: {session_ref}"
        else:
            system_message = f"\nGobby Session ID: {session_id}"
        system_message += " <- Use this for MCP tool calls (session_id parameter)"
        system_message += f"\nExternal ID: {external_id} (CLI-native, rarely needed)"

        # Add active lifecycle workflows
        if wf_response.metadata and "discovered_workflows" in wf_response.metadata:
            wf_list = wf_response.metadata["discovered_workflows"]
            if wf_list:
                system_message += "\nActive workflows:"
                for w in wf_list:
                    source = "project" if w["is_project"] else "global"
                    system_message += f"\n  - {w['name']} ({source}, priority={w['priority']})"

        if wf_response.system_message:
            system_message += f"\n\n{wf_response.system_message}"

        # Build metadata
        metadata: dict[str, Any] = {
            "session_id": session_id,
            "session_ref": session_ref,
            "parent_session_id": parent_session_id,
            "machine_id": machine_id,
            "project_id": project_id,
            "external_id": external_id,
            "task_id": task_id,
        }
        if is_pre_created:
            metadata["is_pre_created"] = True
        if terminal_context:
            # Only include non-null terminal values
            for key, value in terminal_context.items():
                if value is not None:
                    metadata[f"terminal_{key}"] = value

        final_context = "\n".join(context_parts) if context_parts else None

        # Debug: echo additionalContext to system_message if enabled
        # Workflow variable takes precedence over config
        debug_echo = False
        workflow_vars = (wf_response.metadata or {}).get("workflow_variables", {})
        if workflow_vars.get("debug_echo_context") is not None:
            debug_echo = bool(workflow_vars.get("debug_echo_context"))
        elif self._workflow_config and self._workflow_config.debug_echo_context:
            debug_echo = True

        if debug_echo and final_context:
            system_message += f"\n\n[DEBUG additionalContext]\n{final_context}"

        return HookResponse(
            decision="allow",
            context=final_context,
            system_message=system_message,
            metadata=metadata,
        )
