"""Helper functions and constants for task tools.

Pure functions with no external dependencies that provide utility
for task operations.
"""

# Reasons for which commit linking and validation are skipped when closing tasks
SKIP_REASONS: frozenset[str] = frozenset(
    {"duplicate", "already_implemented", "wont_fix", "obsolete"}
)

# Category inference patterns mapping category to keywords/phrases
_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "code": (
        "implement",
        "create function",
        "add method",
        "refactor",
        "fix bug",
        "write code",
        "add class",
        "modify function",
        "update implementation",
        "build feature",
    ),
    "config": (
        ".yaml",
        ".toml",
        ".json",
        ".env",
        "config",
        "settings",
        "configuration",
        "environment variable",
    ),
    "docs": (
        "document",
        "readme",
        "update docs",
        "write documentation",
        "docstring",
        "add comments",
        "api docs",
    ),
    "test": (
        "write test",
        "add test",
        "unit test",
        "integration test",
        "test case",
        "test coverage",
        "write tests for:",
    ),
    "research": (
        "investigate",
        "explore",
        "research",
        "analyze",
        "study",
        "evaluate options",
        "compare",
        "spike",
    ),
    "planning": (
        "design",
        "plan",
        "architect",
        "spec",
        "blueprint",
        "roadmap",
        "define",
    ),
    "manual": (
        "verify that",
        "verify the",
        "check that",
        "check the",
        "functional test",
        "functional testing",
        "smoke test",
        "sanity test",
        "sanity check",
        "manual test",
        "manually verify",
        "manually test",
        "manually check",
        "run and check",
        "run and verify",
        "test that the",
        "confirm that",
        "ensure that",
        "validate that",
        "run each command",
        "run the command",
        "verify output",
        "check output",
        "verify functionality",
        "test functionality",
    ),
}


def _infer_category(title: str, description: str | None) -> str | None:
    """
    Infer category from task title/description patterns.

    Checks against known patterns for each category type.
    Returns the first matching category, or None to let user/LLM decide.

    Priority order: test, code, config, docs, research, planning, manual
    """
    text = f"{title} {description or ''}".lower()

    # Check categories in priority order
    priority_order = ("test", "code", "config", "docs", "research", "planning", "manual")
    for category in priority_order:
        patterns = _CATEGORY_PATTERNS.get(category, ())
        for pattern in patterns:
            if pattern in text:
                return category
    return None


def _is_path_format(ref: str) -> bool:
    """Check if a reference is in path format (e.g., 1.2.3)."""
    if "." not in ref:
        return False
    parts = ref.split(".")
    return all(part.isdigit() for part in parts)
