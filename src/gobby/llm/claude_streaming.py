"""Claude streaming logic.

Async generator for streaming Claude Agent SDK responses with MCP tools.
Extracted from ClaudeLLMProvider.stream_with_mcp_tools() as part of the
Strangler Fig decomposition.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from gobby.llm.claude_models import (
    ChatEvent,
    DoneEvent,
    TextChunk,
    ToolCallEvent,
    ToolResultEvent,
    resolve_model_id,
)

logger = logging.getLogger(__name__)


def parse_server_name(full_tool_name: str) -> str:
    """Extract server name from mcp__{server}__{tool} format."""
    if full_tool_name.startswith("mcp__"):
        parts = full_tool_name.split("__")
        if len(parts) >= 2:
            return parts[1]
    return "builtin"


async def stream_with_mcp_tools(
    cli_path: str,
    prompt: str,
    allowed_tools: list[str],
    system_prompt: str | None = None,
    model: str | None = None,
    max_turns: int = 10,
) -> AsyncIterator[ChatEvent]:
    """
    Stream generation with MCP tools, yielding events as they occur.

    This is a standalone async generator that handles the Claude Agent SDK
    query loop. The caller is responsible for auth mode checks and CLI path
    verification.

    Args:
        cli_path: Path to the Claude CLI binary.
        prompt: User prompt to process.
        allowed_tools: List of allowed MCP tool patterns.
        system_prompt: Optional system prompt.
        model: Optional model override (default: claude-sonnet-4-5).
        max_turns: Maximum number of agentic turns (default: 10).

    Yields:
        ChatEvent: One of TextChunk, ToolCallEvent, ToolResultEvent, or DoneEvent.
    """
    # Build mcp_servers config - use .mcp.json if gobby tools requested
    mcp_servers_config: dict[str, Any] | str | None = None

    if any("gobby" in t for t in allowed_tools):
        cwd_config = Path.cwd() / ".mcp.json"
        if cwd_config.exists():
            mcp_servers_config = str(cwd_config)
        else:
            gobby_root = Path(__file__).parent.parent.parent.parent
            gobby_config = gobby_root / ".mcp.json"
            if gobby_config.exists():
                mcp_servers_config = str(gobby_config)

    # Configure Claude Agent SDK with MCP tools
    options = ClaudeAgentOptions(
        system_prompt=system_prompt or "You are Gobby, a helpful assistant with access to tools.",
        max_turns=max_turns,
        model=resolve_model_id(model or "claude-sonnet-4-5"),
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions",
        cli_path=cli_path,
        mcp_servers=mcp_servers_config if mcp_servers_config is not None else {},
    )

    tool_calls_count = 0
    pending_tool_calls: dict[str, str] = {}  # Map tool_use_id -> tool_name
    needs_spacing_before_text = False  # Track if we need spacing before text

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                # Final result - extract metadata
                cost_usd = getattr(message, "total_cost_usd", None)
                duration_ms = getattr(message, "duration_ms", None)
                yield DoneEvent(
                    tool_calls_count=tool_calls_count,
                    cost_usd=cost_usd,
                    duration_ms=duration_ms,
                )

            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # Add spacing before text that follows tool calls/results
                        # This ensures proper paragraph separation in the UI
                        text = block.text
                        if needs_spacing_before_text and text:
                            # Ensure we have a proper paragraph break (double newline)
                            # even if the text starts with a single newline
                            text = text.lstrip("\n")
                            if text:
                                text = "\n\n" + text
                        yield TextChunk(content=text)
                        needs_spacing_before_text = False
                    elif isinstance(block, ToolUseBlock):
                        tool_calls_count += 1
                        server_name = parse_server_name(block.name)
                        pending_tool_calls[block.id] = block.name
                        yield ToolCallEvent(
                            tool_call_id=block.id,
                            tool_name=block.name,
                            server_name=server_name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        )

            elif isinstance(message, UserMessage):
                # UserMessage may contain tool results
                if isinstance(message.content, list):
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            # Determine success based on is_error attribute
                            is_error = getattr(block, "is_error", False)
                            yield ToolResultEvent(
                                tool_call_id=block.tool_use_id,
                                success=not is_error,
                                result=block.content if not is_error else None,
                                error=str(block.content) if is_error else None,
                            )
                            needs_spacing_before_text = True

    except ExceptionGroup as eg:
        errors = [f"{type(exc).__name__}: {exc}" for exc in eg.exceptions]
        yield TextChunk(content=f"Generation failed: {'; '.join(errors)}")
        yield DoneEvent(tool_calls_count=tool_calls_count)
    except Exception as e:
        logger.error(f"Failed to stream with MCP tools: {e}", exc_info=True)
        yield TextChunk(content=f"Generation failed: {e}")
        yield DoneEvent(tool_calls_count=tool_calls_count)
