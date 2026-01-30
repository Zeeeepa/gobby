"""
Event handlers module for hook event processing.

This module is extracted from hook_manager.py using Strangler Fig pattern.
It provides centralized event handler registration and dispatch.

Classes:
    EventHandlers: Manages event handler registration and dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse

if TYPE_CHECKING:
    from gobby.config.skills import SkillsConfig
    from gobby.hooks.session_coordinator import SessionCoordinator
    from gobby.hooks.skill_manager import HookSkillManager
    from gobby.sessions.manager import SessionManager
    from gobby.sessions.summary import SummaryFileGenerator
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.session_tasks import SessionTaskManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.workflows.hooks import WorkflowHookHandler


EDIT_TOOLS = {
    "write_file",
    "replace",
    "edit_file",
    "notebook_edit",
    "edit",
    "write",
}


class EventHandlers:
    """
    Manages event handler registration and dispatch.

    Provides handler methods for all HookEventType values and a registration
    mechanism for looking up handlers by event type.

    Extracted from HookManager to separate event handling concerns.
    """

    def __init__(
        self,
        session_manager: SessionManager | None = None,
        workflow_handler: WorkflowHookHandler | None = None,
        session_storage: LocalSessionManager | None = None,
        session_task_manager: SessionTaskManager | None = None,
        message_processor: Any | None = None,
        summary_file_generator: SummaryFileGenerator | None = None,
        task_manager: LocalTaskManager | None = None,
        session_coordinator: SessionCoordinator | None = None,
        message_manager: LocalSessionMessageManager | None = None,
        skill_manager: HookSkillManager | None = None,
        skills_config: SkillsConfig | None = None,
        get_machine_id: Callable[[], str] | None = None,
        resolve_project_id: Callable[[str | None, str | None], str] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """
        Initialize EventHandlers.

        Args:
            session_manager: SessionManager for session operations
            workflow_handler: WorkflowHookHandler for lifecycle workflows
            session_storage: LocalSessionManager for session storage
            session_task_manager: SessionTaskManager for session-task links
            message_processor: SessionMessageProcessor for message handling
            summary_file_generator: SummaryFileGenerator for summaries
            task_manager: LocalTaskManager for task operations
            session_coordinator: SessionCoordinator for session tracking
            message_manager: LocalSessionMessageManager for messages
            skill_manager: HookSkillManager for skill discovery
            skills_config: SkillsConfig for skill injection settings
            get_machine_id: Function to get machine ID
            resolve_project_id: Function to resolve project ID from cwd
            logger: Optional logger instance
        """
        self._session_manager = session_manager
        self._workflow_handler = workflow_handler
        self._session_storage = session_storage
        self._session_task_manager = session_task_manager
        self._message_processor = message_processor
        self._summary_file_generator = summary_file_generator
        self._task_manager = task_manager
        self._session_coordinator = session_coordinator
        self._message_manager = message_manager
        self._skill_manager = skill_manager
        self._skills_config = skills_config
        self._get_machine_id = get_machine_id or (lambda: "unknown-machine")
        self._resolve_project_id = resolve_project_id or (lambda p, c: p or "")
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

    def _auto_activate_workflow(
        self, workflow_name: str, session_id: str, project_path: str | None
    ) -> None:
        """Auto-activate a workflow for a session.

        Args:
            workflow_name: Name of the workflow to activate
            session_id: Session ID to activate workflow for
            project_path: Project path for workflow context
        """
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

    # ==================== SESSION HANDLERS ====================

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
        # When we spawn an agent in terminal mode, we pass --session-id <internal_id>
        # to Claude, so external_id here might actually be our internal session ID
        existing_session = None
        if self._session_storage:
            try:
                # Try to find by internal ID first (terminal mode case)
                existing_session = self._session_storage.get(external_id)
                if existing_session:
                    self.logger.info(
                        f"Found pre-created session {external_id}, updating instead of creating"
                    )
                    # Update the session with actual runtime info
                    self._session_storage.update(
                        session_id=existing_session.id,
                        jsonl_path=transcript_path,
                        status="active",
                    )
                    # Return early with the pre-created session's context
                    session_id: str | None = existing_session.id
                    parent_session_id = existing_session.parent_session_id

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
                            existing_session.workflow_name, session_id, cwd
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
                    context_parts = [""]
                    wf_response = HookResponse(decision="allow", context="")
                    if self._workflow_handler:
                        try:
                            wf_response = self._workflow_handler.handle_all_lifecycles(event)
                            if wf_response.context:
                                context_parts.append(wf_response.context)
                        except Exception as e:
                            self.logger.warning(f"Workflow error: {e}")

                    # Build system message (terminal display only)
                    # Display #N format if seq_num available, fallback to UUID
                    session_ref = (
                        f"#{existing_session.seq_num}" if existing_session.seq_num else session_id
                    )
                    system_message = f"\nGobby Session ID: {session_ref}"
                    system_message += " <- Use this for MCP tool calls (session_id parameter)"
                    system_message += f"\nExternal ID: {external_id} (CLI-native, rarely needed)"
                    if parent_session_id:
                        context_parts.append(f"Parent session: {parent_session_id}")

                    # Add active lifecycle workflows
                    if wf_response.metadata and "discovered_workflows" in wf_response.metadata:
                        wf_list = wf_response.metadata["discovered_workflows"]
                        if wf_list:
                            system_message += "\nActive workflows:"
                            for w in wf_list:
                                source = "project" if w["is_project"] else "global"
                                system_message += (
                                    f"\n  - {w['name']} ({source}, priority={w['priority']})"
                                )

                    if wf_response.system_message:
                        system_message += f"\n\n{wf_response.system_message}"

                    return HookResponse(
                        decision="allow",
                        context="\n".join(context_parts) if context_parts else None,
                        system_message=system_message,
                        metadata={
                            "session_id": session_id,
                            "session_ref": session_ref,
                            "parent_session_id": parent_session_id,
                            "machine_id": machine_id,
                            "project_id": existing_session.project_id,
                            "external_id": external_id,
                            "task_id": event.task_id,
                            "is_pre_created": True,
                        },
                    )
            except Exception as e:
                self.logger.debug(f"No pre-created session found: {e}")

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
        # Extract terminal context (injected by hook_dispatcher for terminal correlation)
        terminal_context = input_data.get("terminal_context")
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
        context_parts = [""]
        wf_response = HookResponse(decision="allow", context="")
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.context:
                    context_parts.append(wf_response.context)
            except Exception as e:
                self.logger.warning(f"Workflow error: {e}")

        if parent_session_id:
            context_parts.append(f"Parent session: {parent_session_id}")

        # Build system message (terminal display only)
        # Fetch session to get seq_num for #N display
        session_ref = session_id  # fallback
        if session_id and self._session_storage:
            session_obj = self._session_storage.get(session_id)
            if session_obj and session_obj.seq_num:
                session_ref = f"#{session_obj.seq_num}"
        # Format: "Gobby Session ID: #N" with usage hint
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

        # Inject active task context if available
        if event.task_id:
            task_title = event.metadata.get("_task_title", "Unknown Task")
            context_parts.append("\n## Active Task Context\n")
            context_parts.append(f"You are working on task: {task_title} ({event.task_id})")

        # Inject core skills if enabled (restoring from parent session if available)
        skill_context = self._build_skill_injection_context(parent_session_id)
        if skill_context:
            context_parts.append(skill_context)

        # Build metadata with terminal context (filter out nulls)
        metadata: dict[str, Any] = {
            "session_id": session_id,
            "session_ref": session_ref,
            "parent_session_id": parent_session_id,
            "machine_id": machine_id,
            "project_id": project_id,
            "external_id": external_id,
            "task_id": event.task_id,
        }
        if terminal_context:
            # Only include non-null terminal values
            for key, value in terminal_context.items():
                if value is not None:
                    metadata[f"terminal_{key}"] = value

        return HookResponse(
            decision="allow",
            context="\n".join(context_parts) if context_parts else None,
            system_message=system_message,
            metadata=metadata,
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

    def _build_skill_injection_context(self, parent_session_id: str | None = None) -> str | None:
        """Build skill injection context for session-start.

        Combines alwaysApply skills with skills restored from parent session.

        Args:
            parent_session_id: Optional parent session ID to restore skills from

        Returns context string with available skills if injection is enabled,
        or None if disabled.
        """
        # Skip if no skill manager or config
        if not self._skill_manager or not self._skills_config:
            return None

        # Check if injection is enabled
        if not self._skills_config.inject_core_skills:
            return None

        # Check injection format
        if self._skills_config.injection_format == "none":
            return None

        # Get alwaysApply skills
        try:
            core_skills = self._skill_manager.discover_core_skills()
            always_apply_skills = [s for s in core_skills if s.is_always_apply()]

            # Get restored skills from parent session
            restored_skills = self._restore_skills_from_parent(parent_session_id)

            # Combine: alwaysApply skills + any additional restored skills
            skill_names = [s.name for s in always_apply_skills]
            for skill_name in restored_skills:
                if skill_name not in skill_names:
                    skill_names.append(skill_name)

            if not skill_names:
                return None

            # Build context based on format
            if self._skills_config.injection_format == "summary":
                return (
                    "\n## Available Skills\n"
                    f"The following skills are always available: {', '.join(skill_names)}\n"
                    "Use the /skill-name syntax to invoke them."
                )
            elif self._skills_config.injection_format == "full":
                parts = ["\n## Available Skills\n"]
                # Build a map of always_apply skills for quick lookup
                always_apply_map = {s.name: s for s in always_apply_skills}
                # Iterate over combined skill_names list (always_apply + restored)
                for skill_name in skill_names:
                    parts.append(f"### {skill_name}")
                    # Get description from always_apply skill if available
                    if skill_name in always_apply_map:
                        skill = always_apply_map[skill_name]
                        if skill.description:
                            parts.append(skill.description)
                    parts.append("")
                return "\n".join(parts)
            else:
                return None

        except Exception as e:
            self.logger.warning(f"Failed to build skill injection context: {e}")
            return None

    def _restore_skills_from_parent(self, parent_session_id: str | None) -> list[str]:
        """Restore active skills from parent session's handoff context.

        Args:
            parent_session_id: Parent session ID to restore from

        Returns:
            List of skill names from the parent session
        """
        if not parent_session_id or not self._session_storage:
            return []

        try:
            parent = self._session_storage.get(parent_session_id)
            if not parent:
                return []

            compact_md = getattr(parent, "compact_markdown", None)
            if not compact_md:
                return []

            # Parse active skills from markdown
            # Format: "### Active Skills\nSkills available: skill1, skill2, skill3"
            import re

            match = re.search(r"### Active Skills\s*\nSkills available:\s*([^\n]+)", compact_md)
            if match:
                skills_str = match.group(1).strip()
                skills = [s.strip() for s in skills_str.split(",") if s.strip()]
                self.logger.debug(f"Restored {len(skills)} skills from parent session")
                return skills

            return []

        except Exception as e:
            self.logger.warning(f"Failed to restore skills from parent: {e}")
            return []

    # ==================== AGENT HANDLERS ====================

    def handle_before_agent(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_AGENT event (user prompt submit)."""
        input_data = event.data
        prompt = input_data.get("prompt", "")
        transcript_path = input_data.get("transcript_path")
        session_id = event.metadata.get("_platform_session_id")

        context_parts = []

        if session_id:
            self.logger.debug(f"BEFORE_AGENT: session {session_id}")
            self.logger.debug(f"   Prompt: {prompt[:100]}...")

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
                if wf_response.decision != "allow":
                    return wf_response
                if wf_response.context:
                    return wf_response
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(decision="allow")

    # ==================== TOOL HANDLERS ====================

    def handle_before_tool(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_TOOL event."""
        input_data = event.data
        tool_name = input_data.get("tool_name", "unknown")
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"BEFORE_TOOL: {tool_name}, session {session_id}")
        else:
            self.logger.debug(f"BEFORE_TOOL: {tool_name}")

        context_parts = []

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

    def handle_after_tool(self, event: HookEvent) -> HookResponse:
        """Handle AFTER_TOOL event."""
        input_data = event.data
        tool_name = input_data.get("tool_name", "unknown")
        session_id = event.metadata.get("_platform_session_id")
        is_failure = event.metadata.get("is_failure", False)

        status = "FAIL" if is_failure else "OK"
        if session_id:
            self.logger.debug(f"AFTER_TOOL [{status}]: {tool_name}, session {session_id}")

            # Track edits for session high-water mark
            # Only if tool succeeded, matches edit tools, and session has claimed a task
            # Skip .gobby/ internal files (tasks.jsonl, memories.jsonl, etc.)
            tool_input = input_data.get("tool_input", {})
            file_path = tool_input.get("file_path", "")
            is_gobby_internal = "/.gobby/" in file_path or file_path.startswith(".gobby/")

            if (
                not is_failure
                and tool_name
                and tool_name.lower() in EDIT_TOOLS
                and not is_gobby_internal
                and self._session_storage
                and self._task_manager
            ):
                try:
                    # Check if session has any claimed tasks in progress
                    claimed_tasks = self._task_manager.list_tasks(
                        assignee=session_id, status="in_progress", limit=1
                    )
                    if claimed_tasks:
                        self._session_storage.mark_had_edits(session_id)
                        self.logger.debug(f"Marked session {session_id} as had_edits")
                except Exception as e:
                    self.logger.warning(f"Failed to track edit history: {e}")

        else:
            self.logger.debug(f"AFTER_TOOL [{status}]: {tool_name}")

        context_parts = []

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

    # ==================== STOP HANDLER ====================

    def handle_stop(self, event: HookEvent) -> HookResponse:
        """Handle STOP event (Claude Code only)."""
        session_id = event.metadata.get("_platform_session_id")
        cli_source = event.source.value

        self.logger.debug(f"STOP: session {session_id}, cli={cli_source}")

        # Execute lifecycle workflow triggers for on_stop
        if self._workflow_handler:
            try:
                wf_response = self._workflow_handler.handle_all_lifecycles(event)
                if wf_response.decision != "allow":
                    return wf_response
                if wf_response.context:
                    return wf_response
            except Exception as e:
                self.logger.error(f"Failed to execute lifecycle workflows: {e}", exc_info=True)

        return HookResponse(decision="allow")

    # ==================== COMPACT HANDLER ====================

    def handle_pre_compact(self, event: HookEvent) -> HookResponse:
        """Handle PRE_COMPACT event.

        Note: Gemini fires PreCompress constantly during normal operation,
        unlike Claude which fires it only when approaching context limits.
        We skip handoff logic and workflow execution for Gemini to avoid
        excessive state changes and workflow interruptions.
        """
        from gobby.hooks.events import SessionSource

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

    # ==================== SUBAGENT HANDLERS ====================

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

    # ==================== NOTIFICATION HANDLER ====================

    def handle_notification(self, event: HookEvent) -> HookResponse:
        """Handle NOTIFICATION event."""
        input_data = event.data
        notification_type = (
            input_data.get("notification_type")
            or input_data.get("notificationType")
            or input_data.get("type")
            or "general"
        )
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"NOTIFICATION ({notification_type}): session {session_id}")
            if self._session_manager:
                try:
                    self._session_manager.update_session_status(session_id, "paused")
                except Exception as e:
                    self.logger.warning(f"Failed to update session status: {e}")
        else:
            self.logger.debug(f"NOTIFICATION ({notification_type})")

        return HookResponse(decision="allow")

    # ==================== PERMISSION HANDLER ====================

    def handle_permission_request(self, event: HookEvent) -> HookResponse:
        """Handle PERMISSION_REQUEST event (Claude Code only)."""
        input_data = event.data
        session_id = event.metadata.get("_platform_session_id")
        permission_type = input_data.get("permission_type", "unknown")

        if session_id:
            self.logger.debug(f"PERMISSION_REQUEST ({permission_type}): session {session_id}")
        else:
            self.logger.debug(f"PERMISSION_REQUEST ({permission_type})")

        return HookResponse(decision="allow")

    # ==================== GEMINI-ONLY HANDLERS ====================

    def handle_before_tool_selection(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_TOOL_SELECTION event (Gemini only)."""
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"BEFORE_TOOL_SELECTION: session {session_id}")
        else:
            self.logger.debug("BEFORE_TOOL_SELECTION")

        return HookResponse(decision="allow")

    def handle_before_model(self, event: HookEvent) -> HookResponse:
        """Handle BEFORE_MODEL event (Gemini only)."""
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"BEFORE_MODEL: session {session_id}")
        else:
            self.logger.debug("BEFORE_MODEL")

        return HookResponse(decision="allow")

    def handle_after_model(self, event: HookEvent) -> HookResponse:
        """Handle AFTER_MODEL event (Gemini only)."""
        session_id = event.metadata.get("_platform_session_id")

        if session_id:
            self.logger.debug(f"AFTER_MODEL: session {session_id}")
        else:
            self.logger.debug("AFTER_MODEL")

        return HookResponse(decision="allow")


__all__ = ["EventHandlers"]
