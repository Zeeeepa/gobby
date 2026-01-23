"""
LiteLLM implementation of AgentExecutor.

Provides a unified interface to 100+ LLM providers using OpenAI-compatible
function calling API. Supports models from OpenAI, Anthropic, Mistral,
Cohere, and many others through a single interface.

This executor is the unified path for all api_key and adc authentication modes
across all providers (Claude, Gemini, Codex/OpenAI). Provider-specific executors
are only used for subscription/cli modes that require special SDK integrations.
"""

import asyncio
import json
import logging
import os
from typing import Any, Literal

from gobby.llm.executor import (
    AgentExecutor,
    AgentResult,
    CostInfo,
    ToolCallRecord,
    ToolHandler,
    ToolResult,
    ToolSchema,
)

logger = logging.getLogger(__name__)

# Provider type for routing
ProviderType = Literal["claude", "gemini", "codex", "openai", "litellm"]
AuthModeType = Literal["api_key", "adc"]


def get_litellm_model(
    model: str,
    provider: ProviderType | None = None,
    auth_mode: AuthModeType | None = None,
) -> str:
    """
    Map provider/model/auth_mode to LiteLLM model string format.

    LiteLLM uses prefixes to route to the correct provider:
    - anthropic/model-name -> Anthropic API
    - gemini/model-name -> Google AI Studio (API key)
    - vertex_ai/model-name -> Google Vertex AI (ADC)
    - No prefix -> OpenAI (default)

    Args:
        model: The model name (e.g., "claude-sonnet-4-5", "gemini-2.0-flash")
        provider: The provider type (claude, gemini, codex, openai)
        auth_mode: The authentication mode (api_key, adc)

    Returns:
        LiteLLM-formatted model string with appropriate prefix.

    Examples:
        >>> get_litellm_model("claude-sonnet-4-5", provider="claude")
        "anthropic/claude-sonnet-4-5"
        >>> get_litellm_model("gemini-2.0-flash", provider="gemini", auth_mode="api_key")
        "gemini/gemini-2.0-flash"
        >>> get_litellm_model("gemini-2.0-flash", provider="gemini", auth_mode="adc")
        "vertex_ai/gemini-2.0-flash"
        >>> get_litellm_model("gpt-4o", provider="codex")
        "gpt-4o"
    """
    # If model already has a prefix, assume it's already formatted
    if "/" in model:
        return model

    if provider == "claude":
        return f"anthropic/{model}"
    elif provider == "gemini":
        if auth_mode == "adc":
            # ADC uses Vertex AI endpoint
            return f"vertex_ai/{model}"
        # API key uses Gemini API endpoint
        return f"gemini/{model}"
    elif provider in ("codex", "openai"):
        # OpenAI models don't need a prefix
        return model
    else:
        # Default: return as-is (OpenAI-compatible or already prefixed)
        return model


def setup_provider_env(
    provider: ProviderType | None = None,
    auth_mode: AuthModeType | None = None,
) -> None:
    """
    Set up environment variables needed for specific provider/auth_mode combinations.

    For Gemini ADC mode via Vertex AI, this ensures VERTEXAI_PROJECT and
    VERTEXAI_LOCATION are set from common Google Cloud environment variables.

    Args:
        provider: The provider type
        auth_mode: The authentication mode
    """
    if provider == "gemini" and auth_mode == "adc":
        # Vertex AI needs project and location
        # Check if already set, otherwise try common GCP env vars
        if "VERTEXAI_PROJECT" not in os.environ:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
            if project:
                os.environ["VERTEXAI_PROJECT"] = project
                logger.debug(f"Set VERTEXAI_PROJECT from GCP env: {project}")

        if "VERTEXAI_LOCATION" not in os.environ:
            location = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
            os.environ["VERTEXAI_LOCATION"] = location
            logger.debug(f"Set VERTEXAI_LOCATION: {location}")


class LiteLLMExecutor(AgentExecutor):
    """
    LiteLLM implementation of AgentExecutor.

    Uses LiteLLM's unified API to access 100+ LLM providers with OpenAI-compatible
    function calling. Supports models from OpenAI, Anthropic, Mistral, Cohere, etc.

    This is the unified executor for all api_key and adc authentication modes:
    - Claude (api_key) -> anthropic/model-name
    - Gemini (api_key) -> gemini/model-name
    - Gemini (adc) -> vertex_ai/model-name
    - Codex/OpenAI (api_key) -> model-name (no prefix)

    The executor implements a proper agentic loop:
    1. Send prompt to LLM with function/tool schemas
    2. When LLM requests a function call, call tool_handler
    3. Send function result back to LLM
    4. Repeat until LLM stops requesting functions or limits are reached

    Example:
        >>> executor = LiteLLMExecutor(
        ...     default_model="claude-sonnet-4-5",
        ...     provider="claude",
        ...     auth_mode="api_key",
        ... )
        >>> result = await executor.run(
        ...     prompt="Create a task",
        ...     tools=[ToolSchema(name="create_task", ...)],
        ...     tool_handler=my_handler,
        ... )
        >>> print(result.cost_info)  # Unified cost tracking
    """

    def __init__(
        self,
        default_model: str = "gpt-4o-mini",
        api_base: str | None = None,
        api_keys: dict[str, str] | None = None,
        provider: ProviderType | None = None,
        auth_mode: AuthModeType | None = None,
    ):
        """
        Initialize LiteLLMExecutor.

        Args:
            default_model: Default model to use if not specified in run().
                          Examples: "gpt-4o-mini", "claude-sonnet-4-5",
                          "gemini-2.0-flash"
            api_base: Optional custom API base URL (e.g., OpenRouter endpoint).
            api_keys: Optional dict of API keys to set in environment.
                     Keys should be like "OPENAI_API_KEY", "ANTHROPIC_API_KEY", etc.
            provider: Provider type for model routing (claude, gemini, codex, openai).
                     Used to determine the correct LiteLLM model prefix.
            auth_mode: Authentication mode (api_key, adc).
                      Used for Gemini to choose between gemini/ and vertex_ai/ prefixes.
        """
        self.default_model = default_model
        self.api_base = api_base
        self.provider = provider
        self.auth_mode = auth_mode
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

            # Set up provider-specific environment variables
            setup_provider_env(provider, auth_mode)

            self.logger.debug(
                f"LiteLLM executor initialized (provider={provider}, auth_mode={auth_mode})"
            )

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
        # Apply model routing based on provider/auth_mode
        raw_model = model or self.default_model
        effective_model = get_litellm_model(raw_model, self.provider, self.auth_mode)
        self.logger.debug(f"Model routing: {raw_model} -> {effective_model}")

        # Track cumulative costs across turns (outer scope for timeout handler)
        cost_tracker = [CostInfo(model=effective_model)]

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

                    # Track costs
                    if hasattr(response, "usage") and response.usage:
                        cost_tracker[0].prompt_tokens += response.usage.prompt_tokens or 0
                        cost_tracker[0].completion_tokens += response.usage.completion_tokens or 0

                    # Calculate cost using LiteLLM's cost tracking
                    try:
                        turn_cost = litellm.completion_cost(response)
                        cost_tracker[0].total_cost += turn_cost
                    except Exception:  # nosec B110 - best effort cost tracking, failure is non-critical
                        # Cost calculation may fail for some models
                        pass

                except Exception as e:
                    self.logger.error(f"LiteLLM API error: {e}")
                    return AgentResult(
                        output="",
                        status="error",
                        tool_calls=tool_calls_records,
                        error=f"LiteLLM API error: {e}",
                        turns_used=turns_used,
                        cost_info=cost_tracker[0],
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
                        cost_info=cost_tracker[0],
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
                cost_info=cost_tracker[0],
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
                cost_info=cost_tracker[0],
            )
