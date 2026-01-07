"""Auto-decomposition of multi-step tasks.

Detects when a task description contains multiple implementation steps
that should be broken down into subtasks.
"""

import re

# Patterns that indicate false positives (not implementation steps)
FALSE_POSITIVE_PATTERNS = [
    r"steps?\s+to\s+reproduce",
    r"reproduction\s+steps?",
    r"acceptance\s+criteria",
    r"(?:possible\s+)?options\s*:",
    r"(?:possible\s+)?approaches\s*:",
    r"files?\s+to\s+modify",
    r"requirements?\s*:",
    r"requirements\s+for\s+fix",
]

# Patterns that indicate implementation steps
STEP_SECTION_PATTERNS = [
    r"^steps?\s*:",
    r"^implementation\s+steps?\s*:",
    r"^implementation\s+tasks?\s*:",
    r"^tasks?\s*:",
]

# Action verbs commonly used in implementation steps
ACTION_VERBS = [
    "create",
    "add",
    "implement",
    "build",
    "update",
    "install",
    "configure",
    "set up",
    "setup",
    "write",
    "define",
    "extract",
    "refactor",
    "migrate",
]


def detect_multi_step(description: str | None) -> bool:
    """
    Detect if a task description contains multiple implementation steps.

    Args:
        description: Task description text to analyze

    Returns:
        True if the description indicates multiple steps that should
        be decomposed into subtasks, False otherwise.

    Examples:
        >>> detect_multi_step("1. Create model\\n2. Add API\\n3. Build UI")
        True
        >>> detect_multi_step("Fix the typo in README")
        False
        >>> detect_multi_step("Steps to reproduce:\\n1. Click button")
        False  # Bug reproduction steps, not implementation
    """
    if not description:
        return False

    description_lower = description.lower()

    # Check for false positive patterns first
    for pattern in FALSE_POSITIVE_PATTERNS:
        if re.search(pattern, description_lower, re.IGNORECASE):
            # Check if there's also an implementation section that overrides
            has_impl_section = any(
                re.search(p, description_lower, re.IGNORECASE | re.MULTILINE)
                for p in STEP_SECTION_PATTERNS
            )
            if not has_impl_section:
                return False

    # Check for phase headers (## Phase 1, ## Phase 2, etc.)
    phase_matches = re.findall(r"##\s*phase\s*\d+", description_lower)
    if len(phase_matches) >= 2:
        return True

    # Check for numbered lists (1. or 1) format) with at least 3 items
    numbered_pattern = r"^\s*\d+[.)]\s*\S"
    numbered_matches = re.findall(numbered_pattern, description, re.MULTILINE)
    if len(numbered_matches) >= 3:
        return True

    # Check for step section headers followed by bullets
    for pattern in STEP_SECTION_PATTERNS:
        if re.search(pattern, description_lower, re.IGNORECASE | re.MULTILINE):
            # Count bullets after the section header
            bullets = re.findall(r"^\s*[-*]\s*\S", description, re.MULTILINE)
            if len(bullets) >= 2:
                return True

    # Check for sequential action bullets (bullets starting with action verbs)
    bullet_pattern = r"^\s*[-*]\s*(\w+)"
    bullets = re.findall(bullet_pattern, description, re.MULTILINE)
    action_bullets = [b for b in bullets if b.lower() in ACTION_VERBS]
    if len(action_bullets) >= 3:
        return True

    # Check for "first... then... finally" sequence
    sequence_words = ["first", "then", "finally", "next", "after that", "lastly"]
    sequence_count = sum(1 for word in sequence_words if word in description_lower)
    if sequence_count >= 3:
        return True

    # Check for markdown task headers (### Tasks, ### Implementation)
    task_header = re.search(r"###?\s*tasks?\s*$", description_lower, re.MULTILINE)
    if task_header:
        # Count numbered items or bullets after the header
        after_header = description[task_header.end() :]
        items = re.findall(r"^\s*(?:\d+[.)]|[-*])\s*\S", after_header, re.MULTILINE)
        if len(items) >= 2:
            return True

    return False


def extract_steps(description: str | None) -> list[dict[str, str | list[int] | None]]:
    """
    Extract implementation steps from a task description.

    Parses numbered lists, bullet points, and other step formats to
    generate subtask specifications.

    Args:
        description: Task description text to parse

    Returns:
        List of step dicts, each containing:
        - title: Step title (required)
        - description: Additional details (optional)
        - depends_on: List of step indices this step depends on (optional)

    Examples:
        >>> steps = extract_steps("1. Create model\\n2. Add API")
        >>> steps[0]["title"]
        'Create model'
        >>> steps[1]["depends_on"]
        [0]
    """
    # TDD stub - implementation to follow
    raise NotImplementedError("extract_steps not yet implemented")
