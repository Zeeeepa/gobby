"""Tests for the markdown spec parser."""

import pytest

from gobby.tasks.spec_parser import (
    CHECKBOX_PATTERN,
    CheckboxExtractor,
    CheckboxItem,
    CreatedTask,
    ExtractedCheckboxes,
    HeadingNode,
    HierarchyBuildResult,
    MarkdownStructureParser,
    TaskHierarchyBuilder,
)

# =============================================================================
# Heading Parser Tests
# =============================================================================


@pytest.fixture
def parser():
    """Create a MarkdownStructureParser instance."""
    return MarkdownStructureParser()


class TestMarkdownStructureParser:
    """Tests for MarkdownStructureParser.parse() method."""

    def test_parse_empty_text(self, parser):
        """Empty text returns empty list."""
        result = parser.parse("")
        assert result == []

    def test_parse_no_headings(self, parser):
        """Text with no headings returns empty list."""
        text = """This is just some text.
No headings here.
Just paragraphs."""
        result = parser.parse(text)
        assert result == []

    def test_parse_single_h2(self, parser):
        """Single ## heading is parsed correctly."""
        text = """## Introduction

This is the introduction."""
        result = parser.parse(text)

        assert len(result) == 1
        assert result[0].text == "Introduction"
        assert result[0].level == 2
        assert result[0].line_start == 1
        assert result[0].line_end == 3
        assert "This is the introduction." in result[0].content

    def test_parse_multiple_h2(self, parser):
        """Multiple ## headings at same level."""
        text = """## Section One

Content one.

## Section Two

Content two."""
        result = parser.parse(text)

        assert len(result) == 2
        assert result[0].text == "Section One"
        assert result[1].text == "Section Two"
        assert result[0].line_end == 4
        assert result[1].line_start == 5

    def test_parse_nested_h2_h3(self, parser):
        """### headings are children of ## headings."""
        text = """## Parent Section

Parent content.

### Child One

Child one content.

### Child Two

Child two content."""
        result = parser.parse(text)

        assert len(result) == 1
        parent = result[0]
        assert parent.text == "Parent Section"
        assert len(parent.children) == 2
        assert parent.children[0].text == "Child One"
        assert parent.children[1].text == "Child Two"

    def test_parse_deep_nesting(self, parser):
        """#### headings nest under ### headings."""
        text = """## Top Level

### Phase One

#### Task A

Task A details.

#### Task B

Task B details.

### Phase Two

Phase two content."""
        result = parser.parse(text)

        assert len(result) == 1
        top = result[0]
        assert top.text == "Top Level"
        assert len(top.children) == 2

        phase_one = top.children[0]
        assert phase_one.text == "Phase One"
        assert len(phase_one.children) == 2
        assert phase_one.children[0].text == "Task A"
        assert phase_one.children[1].text == "Task B"

        phase_two = top.children[1]
        assert phase_two.text == "Phase Two"
        assert len(phase_two.children) == 0

    def test_parse_line_numbers_correct(self, parser):
        """Line numbers are 1-indexed and accurate."""
        text = """## First
Content
## Second
More content
## Third"""
        result = parser.parse(text)

        assert result[0].line_start == 1
        assert result[0].line_end == 2
        assert result[1].line_start == 3
        assert result[1].line_end == 4
        assert result[2].line_start == 5
        assert result[2].line_end == 5

    def test_parse_content_extraction(self, parser):
        """Content is extracted correctly without the heading."""
        text = """## Section

This is the content.
Multiple lines here.

## Next Section"""
        result = parser.parse(text)

        assert "This is the content." in result[0].content
        assert "Multiple lines here." in result[0].content
        assert "## Section" not in result[0].content

    def test_parse_content_strips_empty_lines(self, parser):
        """Leading and trailing empty lines in content are stripped."""
        text = """## Section


Content with surrounding empty lines.


## Next"""
        result = parser.parse(text)

        assert result[0].content == "Content with surrounding empty lines."

    def test_parse_ignores_h1(self, parser):
        """# headings (h1) are ignored."""
        text = """# Title

## Section

Content."""
        result = parser.parse(text)

        assert len(result) == 1
        assert result[0].text == "Section"

    def test_parse_ignores_h5_and_deeper(self, parser):
        """##### and deeper headings are ignored."""
        text = """## Section

##### Deep heading

Content."""
        result = parser.parse(text)

        assert len(result) == 1
        assert len(result[0].children) == 0
        assert "##### Deep heading" in result[0].content

    def test_parse_handles_heading_with_formatting(self, parser):
        """Headings with inline formatting are parsed."""
        text = """## **Bold** Section

### _Italic_ Subsection"""
        result = parser.parse(text)

        assert result[0].text == "**Bold** Section"
        assert result[0].children[0].text == "_Italic_ Subsection"


class TestGetSectionsAtLevel:
    """Tests for MarkdownStructureParser.get_sections_at_level()."""

    def test_get_all_h2_sections(self, parser):
        """Get all level 2 sections."""
        text = """## One
### Sub One
## Two
### Sub Two"""
        tree = parser.parse(text)
        h2_sections = parser.get_sections_at_level(tree, 2)

        assert len(h2_sections) == 2
        assert h2_sections[0].text == "One"
        assert h2_sections[1].text == "Two"

    def test_get_all_h3_sections(self, parser):
        """Get all level 3 sections from nested tree."""
        text = """## Parent One
### Child A
### Child B
## Parent Two
### Child C"""
        tree = parser.parse(text)
        h3_sections = parser.get_sections_at_level(tree, 3)

        assert len(h3_sections) == 3
        assert h3_sections[0].text == "Child A"
        assert h3_sections[1].text == "Child B"
        assert h3_sections[2].text == "Child C"

    def test_get_sections_empty_level(self, parser):
        """Returns empty list if no sections at level."""
        text = """## Only H2"""
        tree = parser.parse(text)
        h3_sections = parser.get_sections_at_level(tree, 3)

        assert h3_sections == []


class TestHeadingNode:
    """Tests for HeadingNode dataclass."""

    def test_heading_node_defaults(self):
        """HeadingNode has correct defaults."""
        node = HeadingNode(text="Test", level=2, line_start=1)

        assert node.text == "Test"
        assert node.level == 2
        assert node.line_start == 1
        assert node.line_end == 0
        assert node.children == []
        assert node.content == ""

    def test_heading_node_with_children(self):
        """HeadingNode can have children."""
        child = HeadingNode(text="Child", level=3, line_start=5)
        parent = HeadingNode(
            text="Parent",
            level=2,
            line_start=1,
            line_end=10,
            children=[child],
            content="Parent content",
        )

        assert len(parent.children) == 1
        assert parent.children[0].text == "Child"


class TestRealWorldSpec:
    """Tests with realistic spec document structure."""

    def test_parse_typical_spec_structure(self, parser):
        """Parse a typical spec document with phases and tasks."""
        text = """## Overview

This document describes the implementation plan.

## Phase 1: Foundation

### Task 1.1: Setup

Set up the basic infrastructure.

### Task 1.2: Configuration

Configure the settings.

## Phase 2: Implementation

### Task 2.1: Core Logic

Implement the main functionality.

#### Subtask 2.1.1: Data Model

Define the data model.

#### Subtask 2.1.2: Business Logic

Implement business rules.

## Phase 3: Testing

Write tests."""
        result = parser.parse(text)

        # Should have 4 top-level sections
        assert len(result) == 4
        assert result[0].text == "Overview"
        assert result[1].text == "Phase 1: Foundation"
        assert result[2].text == "Phase 2: Implementation"
        assert result[3].text == "Phase 3: Testing"

        # Phase 1 has 2 tasks
        phase1 = result[1]
        assert len(phase1.children) == 2
        assert phase1.children[0].text == "Task 1.1: Setup"

        # Phase 2's Task 2.1 has subtasks
        phase2 = result[2]
        assert len(phase2.children) == 1
        task21 = phase2.children[0]
        assert task21.text == "Task 2.1: Core Logic"
        assert len(task21.children) == 2
        assert task21.children[0].text == "Subtask 2.1.1: Data Model"
        assert task21.children[1].text == "Subtask 2.1.2: Business Logic"

        # Phase 3 has no subtasks
        phase3 = result[3]
        assert len(phase3.children) == 0
        assert "Write tests." in phase3.content


# =============================================================================
# Checkbox Parser Tests
# =============================================================================


class TestCheckboxPattern:
    """Tests for the checkbox regex pattern."""

    def test_matches_unchecked_with_dash(self):
        match = CHECKBOX_PATTERN.match("- [ ] Task item")
        assert match is not None
        indent, marker, text = match.groups()
        assert indent == ""
        assert marker == " "
        assert text == "Task item"

    def test_matches_checked_with_dash(self):
        match = CHECKBOX_PATTERN.match("- [x] Done task")
        assert match is not None
        indent, marker, text = match.groups()
        assert indent == ""
        assert marker == "x"
        assert text == "Done task"

    def test_matches_checked_uppercase_x(self):
        match = CHECKBOX_PATTERN.match("- [X] Done task")
        assert match is not None
        _, marker, _ = match.groups()
        assert marker == "X"

    def test_matches_with_asterisk(self):
        match = CHECKBOX_PATTERN.match("* [ ] Asterisk item")
        assert match is not None
        _, _, text = match.groups()
        assert text == "Asterisk item"

    def test_matches_indented_checkbox(self):
        match = CHECKBOX_PATTERN.match("  - [ ] Indented task")
        assert match is not None
        indent, marker, text = match.groups()
        assert indent == "  "
        assert marker == " "
        assert text == "Indented task"

    def test_matches_deeply_indented(self):
        match = CHECKBOX_PATTERN.match("      - [x] Deep item")
        assert match is not None
        indent, _, _ = match.groups()
        assert indent == "      "
        assert len(indent) == 6

    def test_no_match_regular_list(self):
        assert CHECKBOX_PATTERN.match("- Regular item") is None

    def test_no_match_no_space_after_bracket(self):
        assert CHECKBOX_PATTERN.match("- []No space") is None

    def test_no_match_wrong_bracket_content(self):
        assert CHECKBOX_PATTERN.match("- [y] Wrong marker") is None


class TestCheckboxItem:
    """Tests for the CheckboxItem dataclass."""

    def test_depth_calculation_no_indent(self):
        item = CheckboxItem(
            text="Test",
            checked=False,
            line_number=0,
            indent_level=0,
            raw_line="- [ ] Test",
        )
        assert item.depth == 0

    def test_depth_calculation_two_spaces(self):
        item = CheckboxItem(
            text="Test",
            checked=False,
            line_number=0,
            indent_level=2,
            raw_line="  - [ ] Test",
        )
        assert item.depth == 1

    def test_depth_calculation_four_spaces(self):
        item = CheckboxItem(
            text="Test",
            checked=False,
            line_number=0,
            indent_level=4,
            raw_line="    - [ ] Test",
        )
        assert item.depth == 2

    def test_to_dict(self):
        item = CheckboxItem(
            text="My task",
            checked=True,
            line_number=5,
            indent_level=2,
            raw_line="  - [x] My task",
            parent_heading="Implementation",
        )
        result = item.to_dict()
        assert result["text"] == "My task"
        assert result["checked"] is True
        assert result["line_number"] == 5
        assert result["indent_level"] == 2
        assert result["depth"] == 1
        assert result["parent_heading"] == "Implementation"
        assert result["children"] == []

    def test_to_dict_with_children(self):
        child = CheckboxItem(
            text="Child",
            checked=False,
            line_number=2,
            indent_level=2,
            raw_line="  - [ ] Child",
        )
        parent = CheckboxItem(
            text="Parent",
            checked=False,
            line_number=1,
            indent_level=0,
            raw_line="- [ ] Parent",
            children=[child],
        )
        result = parent.to_dict()
        assert len(result["children"]) == 1
        assert result["children"][0]["text"] == "Child"


class TestExtractedCheckboxes:
    """Tests for the ExtractedCheckboxes dataclass."""

    def test_unchecked_count(self):
        result = ExtractedCheckboxes(
            items=[],
            total_count=10,
            checked_count=3,
        )
        assert result.unchecked_count == 7

    def test_to_dict(self):
        item = CheckboxItem(
            text="Task",
            checked=False,
            line_number=0,
            indent_level=0,
            raw_line="- [ ] Task",
        )
        result = ExtractedCheckboxes(
            items=[item],
            total_count=1,
            checked_count=0,
        )
        data = result.to_dict()
        assert data["total_count"] == 1
        assert data["checked_count"] == 0
        assert len(data["items"]) == 1

    def test_get_flat_items_no_nesting(self):
        items = [
            CheckboxItem("A", False, 0, 0, "- [ ] A"),
            CheckboxItem("B", True, 1, 0, "- [x] B"),
        ]
        result = ExtractedCheckboxes(items=items, total_count=2, checked_count=1)
        flat = result.get_flat_items()
        assert len(flat) == 2
        assert flat[0].text == "A"
        assert flat[1].text == "B"

    def test_get_flat_items_with_nesting(self):
        child = CheckboxItem("Child", False, 2, 2, "  - [ ] Child")
        parent = CheckboxItem("Parent", False, 1, 0, "- [ ] Parent", children=[child])
        result = ExtractedCheckboxes(items=[parent], total_count=2, checked_count=0)
        flat = result.get_flat_items()
        assert len(flat) == 2
        assert flat[0].text == "Parent"
        assert flat[1].text == "Child"


class TestCheckboxExtractor:
    """Tests for the CheckboxExtractor class."""

    def test_extract_simple_checkboxes(self):
        content = """
# Tasks
- [ ] First task
- [x] Second task (done)
- [ ] Third task
"""
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.total_count == 3
        assert result.checked_count == 1
        assert len(result.items) == 3
        assert result.items[0].text == "First task"
        assert result.items[0].checked is False
        assert result.items[1].text == "Second task (done)"
        assert result.items[1].checked is True
        assert result.items[2].text == "Third task"

    def test_extract_with_heading_tracking(self):
        content = """
## Phase 1
- [ ] Task under phase 1

## Phase 2
- [ ] Task under phase 2
- [x] Another task under phase 2
"""
        extractor = CheckboxExtractor(track_headings=True)
        result = extractor.extract(content)

        assert result.total_count == 3
        assert result.items[0].parent_heading == "Phase 1"
        assert result.items[1].parent_heading == "Phase 2"
        assert result.items[2].parent_heading == "Phase 2"

    def test_extract_without_heading_tracking(self):
        content = """
## Phase 1
- [ ] Task under phase 1
"""
        extractor = CheckboxExtractor(track_headings=False)
        result = extractor.extract(content)

        assert result.total_count == 1
        assert result.items[0].parent_heading is None

    def test_extract_nested_checkboxes_builds_hierarchy(self):
        content = """
- [ ] Parent task
  - [ ] Child task 1
  - [ ] Child task 2
    - [ ] Grandchild task
- [ ] Another parent
"""
        extractor = CheckboxExtractor(build_hierarchy=True)
        result = extractor.extract(content)

        # Should have 2 root items (Parent task, Another parent)
        assert len(result.items) == 2
        assert result.items[0].text == "Parent task"
        assert result.items[1].text == "Another parent"

        # Parent task should have 2 children
        parent = result.items[0]
        assert len(parent.children) == 2
        assert parent.children[0].text == "Child task 1"
        assert parent.children[1].text == "Child task 2"

        # Child task 2 should have 1 grandchild
        child2 = parent.children[1]
        assert len(child2.children) == 1
        assert child2.children[0].text == "Grandchild task"

        # Total count includes all items
        assert result.total_count == 5

    def test_extract_without_hierarchy_building(self):
        content = """
- [ ] Parent task
  - [ ] Child task
"""
        extractor = CheckboxExtractor(build_hierarchy=False)
        result = extractor.extract(content)

        # Should have flat list
        assert len(result.items) == 2
        assert result.items[0].text == "Parent task"
        assert result.items[1].text == "Child task"
        # No children populated
        assert len(result.items[0].children) == 0
        assert len(result.items[1].children) == 0

    def test_extract_preserves_line_numbers(self):
        content = """Line 0
Line 1
- [ ] Task on line 2
Line 3
- [x] Task on line 4
"""
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.items[0].line_number == 2
        assert result.items[1].line_number == 4

    def test_extract_preserves_raw_line(self):
        content = "  - [ ] Indented task with extra text  "
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.items[0].raw_line == "  - [ ] Indented task with extra text  "

    def test_extract_handles_uppercase_x(self):
        content = """
- [X] Done with uppercase
- [x] Done with lowercase
"""
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.checked_count == 2
        assert result.items[0].checked is True
        assert result.items[1].checked is True

    def test_extract_ignores_regular_list_items(self):
        content = """
- Regular item (no checkbox)
- [ ] Checkbox item
* Another regular item
* [x] Another checkbox
"""
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.total_count == 2
        assert result.items[0].text == "Checkbox item"
        assert result.items[1].text == "Another checkbox"

    def test_extract_empty_content(self):
        extractor = CheckboxExtractor()
        result = extractor.extract("")

        assert result.total_count == 0
        assert result.checked_count == 0
        assert len(result.items) == 0

    def test_extract_no_checkboxes(self):
        content = """
# Heading
Some paragraph text.

- Regular list
- Another item
"""
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.total_count == 0

    def test_extract_under_heading_basic(self):
        content = """
## Implementation
- [ ] Impl task 1
- [ ] Impl task 2

## Testing
- [ ] Test task 1
- [x] Test task 2
"""
        extractor = CheckboxExtractor()
        result = extractor.extract_under_heading(content, "Testing")

        assert result.total_count == 2
        assert result.items[0].text == "Test task 1"
        assert result.items[1].text == "Test task 2"
        assert result.checked_count == 1

    def test_extract_under_heading_regex_pattern(self):
        content = """
## Phase 1: Setup
- [ ] Setup task

## Phase 2: Implementation
- [ ] Impl task
"""
        extractor = CheckboxExtractor()
        result = extractor.extract_under_heading(content, r"Phase \d+: Implementation")

        assert result.total_count == 1
        assert result.items[0].text == "Impl task"

    def test_extract_under_heading_case_insensitive(self):
        content = """
## TESTING
- [ ] Test 1

## testing
- [ ] Test 2
"""
        extractor = CheckboxExtractor()
        result = extractor.extract_under_heading(content, "testing", case_sensitive=False)

        assert result.total_count == 2

    def test_extract_under_heading_case_sensitive(self):
        content = """
## TESTING
- [ ] Test 1

## testing
- [ ] Test 2
"""
        extractor = CheckboxExtractor()
        result = extractor.extract_under_heading(content, "testing", case_sensitive=True)

        # Should only match lowercase
        assert result.total_count == 1
        assert result.items[0].text == "Test 2"

    def test_extract_under_heading_no_match(self):
        content = """
## Implementation
- [ ] Task 1
"""
        extractor = CheckboxExtractor()
        result = extractor.extract_under_heading(content, "Testing")

        assert result.total_count == 0
        assert len(result.items) == 0

    def test_heading_context_updates_correctly(self):
        content = """
## First Section
- [ ] Task in first

### Subsection
- [ ] Task in subsection

## Second Section
- [ ] Task in second
"""
        extractor = CheckboxExtractor(track_headings=True)
        result = extractor.extract(content)

        assert result.items[0].parent_heading == "First Section"
        assert result.items[1].parent_heading == "Subsection"
        assert result.items[2].parent_heading == "Second Section"


class TestCheckboxExtractorEdgeCases:
    """Edge case tests for CheckboxExtractor."""

    def test_checkbox_with_special_characters(self):
        content = "- [ ] Task with `code` and **bold** and [link](url)"
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.total_count == 1
        assert "code" in result.items[0].text
        assert "bold" in result.items[0].text

    def test_checkbox_with_emoji(self):
        content = "- [ ] Task with emoji \U0001F680"
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.total_count == 1
        assert "\U0001F680" in result.items[0].text

    def test_mixed_indentation_levels(self):
        content = """
- [ ] Level 0
    - [ ] Level 2 (4 spaces)
  - [ ] Level 1 (2 spaces)
      - [ ] Level 3 (6 spaces)
"""
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        items = result.get_flat_items()
        assert len(items) == 4
        assert items[0].indent_level == 0
        assert items[1].indent_level == 4
        assert items[2].indent_level == 2
        assert items[3].indent_level == 6

    def test_tabs_as_indentation(self):
        content = "\t- [ ] Tab indented"
        extractor = CheckboxExtractor()
        result = extractor.extract(content)

        assert result.total_count == 1
        assert result.items[0].indent_level == 1  # Tab counts as 1 character

    def test_heading_without_space(self):
        # Invalid heading format - should not be recognized as heading
        content = """
##NoSpace
- [ ] Task
"""
        extractor = CheckboxExtractor(track_headings=True)
        result = extractor.extract(content)

        # Task should not have parent heading since ##NoSpace is invalid
        assert result.items[0].parent_heading is None

    def test_very_deep_nesting(self):
        content = """
- [ ] Level 0
  - [ ] Level 1
    - [ ] Level 2
      - [ ] Level 3
        - [ ] Level 4
"""
        extractor = CheckboxExtractor(build_hierarchy=True)
        result = extractor.extract(content)

        # Should have single root
        assert len(result.items) == 1
        assert result.total_count == 5

        # Verify chain
        current = result.items[0]
        for _ in range(4):
            assert len(current.children) == 1
            current = current.children[0]
        assert len(current.children) == 0  # Deepest level

    def test_sibling_items_at_various_levels(self):
        content = """
- [ ] Root 1
  - [ ] Child 1.1
  - [ ] Child 1.2
- [ ] Root 2
  - [ ] Child 2.1
"""
        extractor = CheckboxExtractor(build_hierarchy=True)
        result = extractor.extract(content)

        assert len(result.items) == 2  # Two root items
        assert len(result.items[0].children) == 2  # Root 1 has 2 children
        assert len(result.items[1].children) == 1  # Root 2 has 1 child


# =============================================================================
# Task Hierarchy Builder Tests
# =============================================================================


class MockTask:
    """Mock task object for testing."""

    def __init__(self, id: str, title: str, task_type: str, parent_task_id: str | None = None):
        self.id = id
        self.title = title
        self.task_type = task_type
        self.parent_task_id = parent_task_id


class MockTaskManager:
    """Mock task manager for testing TaskHierarchyBuilder."""

    def __init__(self):
        self.tasks: list[MockTask] = []
        self.task_counter = 0
        self.updates: list[dict] = []

    def create_task(
        self,
        title: str,
        project_id: str,
        task_type: str = "task",
        parent_task_id: str | None = None,
        description: str | None = None,
        priority: int = 2,
        **kwargs,
    ) -> MockTask:
        """Create a mock task and return it."""
        self.task_counter += 1
        task = MockTask(
            id=f"gt-mock{self.task_counter}",
            title=title,
            task_type=task_type,
            parent_task_id=parent_task_id,
        )
        self.tasks.append(task)
        return task

    def update_task(self, task_id: str, **kwargs) -> None:
        """Record a task update."""
        self.updates.append({"task_id": task_id, **kwargs})


@pytest.fixture
def mock_task_manager():
    """Create a MockTaskManager instance."""
    return MockTaskManager()


@pytest.fixture
def hierarchy_builder(mock_task_manager):
    """Create a TaskHierarchyBuilder with mock task manager."""
    return TaskHierarchyBuilder(
        task_manager=mock_task_manager,
        project_id="test-project",
    )


class TestCreatedTask:
    """Tests for CreatedTask dataclass."""

    def test_created_task_fields(self):
        task = CreatedTask(
            id="gt-123",
            title="Test Task",
            task_type="task",
            status="open",
            parent_task_id="gt-parent",
        )
        assert task.id == "gt-123"
        assert task.title == "Test Task"
        assert task.task_type == "task"
        assert task.status == "open"
        assert task.parent_task_id == "gt-parent"

    def test_created_task_defaults(self):
        task = CreatedTask(
            id="gt-123",
            title="Test Task",
            task_type="task",
            status="open",
        )
        assert task.parent_task_id is None


class TestHierarchyBuildResult:
    """Tests for HierarchyBuildResult dataclass."""

    def test_task_ids_property(self):
        tasks = [
            CreatedTask("gt-1", "Task 1", "task", "open"),
            CreatedTask("gt-2", "Task 2", "task", "open"),
            CreatedTask("gt-3", "Task 3", "epic", "open"),
        ]
        result = HierarchyBuildResult(
            tasks=tasks,
            root_task_ids=["gt-1", "gt-3"],
            total_count=3,
        )
        assert result.task_ids == ["gt-1", "gt-2", "gt-3"]


class TestTaskHierarchyBuilderInit:
    """Tests for TaskHierarchyBuilder initialization."""

    def test_init_with_defaults(self, mock_task_manager):
        builder = TaskHierarchyBuilder(
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        assert builder.project_id == "test-project"
        assert builder.parent_task_id is None
        assert builder.default_priority == 2

    def test_init_with_parent_task(self, mock_task_manager):
        builder = TaskHierarchyBuilder(
            task_manager=mock_task_manager,
            project_id="test-project",
            parent_task_id="gt-parent",
        )
        assert builder.parent_task_id == "gt-parent"

    def test_init_with_custom_priority(self, mock_task_manager):
        builder = TaskHierarchyBuilder(
            task_manager=mock_task_manager,
            project_id="test-project",
            default_priority=1,
        )
        assert builder.default_priority == 1


class TestBuildFromHeadings:
    """Tests for TaskHierarchyBuilder.build_from_headings()."""

    def test_build_empty_headings(self, hierarchy_builder):
        result = hierarchy_builder.build_from_headings([])
        assert result.total_count == 0
        assert result.root_task_ids == []
        assert result.tasks == []

    def test_build_single_h2_heading(self, hierarchy_builder, mock_task_manager):
        headings = [
            HeadingNode(text="Overview", level=2, line_start=1, line_end=5, content="Some content")
        ]
        result = hierarchy_builder.build_from_headings(headings)

        assert result.total_count == 1
        assert len(result.root_task_ids) == 1

        # Verify task was created as epic (level 2-3 are epics)
        assert mock_task_manager.tasks[0].task_type == "epic"
        assert mock_task_manager.tasks[0].title == "Overview"

    def test_build_h2_with_h3_children(self, hierarchy_builder, mock_task_manager):
        child1 = HeadingNode(text="Task 1", level=3, line_start=5, line_end=10)
        child2 = HeadingNode(text="Task 2", level=3, line_start=11, line_end=15)
        parent = HeadingNode(
            text="Phase 1",
            level=2,
            line_start=1,
            line_end=15,
            children=[child1, child2],
        )

        result = hierarchy_builder.build_from_headings([parent])

        assert result.total_count == 3
        assert len(result.root_task_ids) == 1

        # Verify hierarchy - all level 2-3 are epics
        tasks = mock_task_manager.tasks
        assert tasks[0].title == "Phase 1"
        assert tasks[0].task_type == "epic"
        assert tasks[0].parent_task_id is None

        assert tasks[1].title == "Task 1"
        assert tasks[1].task_type == "epic"  # level 3 is still epic
        assert tasks[1].parent_task_id == tasks[0].id

        assert tasks[2].title == "Task 2"
        assert tasks[2].parent_task_id == tasks[0].id

    def test_build_h4_becomes_task(self, hierarchy_builder, mock_task_manager):
        subtask = HeadingNode(text="Subtask A", level=4, line_start=5, line_end=10)
        phase = HeadingNode(
            text="Phase 1",
            level=3,
            line_start=1,
            line_end=10,
            children=[subtask],
        )

        result = hierarchy_builder.build_from_headings([phase])

        assert result.total_count == 2
        tasks = mock_task_manager.tasks

        # Level 3 is epic
        assert tasks[0].task_type == "epic"
        # Level 4+ is task
        assert tasks[1].task_type == "task"
        assert tasks[1].parent_task_id == tasks[0].id

    def test_build_multiple_root_headings(self, hierarchy_builder, mock_task_manager):
        h1 = HeadingNode(text="Phase 1", level=2, line_start=1, line_end=5)
        h2 = HeadingNode(text="Phase 2", level=2, line_start=6, line_end=10)
        h3 = HeadingNode(text="Phase 3", level=2, line_start=11, line_end=15)

        result = hierarchy_builder.build_from_headings([h1, h2, h3])

        assert result.total_count == 3
        assert len(result.root_task_ids) == 3
        assert all(t.parent_task_id is None for t in mock_task_manager.tasks)

    def test_build_with_parent_task_id(self, mock_task_manager):
        builder = TaskHierarchyBuilder(
            task_manager=mock_task_manager,
            project_id="test-project",
            parent_task_id="gt-epic-parent",
        )
        heading = HeadingNode(text="Child Phase", level=2, line_start=1, line_end=5)

        result = builder.build_from_headings([heading])

        assert result.total_count == 1
        assert mock_task_manager.tasks[0].parent_task_id == "gt-epic-parent"

    def test_build_with_checkboxes_integration(self, hierarchy_builder, mock_task_manager):
        """Test that checkboxes are integrated under their parent headings."""
        heading = HeadingNode(text="Implementation", level=3, line_start=1, line_end=10)

        checkbox_item = CheckboxItem(
            text="Write tests",
            checked=False,
            line_number=5,
            indent_level=0,
            raw_line="- [ ] Write tests",
            parent_heading="Implementation",
        )
        checkboxes = ExtractedCheckboxes(
            items=[checkbox_item],
            total_count=1,
            checked_count=0,
        )

        result = hierarchy_builder.build_from_headings([heading], checkboxes)

        # Should create 2 tasks: epic for heading + task for checkbox
        assert result.total_count == 2

        tasks = mock_task_manager.tasks
        assert tasks[0].title == "Implementation"
        assert tasks[0].task_type == "epic"

        assert tasks[1].title == "Write tests"
        assert tasks[1].task_type == "task"
        assert tasks[1].parent_task_id == tasks[0].id


class TestBuildFromCheckboxes:
    """Tests for TaskHierarchyBuilder.build_from_checkboxes()."""

    def test_build_empty_checkboxes(self, hierarchy_builder):
        checkboxes = ExtractedCheckboxes(items=[], total_count=0, checked_count=0)
        result = hierarchy_builder.build_from_checkboxes(checkboxes)

        assert result.total_count == 0
        assert result.root_task_ids == []

    def test_build_simple_checkboxes(self, hierarchy_builder, mock_task_manager):
        items = [
            CheckboxItem("Task 1", False, 0, 0, "- [ ] Task 1"),
            CheckboxItem("Task 2", False, 1, 0, "- [ ] Task 2"),
        ]
        checkboxes = ExtractedCheckboxes(items=items, total_count=2, checked_count=0)

        result = hierarchy_builder.build_from_checkboxes(checkboxes)

        assert result.total_count == 2
        assert len(result.root_task_ids) == 2
        assert mock_task_manager.tasks[0].title == "Task 1"
        assert mock_task_manager.tasks[1].title == "Task 2"

    def test_build_checkboxes_with_heading_creates_epic(self, hierarchy_builder, mock_task_manager):
        items = [CheckboxItem("Task 1", False, 0, 0, "- [ ] Task 1")]
        checkboxes = ExtractedCheckboxes(items=items, total_count=1, checked_count=0)

        result = hierarchy_builder.build_from_checkboxes(checkboxes, heading_text="My Epic")

        assert result.total_count == 2
        assert len(result.root_task_ids) == 1  # Only epic is root

        tasks = mock_task_manager.tasks
        assert tasks[0].title == "My Epic"
        assert tasks[0].task_type == "epic"
        assert tasks[1].title == "Task 1"
        assert tasks[1].parent_task_id == tasks[0].id

    def test_build_nested_checkboxes(self, hierarchy_builder, mock_task_manager):
        child = CheckboxItem("Child Task", False, 1, 2, "  - [ ] Child Task")
        parent_item = CheckboxItem("Parent Task", False, 0, 0, "- [ ] Parent Task", children=[child])
        checkboxes = ExtractedCheckboxes(items=[parent_item], total_count=2, checked_count=0)

        result = hierarchy_builder.build_from_checkboxes(checkboxes)

        assert result.total_count == 2

        tasks = mock_task_manager.tasks
        assert tasks[0].title == "Parent Task"
        assert tasks[1].title == "Child Task"
        assert tasks[1].parent_task_id == tasks[0].id

    def test_build_checked_checkbox_creates_closed_task(self, hierarchy_builder, mock_task_manager):
        item = CheckboxItem("Done Task", True, 0, 0, "- [x] Done Task")
        checkboxes = ExtractedCheckboxes(items=[item], total_count=1, checked_count=1)

        result = hierarchy_builder.build_from_checkboxes(checkboxes)

        assert result.total_count == 1
        # Task should have been updated to closed status
        assert len(mock_task_manager.updates) == 1
        assert mock_task_manager.updates[0]["status"] == "closed"


class TestTaskHierarchyBuilderIntegration:
    """Integration tests combining parsers with hierarchy builder."""

    def test_full_pipeline_heading_to_tasks(self, mock_task_manager):
        """Parse markdown and build tasks in one flow."""
        content = """## Phase 1: Setup

Initialize the project.

### Task 1.1: Environment

Set up dev environment.

### Task 1.2: Dependencies

Install required packages.

## Phase 2: Implementation

#### Subtask 2.1

First implementation step.
"""
        parser = MarkdownStructureParser()
        headings = parser.parse(content)

        builder = TaskHierarchyBuilder(
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        result = builder.build_from_headings(headings)

        # Should create: Phase 1 (epic), Task 1.1 (epic), Task 1.2 (epic), Phase 2 (epic), Subtask 2.1 (task)
        assert result.total_count == 5
        assert len(result.root_task_ids) == 2  # Two phases at root

        # Verify types
        task_types = [t.task_type for t in mock_task_manager.tasks]
        assert task_types.count("epic") == 4  # All level 2-3
        assert task_types.count("task") == 1  # Only level 4

    def test_full_pipeline_checkbox_to_tasks(self, mock_task_manager):
        """Parse checkboxes and build tasks in one flow."""
        content = """## Implementation Tasks

- [ ] Write unit tests
  - [ ] Test parser
  - [ ] Test builder
- [x] Setup CI/CD
- [ ] Deploy to staging
"""
        extractor = CheckboxExtractor(track_headings=True, build_hierarchy=True)
        checkboxes = extractor.extract(content)

        builder = TaskHierarchyBuilder(
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        result = builder.build_from_checkboxes(checkboxes)

        # Should create: Write unit tests, Test parser, Test builder, Setup CI/CD, Deploy to staging
        assert result.total_count == 5
        assert len(result.root_task_ids) == 3  # 3 top-level checkboxes

        # Verify hierarchy: Test parser and Test builder are children of Write unit tests
        tasks = mock_task_manager.tasks
        parent_id = tasks[0].id
        assert tasks[1].parent_task_id == parent_id  # Test parser
        assert tasks[2].parent_task_id == parent_id  # Test builder

        # Setup CI/CD should have status update to closed
        assert any(u.get("status") == "closed" for u in mock_task_manager.updates)

    def test_full_pipeline_headings_with_checkboxes(self, mock_task_manager):
        """Parse headings and checkboxes together."""
        content = """## Phase 1: Foundation

### Setup Tasks

- [ ] Install dependencies
- [ ] Configure environment

### Implementation

- [ ] Write core logic
- [x] Add error handling

## Phase 2: Testing

- [ ] Unit tests
- [ ] Integration tests
"""
        # Parse both structures
        heading_parser = MarkdownStructureParser()
        headings = heading_parser.parse(content)

        checkbox_extractor = CheckboxExtractor(track_headings=True, build_hierarchy=True)
        checkboxes = checkbox_extractor.extract(content)

        # Build hierarchy
        builder = TaskHierarchyBuilder(
            task_manager=mock_task_manager,
            project_id="test-project",
        )
        result = builder.build_from_headings(headings, checkboxes)

        # Headings: Phase 1, Setup Tasks, Implementation, Phase 2 (4 epics)
        # Checkboxes: 6 tasks under their respective headings
        assert result.total_count == 10
        assert len(result.root_task_ids) == 2  # Two phases
