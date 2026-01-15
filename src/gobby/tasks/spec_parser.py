"""
Spec document parser module.

Parses markdown specification documents into hierarchical structures
for task expansion. Includes:
- HeadingNode/MarkdownStructureParser: Parse ## through #### headings into tree
- CheckboxItem/CheckboxExtractor: Parse markdown checkboxes with hierarchy
- TaskHierarchyBuilder: Convert parsed structures to gobby tasks
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.llm.service import LLMService
    from gobby.storage.tasks import LocalTaskManager
    from gobby.tasks.criteria import CriteriaGenerator
    from gobby.tasks.expansion import TaskExpander

logger = logging.getLogger(__name__)


# =============================================================================
# Heading Parser
# =============================================================================


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
    children: list[HeadingNode] = field(default_factory=list)
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

    # Pattern to detect fenced code block markers (``` or ~~~)
    FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})")

    def _extract_headings(self, lines: list[str]) -> list[HeadingNode]:
        """Extract all headings from the lines.

        Skips headings that appear inside fenced code blocks (``` or ~~~).

        Args:
            lines: List of lines from the markdown text

        Returns:
            Flat list of HeadingNode objects in document order
        """
        headings: list[HeadingNode] = []
        in_code_block = False
        fence_marker: str | None = None  # Track the specific fence character

        for i, line in enumerate(lines):
            # Check for fenced code block markers
            fence_match = self.FENCE_PATTERN.match(line)
            if fence_match:
                marker = fence_match.group(1)[0]  # Get ` or ~
                if not in_code_block:
                    # Starting a code block
                    in_code_block = True
                    fence_marker = marker
                elif marker == fence_marker:
                    # Ending the code block (must match same fence type)
                    in_code_block = False
                    fence_marker = None
                continue

            # Skip headings inside code blocks
            if in_code_block:
                continue

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

    def _calculate_line_ends(self, headings: list[HeadingNode], total_lines: int) -> None:
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

    def _extract_content(self, headings: list[HeadingNode], lines: list[str]) -> None:
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
        min_level = min(h.level for h in headings)  # noqa: F841

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

    def get_sections_at_level(self, tree: list[HeadingNode], level: int) -> list[HeadingNode]:
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


# =============================================================================
# Checkbox Parser
# =============================================================================


@dataclass
class CheckboxItem:
    """A parsed markdown checkbox item."""

    text: str  # The checkbox text (without the checkbox marker)
    checked: bool  # True if [x], False if [ ]
    line_number: int  # 0-indexed line number
    indent_level: int  # Number of leading spaces (for nested checkboxes)
    raw_line: str  # Original line content
    parent_heading: str | None = None  # Text of nearest parent heading (if tracked)
    children: list[CheckboxItem] = field(default_factory=list)

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

    def to_dict(self) -> dict[str, Any]:
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
# Matches: optional leading spaces, bullet (- or *) or number (1.), space, [x] or [ ], space, text
# Groups: (indent)(marker: x or space)(text)
# Supports: - [ ] task, * [ ] task, 1. [ ] task, 10. [ ] task
CHECKBOX_PATTERN = re.compile(r"^(\s*)(?:[-*]|\d+\.)\s+\[([ xX])\]\s+(.+)$")

# Regex pattern for markdown headings (to track parent context)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")

# Regex pattern for fenced code block markers (``` or ~~~)
FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})")

# Keywords that indicate a section contains actionable items worth expanding
# Sections without these keywords (e.g., "Overview", "Configuration Example")
# should NOT be LLM-expanded to avoid creating duplicate/invalid tasks
ACTIONABLE_KEYWORDS = {
    "implementation",
    "tasks",
    "steps",
    "phase",
    "work items",
    "todo",
    "action items",
    "deliverables",
    "changes",
    "modifications",
    "requirements",
}


@dataclass
class ExtractedCheckboxes:
    """Result of extracting checkboxes from markdown."""

    items: list[CheckboxItem]  # All checkbox items (may be nested via children)
    total_count: int  # Total number of checkboxes found
    checked_count: int  # Number of checked checkboxes

    def to_dict(self) -> dict[str, Any]:
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

        Skips content inside fenced code blocks (``` or ~~~).

        Args:
            lines: List of markdown lines

        Returns:
            Flat list of CheckboxItem objects
        """
        items: list[CheckboxItem] = []
        current_heading: str | None = None
        in_code_block = False
        fence_marker: str | None = None

        for line_num, line in enumerate(lines):
            # Check for fenced code block markers
            fence_match = FENCE_PATTERN.match(line)
            if fence_match:
                marker = fence_match.group(1)[0]  # Get ` or ~
                if not in_code_block:
                    in_code_block = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_code_block = False
                    fence_marker = None
                continue

            # Skip content inside code blocks
            if in_code_block:
                continue

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


# =============================================================================
# Task Hierarchy Builder
# =============================================================================


@dataclass
class ParallelGroup:
    """A group of tasks that can be executed in parallel.

    Sibling tasks at the same heading level with no cross-references
    are parallelizable and can be assigned to separate worktrees.

    Attributes:
        task_ids: List of task IDs in this parallel group
        parent_task_id: The parent epic that depends on all tasks in this group
        heading_level: The heading level these tasks came from (for debugging)
    """

    task_ids: list[str]
    parent_task_id: str | None = None
    heading_level: int = 0

    @property
    def size(self) -> int:
        """Number of tasks in this group."""
        return len(self.task_ids)

    def is_parallelizable(self) -> bool:
        """True if group has multiple tasks that can run in parallel."""
        return len(self.task_ids) > 1


@dataclass
class CreatedTask:
    """Result of creating a task from parsed structure."""

    id: str
    title: str
    task_type: str
    status: str
    parent_task_id: str | None = None


@dataclass
class HierarchyBuildResult:
    """Result of building task hierarchy from parsed spec."""

    tasks: list[CreatedTask]
    root_task_ids: list[str]  # Top-level task IDs (no parent in this build)
    total_count: int
    parallel_groups: list[ParallelGroup] = field(default_factory=list)

    @property
    def task_ids(self) -> list[str]:
        """All created task IDs."""
        return [t.id for t in self.tasks]

    @property
    def parallelizable_groups(self) -> list[ParallelGroup]:
        """Groups with multiple tasks that can run in parallel."""
        return [g for g in self.parallel_groups if g.is_parallelizable()]


class TaskHierarchyBuilder:
    """Builds gobby tasks from parsed markdown structure.

    Converts HeadingNodes and CheckboxItems into tasks with proper
    parent-child relationships.

    Mapping rules:
    - ### Phase heading -> Epic task
    - #### Sub-phase heading -> Task (child of epic)
    - - [ ] Checkbox -> Leaf task under nearest heading
    - - [x] Completed checkbox -> Leaf task (status: closed)

    Example:
        builder = TaskHierarchyBuilder(task_manager, project_id)
        result = builder.build_from_headings(heading_tree, checkboxes)
        print(f"Created {result.total_count} tasks")
    """

    def __init__(
        self,
        task_manager: LocalTaskManager,
        project_id: str,
        parent_task_id: str | None = None,
        default_priority: int = 2,
        parent_labels: list[str] | None = None,
        criteria_generator: CriteriaGenerator | None = None,
        tdd_mode: bool = False,
        llm_service: LLMService | None = None,
        config: DaemonConfig | None = None,
        reference_doc: str | None = None,
    ) -> None:
        """Initialize the builder.

        Args:
            task_manager: LocalTaskManager instance for creating tasks
            project_id: Project ID for created tasks
            parent_task_id: Optional parent task ID (tasks created will be children)
            default_priority: Default priority for created tasks (1=high, 2=medium, 3=low)
            parent_labels: Optional labels from parent task (for pattern detection in LLM expansion)
            criteria_generator: Optional CriteriaGenerator for validation criteria
            tdd_mode: If True, create test→implement pairs for coding tasks
            llm_service: Optional LLMService for generating task descriptions
            config: Optional DaemonConfig with task_description settings
            reference_doc: Path to source specification document for traceability
        """
        self.task_manager = task_manager
        self.project_id = project_id
        self.parent_task_id = parent_task_id
        self.default_priority = default_priority
        self.parent_labels = parent_labels or []
        self.criteria_generator = criteria_generator
        self.tdd_mode = tdd_mode
        self.llm_service = llm_service
        self.config = config
        self.reference_doc = reference_doc
        # Lazy-load dependency manager when needed
        self._dep_manager: Any = None

    @property
    def dep_manager(self) -> Any:
        """Get or create the dependency manager."""
        if self._dep_manager is None:
            from gobby.storage.task_dependencies import TaskDependencyManager

            self._dep_manager = TaskDependencyManager(self.task_manager.db)
        return self._dep_manager

    async def _generate_description_llm(
        self,
        checkbox: CheckboxItem,
        heading: HeadingNode | None,
        existing_context: str | None,
    ) -> str | None:
        """Generate description via LLM when structured extraction fails.

        Uses configured provider/model. Supports subscription or API key auth.

        Args:
            checkbox: The checkbox item to generate description for
            heading: Optional parent heading node with section context
            existing_context: Existing description from structured extraction

        Returns:
            Generated description string, or existing_context if LLM unavailable
        """
        if not self.llm_service:
            return existing_context

        # TaskDescriptionConfig may not exist on DaemonConfig yet (Phase 2)
        config = getattr(self.config, "task_description", None) if self.config else None
        if not config or not getattr(config, "enabled", False):
            return existing_context

        # Try configured provider, fall back to default
        provider_name = getattr(config, "provider", None)
        try:
            provider = (
                self.llm_service.get_provider(provider_name)
                if provider_name
                else self.llm_service.get_default_provider()
            )
        except ValueError:
            # Provider not available, try default
            try:
                provider = self.llm_service.get_default_provider()
            except ValueError:
                return existing_context

        # Get config attributes with safe defaults
        prompt_template = getattr(config, "prompt", "{task_title}")
        model = getattr(config, "model", None)
        system_prompt = getattr(config, "system_prompt", None)

        # Build prompt from template with safe fallbacks
        try:
            prompt = prompt_template.format(
                task_title=checkbox.text or "",
                section_title=heading.text if heading else "",
                section_content=(heading.content[:500] if heading and heading.content else ""),
                existing_context=existing_context or "",
            )
        except (KeyError, IndexError, ValueError, TypeError):
            # Template format error - skip LLM generation
            return existing_context

        try:
            response = await provider.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
            )
            return response.strip() or existing_context
        except Exception:
            return existing_context  # Graceful degradation on LLM failure

    async def _build_smart_description(
        self,
        checkbox: CheckboxItem,
        heading: HeadingNode | None,
        all_checkboxes: list[CheckboxItem],
    ) -> str | None:
        """Build focused description with context from spec.

        Tries structured extraction first, falls back to LLM if minimal.

        Args:
            checkbox: The checkbox item to build description for
            heading: Optional parent heading node
            all_checkboxes: All checkboxes for finding related tasks

        Returns:
            Description string or None if no content available
        """
        parts: list[str] = []

        # Structured extraction from heading
        if heading:
            parts.append(f"Part of: {heading.text}")

            # Extract goal if present
            if heading.content:
                goal_match = re.search(
                    r"\*\*Goal\*\*:?\s*(.+?)(?:\n\n|\*\*|$)",
                    heading.content,
                    re.DOTALL,
                )
                if goal_match:
                    parts.append(f"Goal: {goal_match.group(1).strip()}")

        # Related tasks (siblings under same heading)
        if heading:
            siblings = [
                cb
                for cb in all_checkboxes
                if getattr(cb, "parent_heading", None) == heading.text and cb != checkbox
            ]
            if siblings:
                related = ", ".join(cb.text[:40] for cb in siblings[:3])
                parts.append(f"Related tasks: {related}")

        description = "\n\n".join(parts) if parts else None

        # LLM fallback if structured extraction yielded minimal results
        task_config = (
            getattr(self.config, "task_description", None) if self.config else None
        )
        min_length = getattr(task_config, "min_structured_length", 50) if task_config else 50

        if not description or len(description) < min_length:
            description = await self._generate_description_llm(
                checkbox, heading, description
            )

        return description

    def _get_checkboxes_for_heading(
        self,
        heading: HeadingNode,
        all_checkboxes: list[CheckboxItem],
    ) -> list[CheckboxItem]:
        """Get top-level checkboxes within this heading's line range.

        This prevents duplicates when multiple headings have the same text
        (e.g., "Configuration" under Phase D and Phase E).

        Args:
            heading: The heading node to get checkboxes for
            all_checkboxes: Flat list of all checkboxes from the document

        Returns:
            List of top-level checkboxes that fall within the heading's line range
        """
        return [
            cb
            for cb in all_checkboxes
            if cb.parent_heading == heading.text
            and heading.line_start <= cb.line_number <= heading.line_end
            and cb.depth == 0
        ]

    async def build_from_headings(
        self,
        headings: list[HeadingNode],
        checkboxes: ExtractedCheckboxes | None = None,
    ) -> HierarchyBuildResult:
        """Build task hierarchy from parsed heading tree.

        Creates tasks from headings with optional checkbox integration.
        Level 2/3 headings become epics, level 4 become tasks.
        Checkboxes under headings become leaf tasks.

        Args:
            headings: List of HeadingNode from MarkdownStructureParser.parse()
            checkboxes: Optional ExtractedCheckboxes to integrate under headings

        Returns:
            HierarchyBuildResult with created tasks
        """
        created_tasks: list[CreatedTask] = []
        root_task_ids: list[str] = []

        # Get flat list of all checkboxes for line-range scoped lookup
        all_checkboxes = checkboxes.get_flat_items() if checkboxes else []

        # Process each heading tree recursively
        for heading in headings:
            task_ids = await self._process_heading(
                heading=heading,
                parent_task_id=self.parent_task_id,
                all_checkboxes=all_checkboxes,
                created_tasks=created_tasks,
            )
            root_task_ids.extend(task_ids)

        # Detect parallel groups from sibling headings
        parallel_groups = self._detect_parallel_groups(headings, created_tasks)

        return HierarchyBuildResult(
            tasks=created_tasks,
            root_task_ids=root_task_ids,
            total_count=len(created_tasks),
            parallel_groups=parallel_groups,
        )

    async def build_from_checkboxes(
        self,
        checkboxes: ExtractedCheckboxes,
        heading_text: str | None = None,
    ) -> HierarchyBuildResult:
        """Build task hierarchy from parsed checkboxes only.

        Creates tasks from checkboxes, preserving their nesting structure.
        Useful when spec has checkboxes without structured headings.

        Args:
            checkboxes: ExtractedCheckboxes from CheckboxExtractor.extract()
            heading_text: Optional heading text to use as epic title

        Returns:
            HierarchyBuildResult with created tasks
        """
        created_tasks: list[CreatedTask] = []
        root_task_ids: list[str] = []

        # Optionally create a parent epic from heading
        epic_id = self.parent_task_id
        if heading_text:
            epic = self._create_task(
                title=heading_text,
                task_type="epic",
                parent_task_id=self.parent_task_id,
                description=None,
            )
            created_tasks.append(epic)
            root_task_ids.append(epic.id)
            epic_id = epic.id

        # Collect all checkbox items for context
        all_checkbox_items = list(checkboxes.items)

        # Process top-level checkboxes
        for item in checkboxes.items:
            task_ids = await self._process_checkbox(
                checkbox=item,
                parent_task_id=epic_id,
                created_tasks=created_tasks,
                current_heading=None,
                all_checkboxes=all_checkbox_items,
            )
            if not heading_text:
                root_task_ids.extend(task_ids)

        return HierarchyBuildResult(
            tasks=created_tasks,
            root_task_ids=root_task_ids,
            total_count=len(created_tasks),
        )

    async def _process_heading(
        self,
        heading: HeadingNode,
        parent_task_id: str | None,
        all_checkboxes: list[CheckboxItem],
        created_tasks: list[CreatedTask],
    ) -> list[str]:
        """Process a heading node and its children recursively.

        Args:
            heading: HeadingNode to process
            parent_task_id: ID of parent task (if any)
            all_checkboxes: Flat list of all checkboxes (filtered by line range)
            created_tasks: List to append created tasks to

        Returns:
            List of task IDs created at this level (for root tracking)
        """
        created_at_level: list[str] = []

        # Determine task type based on heading level
        # Level 2-3: Epic (major sections)
        # Level 4+: Task (implementation items)
        task_type = "epic" if heading.level <= 3 else "task"

        # In TDD mode, create test→implement pairs for non-epic tasks (h4+)
        if self.tdd_mode and task_type == "task":
            tasks = self._create_tdd_triplet(
                title=heading.text,
                parent_task_id=parent_task_id,
                description=heading.content if heading.content.strip() else None,
            )
            created_tasks.extend(tasks)
            created_at_level.extend(t.id for t in tasks)
            # Use implementation task (second in triplet) as parent for children
            task = tasks[1]
        else:
            # Create task for this heading
            task = self._create_task(
                title=heading.text,
                task_type=task_type,
                parent_task_id=parent_task_id,
                description=heading.content if heading.content.strip() else None,
            )
            created_tasks.append(task)
            created_at_level.append(task.id)

        # Process checkboxes under this heading (scoped by line range)
        for checkbox in self._get_checkboxes_for_heading(heading, all_checkboxes):
            await self._process_checkbox(
                checkbox=checkbox,
                parent_task_id=task.id,
                created_tasks=created_tasks,
                current_heading=heading,
                all_checkboxes=all_checkboxes,
            )

        # Process child headings
        for child in heading.children:
            await self._process_heading(
                heading=child,
                parent_task_id=task.id,
                all_checkboxes=all_checkboxes,
                created_tasks=created_tasks,
            )

        return created_at_level

    async def _process_checkbox(
        self,
        checkbox: CheckboxItem,
        parent_task_id: str | None,
        created_tasks: list[CreatedTask],
        current_heading: HeadingNode | None = None,
        all_checkboxes: list[CheckboxItem] | None = None,
    ) -> list[str]:
        """Process a checkbox item and its children recursively.

        Args:
            checkbox: CheckboxItem to process
            parent_task_id: ID of parent task (if any)
            created_tasks: List to append created tasks to
            current_heading: The heading this checkbox belongs to (for context)
            all_checkboxes: All checkboxes in the document (for related task context)

        Returns:
            List of task IDs created at this level
        """
        created_at_level: list[str] = []

        # Determine status based on checkbox state
        status = "closed" if checkbox.checked else "open"

        # Build smart description with context from heading and related tasks
        description = await self._build_smart_description(
            checkbox=checkbox,
            heading=current_heading,
            all_checkboxes=all_checkboxes or [],
        )

        # In TDD mode, create test→implement pairs for open tasks
        if self.tdd_mode and status == "open":
            tasks = self._create_tdd_triplet(
                title=checkbox.text,
                parent_task_id=parent_task_id,
                description=description,
            )
            created_tasks.extend(tasks)
            created_at_level.extend(t.id for t in tasks)
            # Use the implementation task (second in triplet) as parent for children
            impl_task = tasks[1]
        else:
            # Create task for this checkbox
            task = self._create_task(
                title=checkbox.text,
                task_type="task",
                parent_task_id=parent_task_id,
                description=description,
                status=status,
            )
            created_tasks.append(task)
            created_at_level.append(task.id)
            impl_task = task

        # Process nested checkboxes as child tasks
        for child in checkbox.children:
            await self._process_checkbox(
                checkbox=child,
                parent_task_id=impl_task.id,
                created_tasks=created_tasks,
                current_heading=current_heading,
                all_checkboxes=all_checkboxes,
            )

        return created_at_level

    def _create_task(
        self,
        title: str,
        task_type: str,
        parent_task_id: str | None,
        description: str | None,
        status: str = "open",
        labels: list[str] | None = None,
    ) -> CreatedTask:
        """Create a task using the task manager.

        Args:
            title: Task title
            task_type: Task type (epic, task, etc.)
            parent_task_id: Parent task ID
            description: Task description
            status: Task status (default: open)
            labels: Optional labels (for pattern detection)

        Returns:
            CreatedTask with task details
        """
        # Generate validation criteria if generator available (skip epics)
        validation_criteria = None
        if self.criteria_generator and task_type != "epic":
            validation_criteria = self.criteria_generator.generate(
                title=title,
                description=description,
                labels=labels or self.parent_labels,
            )

        task = self.task_manager.create_task(
            title=title,
            project_id=self.project_id,
            task_type=task_type,
            parent_task_id=parent_task_id,
            description=description,
            priority=self.default_priority,
            labels=labels,
            validation_criteria=validation_criteria if validation_criteria else None,
            reference_doc=self.reference_doc,
        )

        # Update status if not default
        if status != "open":
            self.task_manager.update_task(task.id, status=status)

        logger.debug(f"Created {task_type} task {task.id}: {title}")

        return CreatedTask(
            id=task.id,
            title=title,
            task_type=task_type,
            status=status,
            parent_task_id=parent_task_id,
        )

    def _create_tdd_triplet(
        self,
        title: str,
        parent_task_id: str | None,
        description: str | None,
        labels: list[str] | None = None,
    ) -> list[CreatedTask]:
        """Create a Red-Green-Refactor triplet for TDD mode.

        Creates three tasks:
        1. Test (Red): Write failing tests
        2. Implement (Green): Make tests pass
        3. Refactor (Blue): Clean up code

        Args:
            title: Original task title
            parent_task_id: Parent task ID
            description: Task description
            labels: Optional labels

        Returns:
            List of [test_task, impl_task, refactor_task]
        """
        # 1. Test Task (Red)
        test_title = f"Write tests for: {title}"
        test_description = (
            f"Write failing tests for: {title}\n\n"
            "Test strategy: Tests should fail initially (red phase)"
        )
        test_task = self._create_task(
            title=test_title,
            task_type="task",
            parent_task_id=parent_task_id,
            description=test_description,
            labels=labels,
        )

        # 2. Implementation Task (Green)
        impl_title = f"Implement: {title}"
        impl_description = description or ""
        if impl_description:
            impl_description += "\n\n"
        impl_description += (
            "Test strategy: All tests from previous subtask should pass (green phase)"
        )

        impl_task = self._create_task(
            title=impl_title,
            task_type="task",
            parent_task_id=parent_task_id,
            description=impl_description,
            labels=labels,
        )

        # 3. Refactor Task (Refactor)
        refactor_title = f"Refactor: {title}"
        refactor_description = (
            f"Refactor the implementation of: {title}\n\n"
            "Test strategy: All tests must continue to pass after refactoring"
        )
        refactor_task = self._create_task(
            title=refactor_title,
            task_type="task",
            parent_task_id=parent_task_id,
            description=refactor_description,
            labels=labels,
        )

        # Wire dependencies
        try:
            # Implement blocked by Test
            self.dep_manager.add_dependency(
                task_id=impl_task.id,
                depends_on=test_task.id,
                dep_type="blocks",
            )
            # Refactor blocked by Implement
            self.dep_manager.add_dependency(
                task_id=refactor_task.id,
                depends_on=impl_task.id,
                dep_type="blocks",
            )
            logger.debug(
                f"TDD triplet created: {test_task.id} -> {impl_task.id} -> {refactor_task.id}"
            )
        except ValueError as e:
            logger.warning(f"Failed to add TDD dependency: {e}")

        return [test_task, impl_task, refactor_task]

    async def build_from_headings_with_fallback(
        self,
        headings: list[HeadingNode],
        checkboxes: ExtractedCheckboxes | None,
        task_expander: TaskExpander | None = None,
    ) -> HierarchyBuildResult:
        """Build task hierarchy with LLM fallback for underspecified sections.

        For headings WITH checkboxes: uses checkboxes directly as tasks (no LLM).
        For headings WITHOUT checkboxes: falls back to LLM expansion on that section.

        This enables hybrid specs where some phases are detailed and others
        need LLM decomposition.

        Args:
            headings: List of HeadingNode from MarkdownStructureParser.parse()
            checkboxes: ExtractedCheckboxes to integrate under headings
            task_expander: Optional TaskExpander for LLM fallback. If None,
                          sections without checkboxes are created as single tasks.

        Returns:
            HierarchyBuildResult with created tasks
        """
        created_tasks: list[CreatedTask] = []
        root_task_ids: list[str] = []

        # Get flat list of all checkboxes for line-range scoped lookup
        all_checkboxes = checkboxes.get_flat_items() if checkboxes else []

        # Process each heading tree with fallback logic
        for heading in headings:
            task_ids = await self._process_heading_with_fallback(
                heading=heading,
                parent_task_id=self.parent_task_id,
                all_checkboxes=all_checkboxes,
                created_tasks=created_tasks,
                task_expander=task_expander,
            )
            root_task_ids.extend(task_ids)

        return HierarchyBuildResult(
            tasks=created_tasks,
            root_task_ids=root_task_ids,
            total_count=len(created_tasks),
        )

    async def _process_heading_with_fallback(
        self,
        heading: HeadingNode,
        parent_task_id: str | None,
        all_checkboxes: list[CheckboxItem],
        created_tasks: list[CreatedTask],
        task_expander: TaskExpander | None,
    ) -> list[str]:
        """Process a heading with LLM fallback for sections without checkboxes.

        Args:
            heading: HeadingNode to process
            parent_task_id: ID of parent task (if any)
            all_checkboxes: Flat list of all checkboxes (filtered by line range)
            created_tasks: List to append created tasks to
            task_expander: Optional TaskExpander for LLM fallback

        Returns:
            List of task IDs created at this level
        """
        created_at_level: list[str] = []

        # Determine if this heading (or its children) have checkboxes
        has_checkboxes = self._heading_has_checkboxes(heading, all_checkboxes)

        # Check if this section is actionable (worth creating a task for)
        is_actionable = self._is_actionable_section(heading.text)

        # Check if any children are actionable (recursively)
        has_actionable_children = self._has_actionable_descendants(heading, all_checkboxes)

        # Skip non-actionable sections without checkboxes and without actionable children
        # These are documentation sections like "Problem Statement", "Design Decisions", etc.
        if not has_checkboxes and not is_actionable and not has_actionable_children:
            logger.debug(f"Skipping non-actionable section without checkboxes: '{heading.text}'")
            return created_at_level

        # Determine task type based on heading level
        task_type = "epic" if heading.level <= 3 else "task"

        # Create task for this heading
        # Inherit parent labels for pattern detection during LLM expansion
        task = self._create_task(
            title=heading.text,
            task_type=task_type,
            parent_task_id=parent_task_id,
            description=heading.content if heading.content.strip() else None,
            labels=self.parent_labels if not has_checkboxes else None,
        )
        created_tasks.append(task)
        created_at_level.append(task.id)

        # Process based on checkbox presence
        if has_checkboxes:
            # Use checkboxes directly under this heading (scoped by line range)
            for checkbox in self._get_checkboxes_for_heading(heading, all_checkboxes):
                await self._process_checkbox(
                    checkbox=checkbox,
                    parent_task_id=task.id,
                    created_tasks=created_tasks,
                    current_heading=heading,
                    all_checkboxes=all_checkboxes,
                )

            # Process child headings recursively
            for child in heading.children:
                await self._process_heading_with_fallback(
                    heading=child,
                    parent_task_id=task.id,
                    all_checkboxes=all_checkboxes,
                    created_tasks=created_tasks,
                    task_expander=task_expander,
                )
        else:
            # No checkboxes - fall back to LLM expansion if section is actionable
            is_actionable = self._is_actionable_section(heading.text)
            if task_expander and heading.content.strip() and is_actionable:
                logger.info(f"No checkboxes under '{heading.text}', using LLM expansion")
                try:
                    result = await task_expander.expand_task(
                        task_id=task.id,
                        title=heading.text,
                        description=heading.content,
                        context="Expand this section into actionable tasks. "
                        "This is from a specification document.",
                        enable_web_research=False,
                        enable_code_context=False,
                    )

                    # Track created subtasks
                    subtask_ids = result.get("subtask_ids", [])
                    for subtask_id in subtask_ids:
                        subtask = self.task_manager.get_task(subtask_id)
                        if subtask:
                            created_tasks.append(
                                CreatedTask(
                                    id=subtask.id,
                                    title=subtask.title,
                                    task_type=subtask.task_type,
                                    status=subtask.status,
                                    parent_task_id=task.id,
                                )
                            )

                    if result.get("error"):
                        logger.warning(
                            f"LLM expansion failed for '{heading.text}': {result.get('error')}"
                        )
                except Exception as e:
                    logger.warning(f"LLM fallback failed for '{heading.text}': {e}")
            else:
                # No expander, no content, or non-actionable section - skip LLM expansion
                if task_expander and heading.content.strip() and not is_actionable:
                    logger.debug(
                        f"Skipping LLM expansion for non-actionable section '{heading.text}'"
                    )
                # Still process children (as epics/tasks)
                for child in heading.children:
                    await self._process_heading_with_fallback(
                        heading=child,
                        parent_task_id=task.id,
                        all_checkboxes=all_checkboxes,
                        created_tasks=created_tasks,
                        task_expander=task_expander,
                    )

        return created_at_level

    def _heading_has_checkboxes(
        self,
        heading: HeadingNode,
        all_checkboxes: list[CheckboxItem],
    ) -> bool:
        """Check if a heading or any of its children have checkboxes.

        Args:
            heading: HeadingNode to check
            all_checkboxes: Flat list of all checkboxes (filtered by line range)

        Returns:
            True if heading or any descendant has checkboxes
        """
        # Direct checkboxes under this heading (scoped by line range)
        if self._get_checkboxes_for_heading(heading, all_checkboxes):
            return True

        # Check children recursively
        for child in heading.children:
            if self._heading_has_checkboxes(child, all_checkboxes):
                return True

        return False

    def _has_actionable_descendants(
        self,
        heading: HeadingNode,
        all_checkboxes: list[CheckboxItem],
    ) -> bool:
        """Check if any child headings are actionable or have checkboxes.

        Used to determine if a parent section should be created as a container
        even if the parent itself is not actionable.

        Args:
            heading: HeadingNode to check
            all_checkboxes: Flat list of all checkboxes (filtered by line range)

        Returns:
            True if any descendant is actionable or has checkboxes
        """
        for child in heading.children:
            # Check if child has checkboxes
            if self._heading_has_checkboxes(child, all_checkboxes):
                return True

            # Check if child heading text is actionable
            if self._is_actionable_section(child.text):
                return True

            # Recursively check grandchildren
            if self._has_actionable_descendants(child, all_checkboxes):
                return True

        return False

    def _is_actionable_section(self, heading_text: str) -> bool:
        """Check if a heading indicates an actionable section worth expanding.

        Sections like "Overview", "Configuration Example", etc. should NOT
        be expanded as they contain informational content, not work items.

        Args:
            heading_text: The heading text to check

        Returns:
            True if the heading contains actionable keywords
        """
        heading_lower = heading_text.lower()
        return any(keyword in heading_lower for keyword in ACTIONABLE_KEYWORDS)

    def _detect_parallel_groups(
        self,
        headings: list[HeadingNode],
        created_tasks: list[CreatedTask],
    ) -> list[ParallelGroup]:
        """Detect parallelizable task groups from sibling headings.

        Sibling headings at the same level under the same parent are
        considered parallelizable (can run in separate worktrees).

        Args:
            headings: The original heading tree
            created_tasks: List of created tasks (to map heading text -> task ID)

        Returns:
            List of ParallelGroup objects for sibling groups
        """
        parallel_groups: list[ParallelGroup] = []

        # Build a mapping from (title, parent_id) to task ID to handle duplicate titles
        heading_to_task: dict[tuple[str, str | None], str] = {}
        for task in created_tasks:
            heading_to_task[(task.title, task.parent_task_id)] = task.id

        # Recursively collect parallel groups from the heading tree
        self._collect_parallel_groups(
            headings=headings,
            parent_task_id=self.parent_task_id,
            heading_to_task=heading_to_task,
            parallel_groups=parallel_groups,
        )

        return parallel_groups

    def _collect_parallel_groups(
        self,
        headings: list[HeadingNode],
        parent_task_id: str | None,
        heading_to_task: dict[tuple[str, str | None], str],
        parallel_groups: list[ParallelGroup],
    ) -> None:
        """Recursively collect parallel groups from heading siblings.

        Args:
            headings: List of sibling headings at the current level
            parent_task_id: The parent task ID for these headings
            heading_to_task: Mapping from (heading text, parent_id) to task ID
            parallel_groups: List to append ParallelGroup objects to
        """
        if not headings:
            return

        # Collect task IDs for sibling headings at this level
        sibling_task_ids: list[str] = []
        heading_level = headings[0].level if headings else 0

        for heading in headings:
            task_id = heading_to_task.get((heading.text, parent_task_id))
            if task_id:
                sibling_task_ids.append(task_id)

            # Recursively process children of this heading
            if heading.children:
                # Get the task ID for this heading to use as parent for children
                this_task_id = heading_to_task.get((heading.text, parent_task_id))
                self._collect_parallel_groups(
                    headings=heading.children,
                    parent_task_id=this_task_id,
                    heading_to_task=heading_to_task,
                    parallel_groups=parallel_groups,
                )

        # Create a parallel group if there are multiple siblings
        if len(sibling_task_ids) >= 1:
            parallel_groups.append(
                ParallelGroup(
                    task_ids=sibling_task_ids,
                    parent_task_id=parent_task_id,
                    heading_level=heading_level,
                )
            )
