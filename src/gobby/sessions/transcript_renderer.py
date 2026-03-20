from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from gobby.sessions.transcripts.base import ParsedMessage, TokenUsage

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a tool execution."""

    content: Any
    content_type: str  # text/json/image/error
    truncated: bool = False
    metadata: dict[str, Any] | None = None


@dataclass
class RenderedToolCall:
    """A tool call and its result."""

    id: str
    tool_name: str
    server_name: str
    tool_type: str
    arguments: dict[str, Any]
    result: ToolResult | None = None
    status: str = "pending"
    error: str | None = None


@dataclass
class ContentBlock:
    """A block of content within a message."""

    type: str  # text, thinking, tool_chain, tool_reference, image, document, web_search_result, unknown
    content: Any | None = None  # content can be Any for pass-through types
    tool_calls: list[RenderedToolCall] | None = None
    raw: dict[str, Any] | None = None
    source_line: int | None = None
    block_type: str | None = None  # Original type for 'unknown' blocks


@dataclass
class RenderedMessage:
    """A grouped message ready for rendering."""

    id: str
    role: str
    content: str  # plain text summary
    timestamp: datetime
    content_blocks: list[ContentBlock] = field(default_factory=list)
    model: str | None = None
    usage: TokenUsage | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "content_blocks": [asdict(b) for b in self.content_blocks],
            "model": self.model,
            "usage": asdict(self.usage) if self.usage else None,
        }


@dataclass
class RenderState:
    """Accumulator for in-progress message turns."""

    current_message: RenderedMessage | None = None
    # Map of tool_use_id -> RenderedToolCall
    pending_tool_calls: dict[str, RenderedToolCall] = field(default_factory=dict)
    # Track seen content hashes to deduplicate Claude Code streaming duplicates
    seen_content: set[int] = field(default_factory=set)


def render_transcript(
    parsed_messages: Iterable[ParsedMessage], session_id: str | None = None
) -> list[RenderedMessage]:
    """
    Render a full transcript from a stream of parsed messages.

    Args:
        parsed_messages: Stream of flat ParsedMessage objects.
        session_id: Optional session identifier.

    Returns:
        List of grouped RenderedMessage objects.
    """
    state = RenderState()
    rendered_messages = []

    for msg in parsed_messages:
        completed, state = render_incremental([msg], state)
        rendered_messages.extend(completed)

    if state.current_message:
        rendered_messages.append(state.current_message)

    return rendered_messages


def render_incremental(
    new_messages: list[ParsedMessage], pending_state: RenderState
) -> tuple[list[RenderedMessage], RenderState]:
    """
    Process new messages and return completed turns.

    Args:
        new_messages: Batch of new ParsedMessage objects.
        pending_state: Current accumulation state.

    Returns:
        Tuple of (newly completed messages, updated state).
    """
    completed_messages = []
    state = pending_state

    for msg in new_messages:
        # 1. Classify role and detect hook feedback
        role = msg.role
        if _is_hook_feedback(msg):
            role = "system"

        # 2. Tool result pairing (can bypass turn logic if paired)
        is_tool_result = msg.content_type in ["tool_result", "mcp_tool_result"]
        if is_tool_result and msg.tool_use_id in state.pending_tool_calls:
            _process_message_block(msg, state)
            continue

        # 3. Detect turn boundary
        is_new_turn = False
        if not state.current_message:
            is_new_turn = True
        elif state.current_message.role != role:
            is_new_turn = True
        elif role in ["user", "system"]:
            is_new_turn = True

        if is_new_turn and state.current_message:
            completed_messages.append(state.current_message)
            state.current_message = None
            state.seen_content.clear()

        # 4. Initialize new message if needed
        if not state.current_message:
            state.current_message = RenderedMessage(
                id=f"{role}-{msg.timestamp.timestamp()}-{msg.index}",
                role=role,
                content="",
                timestamp=msg.timestamp,
                model=msg.model,
                usage=msg.usage,
            )

        # 5. Process block
        _process_message_block(msg, state)

    return completed_messages, state


def _is_hook_feedback(msg: ParsedMessage) -> bool:
    """Identify hook feedback messages that should be role='system'."""
    prefixes = [
        "Stop hook feedback:",
        "PreToolUse hook",
        "PostToolUse hook",
        "UserPromptSubmit hook",
    ]
    return any(msg.content.startswith(p) for p in prefixes)


def _strip_hook_context(content: str) -> str:
    """Remove <hook_context> tags from user messages."""
    if "<hook_context>" in content:
        return content.split("<hook_context>")[0].strip()
    return content


def _extract_server_name(tool_name: str | None) -> str:
    """Extract server name from tool name (mcp__server__tool -> server)."""
    if not tool_name:
        return "unknown"
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        if len(parts) >= 3:
            return parts[1]
    return "unknown"


def _process_message_block(msg: ParsedMessage, state: RenderState) -> None:
    """Integrate a ParsedMessage into the current RenderedMessage or pair as tool result."""

    # Tool Result Pairing
    if msg.content_type in ["tool_result", "mcp_tool_result"]:
        if msg.tool_use_id and msg.tool_use_id in state.pending_tool_calls:
            tool_call = state.pending_tool_calls[msg.tool_use_id]
            tool_call.result = ToolResult(
                content=msg.tool_result or msg.content,
                content_type="json" if msg.tool_result else "text",
            )
            tool_call.status = "success"
            return

    if not state.current_message:
        return

    # Update metadata
    if msg.model and not state.current_message.model:
        state.current_message.model = msg.model
    if msg.usage and not state.current_message.usage:
        state.current_message.usage = msg.usage

    # Content Deduplication
    content_key = (msg.content_type, msg.content, msg.tool_use_id, msg.tool_name)
    content_hash = hash(content_key)
    if content_hash in state.seen_content:
        return
    state.seen_content.add(content_hash)

    # User message cleanup
    content: Any = msg.content
    if state.current_message.role == "user" and isinstance(content, str):
        content = _strip_hook_context(content)

    # Block Type Mapping
    original_type = msg.content_type
    block_type = original_type
    block_content: Any = content

    if block_type in ["tool_use", "mcp_tool_use"]:
        block_type = "tool_chain"
    elif block_type == "web_search_tool_result":
        block_type = "web_search_result"
        block_content = msg.tool_result or content
    elif block_type in ["text", "thinking", "tool_reference", "image", "document"]:
        pass  # Use as-is
    else:
        # Fallback for unknown types
        block_type = "unknown"

    # Merge consecutive blocks of same type if appropriate
    if (
        state.current_message.content_blocks
        and state.current_message.content_blocks[-1].type == block_type
        and block_type in ["text", "thinking"]
    ):
        last_block = state.current_message.content_blocks[-1]
        if isinstance(last_block.content, str) and isinstance(block_content, str):
            last_block.content += block_content
    else:
        # Create new block
        block = ContentBlock(
            type=block_type,
            content=block_content if block_type != "tool_chain" else None,
            source_line=msg.index,
        )

        if block_type == "unknown":
            block.block_type = original_type
            block.raw = msg.raw_json

        if block_type == "tool_chain":
            tool_call = RenderedToolCall(
                id=msg.tool_use_id or f"call-{msg.index}",
                tool_name=msg.tool_name or "unknown",
                server_name=_extract_server_name(msg.tool_name),
                tool_type="mcp",
                arguments=msg.tool_input or {},
            )
            block.tool_calls = [tool_call]
            if msg.tool_use_id:
                state.pending_tool_calls[msg.tool_use_id] = tool_call

        state.current_message.content_blocks.append(block)

    # Update summary content
    if msg.content_type == "text" and state.current_message.role != "system":
        if isinstance(block_content, str):
            state.current_message.content += block_content
