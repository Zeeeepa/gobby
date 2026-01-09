"""Conflict extraction utilities for parsing Git merge conflicts.

Parses Git conflict markers (<<<<<<< HEAD, =======, >>>>>>> branch) and
extracts conflict regions with context windowing.
"""

import re
from dataclasses import dataclass


@dataclass
class ConflictHunk:
    """A single merge conflict extracted from a file.

    Attributes:
        ours: Content from the HEAD/current branch side
        theirs: Content from the incoming/merging branch side
        base: Content from the common ancestor (for diff3-style conflicts)
        start_line: Line number where conflict starts (1-indexed)
        end_line: Line number where conflict ends (1-indexed)
        context_before: Lines of context before the conflict
        context_after: Lines of context after the conflict
        ours_marker: Full <<<<<<< marker line
        theirs_marker: Full >>>>>>> marker line
    """

    ours: str
    theirs: str
    base: str | None
    start_line: int
    end_line: int
    context_before: str
    context_after: str
    ours_marker: str = ""
    theirs_marker: str = ""


# Regex patterns for conflict markers
# Must be at start of line, with optional whitespace before
CONFLICT_START = re.compile(r"^(<<<<<<<\s+.*)$", re.MULTILINE)
CONFLICT_SEPARATOR = re.compile(r"^(=======)\s*$", re.MULTILINE)
CONFLICT_BASE_SEPARATOR = re.compile(r"^(\|\|\|\|\|\|\|\s+.*)$", re.MULTILINE)  # diff3 base
CONFLICT_END = re.compile(r"^(>>>>>>>\s+.*)$", re.MULTILINE)


def extract_conflict_hunks(file_content: str, context_lines: int = 3) -> list[ConflictHunk]:
    """Extract conflict hunks from file content.

    Parses Git conflict markers and extracts conflict regions with
    surrounding context.

    Args:
        file_content: The full file content with conflict markers
        context_lines: Number of context lines before/after conflict (default: 3)

    Returns:
        List of ConflictHunk objects, one per conflict region.
        Returns empty list if no conflicts found.
    """
    if not file_content:
        return []

    # Normalize line endings
    content = file_content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")

    hunks: list[ConflictHunk] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for conflict start marker
        if line.startswith("<<<<<<<"):
            hunk = _parse_conflict_at(lines, i, context_lines)
            if hunk:
                hunks.append(hunk)
                # Skip to end of conflict
                i = hunk.end_line
            else:
                i += 1
        else:
            i += 1

    return hunks


def _parse_conflict_at(lines: list[str], start_idx: int, context_lines: int) -> ConflictHunk | None:
    """Parse a single conflict starting at the given line index.

    Args:
        lines: All lines in the file
        start_idx: Index of the <<<<<<< line
        context_lines: Number of context lines to include

    Returns:
        ConflictHunk if valid conflict found, None if malformed
    """
    n = len(lines)

    # Validate start marker
    if start_idx >= n or not lines[start_idx].startswith("<<<<<<<"):
        return None

    ours_marker = lines[start_idx]
    start_line = start_idx + 1  # Convert to 1-indexed

    # Find separator (=======)
    separator_idx = None
    base_separator_idx = None

    for idx in range(start_idx + 1, n):
        line = lines[idx]
        if line.startswith("|||||||"):  # diff3 base separator
            base_separator_idx = idx
        elif line.startswith("======="):
            separator_idx = idx
            break
        elif line.startswith(">>>>>>>"):
            # End marker before separator - malformed
            return None
        elif line.startswith("<<<<<<<"):
            # Nested conflict start - malformed
            return None

    if separator_idx is None:
        # No separator found - malformed
        return None

    # Find end marker (>>>>>>>)
    end_idx = None
    for idx in range(separator_idx + 1, n):
        line = lines[idx]
        if line.startswith(">>>>>>>"):
            end_idx = idx
            break
        elif line.startswith("<<<<<<<") or line.startswith("======="):
            # Another conflict start or extra separator - malformed
            return None

    if end_idx is None:
        # No end marker found - malformed
        return None

    theirs_marker = lines[end_idx]
    end_line = end_idx + 1  # Convert to 1-indexed

    # Extract content sections
    if base_separator_idx is not None:
        # diff3-style: ours | base | theirs
        ours_content = "\n".join(lines[start_idx + 1 : base_separator_idx])
        base_content = "\n".join(lines[base_separator_idx + 1 : separator_idx])
        theirs_content = "\n".join(lines[separator_idx + 1 : end_idx])
    else:
        # Standard: ours | theirs
        ours_content = "\n".join(lines[start_idx + 1 : separator_idx])
        base_content = None
        theirs_content = "\n".join(lines[separator_idx + 1 : end_idx])

    # Extract context
    context_start = max(0, start_idx - context_lines)
    context_end = min(n, end_idx + 1 + context_lines)

    context_before = "\n".join(lines[context_start:start_idx]) if start_idx > 0 else ""
    context_after = "\n".join(lines[end_idx + 1 : context_end]) if end_idx + 1 < n else ""

    return ConflictHunk(
        ours=ours_content,
        theirs=theirs_content,
        base=base_content,
        start_line=start_line,
        end_line=end_line,
        context_before=context_before,
        context_after=context_after,
        ours_marker=ours_marker,
        theirs_marker=theirs_marker,
    )
