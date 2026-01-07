"""
Codex (OpenAI) implementation of AgentExecutor.

Supports two authentication modes with different capabilities:

1. api_key mode (OPENAI_API_KEY):
   - Uses OpenAI API with function calling
   - Full tool injection support
   - Requires OPENAI_API_KEY environment variable

2. subscription mode (ChatGPT Plus/Pro/Team/Enterprise):
   - Spawns `codex exec --json` CLI and parses JSONL events
   - Uses Codex's built-in tools (bash, file operations, etc.)
   - NO custom tool injection - tools parameter is IGNORED
   - Good for delegating complete autonomous tasks

IMPORTANT: These modes have fundamentally different capabilities.
Use api_key mode if you need custom MCP tool injection.
Use subscription mode for delegating complete tasks to Codex.
"""

import asyncio
import json
import logging
import os
import shutil
from typing import Any, Literal

from gobby.llm.executor import (
    AgentExecutor,
    AgentResult,
    ToolCallRecord,
    ToolHandler,
    ToolSchema,
)

logger = logging.getLogger(__name__)

# Auth mode type
CodexAuthMode = Literal["api_key", "subscription"]


class CodexExecutor(AgentExecutor):
    """
    Codex (OpenAI) implementation of AgentExecutor.

    Supports two authentication modes with DIFFERENT CAPABILITIES:

    api_key mode:
        - Uses OpenAI API function calling (like GPT-4)
        - Full tool injection support via tools parameter
        - Requires OPENAI_API_KEY environment variable
        - Standard agentic loop with custom tools

    subscription mode:
        - Spawns `codex exec --json` CLI process
        - Parses JSONL events (thread.started, item.completed, turn.completed)
        - Uses Codex's built-in tools ONLY (bash, file ops, web search, etc.)
        - The `tools` parameter is IGNORED in this mode
        - Cannot inject custom MCP tools
        - Best for delegating complete autonomous tasks

    Example (api_key mode):
        >>> executor = CodexExecutor(auth_mode="api_key")
        >>> result = await executor.run(
        ...     prompt="Create a task",
        ...     tools=[ToolSchema(name="create_task", ...)],
        ...     tool_handler=my_handler,
        ... )

    Example (subscription mode):
        >>> executor = CodexExecutor(auth_mode="subscription")
        >>> result = await executor.run(
        ...     prompt="Fix the bug in main.py and run the tests",
        ...     tools=[],  # Ignored - Codex uses its own tools
        ...     tool_handler=lambda *args: None,  # Not called
        ... )
    """

    def __init__(
        self,
        auth_mode: CodexAuthMode = "api_key",
        api_key: str | None = None,
        default_model: str = "gpt-4o",
    ):
        """
        Initialize CodexExecutor.

        Args:
            auth_mode: Authentication mode.
                - "api_key": Use OpenAI API with function calling (requires OPENAI_API_KEY)
                - "subscription": Use Codex CLI with ChatGPT subscription (requires `codex` in PATH)
            api_key: OpenAI API key (optional for api_key mode, uses OPENAI_API_KEY env var).
            default_model: Default model for api_key mode (default: gpt-4o).
        """
        self.auth_mode = auth_mode
        self.default_model = default_model
        self.logger = logger
        self._client: Any = None
        self._cli_path: str = ""

        if auth_mode == "api_key":
            # Use provided key or fall back to environment variable
            key = api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError(
                    "API key required for api_key mode. "
                    "Provide api_key parameter or set OPENAI_API_KEY env var."
                )
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=key)
                self.logger.debug("CodexExecutor initialized with API key")
            except ImportError as e:
                raise ImportError(
                    "openai package not found. Please install with `pip install openai`."
                ) from e

        elif auth_mode == "subscription":
            # Verify Codex CLI is available
            cli_path = shutil.which("codex")
            if not cli_path:
                raise ValueError(
                    "Codex CLI not found in PATH. "
                    "Install Codex CLI and run `codex login` for subscription mode."
                )
            self._cli_path = cli_path
            self.logger.debug(f"CodexExecutor initialized with CLI at {cli_path}")

        else:
            raise ValueError(f"Unknown auth_mode: {auth_mode}")

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "codex"

    def _convert_tools_to_openai_format(self, tools: list[ToolSchema]) -> list[dict[str, Any]]:
        """Convert ToolSchema list to OpenAI function calling format."""
        openai_tools = []
        for tool in tools:
            # Ensure input_schema has "type": "object"
            params = {"type": "object", **tool.input_schema}
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
        Execute an agentic loop.

        For api_key mode: Uses OpenAI function calling with custom tools.
        For subscription mode: Spawns Codex CLI (tools parameter is IGNORED).

        Args:
            prompt: The user prompt to process.
            tools: List of available tools (IGNORED in subscription mode).
            tool_handler: Callback for tool calls (NOT CALLED in subscription mode).
            system_prompt: Optional system prompt (api_key mode only).
            model: Optional model override (api_key mode only).
            max_turns: Maximum turns before stopping (api_key mode only).
            timeout: Maximum execution time in seconds.

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
            return await self._run_with_cli(
                prompt=prompt,
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
        """Run using OpenAI API with function calling."""
        if self._client is None:
            return AgentResult(
                output="",
                status="error",
                error="OpenAI client not initialized",
                turns_used=0,
            )

        tool_calls_list: list[ToolCallRecord] = []
        openai_tools = self._convert_tools_to_openai_format(tools)

        # Build initial messages
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Track turns in outer scope so timeout handler can access the count
        turns_counter = [0]

        async def _run_loop() -> AgentResult:
            nonlocal messages
            turns_used = 0
            final_output = ""
            client = self._client
            assert client is not None

            while turns_used < max_turns:
                turns_used += 1
                turns_counter[0] = turns_used

                # Call OpenAI
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=openai_tools if openai_tools else None,
                        max_tokens=8192,
                    )
                except Exception as e:
                    self.logger.error(f"OpenAI API error: {e}")
                    return AgentResult(
                        output="",
                        status="error",
                        tool_calls=tool_calls_list,
                        error=f"OpenAI API error: {e}",
                        turns_used=turns_used,
                    )

                # Get the assistant's message
                choice = response.choices[0]
                message = choice.message

                # Extract text content
                if message.content:
                    final_output = message.content

                # Add assistant message to history
                messages.append(message.model_dump())

                # Check if there are tool calls
                if not message.tool_calls:
                    # No tool calls - we're done
                    return AgentResult(
                        output=final_output,
                        status="success",
                        tool_calls=tool_calls_list,
                        turns_used=turns_used,
                    )

                # Handle tool calls
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    # Record the tool call
                    record = ToolCallRecord(
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                    tool_calls_list.append(record)

                    # Execute via handler
                    try:
                        result = await tool_handler(tool_name, arguments)
                        record.result = result

                        # Format result for OpenAI
                        if result.success:
                            content = json.dumps(result.result) if result.result else "Success"
                        else:
                            content = f"Error: {result.error}"

                    except Exception as e:
                        self.logger.error(f"Tool handler error for {tool_name}: {e}")
                        from gobby.llm.executor import ToolResult as TR

                        record.result = TR(
                            tool_name=tool_name,
                            success=False,
                            error=str(e),
                        )
                        content = f"Error: {e}"

                    # Add tool result to messages
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": content,
                        }
                    )

                # Check finish reason
                if choice.finish_reason == "stop":
                    return AgentResult(
                        output=final_output,
                        status="success",
                        tool_calls=tool_calls_list,
                        turns_used=turns_used,
                    )

            # Max turns reached
            return AgentResult(
                output=final_output,
                status="partial",
                tool_calls=tool_calls_list,
                turns_used=turns_used,
            )

        # Run with timeout
        try:
            return await asyncio.wait_for(_run_loop(), timeout=timeout)
        except TimeoutError:
            return AgentResult(
                output="",
                status="timeout",
                tool_calls=tool_calls_list,
                error=f"Execution timed out after {timeout}s",
                turns_used=turns_counter[0],
            )

    async def _run_with_cli(
        self,
        prompt: str,
        timeout: float,
    ) -> AgentResult:
        """
        Run using Codex CLI in subscription mode.

        This mode spawns `codex exec --json` and parses JSONL events.
        Custom tools are NOT supported - Codex uses its built-in tools.

        JSONL events include:
        - thread.started: Session begins
        - turn.started/completed: Turn lifecycle
        - item.started/completed: Individual items (reasoning, commands, messages)
        - item types: reasoning, command_execution, agent_message, file_change, etc.
        """
        tool_calls_list: list[ToolCallRecord] = []
        final_output = ""
        turns_used = 0

        try:
            # Spawn codex exec with JSON output
            process = await asyncio.create_subprocess_exec(
                self._cli_path,
                "exec",
                "--json",
                prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Read JSONL events with timeout
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return AgentResult(
                    output="",
                    status="timeout",
                    tool_calls=tool_calls_list,
                    error=f"Codex CLI timed out after {timeout}s",
                    turns_used=turns_used,
                )

            # Parse JSONL output
            if stdout_data:
                for line in stdout_data.decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                        event_type = event.get("type", "")

                        if event_type == "turn.started":
                            turns_used += 1

                        elif event_type == "turn.completed":
                            # Extract usage stats if available
                            pass

                        elif event_type == "item.completed":
                            item = event.get("item", {})
                            item_type = item.get("type", "")

                            if item_type == "agent_message":
                                # Final message from the agent
                                final_output = item.get("text", "")

                            elif item_type == "command_execution":
                                # Record as a tool call
                                command = item.get("command", "")
                                output = item.get("aggregated_output", "")
                                exit_code = item.get("exit_code", 0)

                                from gobby.llm.executor import ToolResult

                                record = ToolCallRecord(
                                    tool_name="bash",
                                    arguments={"command": command},
                                    result=ToolResult(
                                        tool_name="bash",
                                        success=exit_code == 0,
                                        result=output if exit_code == 0 else None,
                                        error=output if exit_code != 0 else None,
                                    ),
                                )
                                tool_calls_list.append(record)

                            elif item_type == "file_change":
                                # Record file changes
                                file_path = item.get("path", "")
                                change_type = item.get("change_type", "")

                                from gobby.llm.executor import ToolResult

                                record = ToolCallRecord(
                                    tool_name="file_change",
                                    arguments={
                                        "path": file_path,
                                        "type": change_type,
                                    },
                                    result=ToolResult(
                                        tool_name="file_change",
                                        success=True,
                                        result={"path": file_path, "type": change_type},
                                    ),
                                )
                                tool_calls_list.append(record)

                    except json.JSONDecodeError:
                        # Skip non-JSON lines
                        continue

            # Check process exit code
            if process.returncode != 0:
                stderr_text = stderr_data.decode("utf-8") if stderr_data else ""
                return AgentResult(
                    output=final_output,
                    status="error",
                    tool_calls=tool_calls_list,
                    error=f"Codex CLI exited with code {process.returncode}: {stderr_text}",
                    turns_used=turns_used,
                )

            return AgentResult(
                output=final_output,
                status="success",
                tool_calls=tool_calls_list,
                turns_used=turns_used,
            )

        except FileNotFoundError:
            return AgentResult(
                output="",
                status="error",
                error="Codex CLI not found. Install with: npm install -g @openai/codex",
                turns_used=0,
            )
        except Exception as e:
            self.logger.error(f"Codex CLI execution failed: {e}")
            return AgentResult(
                output="",
                status="error",
                tool_calls=tool_calls_list,
                error=str(e),
                turns_used=turns_used,
            )
