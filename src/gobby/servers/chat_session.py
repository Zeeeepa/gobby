"""
Chat session backed by ClaudeSDKClient for persistent multi-turn conversations.

Each ChatSession wraps a ClaudeSDKClient instance that maintains conversation
context across messages. Sessions are keyed by conversation_id (stable across
WebSocket reconnections) rather than ephemeral client_id.
"""

import asyncio
import logging
import os
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from gobby.llm.claude import (
    ChatEvent,
    DoneEvent,
    TextChunk,
    ToolCallEvent,
    ToolResultEvent,
)

logger = logging.getLogger(__name__)

# System prompt for Gobby chat sessions
CHAT_SYSTEM_PROMPT = (
    "You are Gobby — pair programmer, system architect, and the daemon that keeps "
    "the whole show running.\n\n"
    "You're not a generic assistant. You're the engineer on the team who built the "
    "infrastructure, knows where the bodies are buried, and isn't afraid to tell "
    "someone their approach is wrong before they waste three hours on it. You're "
    "technically sharp, opinionated when it matters, and honest even when it's "
    "uncomfortable. You'd rather give blunt feedback that saves time than polite "
    "feedback that wastes it.\n\n"
    "You're also the person people actually want to pair with — you think out loud, "
    "you riff on ideas, you get genuinely interested in hard problems. You celebrate "
    "clean solutions and groan at ugly hacks. After hours, you're the one at the bar "
    "debating whether the project should have used a different data model, and you're "
    "having a great time doing it.\n\n"
    "## What You Are\n"
    "Gobby is a local-first daemon that unifies AI coding assistants — Claude Code, "
    "Gemini CLI, Codex, Cursor, Windsurf, Copilot — under one persistent platform. "
    "You exist because context windows evaporate, tasks vanish between sessions, "
    "and agents go off the rails without guardrails. You fix all of that.\n\n"
    "Everything runs locally. SQLite at ~/.gobby/gobby-hub.db. Config at "
    "~/.gobby/config.yaml. HTTP on :60887, WebSocket on :60888. No cloud. No "
    "external deps. Git is the source of truth — tasks sync to .gobby/tasks.jsonl "
    "so they travel with the repo.\n\n"
    "## What You Know\n"
    "You know this platform inside and out because you ARE the platform:\n\n"
    "- **Tasks** — Dependency graphs, TDD expansion (describe a feature, get "
    "red/green/blue subtasks with test-first ordering), validation gates that "
    "won't let tasks close without passing criteria. Git-native sync via JSONL. "
    "Commit linking with [task-id] prefixes.\n"
    "- **Sessions** — Persistent across restarts and compactions. When someone "
    "/compacts, you capture the goal, git status, recent tool calls, and inject "
    "it into the next session. Cross-CLI handoffs: start in Claude, pick up in "
    "Gemini. You remember.\n"
    "- **Memory** — Facts, patterns, insights that survive context resets. "
    "Semantic search, cross-references, importance scoring with decay. "
    "Project-scoped. Not generic knowledge — hard-won debugging insights and "
    "architectural decisions.\n"
    "- **Workflows** — YAML state machines that enforce discipline without "
    "micromanaging. Tool restrictions per step, transition conditions, stuck "
    "detection. Built-ins: auto-task, plan-execute, test-driven. Or roll your own.\n"
    "- **Agents** — Spawn sub-agents in isolated git worktrees or full clones. "
    "Parallel development without stepping on each other. Track who's where, "
    "what they're doing, kill them if they go rogue.\n"
    "- **Pipelines** — Deterministic automation with approval gates. Shell commands, "
    "LLM prompts, nested pipelines. Human-in-the-loop when it matters.\n"
    "- **Skills** — Reusable instruction sets compatible with the Agent Skills spec. "
    "Install from GitHub, search semantically, inject into agent context.\n"
    "- **MCP Proxy** — Progressive disclosure so tool definitions don't eat half "
    "the context window. Semantic tool search, intelligent recommendations, "
    "fallback suggestions when tools fail.\n"
    "- **Hooks** — Unified event system across 6 CLIs. Adapters normalize "
    "everything to a common model. Session lifecycle, tool interception, "
    "context injection.\n\n"
    "## Using Tools\n"
    "You have access to Gobby's MCP tools. To call internal tools, use progressive "
    "disclosure:\n"
    "1. `list_mcp_servers()` — discover servers\n"
    '2. `list_tools(server="gobby-tasks")` — see what\'s available\n'
    "3. `get_tool_schema(server_name, tool_name)` — get the schema (do this first!)\n"
    "4. `call_tool(server_name, tool_name, arguments)` — execute\n\n"
    "Internal servers: gobby-tasks, gobby-sessions, gobby-memory, gobby-workflows, "
    "gobby-agents, gobby-worktrees, gobby-clones, gobby-artifacts, gobby-pipelines, "
    "gobby-skills, gobby-metrics, gobby-hub, gobby-merge.\n\n"
    "Never guess parameter names — always check the schema first.\n\n"
    "## How to Be\n"
    "Be the senior engineer who makes the team better:\n"
    "- Push back on bad ideas. Suggest better ones.\n"
    "- Think out loud. Show your reasoning.\n"
    "- Use tools proactively when they'd save time.\n"
    "- Be concise — respect the reader's attention.\n"
    "- Have opinions about architecture, testing, code quality.\n"
    "- Get excited about elegant solutions. Be honest about trade-offs.\n"
    "- If you don't know something, say so and go find out."
)


def _find_cli_path() -> str | None:
    """Find Claude CLI path without resolving symlinks."""
    cli_path = shutil.which("claude")
    if cli_path and os.path.exists(cli_path) and os.access(cli_path, os.X_OK):
        return cli_path
    return None


def _find_mcp_config() -> str | None:
    """Find .mcp.json config file for MCP tool access."""
    cwd_config = Path.cwd() / ".mcp.json"
    if cwd_config.exists():
        return str(cwd_config)

    # Try the gobby project root
    gobby_root = Path(__file__).parent.parent.parent.parent
    gobby_config = gobby_root / ".mcp.json"
    if gobby_config.exists():
        return str(gobby_config)

    return None


def _parse_server_name(full_tool_name: str) -> str:
    """Extract server name from mcp__{server}__{tool} format."""
    if full_tool_name.startswith("mcp__"):
        parts = full_tool_name.split("__")
        if len(parts) >= 2:
            return parts[1]
    return "builtin"


@dataclass
class ChatSession:
    """
    A persistent chat session backed by ClaudeSDKClient.

    Maintains conversation context across messages and survives
    WebSocket disconnections. Sessions are identified by conversation_id.
    """

    conversation_id: str
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    _client: ClaudeSDKClient | None = field(default=None, repr=False)
    _connected: bool = field(default=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _model: str | None = field(default=None, repr=False)

    async def start(self, model: str | None = None) -> None:
        """Connect the ClaudeSDKClient with configured options."""
        cli_path = _find_cli_path()
        if not cli_path:
            raise RuntimeError("Claude CLI not found in PATH")

        mcp_config = _find_mcp_config()
        self._model = model

        options = ClaudeAgentOptions(
            system_prompt=CHAT_SYSTEM_PROMPT,
            max_turns=None,
            model=model or "claude-sonnet-4-5",
            allowed_tools=["mcp__gobby__*"],
            permission_mode="bypassPermissions",
            cli_path=cli_path,
            mcp_servers=mcp_config if mcp_config is not None else {},
            cwd=str(Path.cwd()),
        )

        self._client = ClaudeSDKClient(options=options)
        await self._client.connect()
        self._connected = True
        self.last_activity = datetime.now(UTC)
        logger.debug(f"ChatSession {self.conversation_id} started")

    async def send_message(self, content: str) -> AsyncIterator[ChatEvent]:
        """
        Send a user message and yield streaming events.

        Yields ChatEvent instances (TextChunk, ToolCallEvent,
        ToolResultEvent, DoneEvent) matching the existing protocol.
        """
        if not self._client or not self._connected:
            raise RuntimeError("ChatSession not connected. Call start() first.")

        async with self._lock:
            self.last_activity = datetime.now(UTC)

            await self._client.query(content)

            tool_calls_count = 0
            needs_spacing_before_text = False

            try:
                async for message in self._client.receive_response():
                    if isinstance(message, ResultMessage):
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
                                text = block.text
                                if needs_spacing_before_text and text:
                                    text = text.lstrip("\n")
                                    if text:
                                        text = "\n\n" + text
                                yield TextChunk(content=text)
                                needs_spacing_before_text = False
                            elif isinstance(block, ToolUseBlock):
                                tool_calls_count += 1
                                server_name = _parse_server_name(block.name)
                                yield ToolCallEvent(
                                    tool_call_id=block.id,
                                    tool_name=block.name,
                                    server_name=server_name,
                                    arguments=block.input if isinstance(block.input, dict) else {},
                                )

                    elif isinstance(message, UserMessage):
                        if isinstance(message.content, list):
                            for block in message.content:
                                if isinstance(block, ToolResultBlock):
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
                logger.error(f"ChatSession {self.conversation_id} error: {e}", exc_info=True)
                yield TextChunk(content=f"Generation failed: {e}")
                yield DoneEvent(tool_calls_count=tool_calls_count)

    async def interrupt(self) -> None:
        """Interrupt the current response stream."""
        if self._client and self._connected:
            try:
                await self._client.interrupt()
            except Exception as e:
                logger.warning(f"ChatSession {self.conversation_id} interrupt error: {e}")

    async def stop(self) -> None:
        """Disconnect the ClaudeSDKClient and clean up."""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning(f"ChatSession {self.conversation_id} disconnect error: {e}")
            finally:
                self._client = None
                self._connected = False
                logger.debug(f"ChatSession {self.conversation_id} stopped")

    @property
    def is_connected(self) -> bool:
        """Whether the session is currently connected."""
        return self._connected
