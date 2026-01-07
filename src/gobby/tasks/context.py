"""
Context gathering for task expansion.

This module provides tools to gather relevant context from the codebase and
project state to inform the task expansion process.
"""

from __future__ import annotations

import ast
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
    function_signatures: dict[str, list[str]] | None = None  # file -> [signatures]
    verification_commands: dict[str, str] | None = None  # name -> command
    project_structure: str | None = None  # tree view of project directories

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
            "function_signatures": self.function_signatures,
            "verification_commands": self.verification_commands,
            "project_structure": self.project_structure,
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

        # Extract function signatures from Python files
        function_signatures = self.extract_signatures(python_files) if python_files else {}

        # Get verification commands from project config
        verification_commands = self._get_verification_commands()

        # Generate project structure tree
        project_structure = self._generate_project_structure()

        return ExpansionContext(
            task=task,
            related_tasks=related_tasks,
            relevant_files=relevant_files,
            file_snippets=file_snippets,
            project_patterns=project_patterns,
            agent_findings=agent_findings,
            web_research=web_research,
            existing_tests=existing_tests if existing_tests else None,
            function_signatures=function_signatures if function_signatures else None,
            verification_commands=verification_commands if verification_commands else None,
            project_structure=project_structure,
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

    def _get_verification_commands(self) -> dict[str, str]:
        """Get verification commands from project config.

        Returns:
            Dict mapping command names to their values, e.g.:
            {
                "unit_tests": "npm test",
                "lint": "npm run lint",
                "type_check": "npm run typecheck"
            }
        """
        from gobby.utils.project_context import get_verification_config

        commands: dict[str, str] = {}
        config = get_verification_config()

        if not config:
            return commands

        if config.unit_tests:
            commands["unit_tests"] = config.unit_tests
        if config.type_check:
            commands["type_check"] = config.type_check
        if config.lint:
            commands["lint"] = config.lint
        if config.integration:
            commands["integration"] = config.integration

        # Include any custom commands
        if config.custom:
            commands.update(config.custom)

        return commands

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

    def extract_signatures(self, file_paths: list[str]) -> dict[str, list[str]]:
        """
        Extract function and class signatures from Python files using AST.

        Args:
            file_paths: List of file paths (e.g., ['src/gobby/tasks/expansion.py'])

        Returns:
            Dict mapping file path to list of signatures:
            {
                'src/gobby/tasks/expansion.py': [
                    'class TaskExpander',
                    'def expand_task(self, task_id: str, ...) -> dict[str, Any]',
                    'def _parse_subtasks(self, response: str) -> list[SubtaskSpec]',
                ]
            }
        """
        result: dict[str, list[str]] = {}
        root = find_project_root()
        if not root:
            return result

        for file_path in file_paths:
            # Only process Python files
            if not file_path.endswith(".py"):
                continue

            full_path = root / file_path
            if not full_path.exists() or not full_path.is_file():
                continue

            try:
                with open(full_path, encoding="utf-8") as f:
                    source = f.read()

                tree = ast.parse(source)
                signatures = self._extract_signatures_from_ast(tree)

                if signatures:
                    result[file_path] = signatures
                    logger.debug(f"Extracted {len(signatures)} signatures from {file_path}")

            except SyntaxError as e:
                logger.warning(f"Syntax error parsing {file_path}: {e}")
            except Exception as e:
                logger.warning(f"Error extracting signatures from {file_path}: {e}")

        return result

    def _extract_signatures_from_ast(self, tree: ast.AST) -> list[str]:
        """
        Extract signatures from an AST tree.

        Args:
            tree: Parsed AST tree

        Returns:
            List of signature strings
        """
        signatures: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Class signature
                bases = ", ".join(self._get_base_names(node))
                if bases:
                    signatures.append(f"class {node.name}({bases})")
                else:
                    signatures.append(f"class {node.name}")

            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Function signature with type hints
                sig = self._format_function_signature(node)
                signatures.append(sig)

        return signatures

    def _get_base_names(self, class_node: ast.ClassDef) -> list[str]:
        """Get base class names from a ClassDef node."""
        names: list[str] = []
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                names.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle cases like module.Class
                names.append(ast.unparse(base))
            elif isinstance(base, ast.Subscript):
                # Handle generics like Generic[T]
                names.append(ast.unparse(base))
        return names

    def _format_function_signature(
        self, func_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> str:
        """
        Format a function signature with type hints.

        Args:
            func_node: Function AST node

        Returns:
            Formatted signature string like 'def foo(x: int, y: str) -> bool'
        """
        prefix = "async def" if isinstance(func_node, ast.AsyncFunctionDef) else "def"
        name = func_node.name

        # Format arguments
        args_parts: list[str] = []

        # Handle positional-only args (Python 3.8+)
        for arg in func_node.args.posonlyargs:
            args_parts.append(self._format_arg(arg))
        if func_node.args.posonlyargs:
            args_parts.append("/")

        # Regular args
        num_defaults = len(func_node.args.defaults)
        num_args = len(func_node.args.args)
        for i, arg in enumerate(func_node.args.args):
            default_idx = i - (num_args - num_defaults)
            if default_idx >= 0:
                args_parts.append(f"{self._format_arg(arg)}=...")
            else:
                args_parts.append(self._format_arg(arg))

        # *args
        if func_node.args.vararg:
            args_parts.append(f"*{self._format_arg(func_node.args.vararg)}")
        elif func_node.args.kwonlyargs:
            args_parts.append("*")

        # Keyword-only args
        for i, arg in enumerate(func_node.args.kwonlyargs):
            if func_node.args.kw_defaults[i] is not None:
                args_parts.append(f"{self._format_arg(arg)}=...")
            else:
                args_parts.append(self._format_arg(arg))

        # **kwargs
        if func_node.args.kwarg:
            args_parts.append(f"**{self._format_arg(func_node.args.kwarg)}")

        args_str = ", ".join(args_parts)

        # Return type annotation
        return_annotation = ""
        if func_node.returns:
            try:
                return_annotation = f" -> {ast.unparse(func_node.returns)}"
            except Exception:
                return_annotation = " -> ..."

        return f"{prefix} {name}({args_str}){return_annotation}"

    def _format_arg(self, arg: ast.arg) -> str:
        """Format a function argument with optional type annotation."""
        if arg.annotation:
            try:
                return f"{arg.arg}: {ast.unparse(arg.annotation)}"
            except Exception:
                return f"{arg.arg}: ..."
        return arg.arg

    def _generate_project_structure(self, max_depth: int = 3) -> str | None:
        """
        Generate a tree view of the project structure.

        Primary: Uses gitingest (works with any language, respects .gitignore)
        Fallback: Custom tree builder using pathlib

        This provides context to help the LLM understand where files should
        be placed, preventing hallucinated paths like 'gt/core/file.py'.

        Args:
            max_depth: Maximum depth for fallback tree builder

        Returns:
            Tree view string with file placement guidance, or None if failed.
        """
        from pathlib import Path

        root = find_project_root()
        if not root:
            return None

        tree = None

        # Primary: Try gitingest
        try:
            from gitingest import ingest

            _summary, tree, _content = ingest(str(root))
        except ImportError:
            logger.debug("gitingest not installed, using fallback tree builder")
        except Exception as e:
            logger.debug(f"gitingest failed ({e}), using fallback tree builder")

        # Fallback: Custom tree builder
        if not tree:
            tree = self._build_tree_fallback(root, max_depth)

        if not tree:
            return None

        lines = ["## Project Structure", "", tree]

        # Add file placement guidance based on common patterns
        guidance = self._get_file_placement_guidance(root)
        if guidance:
            lines.append("")
            lines.append("## File Placement Guidance")
            lines.append(guidance)

        return "\n".join(lines)

    def _build_tree_fallback(self, root: Path, max_depth: int = 3) -> str | None:
        """
        Fallback tree builder using pathlib when gitingest unavailable.

        Args:
            root: Project root path
            max_depth: Maximum depth to traverse

        Returns:
            Tree string or None
        """
        lines: list[str] = []

        # Source directories to include
        source_dirs = ["src", "lib", "app", "tests"]

        for src_dir in source_dirs:
            dir_path = root / src_dir
            if dir_path.exists() and dir_path.is_dir():
                self._build_tree_recursive(dir_path, root, lines, max_depth=max_depth)

        return "\n".join(lines) if lines else None

    def _build_tree_recursive(
        self,
        path: Path,
        root: Path,
        lines: list[str],
        prefix: str = "",
        max_depth: int = 3,
        current_depth: int = 0,
    ) -> None:
        """Recursively build tree lines for a directory."""
        if current_depth > max_depth:
            return

        skip_dirs = {
            "__pycache__", ".git", ".venv", "venv", "node_modules",
            ".pytest_cache", ".mypy_cache", "htmlcov", "dist", "build", ".egg-info",
        }

        rel_path = path.relative_to(root)
        lines.append(f"{prefix}{rel_path}/")

        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        dirs = [c for c in children if c.is_dir() and c.name not in skip_dirs]

        for i, child in enumerate(dirs):
            is_last = i == len(dirs) - 1
            child_prefix = prefix + ("    " if is_last else "│   ")
            self._build_tree_recursive(
                child, root, lines, prefix=child_prefix,
                max_depth=max_depth, current_depth=current_depth + 1,
            )

    def _get_file_placement_guidance(self, root: Path) -> str:
        """
        Extract file placement guidance from CLAUDE.md or provide defaults.

        Returns guidance string for common file types.
        """
        guidance_lines = []

        # Check for CLAUDE.md
        claude_md = root / "CLAUDE.md"
        if claude_md.exists():
            try:
                content = claude_md.read_text(encoding="utf-8")
                # Look for architecture or file placement sections
                if "src/gobby" in content:
                    # This is a Gobby project - provide specific guidance
                    guidance_lines.extend(
                        [
                            "- Task-related code: `src/gobby/tasks/`",
                            "- Workflow actions: `src/gobby/workflows/`",
                            "- MCP tools: `src/gobby/mcp_proxy/tools/`",
                            "- CLI commands: `src/gobby/cli/`",
                            "- Storage/DB: `src/gobby/storage/`",
                            "- Configuration: `src/gobby/config/`",
                            "- Tests mirror source: `tests/tasks/`, `tests/workflows/`, etc.",
                        ]
                    )
            except Exception:
                pass

        # Default guidance if CLAUDE.md doesn't provide specific info
        if not guidance_lines:
            # Detect common patterns
            if (root / "src").exists():
                pkg_dirs = [d.name for d in (root / "src").iterdir() if d.is_dir()]
                if pkg_dirs:
                    pkg = pkg_dirs[0]  # Usually the main package
                    guidance_lines.append(f"- Source code goes in `src/{pkg}/`")
            if (root / "tests").exists():
                guidance_lines.append("- Tests go in `tests/` mirroring source structure")

        return "\n".join(guidance_lines)
