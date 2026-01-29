#!/usr/bin/env python3
"""Script to add pytest markers and type hints to test files.

This script:
1. Adds `pytestmark = pytest.mark.unit` after imports (if not present)
2. Adds `-> None` to test methods that are missing return types

Usage:
    python scripts/add_pytest_markers.py [--dry-run] [--file PATH]
"""

import argparse
import re
from pathlib import Path


def get_marker_for_directory(file_path: Path) -> str:
    """Determine the appropriate pytest marker based on directory."""
    path_str = str(file_path)

    if "/e2e/" in path_str:
        return "e2e"
    elif "/integration/" in path_str:
        return "integration"
    else:
        return "unit"


def has_pytestmark(content: str) -> bool:
    """Check if file already has pytestmark defined."""
    return bool(re.search(r'^pytestmark\s*=', content, re.MULTILINE))


def has_pytest_import(content: str) -> bool:
    """Check if file imports pytest."""
    return bool(re.search(r'^import pytest\s*$', content, re.MULTILINE))


def find_import_block_end(lines: list[str]) -> int:
    """Find the line index of the last import statement.

    Returns -1 if no imports found.
    """
    last_import_idx = -1
    i = 0
    in_multiline = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Track multiline imports (with parentheses)
        if in_multiline:
            if ')' in line:
                in_multiline = False
                last_import_idx = i
            i += 1
            continue

        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        # Skip docstrings at start of file
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = '"""' if stripped.startswith('"""') else "'''"
            if stripped.count(quote) >= 2:
                # Single line docstring
                i += 1
                continue
            else:
                # Multi-line docstring - skip to end
                i += 1
                while i < len(lines) and quote not in lines[i]:
                    i += 1
                i += 1  # Skip closing line
                continue

        # Check for import statements
        if stripped.startswith('import ') or stripped.startswith('from '):
            if '(' in stripped and ')' not in stripped:
                in_multiline = True
            else:
                last_import_idx = i
            i += 1
            continue

        # If we hit a class, def, decorator, or other code, stop looking
        if stripped.startswith(('class ', 'def ', '@', 'pytestmark')):
            break

        i += 1

    return last_import_idx


def add_pytest_import_and_marker(content: str, marker: str) -> str:
    """Add pytest import (if needed) and pytestmark after imports."""
    if has_pytestmark(content):
        return content

    lines = content.split('\n')
    import_end_idx = find_import_block_end(lines)

    # Build the lines to insert
    lines_to_insert = []
    if not has_pytest_import(content):
        lines_to_insert.append('import pytest')
    lines_to_insert.append('')
    lines_to_insert.append(f'pytestmark = pytest.mark.{marker}')

    if import_end_idx == -1:
        # No imports found - add at start (after docstring if present)
        insert_pos = 0
        if lines and (lines[0].strip().startswith('"""') or lines[0].strip().startswith("'''")):
            quote = '"""' if '"""' in lines[0] else "'''"
            if lines[0].count(quote) >= 2:
                insert_pos = 1
            else:
                for j in range(1, len(lines)):
                    if quote in lines[j]:
                        insert_pos = j + 1
                        break

        # Add blank line before if there's content
        if insert_pos < len(lines) and lines[insert_pos].strip():
            lines_to_insert.append('')

        result = lines[:insert_pos] + lines_to_insert + lines[insert_pos:]
    else:
        # Insert after imports
        result = lines[:import_end_idx + 1] + lines_to_insert

        # Add the rest, ensuring proper spacing
        remaining = lines[import_end_idx + 1:]

        # Skip leading blank lines (we'll add our own spacing)
        while remaining and not remaining[0].strip():
            remaining.pop(0)

        if remaining:
            result.append('')  # Blank line before next content

        result.extend(remaining)

    return '\n'.join(result)


def add_test_return_types(content: str) -> str:
    """Add -> None to test methods that are missing return types."""
    # Pattern: indented def test_... without return type annotation
    # This handles single-line function signatures
    pattern = r'^(\s+def\s+test_\w+\s*\([^)]*\))\s*:\s*$'

    def add_none(match: re.Match) -> str:
        return f"{match.group(1)} -> None:"

    return re.sub(pattern, add_none, content, flags=re.MULTILINE)


def process_file(file_path: Path, dry_run: bool = False) -> bool:
    """Process a single test file. Returns True if changes were made."""
    content = file_path.read_text()
    original_content = content

    # Determine marker type
    marker = get_marker_for_directory(file_path)

    # Add pytest import and pytestmark
    content = add_pytest_import_and_marker(content, marker)

    # Add test method return types
    content = add_test_return_types(content)

    if content != original_content:
        if dry_run:
            print(f"Would modify: {file_path}")
        else:
            file_path.write_text(content)
            print(f"Modified: {file_path}")
        return True

    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Add pytest markers and type hints to test files")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes")
    parser.add_argument("--file", type=Path, help="Process single file")
    args = parser.parse_args()

    if args.file:
        files = [args.file]
    else:
        tests_dir = Path(__file__).parent.parent / "tests"
        files = sorted(tests_dir.rglob("test_*.py"))

    modified_count = 0
    for file_path in files:
        try:
            if process_file(file_path, args.dry_run):
                modified_count += 1
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print(f"\n{'Would modify' if args.dry_run else 'Modified'} {modified_count} files")


if __name__ == "__main__":
    main()
