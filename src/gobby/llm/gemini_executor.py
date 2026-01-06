"""
Gemini implementation of AgentExecutor.

Supports two authentication modes:
- api_key: Use GEMINI_API_KEY environment variable or provided key
- adc: Use Google Application Default Credentials (gcloud auth)
"""

import asyncio
import logging
import os
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

# Auth mode type
GeminiAuthMode = Literal["api_key", "adc"]


class GeminiExecutor(AgentExecutor):
    """
    Gemini implementation of AgentExecutor.

    Supports two authentication modes:
    - api_key: Uses GEMINI_API_KEY environment variable or provided key
    - adc: Uses Google Application Default Credentials (run `gcloud auth application-default login`)

    The executor implements a proper agentic loop:
    1. Send prompt to Gemini with function declarations
    2. When Gemini requests a function call, call tool_handler
    3. Send function result back to Gemini
    4. Repeat until Gemini stops requesting functions or limits are reached

    Example:
        >>> executor = GeminiExecutor(auth_mode="api_key", api_key="...")
        >>> result = await executor.run(
        ...     prompt="Create a task",
        ...     tools=[ToolSchema(name="create_task", ...)],
        ...     tool_handler=my_handler,
        ... )
    """

    def __init__(
        self,
        auth_mode: GeminiAuthMode = "api_key",
        api_key: str | None = None,
        default_model: str = "gemini-2.0-flash",
    ):
        """
        Initialize GeminiExecutor.

        Args:
            auth_mode: Authentication mode ("api_key" or "adc").
            api_key: Gemini API key (optional for api_key mode, uses GEMINI_API_KEY env var).
            default_model: Default model to use if not specified in run().
        """
        self.auth_mode = auth_mode
        self.default_model = default_model
        self.logger = logger
        self._genai: Any = None

        try:
            import google.generativeai as genai

            if auth_mode == "adc":
                # Use Application Default Credentials
                try:
                    import google.auth

                    credentials, _project = google.auth.default()
                    genai.configure(credentials=credentials)
                    self._genai = genai
                    self.logger.debug("Gemini initialized with ADC credentials")
                except Exception as e:
                    raise ValueError(
                        f"Failed to initialize Gemini with ADC: {e}. "
                        "Run 'gcloud auth application-default login' to authenticate."
                    ) from e
            else:
                # Use API key from parameter or environment
                key = api_key or os.environ.get("GEMINI_API_KEY")
                if not key:
                    raise ValueError(
                        "API key required for api_key mode. "
                        "Provide api_key parameter or set GEMINI_API_KEY env var."
                    )
                genai.configure(api_key=key)
                self._genai = genai
                self.logger.debug("Gemini initialized with API key")

        except ImportError as e:
            raise ImportError(
                "google-generativeai package not found. "
                "Please install with `pip install google-generativeai`."
            ) from e

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "gemini"

    def _convert_tools_to_gemini_format(
        self, tools: list[ToolSchema]
    ) -> list[dict[str, Any]]:
        """Convert ToolSchema list to Gemini function declarations format."""
        function_declarations = []
        for tool in tools:
            # Build parameter schema
            params = tool.input_schema.copy()
            # Ensure type is object
            if "type" not in params:
                params["type"] = "object"

            function_declarations.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": params,
                }
            )
        return function_declarations

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

        Runs Gemini with the given prompt, calling tools via tool_handler
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
        if self._genai is None:
            return AgentResult(
                output="",
                status="error",
                error="Gemini client not initialized",
                turns_used=0,
            )

        tool_calls: list[ToolCallRecord] = []
        effective_model = model or self.default_model

        # Track turns in outer scope so timeout handler can access the count
        turns_counter = [0]

        async def _run_loop() -> AgentResult:
            turns_used = 0
            final_output = ""
            genai = self._genai
            assert genai is not None  # For type checker

            # Create the model with tools
            gemini_tools = self._convert_tools_to_gemini_format(tools)

            # Create tool config
            tool_config: dict[str, Any] | None = None
            if gemini_tools:
                tool_config = {"function_declarations": gemini_tools}

            # Create model with system instruction
            generation_config = {
                "max_output_tokens": 8192,
                "temperature": 0.7,
            }

            model_instance = genai.GenerativeModel(
                model_name=effective_model,
                system_instruction=system_prompt or "You are a helpful assistant.",
                generation_config=generation_config,
                tools=[tool_config] if tool_config else None,
            )

            # Start chat
            chat = model_instance.start_chat()

            # Send initial message
            try:
                response = await chat.send_message_async(prompt)
            except Exception as e:
                self.logger.error(f"Gemini API error: {e}")
                return AgentResult(
                    output="",
                    status="error",
                    tool_calls=tool_calls,
                    error=f"Gemini API error: {e}",
                    turns_used=0,
                )

            while turns_used < max_turns:
                turns_used += 1
                turns_counter[0] = turns_used

                # Extract function calls and text from response
                function_calls: list[dict[str, Any]] = []

                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        # Check for text content
                        if hasattr(part, "text") and part.text:
                            final_output = part.text

                        # Check for function call
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            function_calls.append(
                                {
                                    "name": fc.name,
                                    "args": dict(fc.args) if fc.args else {},
                                }
                            )

                # If no function calls, we're done
                if not function_calls:
                    return AgentResult(
                        output=final_output,
                        status="success",
                        tool_calls=tool_calls,
                        turns_used=turns_used,
                    )

                # Handle function calls
                function_responses = []

                for fc in function_calls:
                    tool_name = fc["name"]
                    arguments = fc["args"]

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

                        # Format result for Gemini
                        if result.success:
                            # Use 'is not None' to preserve legitimate falsy values like 0, False, {}
                            response_data = result.result if result.result is not None else {"status": "success"}
                        else:
                            response_data = {"error": result.error}

                        function_responses.append(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response=response_data
                                    if isinstance(response_data, dict)
                                    else {"result": response_data},
                                )
                            )
                        )
                    except Exception as e:
                        self.logger.error(f"Tool handler error for {tool_name}: {e}")
                        record.result = ToolResult(
                            tool_name=tool_name,
                            success=False,
                            error=str(e),
                        )
                        function_responses.append(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={"error": str(e)},
                                )
                            )
                        )

                # Send function responses back to Gemini
                try:
                    response = await chat.send_message_async(function_responses)
                    # Response will be processed in the next iteration of the while loop
                    # which extracts function calls and text directly from the response object
                except Exception as e:
                    self.logger.error(f"Error sending function response: {e}")
                    return AgentResult(
                        output=final_output,
                        status="error",
                        tool_calls=tool_calls,
                        error=f"Error sending function response: {e}",
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
