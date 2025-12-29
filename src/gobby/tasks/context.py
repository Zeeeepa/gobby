"""
Context gathering for task expansion.

This module provides tools to gather relevant context from the codebase and
project state to inform the task expansion process.
"""

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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task": self.task.to_dict(),
            "related_tasks": [t.to_dict() for t in self.related_tasks],
            "relevant_files": self.relevant_files,
            "project_patterns": self.project_patterns,
            # We don't include full snippets in dict summary often, but useful for debug
            "snippet_count": len(self.file_snippets),
        }


class ExpansionContextGatherer:
    """Gathers context for task expansion."""

    def __init__(self, task_manager: Any):  # Type Any to avoid circular import if needed
        self.task_manager = task_manager

    async def gather_context(self, task: Task) -> ExpansionContext:
        """
        Gather all relevant context for a task.

        Args:
            task: The task to gather context for.

        Returns:
            Populated ExpansionContext object.
        """
        logger.info(f"Gathering expansion context for task {task.id}")

        related_tasks = await self._find_related_tasks(task)
        relevant_files = await self._find_relevant_files(task)
        file_snippets = self._read_file_snippets(relevant_files)
        project_patterns = self._detect_project_patterns()

        return ExpansionContext(
            task=task,
            related_tasks=related_tasks,
            relevant_files=relevant_files,
            file_snippets=file_snippets,
            project_patterns=project_patterns,
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
            words = task.description.split()
            for word in words:
                # remove potential punctuation
                clean_word = word.strip(".,;:()`'")
                if "." in clean_word and len(clean_word) > 2:
                    # Potential filename
                    # Ensure it's not external url
                    if not clean_word.startswith("http"):
                        path = root / clean_word
                        if path.exists() and path.is_file():
                            relevant.append(str(path.relative_to(root)))

        return relevant

    def _read_file_snippets(self, files: list[str]) -> dict[str, str]:
        """Read content of relevant files."""
        snippets = {}
        root = find_project_root()
        if not root:
            return snippets

        for fname in files:
            path = root / fname
            if path.exists() and path.is_file():
                try:
                    # Read first 50 lines as context
                    with open(path, "r", encoding="utf-8") as f:
                        lines = [next(f) for _ in range(50)]
                    snippets[fname] = "".join(lines)
                except Exception as e:
                    logger.warning(f"Failed to read context file {fname}: {e}")
        return snippets

    def _detect_project_patterns(self) -> dict[str, str]:
        """Detect project patterns (e.g. test framework, language)."""
        patterns = {}
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
