"""Handoff helper functions and tools for session management.

This module contains:
- Helper functions for formatting handoff context
- MCP tools for creating and retrieving handoffs
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.sessions.analyzer import HandoffContext


def _format_handoff_markdown(ctx: HandoffContext, notes: str | None = None) -> str:
    """
    Format HandoffContext as markdown for session handoff.

    Args:
        ctx: HandoffContext with extracted session data
        notes: Optional additional notes to include

    Returns:
        Formatted markdown string
    """
    sections: list[str] = ["## Continuation Context", ""]

    # Active task section
    if ctx.active_gobby_task:
        task = ctx.active_gobby_task
        sections.append("### Active Task")
        sections.append(f"**{task.get('title', 'Untitled')}** ({task.get('id', 'unknown')})")
        sections.append(f"Status: {task.get('status', 'unknown')}")
        sections.append("")

    # Todo state section
    if ctx.todo_state:
        sections.append("### In-Progress Work")
        for todo in ctx.todo_state:
            status = todo.get("status", "pending")
            marker = "x" if status == "completed" else ">" if status == "in_progress" else " "
            sections.append(f"- [{marker}] {todo.get('content', '')}")
        sections.append("")

    # Git commits section
    if ctx.git_commits:
        sections.append("### Commits This Session")
        for commit in ctx.git_commits:
            sections.append(f"- `{commit.get('hash', '')[:7]}` {commit.get('message', '')}")
        sections.append("")

    # Git status section
    if ctx.git_status:
        sections.append("### Uncommitted Changes")
        sections.append("```")
        sections.append(ctx.git_status)
        sections.append("```")
        sections.append("")

    # Files modified section
    if ctx.files_modified:
        sections.append("### Files Being Modified")
        for f in ctx.files_modified:
            sections.append(f"- {f}")
        sections.append("")

    # Initial goal section
    if ctx.initial_goal:
        sections.append("### Original Goal")
        sections.append(ctx.initial_goal)
        sections.append("")

    # Recent activity section
    if ctx.recent_activity:
        sections.append("### Recent Activity")
        for activity in ctx.recent_activity[-5:]:
            sections.append(f"- {activity}")
        sections.append("")

    # Notes section (if provided)
    if notes:
        sections.append("### Notes")
        sections.append(notes)
        sections.append("")

    return "\n".join(sections)


def _format_turns_for_llm(turns: list[dict[str, Any]]) -> str:
    """Format transcript turns for LLM analysis."""
    formatted: list[str] = []
    for i, turn in enumerate(turns):
        message = turn.get("message", {})
        role = message.get("role", "unknown")
        content = message.get("content", "")

        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[Tool: {block.get('name', 'unknown')}]")
            content = " ".join(text_parts)

        formatted.append(f"[Turn {i + 1} - {role}]: {content}")

    return "\n\n".join(formatted)
