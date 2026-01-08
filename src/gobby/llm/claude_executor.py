"""
Claude implementation of AgentExecutor.

Supports multiple auth modes:
- api_key: Direct Anthropic API with API key
- subscription: Claude Agent SDK with CLI (Pro/Team subscriptions)
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import shutil
from collections.abc import Callable
from typing import Any, Literal

import anthropic

from gobby.llm.executor import (
    AgentExecutor,
    AgentResult,
    ToolCallRecord,
    ToolHandler,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger(__name__)

# Auth mode type
ClaudeAuthMode = Literal["api_key", "subscription"]


class ClaudeExecutor(AgentExecutor):
    """
    Claude implementation of AgentExecutor.

    Supports two authentication modes:
    - api_key: Uses the Anthropic API directly with an API key
    - subscription: Uses Claude Agent SDK with CLI for Pro/Team subscriptions

    The executor implements a proper agentic loop:
    1. Send prompt to Claude with tool schemas
    2. When Claude requests a tool, call tool_handler
    3. Send tool result back to Claude
    4. Repeat until Claude stops requesting tools or limits are reached

    Example:
        >>> executor = ClaudeExecutor(auth_mode="api_key", api_key="sk-ant-...")
        >>> result = await executor.run(
        ...     prompt="Create a task",
        ...     tools=[ToolSchema(name="create_task", ...)],
        ...     tool_handler=my_handler,
        ... )
    """

    _client: anthropic.AsyncAnthropic | None
    _cli_path: str

    def __init__(
        self,
        auth_mode: ClaudeAuthMode = "api_key",
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
    ):
        """
        Initialize ClaudeExecutor.

        Args:
            auth_mode: Authentication mode ("api_key" or "subscription").
            api_key: Anthropic API key (required for api_key mode).
            default_model: Default model to use if not specified in run().
        """
        self.auth_mode = auth_mode
        self.default_model = default_model
        self.logger = logger
        self._client = None
        self._cli_path = ""

        if auth_mode == "api_key":
            # Use provided key or fall back to environment variable
            key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError(
                    "API key required for api_key mode. "
                    "Provide api_key parameter or set ANTHROPIC_API_KEY env var."
                )
            self._client = anthropic.AsyncAnthropic(api_key=key)
        elif auth_mode == "subscription":
            # Verify Claude CLI is available for subscription mode
            cli_path = shutil.which("claude")
            if not cli_path:
                raise ValueError(
                    "Claude CLI not found in PATH. Install Claude Code for subscription mode."
                )
            self._cli_path = cli_path
        else:
            raise ValueError(f"Unknown auth_mode: {auth_mode}")

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "claude"

    def _convert_tools_to_anthropic_format(
        self, tools: list[ToolSchema]
    ) -> list[anthropic.types.ToolParam]:
        """Convert ToolSchema list to Anthropic API format."""
        anthropic_tools: list[anthropic.types.ToolParam] = []
        for tool in tools:
            # input_schema must have "type": "object" at minimum
            input_schema: dict[str, Any] = {"type": "object", **tool.input_schema}
            anthropic_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": input_schema,
                }
            )
        return anthropic_tools

    async def run(
        self,
        prompt: str,
        tools: list[ToolSchema],
        tool_handler: ToolHandler,
        system_prompt: str | None = None,
        model: str | None = None,
        max_turns: int = 10,
        timeout: float = 120.0,
    ) -> AgentResult:
        """
        Execute an agentic loop with tool calling.

        Runs Claude with the given prompt, calling tools via tool_handler
        until completion, max_turns, or timeout.

        Args:
            prompt: The user prompt to process.
            tools: List of available tools with their schemas.
            tool_handler: Callback to execute tool calls.
            system_prompt: Optional system prompt.
            model: Optional model override.
            max_turns: Maximum turns before stopping (default: 10).
            timeout: Maximum execution time in seconds (default: 120.0).

        Returns:
            AgentResult with output, status, and tool call records.
        """
        if self.auth_mode == "api_key":
            return await self._run_with_api(
                prompt=prompt,
                tools=tools,
                tool_handler=tool_handler,
                system_prompt=system_prompt,
                model=model or self.default_model,
                max_turns=max_turns,
                timeout=timeout,
            )
        else:
            return await self._run_with_sdk(
                prompt=prompt,
                tools=tools,
                tool_handler=tool_handler,
                system_prompt=system_prompt,
                model=model or self.default_model,
                max_turns=max_turns,
                timeout=timeout,
            )

    async def _run_with_api(
        self,
        prompt: str,
        tools: list[ToolSchema],
        tool_handler: ToolHandler,
        system_prompt: str | None,
        model: str,
        max_turns: int,
        timeout: float,
    ) -> AgentResult:
        """Run using direct Anthropic API."""
        if self._client is None:
            return AgentResult(
                output="",
                status="error",
                error="Anthropic client not initialized",
                turns_used=0,
            )

        tool_calls: list[ToolCallRecord] = []
        anthropic_tools = self._convert_tools_to_anthropic_format(tools)

        # Build initial messages
        messages: list[anthropic.types.MessageParam] = [{"role": "user", "content": prompt}]

        # Track turns in outer scope so timeout handler can access the count
        turns_counter = [0]

        async def _run_loop() -> AgentResult:
            nonlocal messages
            turns_used = 0
            final_output = ""
            client = self._client
            if client is None:
                raise RuntimeError("ClaudeExecutor client not initialized")

            while turns_used < max_turns:
                turns_used += 1
                turns_counter[0] = turns_used

                # Call Claude
                try:
                    response = await client.messages.create(
                        model=model,
                        max_tokens=8192,
                        system=system_prompt or "You are a helpful assistant.",
                        messages=messages,
                        tools=anthropic_tools if anthropic_tools else [],
                    )
                except anthropic.APIError as e:
                    return AgentResult(
                        output="",
                        status="error",
                        tool_calls=tool_calls,
                        error=f"Anthropic API error: {e}",
                        turns_used=turns_used,
                    )

                # Process response
                assistant_content: list[anthropic.types.ContentBlockParam] = []
                tool_use_blocks: list[dict[str, Any]] = []

                for block in response.content:
                    if block.type == "text":
                        final_output = block.text
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        tool_use_blocks.append(
                            {
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                        assistant_content.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": dict(block.input) if block.input else {},
                            }
                        )

                # Add assistant message to history
                messages.append({"role": "assistant", "content": assistant_content})

                # If no tool use, we're done
                if not tool_use_blocks:
                    return AgentResult(
                        output=final_output,
                        status="success",
                        tool_calls=tool_calls,
                        turns_used=turns_used,
                    )

                # Handle tool calls
                tool_results: list[anthropic.types.ToolResultBlockParam] = []

                for tool_use in tool_use_blocks:
                    tool_name = tool_use["name"]
                    arguments = tool_use["input"] if isinstance(tool_use["input"], dict) else {}

                    # Record the tool call
                    record = ToolCallRecord(
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                    tool_calls.append(record)

                    # Execute via handler
                    try:
                        result = await tool_handler(tool_name, arguments)
                        record.result = result

                        # Format result for Claude
                        if result.success:
                            content = json.dumps(result.result) if result.result else "Success"
                        else:
                            content = f"Error: {result.error}"

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use["id"],
                                "content": content,
                            }
                        )
                    except Exception as e:
                        self.logger.error(f"Tool handler error for {tool_name}: {e}")
                        record.result = ToolResult(
                            tool_name=tool_name,
                            success=False,
                            error=str(e),
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use["id"],
                                "content": f"Error: {e}",
                                "is_error": True,
                            }
                        )

                # Add tool results to messages
                messages.append({"role": "user", "content": tool_results})

                # Check stop reason
                if response.stop_reason == "end_turn":
                    return AgentResult(
                        output=final_output,
                        status="success",
                        tool_calls=tool_calls,
                        turns_used=turns_used,
                    )

            # Max turns reached
            return AgentResult(
                output=final_output,
                status="partial",
                tool_calls=tool_calls,
                turns_used=turns_used,
            )

        # Run with timeout
        try:
            return await asyncio.wait_for(_run_loop(), timeout=timeout)
        except TimeoutError:
            return AgentResult(
                output="",
                status="timeout",
                tool_calls=tool_calls,
                error=f"Execution timed out after {timeout}s",
                turns_used=turns_counter[0],
            )

    async def _run_with_sdk(
        self,
        prompt: str,
        tools: list[ToolSchema],
        tool_handler: ToolHandler,
        system_prompt: str | None,
        model: str,
        max_turns: int,
        timeout: float,
    ) -> AgentResult:
        """
        Run using Claude Agent SDK with subscription auth.

        This mode uses the claude-agent-sdk which handles subscription
        authentication through the Claude CLI.
        """
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
            create_sdk_mcp_server,
            query,
        )

        tool_calls: list[ToolCallRecord] = []

        # Create in-process tool functions that call our handler
        # The SDK expects sync functions, so we'll use a wrapper
        def make_tool_func(tool_schema: ToolSchema) -> Callable[..., str]:
            """Create a tool function that calls our async handler."""

            def tool_func(**kwargs: Any) -> str:
                # Run the async handler - need to handle already-running loop
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is not None:
                    # We're in an async context, use run_coroutine_threadsafe
                    coro = tool_handler(tool_schema.name, kwargs)
                    future: concurrent.futures.Future[ToolResult] = (
                        asyncio.run_coroutine_threadsafe(coro, loop)
                    )
                    try:
                        result = future.result(timeout=30)
                    except concurrent.futures.TimeoutError:
                        return json.dumps({"error": "Tool execution timed out"})
                    except Exception as e:
                        return json.dumps({"error": str(e)})
                else:
                    # No running loop, use asyncio.run
                    coro = tool_handler(tool_schema.name, kwargs)
                    result = asyncio.run(coro)  # type: ignore[arg-type]

                # Record the call
                record = ToolCallRecord(
                    tool_name=tool_schema.name,
                    arguments=kwargs,
                    result=result,
                )
                tool_calls.append(record)

                if result.success:
                    return json.dumps(result.result) if result.result else "Success"
                else:
                    return json.dumps({"error": result.error})

            # Set function metadata for the SDK
            tool_func.__name__ = tool_schema.name
            tool_func.__doc__ = tool_schema.description
            return tool_func

        # Build tool functions
        tool_functions = [make_tool_func(t) for t in tools]

        # Create MCP server config with our tools
        mcp_server = create_sdk_mcp_server(
            name="gobby-executor",
            tools=tool_functions,
        )
        mcp_servers: dict[str, Any] = {"gobby-executor": mcp_server}

        # Build allowed tools list
        allowed_tools = [f"mcp__gobby-executor__{t.name}" for t in tools]

        # Configure SDK options
        options = ClaudeAgentOptions(
            system_prompt=system_prompt or "You are a helpful assistant.",
            max_turns=max_turns,
            model=model,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            cli_path=self._cli_path,
            mcp_servers=mcp_servers,
        )

        # Track turns in outer scope so timeout handler can access the count
        turns_counter = [0]

        async def _run_query() -> AgentResult:
            result_text = ""
            turns_used = 0

            try:
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, ResultMessage):
                        if message.result:
                            result_text = message.result
                    elif isinstance(message, AssistantMessage):
                        turns_used += 1
                        turns_counter[0] = turns_used
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                result_text = block.text
                            elif isinstance(block, ToolUseBlock):
                                self.logger.debug(
                                    f"ToolUseBlock: {block.name}, input={block.input}"
                                )
                    elif isinstance(message, UserMessage):
                        if isinstance(message.content, list):
                            for block in message.content:
                                if isinstance(block, ToolResultBlock):
                                    self.logger.debug(f"ToolResultBlock: {block.tool_use_id}")

                return AgentResult(
                    output=result_text,
                    status="success",
                    tool_calls=tool_calls,
                    turns_used=turns_used,
                )

            except Exception as e:
                self.logger.error(f"SDK execution failed: {e}", exc_info=True)
                return AgentResult(
                    output="",
                    status="error",
                    tool_calls=tool_calls,
                    error=str(e),
                    turns_used=0,
                )

        # Run with timeout
        try:
            return await asyncio.wait_for(_run_query(), timeout=timeout)
        except TimeoutError:
            return AgentResult(
                output="",
                status="timeout",
                tool_calls=tool_calls,
                error=f"Execution timed out after {timeout}s",
                turns_used=turns_counter[0],
            )
