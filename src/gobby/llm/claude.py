"""
Claude implementation of LLMProvider.
"""

import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Any

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

from gobby.config.app import DaemonConfig
from gobby.llm.base import LLMProvider


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


logger = logging.getLogger(__name__)


class ClaudeLLMProvider(LLMProvider):
    """
    Claude implementation of LLMProvider using claude_agent_sdk.

    Uses subscription-based authentication through Claude CLI.
    Supports code execution via Claude's sandbox.
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "claude"

    @property
    def supports_code_execution(self) -> bool:
        """Claude supports code execution via sandbox."""
        return True

    def __init__(self, config: DaemonConfig):
        """
        Initialize ClaudeLLMProvider.

        Args:
            config: Client configuration.
        """
        self.config = config
        self.logger = logger
        self._claude_cli_path = self._find_cli_path()

    def _find_cli_path(self) -> str | None:
        """
        Find Claude CLI path.

        DO NOT resolve symlinks - npm manages the symlink atomically during upgrades.
        Resolving causes race conditions when Claude Code is being reinstalled.
        """
        cli_path = shutil.which("claude")

        if cli_path:
            # Validate CLI exists and is executable
            if not os.path.exists(cli_path):
                self.logger.warning(f"Claude CLI not found: {cli_path}")
                return None
            elif not os.access(cli_path, os.X_OK):
                self.logger.warning(f"Claude CLI not executable: {cli_path}")
                return None
            else:
                self.logger.debug(f"Claude CLI found: {cli_path}")
                return cli_path
        else:
            self.logger.warning("Claude CLI not found in PATH - LLM features disabled")
            return None

    def _verify_cli_path(self) -> str | None:
        """
        Verify CLI path is still valid and retry if needed.

        Handles race condition when npm install updates Claude Code during hook execution.
        Uses exponential backoff retry to wait for npm install to complete.

        Returns:
            Valid CLI path if found, None otherwise
        """
        cli_path = self._claude_cli_path

        # Validate cached path still exists
        # Retry with backoff if missing (may be in the middle of npm install)
        if cli_path and not os.path.exists(cli_path):
            self.logger.warning(
                f"Cached CLI path no longer exists (may have been reinstalled): {cli_path}"
            )
            # Try to find CLI again with retry logic for npm install race condition
            max_retries = 3
            retry_delays = [0.5, 1.0, 2.0]  # Exponential backoff

            for attempt, delay in enumerate(retry_delays, 1):
                cli_path = shutil.which("claude")
                if cli_path and os.path.exists(cli_path):
                    self.logger.debug(
                        f"Found Claude CLI at new location after {attempt} attempt(s): {cli_path}"
                    )
                    self._claude_cli_path = cli_path
                    break

                if attempt < max_retries:
                    self.logger.debug(
                        f"Claude CLI not found, waiting {delay}s before retry {attempt + 1}/{max_retries}"
                    )
                    time.sleep(delay)
                else:
                    self.logger.warning(f"Claude CLI not found in PATH after {max_retries} retries")
                    cli_path = None

        return cli_path

    async def generate_summary(
        self, context: dict[str, Any], prompt_template: str | None = None
    ) -> str:
        """
        Generate session summary using Claude.
        """
        cli_path = self._verify_cli_path()
        if not cli_path:
            return "Session summary unavailable (Claude CLI not found)"

        # Build formatted context for prompt template
        # Transform list/dict values to strings for template substitution
        formatted_context = {
            "transcript_summary": context.get("transcript_summary", ""),
            "last_messages": json.dumps(context.get("last_messages", []), indent=2),
            "git_status": context.get("git_status", ""),
            "file_changes": context.get("file_changes", ""),
            **{
                k: v
                for k, v in context.items()
                if k not in ["transcript_summary", "last_messages", "git_status", "file_changes"]
            },
        }

        # Build prompt - prompt_template is required
        if not prompt_template:
            raise ValueError(
                "prompt_template is required for generate_summary. "
                "Configure 'session_summary.prompt' in ~/.gobby/config.yaml"
            )
        prompt = prompt_template.format(**formatted_context)

        # Configure Claude Agent SDK
        options = ClaudeAgentOptions(
            system_prompt="You are a session summary generator. Create comprehensive, actionable summaries.",
            max_turns=1,
            model=self.config.session_summary.model,
            allowed_tools=[],
            permission_mode="default",
            cli_path=cli_path,
        )

        # Run async query
        async def _run_query() -> str:
            summary_text = ""
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            summary_text += block.text
            return summary_text

        try:
            return await _run_query()
        except Exception as e:
            self.logger.error(f"Failed to generate summary with Claude: {e}")
            return f"Session summary generation failed: {e}"

    async def synthesize_title(
        self, user_prompt: str, prompt_template: str | None = None
    ) -> str | None:
        """
        Synthesize session title using Claude.
        """
        cli_path = self._verify_cli_path()
        if not cli_path:
            return None

        # Build prompt - prompt_template is required
        if not prompt_template:
            raise ValueError(
                "prompt_template is required for synthesize_title. "
                "Configure 'title_synthesis.prompt' in ~/.gobby/config.yaml"
            )
        prompt = prompt_template.format(user_prompt=user_prompt)

        # Configure Claude Agent SDK
        options = ClaudeAgentOptions(
            system_prompt="You are a session title generator. Create concise, descriptive titles.",
            max_turns=1,
            model=self.config.title_synthesis.model,
            allowed_tools=[],
            permission_mode="default",
            cli_path=cli_path,
        )

        # Run async query
        async def _run_query() -> str:
            title_text = ""
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            title_text = block.text
            return title_text.strip()

        try:
            # Retry logic for title synthesis
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    return await _run_query()
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.logger.warning(
                            f"Title synthesis failed (attempt {attempt + 1}), retrying: {e}"
                        )
                        await asyncio.sleep(1)
                    else:
                        raise e
            # This should be unreachable, but mypy can't prove it
            return None  # pragma: no cover
        except Exception as e:
            self.logger.error(f"Failed to synthesize title with Claude: {e}")
            return None

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        context: str | None = None,
        timeout: float | int | None = None,
        prompt_template: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute code using Claude's code execution sandbox via CLI.

        Uses the Claude Agent SDK with subscription-based auth through the CLI.
        The code_execution tool provides sandboxed Python execution.
        """
        cli_path = self._verify_cli_path()
        if not cli_path:
            return {
                "success": False,
                "error": "Claude CLI not found",
                "language": language,
            }

        if language.lower() != "python":
            return {
                "success": False,
                "error": f"Language '{language}' not supported. Only Python is currently supported.",
            }

        # Build prompt - prompt_template is required
        if not prompt_template:
            raise ValueError(
                "prompt_template is required for execute_code. "
                "Configure 'code_execution.prompt' in ~/.gobby/config.yaml"
            )
        prompt = prompt_template.format(code=code, context=context or "", language=language)

        # Determine timeout
        code_exec_config = self.config.code_execution
        actual_timeout = timeout if timeout is not None else code_exec_config.default_timeout

        # Configure Claude Agent SDK
        # Note: code_execution is an internal tool that provides sandboxed execution
        # Do NOT add explicit sandbox config - it breaks this tool
        options = ClaudeAgentOptions(
            system_prompt="You are a code execution assistant. Execute the provided code using the code_execution tool and return the results. Always use the code_execution tool - never just describe what the code would do.",
            max_turns=code_exec_config.max_turns,
            model=code_exec_config.model,
            allowed_tools=["code_execution"],
            permission_mode="bypassPermissions",
            cli_path=cli_path,
        )

        # Track execution time
        start_time = time.time()

        # Run async query
        async def _run_query() -> str:
            result_text = ""
            tool_results: list[str] = []
            final_result: str | None = None
            async for message in query(prompt=prompt, options=options):
                self.logger.debug(f"Message type: {type(message).__name__}")
                if isinstance(message, ResultMessage):
                    # ResultMessage contains the final result from the agent
                    if message.result:
                        final_result = message.result
                    self.logger.debug(f"ResultMessage: result={message.result}")
                elif isinstance(message, UserMessage):
                    # UserMessage may contain tool results
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            # Capture actual tool execution output
                            tool_results.append(str(block.content))
                            self.logger.debug(f"ToolResultBlock (UserMessage): {block.content}")
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                        elif isinstance(block, ToolResultBlock):
                            # Capture actual code execution output
                            tool_results.append(str(block.content))
                            self.logger.debug(
                                f"ToolResultBlock (AssistantMessage): {block.content}"
                            )
                        elif isinstance(block, ToolUseBlock):
                            self.logger.debug(
                                f"ToolUseBlock: tool={block.name}, input={block.input}"
                            )
            # Priority: tool_results > final_result (summary) > text
            # We want the actual execution output, not the summary
            if tool_results:
                return "\n".join(tool_results)
            if final_result:
                return final_result
            return result_text

        try:
            result_text = await asyncio.wait_for(_run_query(), timeout=actual_timeout)

            execution_time = time.time() - start_time

            return {
                "success": True,
                "result": result_text.strip(),
                "language": language,
                "execution_time": round(execution_time, 2),
                "context": context,
            }

        except TimeoutError:
            return {
                "success": False,
                "error": f"Code execution timed out after {actual_timeout} seconds",
                "error_type": "TimeoutError",
                "timeout": actual_timeout,
            }
        except Exception as e:
            self.logger.error(f"Code execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "language": language,
            }

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        Generate text using Claude.
        """
        cli_path = self._verify_cli_path()
        if not cli_path:
            return "Generation unavailable (Claude CLI not found)"

        # Configure Claude Agent SDK
        # Use tools=[] to disable all tools for pure text generation
        options = ClaudeAgentOptions(
            system_prompt=system_prompt or "You are a helpful assistant.",
            max_turns=1,
            model=model or "claude-haiku-4-5",
            tools=[],  # Explicitly disable all tools
            allowed_tools=[],
            permission_mode="default",
            cli_path=cli_path,
        )

        # Run async query
        async def _run_query() -> str:
            result_text = ""
            message_count = 0
            async for message in query(prompt=prompt, options=options):
                message_count += 1
                self.logger.debug(
                    f"generate_text message {message_count}: {type(message).__name__}"
                )
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            self.logger.debug(f"  TextBlock: {block.text[:100]}...")
                            result_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            self.logger.debug(f"  ToolUseBlock: {block.name}")
                elif isinstance(message, ResultMessage):
                    # ResultMessage contains the final result from the agent
                    self.logger.debug(
                        f"  ResultMessage: result={message.result}, type={type(message.result)}"
                    )
                    if message.result:
                        result_text = message.result
            if message_count == 0:
                self.logger.warning("generate_text: No messages received from Claude SDK")
            elif not result_text:
                self.logger.warning(f"generate_text: {message_count} messages but no text content")
            return result_text

        try:
            return await _run_query()
        except Exception as e:
            self.logger.error(f"Failed to generate text with Claude: {e}", exc_info=True)
            return f"Generation failed: {e}"

    async def generate_with_mcp_tools(
        self,
        prompt: str,
        allowed_tools: list[str],
        system_prompt: str | None = None,
        model: str | None = None,
        max_turns: int = 10,
        tool_functions: dict[str, list] | None = None,
    ) -> MCPToolResult:
        """
        Generate text with access to MCP tools.

        This method enables the agent to call MCP tools during generation,
        tracking all tool calls made and returning them alongside the final text.

        Args:
            prompt: User prompt to process.
            allowed_tools: List of allowed MCP tool patterns.
                Tools should be in format "mcp__{server}__{tool}" or patterns
                like "mcp__gobby-tasks__*" for all tools from a server.
            system_prompt: Optional system prompt.
            model: Optional model override (default: claude-sonnet-4-5).
            max_turns: Maximum number of agentic turns (default: 10).
            tool_functions: Optional dict mapping server names to lists of tool
                functions for in-process MCP servers. Example:
                {"gobby-tasks": [create_task_func, update_task_func]}

        Returns:
            MCPToolResult containing final text and list of tool calls made.

        Example:
            >>> result = await provider.generate_with_mcp_tools(
            ...     prompt="Create a task called 'Fix bug'",
            ...     allowed_tools=["mcp__gobby-tasks__create_task"],
            ...     system_prompt="You are a task manager.",
            ...     tool_functions={"gobby-tasks": [create_task]}
            ... )
            >>> print(result.text)
            >>> for call in result.tool_calls:
            ...     print(f"Called {call.tool_name} with {call.arguments}")
        """
        cli_path = self._verify_cli_path()
        if not cli_path:
            return MCPToolResult(
                text="Generation unavailable (Claude CLI not found)",
                tool_calls=[],
            )

        # Build mcp_servers config
        # Can be a dict of server configs OR a path to .mcp.json file
        from pathlib import Path

        mcp_servers_config: dict[str, Any] | str | None = None

        # Add in-process tool functions if provided
        if tool_functions:
            mcp_servers_config = {}
            for server_name, tools in tool_functions.items():
                mcp_servers_config[server_name] = create_sdk_mcp_server(
                    name=server_name,
                    tools=tools,
                )

        # If no tool_functions provided but we have allowed gobby tools,
        # use the .mcp.json config file (avoids in-process config issues)
        if not tool_functions and any("gobby" in t for t in allowed_tools):
            # Look for .mcp.json in the current working directory or gobby project
            cwd_config = Path.cwd() / ".mcp.json"
            if cwd_config.exists():
                mcp_servers_config = str(cwd_config)
            else:
                # Try the gobby project root
                gobby_root = Path(__file__).parent.parent.parent.parent
                gobby_config = gobby_root / ".mcp.json"
                if gobby_config.exists():
                    mcp_servers_config = str(gobby_config)

        # Configure Claude Agent SDK with MCP tools
        options = ClaudeAgentOptions(
            system_prompt=system_prompt or "You are a helpful assistant with access to MCP tools.",
            max_turns=max_turns,
            model=model or "claude-sonnet-4-5",
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            cli_path=cli_path,
            mcp_servers=mcp_servers_config if mcp_servers_config is not None else {},
        )

        # Track tool calls and results
        tool_calls: list[ToolCall] = []
        pending_tool_calls: dict[str, ToolCall] = {}  # Map tool_use_id -> ToolCall

        def _parse_server_name(full_tool_name: str) -> str:
            """Extract server name from mcp__{server}__{tool} format."""
            if full_tool_name.startswith("mcp__"):
                parts = full_tool_name.split("__")
                if len(parts) >= 2:
                    return parts[1]
            return "unknown"

        # Run async query
        async def _run_query() -> str:
            result_text = ""
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    # Final result from the agent
                    if message.result:
                        result_text = message.result
                    self.logger.debug(f"ResultMessage: result={message.result}")

                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            # Track tool use
                            tool_call = ToolCall(
                                tool_name=block.name,
                                server_name=_parse_server_name(block.name),
                                arguments=block.input if isinstance(block.input, dict) else {},
                            )
                            tool_calls.append(tool_call)
                            pending_tool_calls[block.id] = tool_call
                            self.logger.debug(
                                f"ToolUseBlock: tool={block.name}, input={block.input}"
                            )

                elif isinstance(message, UserMessage):
                    # UserMessage may contain tool results
                    # UserMessage.content can be str | list[...], check first
                    if isinstance(message.content, list):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                # Match result to pending tool call
                                if block.tool_use_id in pending_tool_calls:
                                    pending_tool_calls[block.tool_use_id].result = str(
                                        block.content
                                    )
                                self.logger.debug(
                                    f"ToolResultBlock: id={block.tool_use_id}, content={block.content}"
                                )

            return result_text

        try:
            final_text = await _run_query()
            return MCPToolResult(text=final_text, tool_calls=tool_calls)
        except ExceptionGroup as eg:
            # Handle Python 3.11+ ExceptionGroup from TaskGroup
            errors: list[str] = []
            for exc in eg.exceptions:
                errors.append(f"{type(exc).__name__}: {exc}")
                self.logger.error(f"TaskGroup sub-exception: {type(exc).__name__}: {exc}")
            return MCPToolResult(
                text=f"Generation failed: {'; '.join(errors)}",
                tool_calls=tool_calls,
            )
        except Exception as e:
            self.logger.error(f"Failed to generate with MCP tools: {e}", exc_info=True)
            return MCPToolResult(
                text=f"Generation failed: {e}",
                tool_calls=tool_calls,
            )
