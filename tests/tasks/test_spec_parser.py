"""Tests for the markdown spec parser checkbox extraction."""

from gobby.tasks.spec_parser import (
    CHECKBOX_PATTERN,
    CheckboxExtractor,
    CheckboxItem,
    ExtractedCheckboxes,
)


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
