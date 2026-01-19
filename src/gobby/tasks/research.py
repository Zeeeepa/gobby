"""
Agentic codebase research for task expansion.
"""

import ast
import logging
import os
import re
import shlex
from pathlib import Path
from typing import Any

from gobby.config.app import TaskExpansionConfig
from gobby.llm import LLMService
from gobby.storage.tasks import Task
from gobby.utils.project_context import find_project_root

logger = logging.getLogger(__name__)


class TaskResearchAgent:
    """
    Agent that autonomously researches the codebase to gather context for a task.

    Implements a simple ReAct loop:
    1. Think: Analyze current context and decide next action
    2. Act: Execute a tool (glob, grep, read_file)
    3. Observe: Add tool output to context
    4. Repeat until done or timeout
    """

    def __init__(
        self,
        config: TaskExpansionConfig,
        llm_service: LLMService,
        mcp_manager: Any | None = None,
    ):
        self.config = config
        self.llm_service = llm_service
        self.mcp_manager = mcp_manager
        self.max_steps = 10
        self.root = find_project_root()
        # Search tool discovery happens effectively at runtime now via _build_prompt
        # but we keep the helper method if we want to pre-check.

    async def run(
        self,
        task: Task,
        enable_web_search: bool = False,
    ) -> dict[str, Any]:
        """
        Run the research loop.

        Args:
            task: The task to research.

        Returns:
            Dictionary containing gathered context (files, snippets, findings).
        """
        if not self.root:
            logger.warning("No project root found, skipping research")
            return {"relevant_files": [], "findings": "No project root found"}

        logger.info(f"Starting research for task {task.id}: {task.title}")

        # Initialize context
        context: dict[str, Any] = {
            "task": task,
            "history": [],
            "found_files": set(),
            "snippets": {},
        }

        # Select provider (use research_model if configured, else default)
        model = self.config.research_model or self.config.model
        provider = self.llm_service.get_provider(self.config.provider)

        for step in range(self.max_steps):
            # 1. Generate Thought/Action
            prompt = await self._build_step_prompt(context, step, enable_web_search)  # Made async
            response = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.config.research_system_prompt,
                model=model,
            )

            # Parse action
            action = self._parse_action(response)
            context["history"].append(
                {"role": "model", "content": response, "parsed_action": action}
            )

            if not action or action["tool"] == "done":
                reason = action.get("reason", "No action") if action else "Failed to parse action"
                logger.info(f"Research finished: {reason}")
                break

            # 2. Execute Action
            tool_output = await self._execute_tool(action)

            # 3. Observe
            context["history"].append({"role": "tool", "content": tool_output})
            logger.debug(f"Step {step} tool {action['tool']} output len: {len(tool_output)}")

        return self._summarize_results(context)

    async def _build_step_prompt(
        self,
        context: dict[str, Any],
        step: int,
        enable_web_search: bool = False,
    ) -> str:
        task = context["task"]
        history = context["history"]

        prompt = f"""Task: {task.title}
Description: {task.description}

You are researching this task to identify relevant files and implementation details.
You have access to the following tools:

1. glob(pattern): Find files matching a pattern (e.g. "src/**/*.py")
2. grep(pattern, path): Search for text in files (e.g. "def login", "src/")
3. read_file(path): Read the content of a file
4. done(reason): Finish research
"""
        # Add search tool if available and enabled
        # Check both config global enable AND request-specific enable
        # Note: config.web_research_enabled is the global "allowed" switch.
        # enable_web_search is the per-request "requested" switch.
        # We need BOTH to be true.
        can_use_search = self.config.web_research_enabled and enable_web_search

        if self.mcp_manager and can_use_search:
            # Dynamically check for search tool
            # We prefer 'search_web' if available, else others
            tools = await self.mcp_manager.list_tools()  # Assuming this API
            # Flatten tools list
            all_tools = []
            for _server, server_tools in tools.items():
                all_tools.extend(server_tools)

            for t in all_tools:
                if t.name in ("search_web", "google_search", "brave_search"):
                    prompt += f"5. {t.name}(query): {t.description[:100]}...\n"
                    break

        prompt += f"""
Current Context:
Found Files: {list(context["found_files"])}
Snippets: {list(context["snippets"].keys())}

History:
"""
        # Add limited history (last 5 turns to save context)
        recent_history = history[-5:]
        for item in recent_history:
            if item["role"] == "model":
                prompt += f"Agent: {item['content']}\n"
            elif item["role"] == "tool":
                # Truncate tool output
                content = item["content"]
                if len(content) > 500:
                    content = content[:500] + "... (truncated)"
                prompt += f"Tool: {content}\n"

        prompt += f"\nStep {step + 1}/{self.max_steps}. What is your next move? Respond with THOUGHT followed by ACTION."
        return prompt

    def _parse_action(self, response: str) -> dict[str, Any] | None:
        """
        Parse LLM response for ACTION: tool_name(args).

        Uses multiple parsing strategies in order of robustness:
        1. ast.literal_eval for Python-style tuple syntax
        2. shlex for shell-like quoting (handles commas in quotes)
        3. Simple comma split as last resort
        """
        # Check for explicit "ACTION: done" first (tighter than substring match)
        # Matches: "ACTION: done", "ACTION: done(reason)", "ACTION: done("reason")"
        done_match = re.search(
            r"^ACTION:\s*done(?:\s*\(([^)]*)\))?",
            response,
            re.IGNORECASE | re.MULTILINE,
        )
        if done_match:
            reason = done_match.group(1)
            if reason:
                reason = reason.strip().strip("'\"")
            return {"tool": "done", "reason": reason or response}

        # Parse ACTION: tool_name(args) pattern
        # Use DOTALL to handle args spanning multiple lines
        match = re.search(r"ACTION:\s*(\w+)\((.*)\)", response, re.IGNORECASE | re.DOTALL)
        if not match:
            return None

        tool = match.group(1).lower()
        args_str = match.group(2).strip()

        # Handle done tool explicitly (in case it matched the general pattern)
        if tool == "done":
            return {"tool": "done", "reason": args_str.strip("'\"") or response}

        # If no args, return empty args list
        if not args_str:
            return {"tool": tool, "args": []}

        # Try multiple parsing strategies in order of robustness
        args = None
        parse_errors = []

        # Strategy 1: ast.literal_eval as tuple
        # Handles: "arg1", "arg2" → ('arg1', 'arg2')
        # Handles escaped quotes, nested structures, etc.
        try:
            # Wrap in parens with trailing comma to make it a tuple
            parsed = ast.literal_eval(f"({args_str},)")
            args = [str(a) for a in parsed]
        except (ValueError, SyntaxError) as e:
            parse_errors.append(f"ast.literal_eval: {e}")

        # Strategy 2: shlex-based parsing (handles shell-like quoting)
        # Handles: "arg with spaces", 'single quotes', arg\ with\ escapes
        if args is None:
            try:
                lexer = shlex.shlex(args_str, posix=True)
                lexer.whitespace = ","
                lexer.whitespace_split = True
                args = [token.strip() for token in lexer]
            except ValueError as e:
                parse_errors.append(f"shlex: {e}")

        # Strategy 3: Simple comma split as last resort
        if args is None:
            args = [a.strip().strip("'\"") for a in args_str.split(",")]
            if not args or all(not a for a in args):
                logger.error(
                    f"All parsing strategies failed for args: {args_str!r}. Errors: {parse_errors}"
                )
                return None

        if parse_errors:
            logger.debug(
                f"Argument parsing recovered after failures: {parse_errors}. Final args: {args}"
            )

        return {"tool": tool, "args": args}

    async def _execute_tool(self, action: dict[str, Any]) -> str:
        tool = action["tool"]
        args = action.get("args", [])

        try:
            if tool == "glob":
                if not args:
                    return "Error: Missing pattern"
                return self._glob(args[0])
            elif tool == "grep":
                if len(args) < 2:
                    return "Error: Missing pattern or path"
                return self._grep(args[0], args[1])
            elif tool == "read_file":
                if not args:
                    return "Error: Missing path"
                return self._read_file(args[0])
            elif tool == "done":
                return "Done"

            # Check for MCP search tools
            # We strictly check if the tool is one of the search tools we support
            # The enable_web_search check was done at prompt time, but good to enforce here too
            # However, execute_tool doesn't receive the flag currently.
            # We rely on the model only calling it if presented in prompt.
            if self.mcp_manager:
                if tool in ("search_web", "google_search", "brave_search"):
                    if not args:
                        return "Error: Missing query"
                    # Call via MCP manager
                    # self.mcp_manager.call_tool returns Result object or dict
                    result = await self.mcp_manager.call_tool(tool, {"query": args[0]})
                    # Format result - assume it returns text or structured content
                    return str(result)

            return f"Error: Unknown tool {tool}"
        except Exception as e:
            return f"Error executing {tool}: {e}"

    def _glob(self, pattern: str) -> str:
        if not self.root:
            return "No root"
        # Security: ensure pattern doesn't traverse up
        if ".." in pattern:
            return "Error: .. not allowed"

        matches = []
        try:
            # Use rglob if ** in pattern, else glob
            # Simplified: Use fnmatch on all files walking from root (safer but slower)
            # Or use pathlib.glob
            # Let's use pathlib glob
            for path in self.root.glob(pattern):
                if path.is_file():
                    matches.append(str(path.relative_to(self.root)))
                if len(matches) > 50:  # Limit results
                    break
        except Exception as e:
            return f"Glob error: {e}"

        return "\n".join(matches) or "No matches found"

    def _grep(self, pattern: str, path_str: str) -> str:
        if not self.root:
            return "No root"
        search_path = (self.root / path_str).resolve()
        if self.root not in search_path.parents and search_path != self.root:
            return "Error: Path outside root"

        # Simple recursive grep
        # Limit to text files
        results = []

        is_dir = search_path.is_dir()

        # If dir, walk. If file, search.
        files_to_search = []
        if is_dir:
            for root, _, files in os.walk(search_path):
                for f in files:
                    # Skip hidden and non-text (basic heuristic)
                    if f.startswith("."):
                        continue
                    if f.endswith((".pyc", ".png", ".jpg")):
                        continue
                    files_to_search.append(Path(root) / f)
        else:
            if search_path.exists():
                files_to_search.append(search_path)

        count = 0
        for fpath in files_to_search:
            if count > 20:
                break  # Limit files matched
            try:
                rel_path = fpath.relative_to(self.root)
                with open(fpath, encoding="utf-8", errors="ignore") as fp:
                    content = fp.read()
                    if pattern in content:
                        # Extract snippet (one line context)
                        lines = content.splitlines()
                        for i, line in enumerate(lines):
                            if pattern in line:
                                results.append(f"{rel_path}:{i + 1}: {line.strip()}")
                                break  # One match per file for brevity in overview
                        count += 1
            except Exception:
                continue  # Skip files we can't read

        return "\n".join(results) or "No matches found"

    def _read_file(self, path_str: str) -> str:
        if not self.root:
            return "No root"
        path = (self.root / path_str).resolve()
        if self.root not in path.parents and path != self.root:
            return "Error: Path outside root"

        if not path.exists():
            return "Error: File not found"

        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
                # Limit size
                if len(content) > 5000:
                    return content[:5000] + "\n...(truncated)"
                return content
        except Exception as e:
            return f"Read error: {e}"

    def _summarize_results(self, context: dict[str, Any]) -> dict[str, Any]:
        """Convert agent history into structured context."""
        # Extract files that were read or found relevant
        found_files = set()
        web_search_results: list[dict[str, Any]] = []

        # Process history to extract files and web search results
        history = context["history"]
        i = 0
        while i < len(history):
            item = history[i]
            if item["role"] == "model":
                action = item.get("parsed_action")
                if action:
                    tool = action["tool"]
                    args = action.get("args", [])

                    if tool == "read_file" and args:
                        found_files.add(args[0])

                    # Capture web search results (action followed by tool output)
                    if tool in ("search_web", "google_search", "brave_search") and args:
                        query = args[0]
                        # Look for the tool output in the next item
                        if i + 1 < len(history) and history[i + 1]["role"] == "tool":
                            result = history[i + 1]["content"]
                            web_search_results.append(
                                {
                                    "tool": tool,
                                    "query": query,
                                    "result": result[:2000] if len(result) > 2000 else result,
                                }
                            )
            i += 1

        return {
            "relevant_files": list(found_files),
            "findings": "Agent research completed.",
            "web_research": web_search_results,
            "raw_history": history,
        }
