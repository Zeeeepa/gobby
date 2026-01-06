"""
Markdown structure parser for spec files.

Parses markdown checkboxes into structured items for deterministic
task creation, avoiding LLM re-interpretation of already-structured specs.
"""

import re
from dataclasses import dataclass, field


@dataclass
class CheckboxItem:
    """A parsed markdown checkbox item."""

    text: str  # The checkbox text (without the checkbox marker)
    checked: bool  # True if [x], False if [ ]
    line_number: int  # 0-indexed line number
    indent_level: int  # Number of leading spaces (for nested checkboxes)
    raw_line: str  # Original line content
    parent_heading: str | None = None  # Text of nearest parent heading (if tracked)
    children: list["CheckboxItem"] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Ensure children is a mutable list
        if not isinstance(self.children, list):
            self.children = list(self.children)

    @property
    def depth(self) -> int:
        """Nesting depth based on indentation (0 for top-level, 1 for indented, etc.)."""
        # Common indentation is 2 or 4 spaces per level
        # Use 2 spaces as standard unit
        return self.indent_level // 2

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "checked": self.checked,
            "line_number": self.line_number,
            "indent_level": self.indent_level,
            "depth": self.depth,
            "parent_heading": self.parent_heading,
            "children": [child.to_dict() for child in self.children],
        }


# Regex pattern for markdown checkboxes
# Matches: optional leading spaces, dash, space, [x] or [ ], space, text
# Groups: (indent)(marker: x or space)(text)
CHECKBOX_PATTERN = re.compile(r"^(\s*)[-*]\s+\[([ xX])\]\s+(.+)$")

# Regex pattern for markdown headings (to track parent context)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class ExtractedCheckboxes:
    """Result of extracting checkboxes from markdown."""

    items: list[CheckboxItem]  # All checkbox items (may be nested via children)
    total_count: int  # Total number of checkboxes found
    checked_count: int  # Number of checked checkboxes

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "items": [item.to_dict() for item in self.items],
            "total_count": self.total_count,
            "checked_count": self.checked_count,
        }

    @property
    def unchecked_count(self) -> int:
        """Number of unchecked checkboxes."""
        return self.total_count - self.checked_count

    def get_flat_items(self) -> list[CheckboxItem]:
        """Get all items in a flat list (depth-first traversal)."""
        result: list[CheckboxItem] = []

        def collect(items: list[CheckboxItem]) -> None:
            for item in items:
                result.append(item)
                collect(item.children)

        collect(self.items)
        return result


class CheckboxExtractor:
    """
    Extracts markdown checkboxes from content.

    Supports:
    - Standard checkbox syntax: - [ ] unchecked, - [x] checked
    - Asterisk prefix: * [ ] also supported
    - Indentation tracking for nested checkboxes
    - Parent heading association

    Example:
        extractor = CheckboxExtractor()
        result = extractor.extract(markdown_content)
        for item in result.items:
            status = "done" if item.checked else "todo"
            print(f"[{status}] {item.text} (indent: {item.indent_level})")
    """

    def __init__(self, track_headings: bool = True, build_hierarchy: bool = True) -> None:
        """
        Initialize the extractor.

        Args:
            track_headings: If True, associate checkboxes with nearest parent heading
            build_hierarchy: If True, nest checkboxes based on indentation
        """
        self.track_headings = track_headings
        self.build_hierarchy = build_hierarchy

    def extract(self, content: str) -> ExtractedCheckboxes:
        """
        Extract all checkboxes from markdown content.

        Args:
            content: Raw markdown content

        Returns:
            ExtractedCheckboxes containing parsed checkbox items
        """
        lines = content.split("\n")
        flat_items = self._extract_items(lines)

        total_count = len(flat_items)
        checked_count = sum(1 for item in flat_items if item.checked)

        if self.build_hierarchy and flat_items:
            nested_items = self._build_hierarchy(flat_items)
        else:
            nested_items = flat_items

        return ExtractedCheckboxes(
            items=nested_items,
            total_count=total_count,
            checked_count=checked_count,
        )

    def _extract_items(self, lines: list[str]) -> list[CheckboxItem]:
        """
        Extract checkbox items from lines.

        Args:
            lines: List of markdown lines

        Returns:
            Flat list of CheckboxItem objects
        """
        items: list[CheckboxItem] = []
        current_heading: str | None = None

        for line_num, line in enumerate(lines):
            # Track headings for context
            if self.track_headings:
                heading_match = HEADING_PATTERN.match(line)
                if heading_match:
                    current_heading = heading_match.group(2).strip()
                    continue

            # Check for checkbox
            checkbox_match = CHECKBOX_PATTERN.match(line)
            if not checkbox_match:
                continue

            indent, marker, text = checkbox_match.groups()
            is_checked = marker.lower() == "x"

            items.append(
                CheckboxItem(
                    text=text.strip(),
                    checked=is_checked,
                    line_number=line_num,
                    indent_level=len(indent),
                    raw_line=line,
                    parent_heading=current_heading if self.track_headings else None,
                )
            )

        return items

    def _build_hierarchy(self, items: list[CheckboxItem]) -> list[CheckboxItem]:
        """
        Build nested hierarchy from flat checkbox list based on indentation.

        Items with greater indentation become children of the preceding
        item with less indentation.

        Args:
            items: Flat list of checkbox items in document order

        Returns:
            List of top-level CheckboxItems with nested children
        """
        if not items:
            return []

        root_items: list[CheckboxItem] = []
        stack: list[CheckboxItem] = []  # Stack of potential parent items

        for item in items:
            # Pop from stack until we find a parent (item with less indentation)
            while stack and stack[-1].indent_level >= item.indent_level:
                stack.pop()

            if stack:
                # This item is a child of the top of stack
                stack[-1].children.append(item)
            else:
                # This is a root-level item
                root_items.append(item)

            # Push this item onto stack for potential children
            stack.append(item)

        return root_items

    def extract_under_heading(
        self,
        content: str,
        heading_pattern: str,
        case_sensitive: bool = False,
    ) -> ExtractedCheckboxes:
        """
        Extract checkboxes that appear under a specific heading.

        Args:
            content: Raw markdown content
            heading_pattern: Regex pattern or exact text to match heading
            case_sensitive: Whether heading match is case-sensitive

        Returns:
            ExtractedCheckboxes containing only items under matching heading
        """
        lines = content.split("\n")
        all_items = self._extract_items(lines)

        # Compile pattern
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(heading_pattern, flags)
        except re.error:
            # Treat as literal string if not valid regex
            pattern = re.compile(re.escape(heading_pattern), flags)

        # Filter items by parent heading
        matching_items = [
            item
            for item in all_items
            if item.parent_heading and pattern.search(item.parent_heading)
        ]

        total_count = len(matching_items)
        checked_count = sum(1 for item in matching_items if item.checked)

        if self.build_hierarchy and matching_items:
            nested_items = self._build_hierarchy(matching_items)
        else:
            nested_items = matching_items

        return ExtractedCheckboxes(
            items=nested_items,
            total_count=total_count,
            checked_count=checked_count,
        )
