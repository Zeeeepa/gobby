"""Claude LLM data models.

Dataclasses and type aliases for Claude tool calls and streaming events.
Extracted from src/gobby/llm/claude.py as part of the Strangler Fig
decomposition.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Represents a tool call made during generation."""

    tool_name: str
    """Full tool name (e.g., mcp__gobby-tasks__create_task)."""

    server_name: str
    """Extracted server name from the tool (e.g., gobby-tasks)."""

    arguments: dict[str, Any]
    """Arguments passed to the tool."""

    result: str | None = None
    """Result returned by the tool, if available."""


@dataclass
class MCPToolResult:
    """Result of generate_with_mcp_tools."""

    text: str
    """Final text output from the generation."""

    tool_calls: list[ToolCall] = field(default_factory=list)
    """List of tool calls made during generation."""


# Streaming event types for stream_with_mcp_tools
@dataclass
class TextChunk:
    """A chunk of text from the streaming response."""

    content: str
    """The text content."""


@dataclass
class ToolCallEvent:
    """Event when a tool is being called."""

    tool_call_id: str
    """Unique ID for this tool call."""

    tool_name: str
    """Full tool name (e.g., mcp__gobby-tasks__create_task)."""

    server_name: str
    """Extracted server name (e.g., gobby-tasks)."""

    arguments: dict[str, Any]
    """Arguments passed to the tool."""


@dataclass
class ToolResultEvent:
    """Event when a tool call completes."""

    tool_call_id: str
    """ID matching the original ToolCallEvent."""

    success: bool
    """Whether the tool call succeeded."""

    result: Any = None
    """Result data if successful."""

    error: str | None = None
    """Error message if failed."""


@dataclass
class DoneEvent:
    """Event when streaming is complete."""

    tool_calls_count: int
    """Total number of tool calls made."""

    cost_usd: float | None = None
    """Cost in USD if available."""

    duration_ms: float | None = None
    """Duration in milliseconds if available."""


@dataclass
class ThinkingEvent:
    """Event when the model is using extended thinking."""

    content: str = ""


# Union type for all streaming events
ChatEvent = TextChunk | ToolCallEvent | ToolResultEvent | DoneEvent | ThinkingEvent


