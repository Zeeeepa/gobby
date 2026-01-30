"""
Transcript analyzer for autonomous session handoff.

Extracts structured context from session transcripts to support
autonomous continuity without relying on manual /clear boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from gobby.sessions.transcripts.base import TranscriptParser
from gobby.sessions.transcripts.claude import ClaudeTranscriptParser

logger = logging.getLogger(__name__)


@dataclass
class HandoffContext:
    """Structured context for autonomous handoff."""

    active_gobby_task: dict[str, Any] | None = None
    todo_state: list[dict[str, Any]] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    git_commits: list[dict[str, Any]] = field(default_factory=list)
    git_status: str = ""
    initial_goal: str = ""
    recent_activity: list[str] = field(default_factory=list)
    key_decisions: list[str] | None = None
    active_worktree: dict[str, Any] | None = None
    """Worktree context if session is operating in a worktree."""
    # Note: active_skills field removed - redundant with _build_skill_injection_context()
    # which already handles skill restoration on session start


class TranscriptAnalyzer:
    """
    Transcript analysis for handoff context.

    Primary: Claude Code
    Extensible: Other CLIs via TranscriptParser protocol
    """

    def __init__(self, parser: TranscriptParser | None = None):
        """
        Initialize TranscriptAnalyzer.

        Args:
            parser: Optional specific parser. Defaults to ClaudeTranscriptParser.
        """
        self.parser = parser or ClaudeTranscriptParser()

    def extract_handoff_context(
        self, turns: list[dict[str, Any]], max_turns: int = 150
    ) -> HandoffContext:
        """
        Extract context for autonomous handoff.

        Analyzes recent turns to find:
        - Active task state from gobby-tasks calls
        - TodoWrite state from Claude's internal tracking (if available in transcript)
        - Files modified from Edit/Write/Bash calls
        - Git commits from Bash calls
        - The original user goal (first user message)
        - Recent tool activity summaries

        Args:
            turns: List of transcript turns (dicts)
            max_turns: Maximum number of turns to look back for context

        Returns:
            HandoffContext object populated with extracted data
        """
        context = HandoffContext()

        if not turns:
            return context

        # 1. Extract Initial Goal (First User Message)
        # We scan from the beginning to find the first user message
        for turn in turns:
            if turn.get("type") == "user":
                msg = turn.get("message", {})
                context.initial_goal = str(msg.get("content", "")).strip()
                break

        # 2. Analyze Recent Activity (Scan backwards)
        # We look at the last `max_turns` or less
        relevant_turns = turns[-max_turns:] if len(turns) > max_turns else turns

        # Track what we've found to avoid duplicates where appropriate
        found_active_task = False
        modified_files_set: set[str] = set()

        for turn in reversed(relevant_turns):
            message = turn.get("message", {})
            content_blocks = message.get("content", [])

            # Handle Claude's content block list format
            if isinstance(content_blocks, list):
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue

                    block_type = block.get("type")

                    # Check for Tool Use
                    if block_type == "tool_use":
                        self._analyze_tool_use(
                            block, context, found_active_task, modified_files_set
                        )
                        if (
                            block.get("name") == "mcp_call_tool"
                            and block.get("input", {}).get("server_name") == "gobby-tasks"
                        ):
                            # We found a task interaction, but we want the *latest* active one
                            # The helper _analyze_tool_use will handle extraction,
                            # we just mark we found some task activity if needed.
                            pass

        context.files_modified = sorted(modified_files_set)

        # 3. Extract TodoWrite state
        context.todo_state = self._extract_todowrite(relevant_turns)

        # 4. Recent Activity Summary (Last 10 calls)
        # Extract meaningful details from recent tool uses
        recent_tools = []
        count = 0
        for turn in reversed(turns):
            if count >= 10:
                break
            message = turn.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        description = self._format_tool_description(block)
                        recent_tools.append(description)
                        count += 1
                        if count >= 10:
                            break
        context.recent_activity = recent_tools

        return context

    def _analyze_tool_use(
        self,
        block: dict[str, Any],
        context: HandoffContext,
        found_active_task: bool,
        modified_files_set: set[str],
    ) -> None:
        """Helper to analyze a single tool use block."""
        tool_name = block.get("name")
        tool_input = block.get("input", {})

        # -- Gobby Tasks --
        if tool_name == "mcp_call_tool":
            server = tool_input.get("server_name")
            tool = tool_input.get("tool_name")
            args = tool_input.get("arguments", {})

            if server == "gobby-tasks":
                # We want the most recent task interaction that implies working on a task
                # e.g., create_task, update_task, get_task
                if not context.active_gobby_task:
                    # Heuristic: If we see a task interaction, it might be the active task
                    # especially if it's get_task or update_task
                    task_id = args.get("task_id") or args.get("id")
                    if task_id:
                        context.active_gobby_task = {
                            "id": task_id,
                            "action": tool,
                            # We don't have the full task object here, just the ID and intent
                            # The injection template might need to fetch it or we assume
                            # the ID is enough for the user to know.
                            # Ideally, we'd have the title, but we can't get it from the tool input easily
                            # unless it was a create/update with title.
                            # For now, store what we have.
                            "title": args.get("title", f"Task {task_id}"),
                        }

        # -- File Modifications --
        elif tool_name in ("Edit", "Write", "Replace", "replace_file_content", "write_to_file"):
            # Claude Code uses Edit/Write? Antigravity uses write_to_file/replace_file_content
            # We should support both if possible or stick to what we expect Claude to use.
            # Claude Code typically uses `grep_search`, `view_file`, `edit_file`?
            # Let's assume standard names or generic ones.
            path = (
                tool_input.get("file_path")
                or tool_input.get("TargetFile")
                or tool_input.get("path")
            )
            if path:
                modified_files_set.add(path)

        # -- Git Commits --
        elif tool_name == "Bash":
            command = tool_input.get("command", "")
            if "git commit" in command:
                # Attempt to extract message
                # This is a bit brittle, but useful context
                context.git_commits.append(
                    {
                        "command": command,
                        "timestamp": datetime.now(UTC).isoformat(),  # Approx time
                    }
                )

    def _format_tool_description(self, block: dict[str, Any]) -> str:
        """
        Format a tool use block into a human-readable description.

        Extracts meaningful details instead of just showing the tool name.

        Args:
            block: Tool use block with 'name' and 'input' keys

        Returns:
            Human-readable description of what the tool call did
        """
        tool_name = block.get("name", "unknown")
        tool_input = block.get("input", {})

        # MCP tool calls - show server.tool
        if tool_name in ("mcp__gobby__call_tool", "mcp_call_tool"):
            server = tool_input.get("server_name", "unknown")
            tool = tool_input.get("tool_name", "unknown")
            return f"Called {server}.{tool}"

        # Bash - show the command (truncated)
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            # Truncate long commands
            if len(command) > 60:
                command = command[:57] + "..."
            return f"Ran: {command}"

        # Edit/Write - show the file path
        if tool_name in ("Edit", "Write"):
            path = tool_input.get("file_path", "")
            if path:
                return f"{tool_name}: {path}"
            return f"Called {tool_name}"

        # Read - show the file path
        if tool_name == "Read":
            path = tool_input.get("file_path", "")
            if path:
                return f"Read: {path}"
            return "Called Read"

        # Glob - show the pattern
        if tool_name == "Glob":
            pattern = tool_input.get("pattern", "")
            if pattern:
                return f"Glob: {pattern}"
            return "Called Glob"

        # Grep - show the pattern
        if tool_name == "Grep":
            pattern = tool_input.get("pattern", "")
            if pattern:
                # Truncate long patterns
                if len(pattern) > 40:
                    pattern = pattern[:37] + "..."
                return f"Grep: {pattern}"
            return "Called Grep"

        # TodoWrite - show count
        if tool_name == "TodoWrite":
            todos = tool_input.get("todos", [])
            return f"TodoWrite: {len(todos)} items"

        # Task tool - show subagent type
        if tool_name == "Task":
            subagent = tool_input.get("subagent_type", "")
            desc = tool_input.get("description", "")
            if subagent:
                return f"Task ({subagent}): {desc}" if desc else f"Task ({subagent})"
            return f"Task: {desc}" if desc else "Called Task"

        # Default - just show the tool name
        return f"Called {tool_name}"

    def _extract_todowrite(self, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Extract the most recent TodoWrite state from transcript.

        Scans turns in reverse to find the last TodoWrite tool call and
        extracts the todos list.

        Args:
            turns: List of transcript turns to scan

        Returns:
            List of todo dicts with 'content' and 'status' keys, or empty list
        """
        for turn in reversed(turns):
            message = turn.get("message", {})
            content = message.get("content", [])

            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if block.get("name") == "TodoWrite":
                            tool_input = block.get("input", {})
                            todos = tool_input.get("todos", [])

                            if todos:
                                # Return the raw todo list for HandoffContext
                                return [
                                    {
                                        "content": todo.get("content", ""),
                                        "status": todo.get("status", "pending"),
                                    }
                                    for todo in todos
                                ]

        return []
