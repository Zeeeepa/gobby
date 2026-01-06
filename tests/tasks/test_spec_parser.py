"""Tests for the markdown spec parser."""

import pytest

from gobby.tasks.spec_parser import HeadingNode, MarkdownStructureParser


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
