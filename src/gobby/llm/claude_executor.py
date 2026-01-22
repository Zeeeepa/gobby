"""
Claude implementation of AgentExecutor for subscription mode only.

This executor uses the Claude Agent SDK with CLI for Pro/Team subscriptions.

Note: api_key mode is now routed through LiteLLMExecutor for unified cost tracking.
Use the resolver.create_executor() function which handles routing automatically.
"""

import asyncio
import concurrent.futures
import json
import logging
import shutil
from collections.abc import Callable
from typing import Any, Literal

from gobby.llm.executor import (
    AgentExecutor,
    AgentResult,
    ToolCallRecord,
    ToolHandler,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger(__name__)

# Auth mode type - subscription only, api_key routes through LiteLLM
ClaudeAuthMode = Literal["subscription"]


class ClaudeExecutor(AgentExecutor):
    """
    Claude implementation of AgentExecutor for subscription mode only.

    Uses Claude Agent SDK with CLI for Pro/Team subscriptions. This executor
    is for subscription-based authentication only.

    For api_key mode, use LiteLLMExecutor with provider="claude" which routes
    through anthropic/model-name for unified cost tracking.

    The executor implements a proper agentic loop:
    1. Send prompt to Claude with tool schemas via SDK
    2. When Claude requests a tool, call tool_handler
    3. Send tool result back to Claude
    4. Repeat until Claude stops requesting tools or limits are reached

    Example:
        >>> executor = ClaudeExecutor(auth_mode="subscription")
        >>> result = await executor.run(
        ...     prompt="Create a task",
        ...     tools=[ToolSchema(name="create_task", ...)],
        ...     tool_handler=my_handler,
        ... )
    """

    _cli_path: str

    def __init__(
        self,
        auth_mode: ClaudeAuthMode = "subscription",
        default_model: str = "claude-sonnet-4-20250514",
    ):
        """
        Initialize ClaudeExecutor for subscription mode.

        Args:
            auth_mode: Must be "subscription". API key mode is handled by LiteLLMExecutor.
            default_model: Default model to use if not specified in run().

        Raises:
            ValueError: If auth_mode is not "subscription" or Claude CLI not found.
        """
        if auth_mode != "subscription":
            raise ValueError(
                "ClaudeExecutor only supports subscription mode. "
                "For api_key mode, use LiteLLMExecutor with provider='claude'."
            )

        self.auth_mode = auth_mode
        self.default_model = default_model
        self.logger = logger
        self._cli_path = ""

        # Verify Claude CLI is available for subscription mode
        cli_path = shutil.which("claude")
        if not cli_path:
            raise ValueError(
                "Claude CLI not found in PATH. Install Claude Code for subscription mode."
            )
        self._cli_path = cli_path

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "claude"

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
        Execute an agentic loop with tool calling via Claude Agent SDK.

        Runs Claude with the given prompt using subscription-based authentication,
        calling tools via tool_handler until completion, max_turns, or timeout.

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
        return await self._run_with_sdk(
            prompt=prompt,
            tools=tools,
            tool_handler=tool_handler,
            system_prompt=system_prompt,
            model=model or self.default_model,
            max_turns=max_turns,
            timeout=timeout,
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
                        asyncio.run_coroutine_threadsafe(coro, loop)  # type: ignore[arg-type]
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
            tools=tool_functions,  # type: ignore[arg-type]
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
