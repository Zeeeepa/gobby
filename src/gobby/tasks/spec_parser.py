"""
Spec document parser module.

Parses markdown specification documents into hierarchical structures
for task expansion.
"""

import re
from dataclasses import dataclass, field


@dataclass
class HeadingNode:
    """A node in the heading hierarchy tree.

    Attributes:
        text: The heading text (without # prefix)
        level: The heading level (2 for ##, 3 for ###, etc.)
        line_start: The line number where this heading starts (1-indexed)
        line_end: The line number where this section ends (1-indexed, inclusive)
        children: Child heading nodes
        content: The text content between this heading and the next
    """

    text: str
    level: int
    line_start: int
    line_end: int = 0
    children: list["HeadingNode"] = field(default_factory=list)
    content: str = ""


class MarkdownStructureParser:
    """Parses markdown headings into a hierarchical structure.

    Extracts ## (level 2), ### (level 3), and #### (level 4) headings
    from markdown text and organizes them into a tree structure.

    Example:
        parser = MarkdownStructureParser()
        tree = parser.parse(markdown_text)
        # Returns list of top-level HeadingNode objects with nested children
    """

    # Pattern to match markdown headings (## through ####)
    HEADING_PATTERN = re.compile(r"^(#{2,4})\s+(.+)$", re.MULTILINE)

    def parse(self, text: str) -> list[HeadingNode]:
        """Parse markdown text into a heading tree structure.

        Args:
            text: The markdown text to parse

        Returns:
            List of top-level HeadingNode objects. Each node may have
            children representing nested headings.
        """
        lines = text.split("\n")
        headings = self._extract_headings(lines)

        if not headings:
            return []

        # Calculate line_end for each heading
        self._calculate_line_ends(headings, len(lines))

        # Extract content for each heading
        self._extract_content(headings, lines)

        # Build the tree structure
        return self._build_tree(headings)

    def _extract_headings(self, lines: list[str]) -> list[HeadingNode]:
        """Extract all headings from the lines.

        Args:
            lines: List of lines from the markdown text

        Returns:
            Flat list of HeadingNode objects in document order
        """
        headings: list[HeadingNode] = []

        for i, line in enumerate(lines):
            match = self.HEADING_PATTERN.match(line)
            if match:
                level = len(match.group(1))
                text = match.group(2).strip()
                headings.append(
                    HeadingNode(
                        text=text,
                        level=level,
                        line_start=i + 1,  # 1-indexed
                    )
                )

        return headings

    def _calculate_line_ends(
        self, headings: list[HeadingNode], total_lines: int
    ) -> None:
        """Calculate the line_end for each heading.

        Each heading's section ends at the line before the next heading
        of equal or higher level, or at the end of the document.

        Args:
            headings: List of heading nodes (modified in place)
            total_lines: Total number of lines in the document
        """
        for i, heading in enumerate(headings):
            # Find the next heading that ends this section
            # (same or higher level, i.e., same or fewer #)
            end_line = total_lines

            for j in range(i + 1, len(headings)):
                if headings[j].level <= heading.level:
                    end_line = headings[j].line_start - 1
                    break

            heading.line_end = end_line

    def _extract_content(
        self, headings: list[HeadingNode], lines: list[str]
    ) -> None:
        """Extract the content for each heading section.

        Content is the text between the heading line and the next heading.

        Args:
            headings: List of heading nodes (modified in place)
            lines: List of lines from the markdown text
        """
        for i, heading in enumerate(headings):
            # Find where content ends (next heading or line_end)
            content_end = heading.line_end

            # Check if there's a child heading that starts before line_end
            for j in range(i + 1, len(headings)):
                next_heading = headings[j]
                if next_heading.line_start <= heading.line_end:
                    content_end = next_heading.line_start - 1
                    break

            # Extract content (skip the heading line itself)
            content_start = heading.line_start  # 0-indexed after heading
            content_lines = lines[content_start:content_end]

            # Strip leading/trailing empty lines
            while content_lines and not content_lines[0].strip():
                content_lines = content_lines[1:]
            while content_lines and not content_lines[-1].strip():
                content_lines = content_lines[:-1]

            heading.content = "\n".join(content_lines)

    def _build_tree(self, headings: list[HeadingNode]) -> list[HeadingNode]:
        """Build a tree structure from the flat list of headings.

        Groups headings by their parent-child relationships based on level.
        Level 2 headings are top-level, level 3 are children of level 2, etc.

        Args:
            headings: Flat list of heading nodes

        Returns:
            List of top-level (level 2) HeadingNode objects with
            nested children
        """
        if not headings:
            return []

        # Find the minimum level (usually 2, but could be different)
        min_level = min(h.level for h in headings)

        # Build tree using a stack-based approach
        root_nodes: list[HeadingNode] = []
        stack: list[HeadingNode] = []

        for heading in headings:
            # Pop from stack until we find a parent or empty stack
            while stack and stack[-1].level >= heading.level:
                stack.pop()

            if not stack:
                # This is a root-level heading
                root_nodes.append(heading)
            else:
                # This is a child of the last item on the stack
                stack[-1].children.append(heading)

            stack.append(heading)

        return root_nodes

    def get_sections_at_level(
        self, tree: list[HeadingNode], level: int
    ) -> list[HeadingNode]:
        """Get all sections at a specific heading level.

        Args:
            tree: The heading tree from parse()
            level: The heading level to filter (2, 3, or 4)

        Returns:
            Flat list of all HeadingNode objects at the specified level
        """
        result: list[HeadingNode] = []
        self._collect_at_level(tree, level, result)
        return result

    def _collect_at_level(
        self,
        nodes: list[HeadingNode],
        level: int,
        result: list[HeadingNode],
    ) -> None:
        """Recursively collect nodes at a specific level.

        Args:
            nodes: List of nodes to search
            level: Target level
            result: List to append matching nodes to
        """
        for node in nodes:
            if node.level == level:
                result.append(node)
            self._collect_at_level(node.children, level, result)
