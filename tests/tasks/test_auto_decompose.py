"""Tests for auto-decomposition of multi-step tasks.

TDD: These tests are written first - the detect_multi_step function
does not exist yet and tests should fail in the red phase.
"""

from gobby.tasks.auto_decompose import detect_multi_step, extract_steps


class TestDetectMultiStepPositive:
    """Tests for positive detection of multi-step descriptions."""

    def test_detects_numbered_list(self):
        """Numbered lists indicate multiple steps."""
        description = """Implement user authentication:

1. Create user model with email and password fields
2. Add login endpoint with JWT token generation
3. Implement logout endpoint to invalidate tokens
"""
        assert detect_multi_step(description) is True

    def test_detects_numbered_list_without_periods(self):
        """Numbered lists without trailing periods."""
        description = """1) Set up database connection
2) Create migration files
3) Run migrations"""
        assert detect_multi_step(description) is True

    def test_detects_steps_section(self):
        """'Steps:' section header indicates multi-step."""
        description = """Add caching layer to API.

Steps:
- Install Redis client
- Create cache middleware
- Add cache invalidation logic
"""
        assert detect_multi_step(description) is True

    def test_detects_implementation_tasks_section(self):
        """'Implementation Tasks:' section indicates multi-step."""
        description = """Refactor database layer.

Implementation Tasks:
- Extract repository pattern
- Add unit of work
- Update service layer
"""
        assert detect_multi_step(description) is True

    def test_detects_sequential_action_bullets(self):
        """Sequential action verbs in bullets indicate steps."""
        description = """Feature: Dark mode support

- Create theme context provider
- Add CSS variables for colors
- Implement toggle component
- Update all styled components
"""
        assert detect_multi_step(description) is True

    def test_detects_phase_headers(self):
        """Phase headers indicate multi-step work."""
        description = """Migration to new API version.

## Phase 1: Preparation
Update client libraries

## Phase 2: Migration
Switch endpoints

## Phase 3: Cleanup
Remove deprecated code
"""
        assert detect_multi_step(description) is True

    def test_detects_then_sequence(self):
        """'First... then... finally...' indicates steps."""
        description = """First, create the database schema. Then, implement the
repository layer. Finally, add the API endpoints."""
        assert detect_multi_step(description) is True


class TestDetectMultiStepFalsePositives:
    """Tests for excluding false positives."""

    def test_excludes_steps_to_reproduce(self):
        """'Steps to reproduce' is bug context, not implementation steps."""
        description = """Button click doesn't work.

Steps to reproduce:
1. Open the settings page
2. Click the save button
3. Observe nothing happens

Expected: Settings should save.
"""
        assert detect_multi_step(description) is False

    def test_excludes_reproduction_steps(self):
        """'Reproduction steps' is bug context."""
        description = """API returns 500 error.

Reproduction steps:
1. Send POST to /api/users
2. Include invalid JSON
3. Server crashes
"""
        assert detect_multi_step(description) is False

    def test_excludes_acceptance_criteria(self):
        """Acceptance criteria are validation, not implementation steps."""
        description = """Add password strength indicator.

Acceptance criteria:
- Shows weak/medium/strong indicator
- Updates in real-time as user types
- Displays requirements not met
"""
        assert detect_multi_step(description) is False

    def test_excludes_options_list(self):
        """Options/approaches are alternatives, not sequential steps."""
        description = """Improve API performance.

Options:
- Add Redis caching
- Implement pagination
- Use database indexes

We should evaluate each approach.
"""
        assert detect_multi_step(description) is False

    def test_excludes_approaches_list(self):
        """'Approaches:' section is alternatives."""
        description = """Possible approaches:
1. Use existing library
2. Build custom solution
3. Hybrid approach
"""
        assert detect_multi_step(description) is False

    def test_excludes_files_to_modify(self):
        """File lists are references, not steps."""
        description = """Update copyright headers.

Files to modify:
- src/main.py
- src/utils.py
- src/config.py
"""
        assert detect_multi_step(description) is False

    def test_excludes_requirements_list(self):
        """Requirements are specs, not implementation steps."""
        description = """New feature requirements:
- Must support OAuth 2.0
- Must handle rate limiting
- Must log all requests
"""
        assert detect_multi_step(description) is False


class TestDetectMultiStepEdgeCases:
    """Tests for edge cases."""

    def test_returns_false_for_single_step(self):
        """Single-step descriptions should return False."""
        description = "Fix the typo in the README file."
        assert detect_multi_step(description) is False

    def test_returns_false_for_empty_string(self):
        """Empty descriptions should return False."""
        assert detect_multi_step("") is False

    def test_returns_false_for_none(self):
        """None should return False."""
        assert detect_multi_step(None) is False

    def test_returns_false_for_minimal_description(self):
        """Very short descriptions should return False."""
        assert detect_multi_step("Add tests") is False

    def test_handles_mixed_content_with_steps(self):
        """Mixed content with actual implementation steps should detect."""
        description = """Feature: Add export functionality.

Requirements:
- Support CSV format
- Support JSON format

Implementation steps:
1. Create exporter interface
2. Implement CSV exporter
3. Implement JSON exporter
4. Add export button to UI
"""
        assert detect_multi_step(description) is True

    def test_handles_mixed_content_without_steps(self):
        """Mixed content without implementation steps should not detect."""
        description = """Bug: Export fails silently.

Steps to reproduce:
1. Click export
2. Select CSV
3. Nothing happens

Requirements for fix:
- Show error message
- Log the error
"""
        assert detect_multi_step(description) is False

    def test_two_items_is_borderline(self):
        """Two items may or may not be multi-step depending on context."""
        # Two simple items - probably not worth decomposing
        description = """Update dependencies:
- Update React to v18
- Update TypeScript to v5
"""
        # This is borderline - implementation can decide threshold
        result = detect_multi_step(description)
        assert isinstance(result, bool)  # Just verify it returns a bool

    def test_handles_markdown_formatting(self):
        """Should handle various markdown formats."""
        description = """## Summary
Add new feature.

### Tasks
1. **Create model** - Add database schema
2. **Add API** - Create REST endpoints
3. **Build UI** - Implement React components
"""
        assert detect_multi_step(description) is True

    def test_handles_whitespace_variations(self):
        """Should handle different whitespace patterns."""
        description = """Steps:
  -  Create module
  -  Add tests
  -  Update docs
"""
        assert detect_multi_step(description) is True


# =============================================================================
# Step Extraction Tests (TDD - extract_steps function)
# =============================================================================


class TestExtractStepsFromNumberedList:
    """Tests for extracting steps from numbered lists."""

    def test_extracts_numbered_steps(self):
        """Extract steps from numbered list."""
        description = """Implement feature:

1. Create the database model
2. Add API endpoints
3. Build the UI components
"""
        steps = extract_steps(description)
        assert len(steps) == 3
        assert steps[0]["title"] == "Create the database model"
        assert steps[1]["title"] == "Add API endpoints"
        assert steps[2]["title"] == "Build the UI components"

    def test_extracts_numbered_steps_with_parentheses(self):
        """Extract steps from 1) 2) 3) format."""
        description = """1) Set up environment
2) Install dependencies
3) Run tests"""
        steps = extract_steps(description)
        assert len(steps) == 3
        assert steps[0]["title"] == "Set up environment"

    def test_numbered_steps_have_sequential_dependencies(self):
        """Each step depends on the previous one."""
        description = """1. First step
2. Second step
3. Third step"""
        steps = extract_steps(description)
        assert steps[0].get("depends_on") is None
        assert steps[1].get("depends_on") == [0]
        assert steps[2].get("depends_on") == [1]


class TestExtractStepsFromBullets:
    """Tests for extracting steps from bullet points."""

    def test_extracts_bullet_steps(self):
        """Extract steps from bullet list."""
        description = """Steps:
- Create user model
- Add authentication
- Implement logout
"""
        steps = extract_steps(description)
        assert len(steps) == 3
        assert steps[0]["title"] == "Create user model"

    def test_extracts_asterisk_bullets(self):
        """Extract steps from * bullet format."""
        description = """Tasks:
* Design schema
* Write migrations
* Update tests
"""
        steps = extract_steps(description)
        assert len(steps) == 3
        assert steps[0]["title"] == "Design schema"

    def test_bullet_steps_have_sequential_dependencies(self):
        """Bullet steps also get sequential dependencies."""
        description = """Steps:
- First task
- Second task
- Third task"""
        steps = extract_steps(description)
        assert steps[0].get("depends_on") is None
        assert steps[1].get("depends_on") == [0]
        assert steps[2].get("depends_on") == [1]


class TestExtractStepsMultiLine:
    """Tests for multi-line step descriptions."""

    def test_extracts_multiline_numbered_step(self):
        """Handle numbered step with description on next line."""
        description = """1. Create user model
   Add fields for email, password, and created_at

2. Add API endpoint
   POST /api/users with validation

3. Write tests
"""
        steps = extract_steps(description)
        assert len(steps) == 3
        assert steps[0]["title"] == "Create user model"
        assert "email, password" in steps[0].get("description", "")

    def test_extracts_multiline_bullet_step(self):
        """Handle bullet step with continuation."""
        description = """Steps:
- Implement caching layer
  Use Redis for session storage
  Add TTL configuration

- Add monitoring
  Set up metrics endpoint
"""
        steps = extract_steps(description)
        assert len(steps) == 2
        assert steps[0]["title"] == "Implement caching layer"
        assert "Redis" in steps[0].get("description", "")


class TestExtractStepsSubtaskGeneration:
    """Tests for subtask dict generation."""

    def test_step_has_required_fields(self):
        """Each step dict has title and description."""
        description = """1. Create the feature
2. Add tests
3. Deploy"""
        steps = extract_steps(description)
        assert len(steps) >= 1
        assert "title" in steps[0]
        assert "description" in steps[0] or steps[0].get("description") is None

    def test_preserves_context_in_description(self):
        """Original context from description is preserved."""
        description = """Feature: Add dark mode

Implementation:
1. Create theme context
2. Add CSS variables
3. Update components
"""
        steps = extract_steps(description)
        # Context about "dark mode" or "theme" should be in descriptions
        all_content = " ".join(
            str(s.get("description", "")) + str(s.get("title", "")) for s in steps
        )
        assert "theme" in all_content.lower() or "css" in all_content.lower()


class TestExtractStepsEdgeCases:
    """Tests for edge cases in step extraction."""

    def test_returns_empty_for_no_steps(self):
        """Return empty list when no steps detected."""
        description = "Fix the typo in README"
        steps = extract_steps(description)
        assert steps == []

    def test_returns_empty_for_none(self):
        """Return empty list for None input."""
        steps = extract_steps(None)
        assert steps == []

    def test_returns_empty_for_empty_string(self):
        """Return empty list for empty string."""
        steps = extract_steps("")
        assert steps == []

    def test_handles_inline_code(self):
        """Handle steps with inline code formatting."""
        description = """1. Create `UserModel` class
2. Add `authenticate()` method
3. Update `config.py`"""
        steps = extract_steps(description)
        assert len(steps) == 3
        assert "UserModel" in steps[0]["title"]

    def test_handles_bold_formatting(self):
        """Handle steps with bold markdown."""
        description = """1. **Create model** - database schema
2. **Add API** - REST endpoints
3. **Build UI** - React components"""
        steps = extract_steps(description)
        assert len(steps) == 3
        # Title should include the bold text content
        assert "Create model" in steps[0]["title"] or "model" in steps[0]["title"].lower()

    def test_truncates_long_titles(self):
        """Very long step text should be truncated for title."""
        long_text = "A" * 200
        description = f"""1. {long_text}
2. Short step
3. Another step"""
        steps = extract_steps(description)
        assert len(steps) == 3
        # Title should be truncated (max ~100 chars typical)
        assert len(steps[0]["title"]) <= 150
        # Full text should be in description
        if steps[0].get("description"):
            assert long_text in steps[0]["description"] or len(steps[0]["description"]) > 100

    def test_handles_steps_with_colons(self):
        """Handle steps that contain colons."""
        description = """1. Setup: Configure environment
2. Build: Compile the project
3. Test: Run all tests"""
        steps = extract_steps(description)
        assert len(steps) == 3
        assert "Setup" in steps[0]["title"] or "Configure" in steps[0]["title"]
