"""
TDD sandwich pattern utilities for task expansion.

This module provides shared logic for applying the TDD (Test-Driven Development)
sandwich pattern to task expansions. The sandwich wraps implementation tasks:
- ONE [TDD] task at the start (RED phase - write failing tests)
- Original tasks renamed with [IMPL] prefix (GREEN phase - make tests pass)
- ONE [REF] task at the end (BLUE phase - refactor while keeping tests green)

Used by both MCP expand_task tool and CLI expand command.
"""

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.storage.task_dependencies import TaskDependencyManager
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)

__all__ = [
    "TDD_PREFIXES",
    "TDD_SKIP_PATTERNS",
    "TDD_CRITERIA_RED",
    "TDD_CRITERIA_BLUE",
    "TDD_PARENT_CRITERIA",
    "TDD_CATEGORIES",
    "should_skip_tdd",
    "should_skip_expansion",
    "apply_tdd_sandwich",
    "build_expansion_context",
]

# TDD triplet prefixes - used for both skip detection and triplet creation
TDD_PREFIXES = ("[TDD]", "[IMPL]", "[REF]")

# Task categories that should get TDD treatment
TDD_CATEGORIES = ("code", "config")

# Patterns for tasks that should skip TDD transformation (case-insensitive)
TDD_SKIP_PATTERNS = (
    # New TDD prefixes (already in triplet form)
    r"^\[TDD\]",
    r"^\[IMPL\]",
    r"^\[REF\]",
    # Legacy TDD prefixes (backwards compatibility)
    r"^Write tests for:",
    r"^Implement:",
    r"^Refactor:",
    # Deletion tasks (simple operations, no tests needed)
    r"^Delete\b",
    r"^Remove\b",
    # Documentation updates
    r"^Update.*README",
    r"^Update.*documentation",
    r"^Update.*docs\b",
    # Config file updates
    r"^Update.*\.toml\b",
    r"^Update.*\.yaml\b",
    r"^Update.*\.yml\b",
    r"^Update.*\.json\b",
    r"^Update.*\.env\b",
    r"^Update.*config",
)

# TDD validation criteria templates per phase
TDD_CRITERIA_RED = """## Deliverable
- [ ] Tests written that define expected behavior
- [ ] Tests fail when run (no implementation yet)
- [ ] Test coverage addresses acceptance criteria from parent task
"""

TDD_CRITERIA_BLUE = """## Deliverable
- [ ] All tests continue to pass
- [ ] Code refactored for clarity and maintainability
- [ ] No new functionality added (refactor only)
- [ ] Unrelated bugs discovered during refactor logged as new bug tasks

**Note:** If you discover bugs outside your scope during refactoring, create bug tasks
for them rather than fixing them now.
"""

TDD_PARENT_CRITERIA = """## Deliverable
- [ ] All child tasks completed
"""


def should_skip_tdd(title: str) -> bool:
    """
    Check if a task should skip TDD transformation based on its title.

    Tasks are skipped if they match any TDD_SKIP_PATTERNS:
    - Already TDD triplet tasks ([TDD], [IMPL], [REF] prefixes)
    - Legacy TDD prefixes (Write tests for:, Implement:, Refactor:)
    - Deletion tasks (Delete X, Remove Y)
    - Documentation updates (Update README, Update docs)
    - Config file updates (Update pyproject.toml, Update .env)

    Args:
        title: The task title to check

    Returns:
        True if the task should skip TDD transformation, False otherwise
    """
    for pattern in TDD_SKIP_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False


def should_skip_expansion(title: str, is_expanded: bool, force: bool = False) -> tuple[bool, str]:
    """
    Check if a task should be skipped from expansion.

    Tasks are skipped if:
    - Already expanded (is_expanded=True) unless force=True
    - Title starts with TDD prefixes ([TDD], [IMPL], [REF]) - these are atomic tasks

    Args:
        title: The task title to check
        is_expanded: Whether the task's is_expanded flag is set
        force: Whether to force expansion even if already expanded

    Returns:
        Tuple of (should_skip: bool, reason: str)
        reason is empty string if should_skip is False
    """
    # Check for TDD prefixes - these tasks should never be expanded
    for prefix in TDD_PREFIXES:
        if title.startswith(prefix):
            return True, f"TDD task ({prefix})"

    # Check if already expanded
    if is_expanded and not force:
        return True, "already expanded"

    return False, ""


async def apply_tdd_sandwich(
    task_manager: "LocalTaskManager",
    dep_manager: "TaskDependencyManager",
    parent_task_id: str,
    impl_task_ids: list[str],
) -> dict[str, Any]:
    """Apply TDD sandwich pattern to a parent task's children.

    Creates a "sandwich" structure where implementation tasks are wrapped:
    - ONE [TDD] task at the start (RED phase - write failing tests for all impls)
    - Original child tasks renamed with [IMPL] prefix (GREEN phase)
    - ONE [REF] task at the end (BLUE phase - refactor everything)

    Dependencies are wired:
    - All [IMPL] tasks are blocked by the [TDD] task
    - [REF] task is blocked by [TDD] task and all [IMPL] tasks

    Args:
        task_manager: LocalTaskManager instance for task CRUD
        dep_manager: TaskDependencyManager instance for dependency wiring
        parent_task_id: The parent task ID being expanded
        impl_task_ids: List of implementation task IDs (the original children)

    Returns:
        Dict with:
        - success: True if sandwich was applied
        - tasks_created: Number of tasks created (2: TDD + REF)
        - test_task_id: ID of the created TDD task
        - refactor_task_id: ID of the created REF task
        - impl_task_count: Number of impl tasks wrapped
        Or error info if failed
    """
    parent = task_manager.get_task(parent_task_id)
    if not parent:
        return {"success": False, "error": f"Parent task not found: {parent_task_id}"}

    if not impl_task_ids:
        return {"success": False, "error": "No implementation tasks to wrap"}

    # Skip if already TDD-applied
    if parent.is_tdd_applied:
        return {"success": False, "skipped": True, "reason": "already_applied"}

    try:
        # Build list of impl task titles for TDD task context
        impl_titles = []
        for impl_id in impl_task_ids:
            impl_task = task_manager.get_task(impl_id)
            if impl_task:
                impl_titles.append(f"- {impl_task.title}")
        impl_list = "\n".join(impl_titles) if impl_titles else "- (implementation tasks)"

        # 1. Create ONE Test Task (Red phase) - tests for all implementations
        test_task = task_manager.create_task(
            title=f"[TDD] Write failing tests for {parent.title}",
            description=(
                f"Write failing tests for: {parent.title}\n\n"
                "## Implementation tasks to cover:\n"
                f"{impl_list}\n\n"
                "RED phase of TDD - define expected behavior before implementation."
            ),
            project_id=parent.project_id,
            parent_task_id=parent.id,
            task_type="task",
            priority=parent.priority,
            validation_criteria=TDD_CRITERIA_RED,
            category="test",
        )

        # 2. Add [IMPL] prefix to all implementation tasks and wire dependencies
        for impl_id in impl_task_ids:
            impl_task = task_manager.get_task(impl_id)
            if impl_task and not impl_task.title.startswith("[IMPL]"):
                task_manager.update_task(impl_id, title=f"[IMPL] {impl_task.title}")
            try:
                dep_manager.add_dependency(impl_id, test_task.id, "blocks")
            except ValueError:
                pass  # Dependency already exists

        # 3. Create ONE Refactor Task (Blue phase) - refactor after all impls done
        refactor_task = task_manager.create_task(
            title=f"[REF] Refactor and verify {parent.title}",
            description=(
                f"Refactor implementations in: {parent.title}\n\n"
                "BLUE phase of TDD - clean up while keeping tests green."
            ),
            project_id=parent.project_id,
            parent_task_id=parent.id,
            task_type="task",
            priority=parent.priority,
            validation_criteria=TDD_CRITERIA_BLUE,
            category="code",
        )

        # 4. Wire refactor to be blocked by TDD task and all implementation tasks
        # REFACTOR depends on TDD (must complete testing before refactoring)
        try:
            dep_manager.add_dependency(refactor_task.id, test_task.id, "blocks")
        except ValueError:
            pass  # Dependency already exists

        # REFACTOR depends on all impl tasks
        for impl_id in impl_task_ids:
            try:
                dep_manager.add_dependency(refactor_task.id, impl_id, "blocks")
            except ValueError:
                pass  # Dependency already exists

        # Mark parent as TDD-applied
        task_manager.update_task(
            parent.id,
            is_tdd_applied=True,
            validation_criteria=TDD_PARENT_CRITERIA,
        )

        return {
            "success": True,
            "tasks_created": 2,  # TDD + REF (impl tasks already existed)
            "test_task_id": test_task.id,
            "refactor_task_id": refactor_task.id,
            "impl_task_count": len(impl_task_ids),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_expansion_context(
    expansion_context_json: str | None,
    user_context: str | None,
) -> str | None:
    """
    Build context for expansion by merging stored data with user context.

    If the task has expansion_context (legacy enrichment data), parse it and
    include research findings, validation criteria, and complexity info.

    Args:
        expansion_context_json: JSON string from task.expansion_context (may be None)
        user_context: User-provided context string (may be None)

    Returns:
        Merged context string, or None if no context available
    """
    import json

    enrichment_parts: list[str] = []

    # Parse stored expansion_context (legacy enrichment data)
    if expansion_context_json:
        try:
            enrichment_data = json.loads(expansion_context_json)

            # Include research findings
            if research := enrichment_data.get("research_findings"):
                enrichment_parts.append(f"## Research Findings\n{research}")

            # Include validation criteria
            if validation := enrichment_data.get("validation_criteria"):
                enrichment_parts.append(f"## Validation Criteria\n{validation}")

            # Include complexity info
            complexity_level = enrichment_data.get("complexity_level")
            subtask_count = enrichment_data.get("suggested_subtask_count")
            if complexity_level or subtask_count:
                complexity_info = []
                if complexity_level:
                    complexity_info.append(f"Complexity level: {complexity_level}")
                if subtask_count:
                    complexity_info.append(f"Suggested subtask count: {subtask_count}")
                enrichment_parts.append("## Complexity Analysis\n" + "\n".join(complexity_info))

        except (json.JSONDecodeError, TypeError):
            # Legacy or plain text context - preserve it as raw text
            enrichment_parts.append(f"## Legacy Expansion Context\n{expansion_context_json}")

    # Add user-provided context
    if user_context:
        enrichment_parts.append(f"## Additional Context\n{user_context}")

    # Return merged context or None
    if enrichment_parts:
        return "\n\n".join(enrichment_parts)
    return None
