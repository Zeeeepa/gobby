"""
Tool permission, approval, and plan mode logic for CodexChatSession.

Mirrors ChatSessionPermissionsMixin but returns Codex-compatible dicts
instead of Claude SDK PermissionResultAllow/PermissionResultDeny types.
No EnterPlanMode/ExitPlanMode interception (Codex doesn't have these tools).
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from fnmatch import fnmatch
from typing import Any

from gobby.servers.chat_session_helpers import (
    _BASH_WRITE_PATTERNS,
    _PLAN_FILE_PATTERN,
    _PLAN_MODE_BLOCKED_TOOLS,
    PendingApproval,
)

logger = logging.getLogger(__name__)


class CodexChatSessionPermissionsMixin:
    """Tool permission, approval, and plan mode logic for CodexChatSession.

    Returns Codex-compatible decision dicts:
    {"decision": "accept"} or {"decision": "decline", "reason": "..."}

    Attributes set by the concrete dataclass (declared here for type-checking)."""

    # Attribute type stubs — actual fields live on the CodexChatSession dataclass
    conversation_id: str
    chat_mode: str
    _on_mode_changed: Callable[[str, str], Awaitable[None]] | None
    _on_pre_tool: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None
    _pending_question: dict[str, Any] | None
    _pending_answers: dict[str, str] | None
    _pending_answer_event: asyncio.Event | None
    _approved_tools: set[str]
    _on_approved_tools_persist: Callable[[set[str]], None] | None
    _tool_approval_config: Any | None
    _tool_approval_callback: Any | None
    _plan_approved: bool
    _plan_feedback: str | None
    _plan_file_path: str | None
    _on_mode_persist: Callable[[str], None] | None
    _pending_approval: PendingApproval | None
    _pending_approval_decision: str | None
    _pending_approval_event: asyncio.Event | None

    # Patterns that indicate dangerous bash commands
    _DANGEROUS_BASH_PATTERNS = re.compile(
        r"(?:^|[;&|]\s*)(?:sudo|rm|chmod|chown|kill|killall|mkfs|dd|reboot|shutdown|halt|"
        r"systemctl|service|init|"
        r"mv\s+/|>\s*/|git\s+(?:push|reset\s+--hard|clean\s+-f))\b"
        r"|(?:curl|wget)\s+.*\|\s*(?:ba)?sh\b",
        re.MULTILINE,
    )

    async def _check_tool_permission(
        self,
        tool_name: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Check tool permission for Codex approval handler.

        Returns {"decision": "accept"} or {"decision": "decline", "reason": "..."}.
        """
        # Plan mode: block write tools
        if self.chat_mode == "plan" and not self._plan_approved:
            if tool_name in _PLAN_MODE_BLOCKED_TOOLS:
                # Allow writes to plan files
                if tool_name in ("Write", "Edit"):
                    file_path = input_data.get("file_path", "")
                    if _PLAN_FILE_PATTERN.match(file_path):
                        self._plan_file_path = file_path
                        return {"decision": "accept"}
                return {
                    "decision": "decline",
                    "reason": (
                        f"Plan mode is active — {tool_name} is blocked. "
                        "Present your plan to the user for approval before making changes."
                    ),
                }
            if tool_name == "Bash" and self._is_write_bash(input_data):
                return {
                    "decision": "decline",
                    "reason": (
                        "Plan mode is active — write/destructive Bash commands are blocked. "
                        "Present your plan to the user for approval before making changes."
                    ),
                }

        # Fire session-lifecycle evaluation for tool blocking
        if self._on_pre_tool:
            resp = await self._on_pre_tool({"tool_name": tool_name, "tool_input": input_data})
            if resp and resp.get("decision") == "block":
                return {
                    "decision": "decline",
                    "reason": resp.get("reason", "Blocked by session lifecycle"),
                }

        # Check tool approval
        if self._needs_tool_approval(tool_name):
            return await self._wait_for_tool_approval(tool_name, input_data)

        # In accept_edits mode, auto-approved Bash still needs danger check
        if self.chat_mode == "accept_edits" and tool_name == "Bash":
            if self._is_dangerous_bash(input_data):
                return await self._wait_for_tool_approval(tool_name, input_data)

        return {"decision": "accept"}

    def provide_answer(self, answers: dict[str, str]) -> None:
        """Provide answers to a pending question, unblocking the callback."""
        self._pending_answers = answers
        if self._pending_answer_event is not None:
            self._pending_answer_event.set()

    @property
    def has_pending_question(self) -> bool:
        """Whether a question is currently awaiting a response."""
        return self._pending_question is not None

    def _needs_tool_approval(self, tool_name: str) -> bool:
        """Check if a tool requires user approval based on chat mode and config."""
        mode = self.chat_mode

        if mode == "bypass":
            return False

        if mode == "accept_edits":
            if tool_name in self._approved_tools:
                return False
            if tool_name in ("Edit", "Write", "NotebookEdit"):
                return False
            if tool_name == "Bash":
                return False
            return True

        config = self._tool_approval_config
        if config is None or not config.enabled:
            return False

        if tool_name in self._approved_tools:
            return False

        parts = tool_name.split("__")
        server_name = parts[1] if len(parts) >= 3 else ""
        short_tool = parts[-1] if parts else tool_name

        for policy in config.policies:
            if fnmatch(server_name, policy.server_pattern) and fnmatch(
                short_tool, policy.tool_pattern
            ):
                needs_approval: bool = policy.policy != "auto"
                return needs_approval

        default_needs: bool = config.default_policy != "auto"
        return default_needs

    def _is_dangerous_bash(self, input_data: dict[str, Any]) -> bool:
        """Check if a Bash command matches dangerous patterns."""
        command = input_data.get("command", "")
        if not command:
            return False
        return bool(self._DANGEROUS_BASH_PATTERNS.search(command))

    def _is_write_bash(self, input_data: dict[str, Any]) -> bool:
        """Check if a Bash command performs write/destructive operations (plan mode)."""
        command = input_data.get("command", "")
        if not command:
            return False
        return bool(_BASH_WRITE_PATTERNS.search(command))

    def set_chat_mode(self, mode: str) -> None:
        """Set chat mode, resetting plan state when entering plan mode."""
        self.chat_mode = mode
        if mode == "plan":
            self._plan_approved = False
            self._plan_feedback = None
            self._plan_file_path = None
        else:
            self._plan_approved = False
            self._plan_feedback = None
        if self._on_mode_persist:
            try:
                self._on_mode_persist(mode)
            except Exception as e:
                logger.warning(f"Failed to persist chat_mode={mode}: {e}")

    def approve_plan(self) -> None:
        """Mark the current plan as approved, unlocking write tools."""
        self._plan_approved = True

    def set_plan_feedback(self, feedback: str) -> None:
        """Store user feedback for plan revision."""
        self._plan_feedback = feedback

    def provide_plan_decision(self, decision: str) -> None:
        """Provide plan approval decision."""
        # Codex doesn't have ExitPlanMode tool — plan decisions are user-initiated only.
        # Transition mode directly on approval.
        if decision == "approve":
            self.set_chat_mode("accept_edits")
            # Set _plan_approved AFTER set_chat_mode (which clears it)
            self._plan_approved = True
        # No pending event to unblock since there's no ExitPlanMode tool

    @property
    def has_pending_plan(self) -> bool:
        """Whether a plan is awaiting approval. Always False for Codex (no ExitPlanMode)."""
        return False

    def _consume_plan_mode_context(self) -> str | None:
        """Return plan mode system context for context_prefix injection."""
        if self.chat_mode != "plan":
            return None

        if self._plan_approved:
            return (
                '<plan-mode status="approved">\n'
                "The user has approved your plan. You may now execute it.\n"
                "Write tools (Edit, Write, NotebookEdit, write Bash) are unblocked.\n"
                "</plan-mode>"
            )

        parts = [
            '<plan-mode status="active">',
            "You are in PLAN MODE. Your role is to research and design, not execute.",
            "",
            "ALLOWED: Read, Glob, Grep, read-only Bash (ls, cat, grep, git status/log/diff, find)",
            "BLOCKED: Edit, Write, NotebookEdit, write/destructive Bash (rm, mv, git add/commit/push, redirects)",
            "",
            "Present a structured plan with:",
            "1. Summary of changes needed",
            "2. Files to modify and what changes to make",
            "3. Implementation order",
            "4. Verification steps",
            "",
            "When your plan is complete, present it to the user.",
            "The user will approve or request changes via the chat UI.",
        ]

        if self._plan_feedback:
            parts.append("")
            parts.append(f"USER FEEDBACK on previous plan:\n{self._plan_feedback}")
            self._plan_feedback = None

        parts.append("</plan-mode>")
        return "\n".join(parts)

    async def _wait_for_tool_approval(
        self, tool_name: str, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Block until the user approves or rejects a tool call."""
        self._pending_approval = {
            "tool_name": tool_name,
            "arguments": input_data,
        }
        self._pending_approval_decision = None
        self._pending_approval_event = asyncio.Event()

        if self._tool_approval_callback:
            await self._tool_approval_callback(tool_name, input_data)

        try:
            await asyncio.wait_for(self._pending_approval_event.wait(), timeout=300.0)
        except TimeoutError:
            self._pending_approval_decision = "reject"
            logger.warning(
                "Tool approval timed out",
                extra={"tool": tool_name, "conversation_id": self.conversation_id},
            )

        decision = self._pending_approval_decision or "reject"

        self._pending_approval = None
        self._pending_approval_event = None
        self._pending_approval_decision = None

        if decision == "reject":
            return {"decision": "decline", "reason": f"User rejected tool call: {tool_name}"}

        if decision == "approve_always":
            self._approved_tools.add(tool_name)
            if self._on_approved_tools_persist:
                self._on_approved_tools_persist(self._approved_tools)
            return {"decision": "accept"}

        if decision == "approve":
            return {"decision": "accept"}

        return {"decision": "decline", "reason": f"User rejected tool call: {tool_name}"}

    def provide_approval(self, decision: str) -> None:
        """Provide approval decision for a pending tool call."""
        self._pending_approval_decision = decision
        if self._pending_approval_event is not None:
            self._pending_approval_event.set()

    async def sync_sdk_permission_mode(self) -> None:
        """No-op for Codex — permission mode is enforced via approval callbacks."""

    @property
    def has_pending_approval(self) -> bool:
        """Whether a tool approval is currently awaiting a response."""
        return self._pending_approval is not None
