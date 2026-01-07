"""
Context gathering for task expansion.

This module provides tools to gather relevant context from the codebase and
project state to inform the task expansion process.
"""

import asyncio
import itertools
import logging
from dataclasses import dataclass
from typing import Any

from gobby.storage.tasks import Task
from gobby.utils.project_context import find_project_root

logger = logging.getLogger(__name__)


@dataclass
class ExpansionContext:
    """Context gathered for task expansion."""

    task: Task
    related_tasks: list[Task]
    relevant_files: list[str]
    file_snippets: dict[str, str]
    project_patterns: dict[str, str]
    agent_findings: str = ""
    web_research: list[dict[str, Any]] | None = None
    existing_tests: dict[str, list[str]] | None = None  # module -> [test files]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task": self.task.to_dict(),
            "related_tasks": [t.to_dict() for t in self.related_tasks],
            "relevant_files": self.relevant_files,
            "project_patterns": self.project_patterns,
            "agent_findings": self.agent_findings,
            "web_research": self.web_research,
            "existing_tests": self.existing_tests,
            # We don't include full snippets in dict summary often, but useful for debug
            "snippet_count": len(self.file_snippets),
        }


class ExpansionContextGatherer:
    """Gathers context for task expansion."""

    def __init__(
        self,
        task_manager: Any,
        llm_service: Any = None,
        config: Any = None,
        mcp_manager: Any = None,
    ):  # Type Any to avoid circular import
        self.task_manager = task_manager
        self.llm_service = llm_service
        self.config = config
        self.mcp_manager = mcp_manager

    async def gather_context(
        self,
        task: Task,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
    ) -> ExpansionContext:
        """
        Gather all relevant context for a task.

        Args:
            task: The task to gather context for.
            enable_web_research: Whether to enable web research.
            enable_code_context: Whether to enable code context gathering.
        Returns:
            Populated ExpansionContext object.
        """
        logger.info(f"Gathering expansion context for task {task.id}")

        related_tasks = await self._find_related_tasks(task)

        # 1. Regex/Heuristic based file finding
        relevant_files = []
        if enable_code_context:
            relevant_files = await self._find_relevant_files(task)

        # 2. Agentic research (if enabled)
        agent_findings = ""
        web_research: list[dict[str, Any]] | None = None
        research_globally_enabled = getattr(self.config, "codebase_research_enabled", False)
        should_run_research = enable_code_context and research_globally_enabled

        if should_run_research and self.llm_service:
            # Apply research timeout if configured
            research_timeout = getattr(self.config, "research_timeout", 60.0)
            try:
                async with asyncio.timeout(research_timeout):
                    from gobby.tasks.research import TaskResearchAgent

                    agent = TaskResearchAgent(self.config, self.llm_service, self.mcp_manager)
                    research_result = await agent.run(task, enable_web_search=enable_web_research)

                    # Merge found files
                    for f in research_result.get("relevant_files", []):
                        if f not in relevant_files:
                            relevant_files.append(f)

                    agent_findings = research_result.get("findings", "")

                    # Capture web research results if any
                    web_research_data = research_result.get("web_research", [])
                    if web_research_data:
                        web_research = web_research_data
                        logger.info(f"Captured {len(web_research)} web search results")

                    logger.info(
                        f"Agentic research added {len(research_result.get('relevant_files', []))} files"
                    )
            except TimeoutError:
                logger.warning(
                    f"Research phase timed out after {research_timeout}s. "
                    f"Continuing with partial context. Consider increasing task_expansion.research_timeout."
                )
            except Exception as e:
                logger.error(f"Agentic research failed: {e}")

        file_snippets = self._read_file_snippets(relevant_files)
        project_patterns = self._detect_project_patterns()

        # Discover existing tests for relevant Python files
        python_files = [f for f in relevant_files if f.endswith(".py")]
        existing_tests = self.discover_existing_tests(python_files) if python_files else {}

        return ExpansionContext(
            task=task,
            related_tasks=related_tasks,
            relevant_files=relevant_files,
            file_snippets=file_snippets,
            project_patterns=project_patterns,
            agent_findings=agent_findings,
            web_research=web_research,
            existing_tests=existing_tests if existing_tests else None,
        )

    async def _find_related_tasks(self, task: Task) -> list[Task]:
        """Find tasks related to the current task using fuzzy match or project."""
        # Simple implementation for now: latest tasks in same project
        # In the future, this could use vector search or title fuzzy matching
        cols = self.task_manager.list_tasks(
            project_id=task.project_id,
            limit=5,
            status="open",
        )
        return [t for t in cols if t.id != task.id]

    async def _find_relevant_files(self, task: Task) -> list[str]:
        """Find files relevant to the task description."""
        # Placeholder for actual relevance logic (e.g. grep or filenames in description)
        # For now, return empty list or naive scan?
        # Let's do a simple check: if description mentions a file existing in src, include it.
        root = find_project_root()
        if not root:
            return []

        relevant = []
        # Naive: splits description and checks if tokens match filenames
        # This is very basic but serves as a starting point.
        if task.description:
            # Regex to find potential file paths:
            # - alphanumeric, dots, slashes, dashes, underscores
            # - must end with a common extension
            # - length constraint to avoid noise
            import re

            # Common extensions to look for
            extensions = "py|js|ts|tsx|jsx|md|json|html|css|yaml|toml|sh"
            pattern = re.compile(rf"(?:\.?/)?[\w\-/_]+\.(?:{extensions})\b", re.IGNORECASE)

            matches = pattern.findall(task.description)
            for match in matches:
                # Clean up match
                fpath = match.strip()
                # Resolve path
                try:
                    path = (root / fpath).resolve()
                    # Security check: must be within root
                    if root in path.parents or path == root:
                        if path.exists() and path.is_file():
                            rel_path = str(path.relative_to(root))
                            if rel_path not in relevant:
                                relevant.append(rel_path)
                except Exception:
                    continue

        return relevant

    def _read_file_snippets(self, files: list[str]) -> dict[str, str]:
        """Read content of relevant files."""
        snippets: dict[str, str] = {}
        root = find_project_root()
        if not root:
            return snippets

        for fname in files:
            path = root / fname
            if path.exists() and path.is_file():
                try:
                    # Read first 50 lines as context
                    with open(path, encoding="utf-8") as f:
                        lines = list(itertools.islice(f, 50))
                    snippets[fname] = "".join(lines)
                except Exception as e:
                    logger.warning(f"Failed to read context file {fname}: {e}")
        return snippets

    def _detect_project_patterns(self) -> dict[str, str]:
        """Detect project patterns (e.g. test framework, language)."""
        patterns: dict[str, str] = {}
        root = find_project_root()
        if not root:
            return patterns

        # Check for common config files
        if (root / "pyproject.toml").exists():
            patterns["build_system"] = "pyproject.toml"
        if (root / "package.json").exists():
            patterns["frontend"] = "npm/node"

        # Check for test directories
        if (root / "tests").exists():
            patterns["tests"] = "tests/"

        return patterns

    def discover_existing_tests(self, module_paths: list[str]) -> dict[str, list[str]]:
        """
        Find test files that cover the given modules.

        For each module path, searches the tests/ directory for files that
        import from that module.

        Args:
            module_paths: List of file paths (e.g., ['src/gobby/tasks/expansion.py'])

        Returns:
            Dict mapping module path to list of test files that import it.
        """
        import re
        import subprocess

        result: dict[str, list[str]] = {}
        root = find_project_root()
        if not root:
            return result

        tests_dir = root / "tests"
        if not tests_dir.exists():
            return result

        for module_path in module_paths:
            # Convert file path to import path
            # e.g., src/gobby/tasks/expansion.py -> gobby.tasks.expansion
            import_path = self._path_to_import(module_path)
            if not import_path:
                continue

            # Search for imports of this module in tests/
            try:
                # Use grep to find test files that import this module
                # Pattern matches: from {module} import, import {module}
                pattern = rf"(from\s+{re.escape(import_path)}(\.\w+)*\s+import|import\s+{re.escape(import_path)})"
                grep_result = subprocess.run(
                    ["grep", "-r", "-l", "-E", pattern, str(tests_dir)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if grep_result.returncode == 0 and grep_result.stdout.strip():
                    test_files = []
                    for line in grep_result.stdout.strip().split("\n"):
                        if line:
                            # Convert to relative path from project root
                            rel_path = line.replace(str(root) + "/", "")
                            test_files.append(rel_path)

                    if test_files:
                        result[module_path] = test_files
                        logger.debug(
                            f"Found {len(test_files)} test files for {module_path}: {test_files}"
                        )

            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout searching for tests of {module_path}")
            except Exception as e:
                logger.warning(f"Error searching for tests of {module_path}: {e}")

        return result

    def _path_to_import(self, file_path: str) -> str | None:
        """
        Convert a file path to a Python import path.

        Args:
            file_path: File path like 'src/gobby/tasks/expansion.py'

        Returns:
            Import path like 'gobby.tasks.expansion', or None if not convertible.
        """
        # Remove .py extension
        if not file_path.endswith(".py"):
            return None

        path = file_path[:-3]  # Remove .py

        # Remove common prefixes
        for prefix in ["src/", "lib/"]:
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break

        # Convert slashes to dots
        import_path = path.replace("/", ".")

        # Remove __init__ suffix if present
        if import_path.endswith(".__init__"):
            import_path = import_path[:-9]

        return import_path if import_path else None
