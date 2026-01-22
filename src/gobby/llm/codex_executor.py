"""
Codex (OpenAI) implementation of AgentExecutor for CLI/subscription mode only.

This executor spawns `codex exec --json` CLI and parses JSONL events.
It uses Codex's built-in tools (bash, file operations, etc.) - NO custom tool
injection is supported.

Note: api_key mode is now routed through LiteLLMExecutor for unified cost tracking.
Use the resolver.create_executor() function which handles routing automatically.
"""

import asyncio
import json
import logging
import shutil
from typing import Literal

from gobby.llm.executor import (
    AgentExecutor,
    AgentResult,
    ToolCallRecord,
    ToolHandler,
    ToolSchema,
)

logger = logging.getLogger(__name__)

# Auth mode type - subscription/cli only, api_key routes through LiteLLM
CodexAuthMode = Literal["subscription", "cli"]


class CodexExecutor(AgentExecutor):
    """
    Codex (OpenAI) implementation of AgentExecutor for CLI mode only.

    Spawns `codex exec --json` CLI process and parses JSONL events.
    Uses Codex's built-in tools ONLY (bash, file ops, web search, etc.).
    The `tools` parameter is IGNORED - cannot inject custom MCP tools.
    Best for delegating complete autonomous tasks.

    For api_key mode with custom tool injection, use LiteLLMExecutor with
    provider="codex" which routes through OpenAI API for unified cost tracking.

    Example:
        >>> executor = CodexExecutor(auth_mode="subscription")
        >>> result = await executor.run(
        ...     prompt="Fix the bug in main.py and run the tests",
        ...     tools=[],  # Ignored - Codex uses its own tools
        ...     tool_handler=lambda *args: None,  # Not called
        ... )
    """

    _cli_path: str

    def __init__(
        self,
        auth_mode: CodexAuthMode = "subscription",
        default_model: str = "gpt-4o",
    ):
        """
        Initialize CodexExecutor for CLI/subscription mode.

        Args:
            auth_mode: Must be "subscription" or "cli". API key mode is handled by LiteLLMExecutor.
            default_model: Default model (not used in CLI mode, kept for interface compatibility).

        Raises:
            ValueError: If auth_mode is not "subscription"/"cli" or Codex CLI not found.
        """
        if auth_mode not in ("subscription", "cli"):
            raise ValueError(
                "CodexExecutor only supports subscription/cli mode. "
                "For api_key mode with custom tools, use LiteLLMExecutor with provider='codex'."
            )

        self.auth_mode = auth_mode
        self.default_model = default_model
        self.logger = logger
        self._cli_path = ""

        # Verify Codex CLI is available
        cli_path = shutil.which("codex")
        if not cli_path:
            raise ValueError(
                "Codex CLI not found in PATH. "
                "Install Codex CLI and run `codex login` for subscription mode."
            )
        self._cli_path = cli_path
        self.logger.debug(f"CodexExecutor initialized with CLI at {cli_path}")

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "codex"

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
        Execute Codex CLI and parse JSONL events.

        Note: The tools and tool_handler parameters are IGNORED in CLI mode.
        Codex uses its own built-in tools (bash, file operations, etc.).

        For custom tool injection, use LiteLLMExecutor with provider="codex".

        Args:
            prompt: The user prompt to process.
            tools: IGNORED - Codex uses its own tools.
            tool_handler: IGNORED - not called in CLI mode.
            system_prompt: IGNORED in CLI mode.
            model: IGNORED in CLI mode.
            max_turns: IGNORED in CLI mode.
            timeout: Maximum execution time in seconds.

        Returns:
            AgentResult with output, status, and tool call records.
        """
        return await self._run_with_cli(
            prompt=prompt,
            timeout=timeout,
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
