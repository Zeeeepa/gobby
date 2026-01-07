"""
LiteLLM implementation of AgentExecutor.

Provides a unified interface to 100+ LLM providers using OpenAI-compatible
function calling API. Supports models from OpenAI, Anthropic, Mistral,
Cohere, and many others through a single interface.
"""

import asyncio
import json
import logging
import os
from typing import Any

from gobby.llm.executor import (
    AgentExecutor,
    AgentResult,
    ToolCallRecord,
    ToolHandler,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger(__name__)


class LiteLLMExecutor(AgentExecutor):
    """
    LiteLLM implementation of AgentExecutor.

    Uses LiteLLM's unified API to access 100+ LLM providers with OpenAI-compatible
    function calling. Supports models from OpenAI, Anthropic, Mistral, Cohere, etc.

    The executor implements a proper agentic loop:
    1. Send prompt to LLM with function/tool schemas
    2. When LLM requests a function call, call tool_handler
    3. Send function result back to LLM
    4. Repeat until LLM stops requesting functions or limits are reached

    Example:
        >>> executor = LiteLLMExecutor(default_model="gpt-4o-mini")
        >>> result = await executor.run(
        ...     prompt="Create a task",
        ...     tools=[ToolSchema(name="create_task", ...)],
        ...     tool_handler=my_handler,
        ... )
    """

    def __init__(
        self,
        default_model: str = "gpt-4o-mini",
        api_base: str | None = None,
        api_keys: dict[str, str] | None = None,
    ):
        """
        Initialize LiteLLMExecutor.

        Args:
            default_model: Default model to use if not specified in run().
                          Examples: "gpt-4o-mini", "claude-3-sonnet-20240229",
                          "mistral/mistral-large-latest"
            api_base: Optional custom API base URL (e.g., OpenRouter endpoint).
            api_keys: Optional dict of API keys to set in environment.
                     Keys should be like "OPENAI_API_KEY", "ANTHROPIC_API_KEY", etc.
        """
        self.default_model = default_model
        self.api_base = api_base
        self.logger = logger
        self._litellm: Any = None

        try:
            import litellm

            self._litellm = litellm

            # Set API keys in environment if provided
            if api_keys:
                for key, value in api_keys.items():
                    if value and key not in os.environ:
                        os.environ[key] = value
                        self.logger.debug(f"Set {key} from config")

            self.logger.debug("LiteLLM executor initialized")

        except ImportError as e:
            raise ImportError(
                "litellm package not found. Please install with `pip install litellm`."
            ) from e

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "litellm"

    def _convert_tools_to_openai_format(self, tools: list[ToolSchema]) -> list[dict[str, Any]]:
        """Convert ToolSchema list to OpenAI function calling format."""
        openai_tools = []
        for tool in tools:
            # Build parameter schema
            params = tool.input_schema.copy()
            # Ensure type is object
            if "type" not in params:
                params["type"] = "object"

            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": params,
                    },
                }
            )
        return openai_tools

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
        Execute an agentic loop with function calling.

        Runs LiteLLM with the given prompt, calling tools via tool_handler
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
        if self._litellm is None:
            return AgentResult(
                output="",
                status="error",
                error="LiteLLM client not initialized",
                turns_used=0,
            )

        tool_calls_records: list[ToolCallRecord] = []
        effective_model = model or self.default_model

        # Track turns in outer scope so timeout handler can access the count
        turns_counter = [0]

        async def _run_loop() -> AgentResult:
            turns_used = 0
            final_output = ""
            litellm = self._litellm
            if litellm is None:
                raise RuntimeError("LiteLLMExecutor litellm not initialized")

            # Convert tools to OpenAI format
            openai_tools = self._convert_tools_to_openai_format(tools)

            # Build initial messages
            messages: list[dict[str, Any]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({"role": "system", "content": "You are a helpful assistant."})
            messages.append({"role": "user", "content": prompt})

            while turns_used < max_turns:
                turns_used += 1
                turns_counter[0] = turns_used

                try:
                    # Build completion kwargs
                    completion_kwargs: dict[str, Any] = {
                        "model": effective_model,
                        "messages": messages,
                    }

                    # Add tools if available
                    if openai_tools:
                        completion_kwargs["tools"] = openai_tools
                        completion_kwargs["tool_choice"] = "auto"

                    # Add api_base if configured
                    if self.api_base:
                        completion_kwargs["api_base"] = self.api_base

                    # Call LiteLLM
                    response = await litellm.acompletion(**completion_kwargs)

                except Exception as e:
                    self.logger.error(f"LiteLLM API error: {e}")
                    return AgentResult(
                        output="",
                        status="error",
                        tool_calls=tool_calls_records,
                        error=f"LiteLLM API error: {e}",
                        turns_used=turns_used,
                    )

                # Process response
                response_message = response.choices[0].message
                tool_calls = getattr(response_message, "tool_calls", None)

                # Extract text content
                if response_message.content:
                    final_output = response_message.content

                # If no tool calls, we're done
                if not tool_calls:
                    return AgentResult(
                        output=final_output,
                        status="success",
                        tool_calls=tool_calls_records,
                        turns_used=turns_used,
                    )

                # Add assistant message to history
                messages.append(response_message.model_dump())

                # Handle tool calls
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    try:
                        function_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        function_args = {}

                    # Record the tool call
                    record = ToolCallRecord(
                        tool_name=function_name,
                        arguments=function_args,
                    )
                    tool_calls_records.append(record)

                    # Execute via handler
                    try:
                        result = await tool_handler(function_name, function_args)
                        record.result = result

                        # Format result for LiteLLM
                        if result.success:
                            # Use explicit None check to handle valid falsy values (0, False, "", {}, etc.)
                            content = (
                                json.dumps(result.result)
                                if result.result is not None
                                else "Success"
                            )
                        else:
                            content = f"Error: {result.error}"

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": function_name,
                                "content": content,
                            }
                        )
                    except Exception as e:
                        self.logger.error(f"Tool handler error for {function_name}: {e}")
                        record.result = ToolResult(
                            tool_name=function_name,
                            success=False,
                            error=str(e),
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": function_name,
                                "content": f"Error: {e}",
                            }
                        )

            # Max turns reached
            return AgentResult(
                output=final_output,
                status="partial",
                tool_calls=tool_calls_records,
                turns_used=turns_used,
            )

        # Run with timeout
        try:
            return await asyncio.wait_for(_run_loop(), timeout=timeout)
        except TimeoutError:
            return AgentResult(
                output="",
                status="timeout",
                tool_calls=tool_calls_records,
                error=f"Execution timed out after {timeout}s",
                turns_used=turns_counter[0],
            )
