"""Tests for auto-decomposition of multi-step tasks.

TDD: These tests are written first - the detect_multi_step function
does not exist yet and tests should fail in the red phase.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager
from gobby.tasks.auto_decompose import detect_multi_step, extract_steps
from gobby.workflows.definitions import WorkflowState


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


# =============================================================================
# create_task Integration Tests (TDD - auto_decompose parameter)
# =============================================================================


@pytest.fixture
def task_db(tmp_path):
    """Create a test database with migrations applied."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(str(db_path))
    run_migrations(db)
    # Create a test project
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)",
            ("test-project", "Test Project"),
        )
    return db


@pytest.fixture
def task_manager(task_db):
    """Create a LocalTaskManager instance."""
    return LocalTaskManager(task_db)


@pytest.fixture
def dep_manager(task_db):
    """Create a TaskDependencyManager instance."""
    return TaskDependencyManager(task_db)


class TestCreateTaskAutoDecomposeDefault:
    """Tests for default auto_decompose=True behavior."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_multi_step_description_creates_parent_and_subtasks(self, task_manager, dep_manager):
        """Multi-step description should create parent task plus subtasks."""
        description = """Implement authentication:

1. Create user model with email and password fields
2. Add login endpoint with JWT token generation
3. Implement logout endpoint to invalidate tokens
"""
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Add authentication",
            description=description,
        )

        assert result["auto_decomposed"] is True
        assert "parent_task" in result
        assert "subtasks" in result
        assert len(result["subtasks"]) == 3

    @pytest.mark.slow
    @pytest.mark.integration
    def test_auto_decomposed_result_includes_parent_task(self, task_manager, dep_manager):
        """Result should include the parent task details."""
        description = """Steps:
- Create database schema
- Add API endpoints
- Write tests
"""
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Build feature",
            description=description,
        )

        assert result["auto_decomposed"] is True
        parent = result["parent_task"]
        assert parent["title"] == "Build feature"
        # Task IDs are now UUIDs (8-4-4-4-12 hex chars with dashes)
        assert "-" in parent["id"] and len(parent["id"].split("-")) == 5

    @pytest.mark.slow
    @pytest.mark.integration
    def test_auto_decomposed_subtasks_have_correct_parent(self, task_manager, dep_manager):
        """Subtasks should have parent_task_id set to the parent."""
        description = """1. First step
2. Second step
3. Third step"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Multi-step task",
            description=description,
        )

        parent_id = result["parent_task"]["id"]
        for subtask in result["subtasks"]:
            assert subtask["parent_task_id"] == parent_id

    @pytest.mark.slow
    @pytest.mark.integration
    def test_auto_decomposed_subtasks_have_sequential_dependencies(self, task_manager, dep_manager):
        """Subtasks should have blocking dependencies (step N blocks step N+1)."""
        description = """Implementation:
1. Create schema
2. Build API
3. Add tests"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Sequential task",
            description=description,
        )

        subtasks = result["subtasks"]
        assert len(subtasks) == 3

        # Second subtask should be blocked by first
        blockers_1 = dep_manager.get_blockers(subtasks[1]["id"])
        assert len(blockers_1) == 1
        assert blockers_1[0].depends_on == subtasks[0]["id"]

        # Third subtask should be blocked by second
        blockers_2 = dep_manager.get_blockers(subtasks[2]["id"])
        assert len(blockers_2) == 1
        assert blockers_2[0].depends_on == subtasks[1]["id"]

        # First subtask should have no blockers
        blockers_0 = dep_manager.get_blockers(subtasks[0]["id"])
        assert len(blockers_0) == 0


class TestCreateTaskAutoDecomposeOptOut:
    """Tests for auto_decompose=False behavior."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_opt_out_creates_single_task_with_needs_decomposition(self, task_manager):
        """With auto_decompose=False, multi-step creates single task with needs_decomposition status."""
        description = """1. Step one
2. Step two
3. Step three"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Decompose later",
            description=description,
            auto_decompose=False,
        )

        assert result["auto_decomposed"] is False
        task = result["task"]
        assert task["status"] == "needs_decomposition"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_needs_decomposition_task_cannot_be_claimed(self, task_manager):
        """Task with needs_decomposition status should not appear in ready tasks."""
        description = """1. One
2. Two
3. Three"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Cannot claim yet",
            description=description,
            auto_decompose=False,
        )

        task_id = result["task"]["id"]

        # Task should not be in ready tasks list
        ready_tasks = task_manager.list_ready_tasks(project_id="test-project")
        ready_ids = [t.id for t in ready_tasks]
        assert task_id not in ready_ids

    @pytest.mark.slow
    @pytest.mark.integration
    def test_opt_out_preserves_full_description(self, task_manager):
        """Opt-out should preserve the multi-step description for later decomposition."""
        description = """Feature requirements:

1. Create user interface
2. Build backend API
3. Add database schema
4. Write integration tests
"""
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Big feature",
            description=description,
            auto_decompose=False,
        )

        task = task_manager.get_task(result["task"]["id"])
        assert "1. Create user interface" in task.description
        assert "4. Write integration tests" in task.description


class TestCreateTaskSingleStep:
    """Tests for single-step descriptions (no decomposition)."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_single_step_returns_normal_task(self, task_manager):
        """Single-step description should create normal task."""
        description = "Fix the typo in the README file."

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Fix typo",
            description=description,
        )

        assert result["auto_decomposed"] is False
        task = result["task"]
        assert task["status"] == "open"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_single_step_with_auto_decompose_true(self, task_manager):
        """Single-step description ignores auto_decompose=True."""
        description = "Update version number"

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Bump version",
            description=description,
            auto_decompose=True,
        )

        assert result["auto_decomposed"] is False
        assert "task" in result
        assert "subtasks" not in result

    @pytest.mark.slow
    @pytest.mark.integration
    def test_empty_description_returns_normal_task(self, task_manager):
        """Empty description should create normal task."""
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Quick task",
            description=None,
        )

        assert result["auto_decomposed"] is False
        task = result["task"]
        assert task["title"] == "Quick task"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_false_positive_description_returns_normal_task(self, task_manager):
        """Descriptions with false positive patterns should not decompose."""
        description = """Bug: Login fails.

Steps to reproduce:
1. Open login page
2. Enter valid credentials
3. Click login
4. Observe error message

Expected: Login succeeds."""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Fix login bug",
            description=description,
        )

        # Should not decompose - "steps to reproduce" is false positive
        assert result["auto_decomposed"] is False
        assert "task" in result


class TestCreateTaskAutoDecomposeEdgeCases:
    """Edge cases for auto_decompose integration."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_inherits_parent_properties(self, task_manager):
        """Subtasks should inherit priority and labels from parent."""
        description = """1. Step A
2. Step B
3. Step C"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Prioritized task",
            description=description,
            priority=1,
            labels=["urgent", "backend"],
        )

        parent = result["parent_task"]
        assert parent["priority"] == 1
        assert "urgent" in parent["labels"]

        # Subtasks inherit priority
        for subtask in result["subtasks"]:
            full_task = task_manager.get_task(subtask["id"])
            assert full_task.priority == 1

    @pytest.mark.slow
    @pytest.mark.integration
    def test_subtasks_have_extracted_titles(self, task_manager):
        """Subtask titles should be extracted from step text."""
        description = """Tasks:
- Create user model with email field
- Add password hashing
- Implement login validation"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="User auth",
            description=description,
        )

        subtask_titles = [s["title"] for s in result["subtasks"]]
        assert "Create user model with email field" in subtask_titles
        assert "Add password hashing" in subtask_titles

    @pytest.mark.slow
    @pytest.mark.integration
    def test_parent_task_is_epic_when_has_subtasks(self, task_manager):
        """Parent task with subtasks should be type 'epic' (or remain as specified)."""
        description = """1. First
2. Second
3. Third"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Epic task",
            description=description,
            task_type="feature",
        )

        # Parent becomes epic when it has subtasks
        parent = result["parent_task"]
        assert parent["type"] in ("epic", "feature")  # Implementation may vary


# =============================================================================
# needs_decomposition Status Tests (TDD - gt-490145)
# =============================================================================


class TestNeedsDecompositionStatusValidation:
    """Tests for needs_decomposition status recognition and validation."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_needs_decomposition_is_valid_status(self, task_manager):
        """needs_decomposition should be a recognized task status."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Test task",
        )
        # Should be able to update to needs_decomposition
        updated = task_manager.update_task(task.id, status="needs_decomposition")
        assert updated.status == "needs_decomposition"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_list_tasks_includes_needs_decomposition_status(self, task_manager):
        """Tasks with needs_decomposition status should appear in list_tasks."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Multi-step task",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        # List all tasks - should include needs_decomposition
        tasks = task_manager.list_tasks(project_id="test-project")
        task_ids = [t.id for t in tasks]
        assert task.id in task_ids

    @pytest.mark.slow
    @pytest.mark.integration
    def test_list_tasks_filters_by_needs_decomposition_status(self, task_manager):
        """list_tasks should support filtering by needs_decomposition status."""
        task1 = task_manager.create_task(
            project_id="test-project",
            title="Needs decomposition",
        )
        task_manager.update_task(task1.id, status="needs_decomposition")

        task_manager.create_task(
            project_id="test-project",
            title="Normal task",
        )

        # Filter by needs_decomposition status
        tasks = task_manager.list_tasks(project_id="test-project", status="needs_decomposition")
        assert len(tasks) == 1
        assert tasks[0].id == task1.id


class TestNeedsDecompositionClaimBlocking:
    """Tests for blocking claim on needs_decomposition tasks."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_cannot_claim_needs_decomposition_task(self, task_manager):
        """Tasks with needs_decomposition status cannot be claimed (set to in_progress)."""
        description = """1. Step one
2. Step two
3. Step three"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Multi-step",
            description=description,
            auto_decompose=False,
        )
        task_id = result["task"]["id"]

        # Attempting to claim (set to in_progress) should fail
        with pytest.raises(ValueError) as exc_info:
            task_manager.update_task(task_id, status="in_progress")

        assert "decompos" in str(exc_info.value).lower()

    @pytest.mark.slow
    @pytest.mark.integration
    def test_claim_error_message_indicates_decomposition_required(self, task_manager):
        """Error message should indicate task must be decomposed first."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Big task",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        try:
            task_manager.update_task(task.id, status="in_progress")
            pytest.fail("Expected ValueError")
        except ValueError as e:
            error_msg = str(e).lower()
            assert "decompos" in error_msg or "subtask" in error_msg


class TestNeedsDecompositionStatusTransitions:
    """Tests for status transitions involving needs_decomposition."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_can_transition_to_open_after_decomposition(self, task_manager):
        """needs_decomposition task can transition to open after adding subtasks."""
        parent = task_manager.create_task(
            project_id="test-project",
            title="Parent task",
        )
        task_manager.update_task(parent.id, status="needs_decomposition")

        # Create a subtask
        task_manager.create_task(
            project_id="test-project",
            title="Subtask",
            parent_task_id=parent.id,
        )

        # Now should be able to transition to open
        updated = task_manager.update_task(parent.id, status="open")
        assert updated.status == "open"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_cannot_directly_transition_to_in_progress(self, task_manager):
        """needs_decomposition cannot transition directly to in_progress."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        with pytest.raises(ValueError):
            task_manager.update_task(task.id, status="in_progress")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_cannot_directly_transition_to_closed(self, task_manager):
        """needs_decomposition cannot transition directly to closed."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        with pytest.raises(ValueError):
            task_manager.update_task(task.id, status="closed")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_auto_transition_to_open_when_subtasks_created(self, task_manager):
        """Task should auto-transition from needs_decomposition to open when subtasks added."""
        description = """1. First step
2. Second step
3. Third step"""

        # Create with auto_decompose=False (gets needs_decomposition status)
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Parent",
            description=description,
            auto_decompose=False,
        )
        parent_id = result["task"]["id"]

        # Verify it's in needs_decomposition
        parent = task_manager.get_task(parent_id)
        assert parent.status == "needs_decomposition"

        # Now decompose it by creating subtasks
        for i in range(3):
            task_manager.create_task(
                project_id="test-project",
                title=f"Subtask {i + 1}",
                parent_task_id=parent_id,
            )

        # Parent should auto-transition to open
        parent = task_manager.get_task(parent_id)
        assert parent.status == "open"


# =============================================================================
# Workflow Variable Integration Tests (TDD - gt-5f05d8)
# =============================================================================


@pytest.fixture
def workflow_state():
    """Create a workflow state with empty variables."""
    return WorkflowState(
        session_id="test-session-123",
        workflow_name="test-workflow",
        step="execute",
        step_entered_at=datetime.now(UTC),
        variables={},
    )


@pytest.fixture
def mock_state_manager(workflow_state):
    """Create mock workflow state manager that returns our test state."""
    mock = MagicMock()
    mock.get_state.return_value = workflow_state
    return mock


class TestAutoDecomposeWorkflowVariableDefault:
    """Tests for default behavior when workflow variable not set."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_defaults_to_auto_decompose_true_when_variable_not_set(
        self, task_manager, workflow_state
    ):
        """When auto_decompose workflow variable is not set, defaults to True."""
        # Workflow state has no auto_decompose variable
        assert "auto_decompose" not in workflow_state.variables

        description = """1. First step
2. Second step
3. Third step"""

        # Create task using the workflow-aware method
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Test task",
            description=description,
            # Not passing auto_decompose - should default to True
            workflow_state=workflow_state,
        )

        # Should auto-decompose (default behavior)
        assert result["auto_decomposed"] is True
        assert "parent_task" in result
        assert "subtasks" in result

    @pytest.mark.slow
    @pytest.mark.integration
    def test_defaults_to_true_when_workflow_state_is_none(self, task_manager):
        """When no workflow state provided, defaults to auto_decompose=True."""
        description = """1. First step
2. Second step
3. Third step"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Test task",
            description=description,
            workflow_state=None,
        )

        # Should auto-decompose (default behavior)
        assert result["auto_decomposed"] is True


class TestAutoDecomposeWorkflowVariableOverride:
    """Tests for session-level override via workflow variable."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_session_variable_false_disables_auto_decomposition(self, task_manager, workflow_state):
        """Setting auto_decompose=False in workflow disables decomposition."""
        # Set workflow variable to False
        workflow_state.variables["auto_decompose"] = False

        description = """1. First step
2. Second step
3. Third step"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Test task",
            description=description,
            workflow_state=workflow_state,
        )

        # Should NOT auto-decompose due to session variable
        assert result["auto_decomposed"] is False
        assert "task" in result
        assert result["task"]["status"] == "needs_decomposition"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_session_variable_true_enables_auto_decomposition(self, task_manager, workflow_state):
        """Setting auto_decompose=True in workflow explicitly enables decomposition."""
        # Set workflow variable to True explicitly
        workflow_state.variables["auto_decompose"] = True

        description = """1. First step
2. Second step
3. Third step"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Test task",
            description=description,
            workflow_state=workflow_state,
        )

        # Should auto-decompose
        assert result["auto_decomposed"] is True
        assert "parent_task" in result

    @pytest.mark.slow
    @pytest.mark.integration
    def test_call_parameter_overrides_session_variable(self, task_manager, workflow_state):
        """Individual call parameter overrides session-level setting."""
        # Session says don't auto-decompose
        workflow_state.variables["auto_decompose"] = False

        description = """1. First step
2. Second step
3. Third step"""

        # But explicit call says do it
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Test task",
            description=description,
            auto_decompose=True,  # Explicit override
            workflow_state=workflow_state,
        )

        # Call parameter wins
        assert result["auto_decomposed"] is True
        assert "parent_task" in result

    @pytest.mark.slow
    @pytest.mark.integration
    def test_explicit_false_overrides_session_true(self, task_manager, workflow_state):
        """Explicit auto_decompose=False overrides session True."""
        # Session says auto-decompose
        workflow_state.variables["auto_decompose"] = True

        description = """1. First step
2. Second step
3. Third step"""

        # But explicit call says don't
        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Test task",
            description=description,
            auto_decompose=False,  # Explicit override
            workflow_state=workflow_state,
        )

        # Call parameter wins
        assert result["auto_decomposed"] is False
        assert "task" in result


class TestAutoDecomposeWorkflowVariablePersistence:
    """Tests for workflow variable persistence across calls."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_session_variable_affects_multiple_calls(self, task_manager, workflow_state):
        """Workflow variable persists and affects subsequent calls."""
        # Set workflow variable once
        workflow_state.variables["auto_decompose"] = False

        description = """1. First step
2. Second step
3. Third step"""

        # First call
        result1 = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Task 1",
            description=description,
            workflow_state=workflow_state,
        )
        assert result1["auto_decomposed"] is False

        # Second call (same workflow state)
        result2 = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Task 2",
            description=description,
            workflow_state=workflow_state,
        )
        assert result2["auto_decomposed"] is False

        # Third call - now change the variable
        workflow_state.variables["auto_decompose"] = True
        result3 = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Task 3",
            description=description,
            workflow_state=workflow_state,
        )
        assert result3["auto_decomposed"] is True

    @pytest.mark.slow
    @pytest.mark.integration
    def test_different_sessions_have_independent_variables(self, task_manager):
        """Different sessions have independent auto_decompose settings."""
        state1 = WorkflowState(
            session_id="session-1",
            workflow_name="test-workflow",
            step="execute",
            step_entered_at=datetime.now(UTC),
            variables={"auto_decompose": False},
        )
        state2 = WorkflowState(
            session_id="session-2",
            workflow_name="test-workflow",
            step="execute",
            step_entered_at=datetime.now(UTC),
            variables={"auto_decompose": True},
        )

        description = """1. First step
2. Second step
3. Third step"""

        # Session 1 - should NOT decompose
        result1 = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Session 1 task",
            description=description,
            workflow_state=state1,
        )
        assert result1["auto_decomposed"] is False

        # Session 2 - should decompose
        result2 = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Session 2 task",
            description=description,
            workflow_state=state2,
        )
        assert result2["auto_decomposed"] is True


# =============================================================================
# update_task Step Detection Tests (TDD - gt-ecaa19)
# =============================================================================


class TestUpdateTaskStepDetection:
    """Tests for detecting multi-step content when updating task descriptions."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_detects_multi_step_content(self, task_manager):
        """Updating description with multi-step content should be detected."""
        # Create a simple single-step task
        task = task_manager.create_task(
            project_id="test-project",
            title="Simple task",
            description="Just a single thing to do.",
        )

        # Update with multi-step content
        multi_step_description = """1. First step
2. Second step
3. Third step"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
        )

        # Should detect the steps
        assert result["steps_detected"] is True
        assert result["step_count"] >= 3

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_auto_decomposes_when_enabled(self, task_manager):
        """When auto_decompose=True, updating with steps creates subtasks."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task to decompose",
        )

        multi_step_description = """1. Create model
2. Add API
3. Build UI"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
            auto_decompose=True,
        )

        assert result["auto_decomposed"] is True
        assert "subtasks" in result
        assert len(result["subtasks"]) == 3

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_sets_needs_decomposition_when_disabled(self, task_manager):
        """When auto_decompose=False, updating with steps sets needs_decomposition."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task needing manual decomposition",
        )

        multi_step_description = """1. Step one
2. Step two
3. Step three"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
            auto_decompose=False,
        )

        assert result["auto_decomposed"] is False
        assert result["steps_detected"] is True
        # Task should be in needs_decomposition status
        updated_task = task_manager.get_task(task.id)
        assert updated_task.status == "needs_decomposition"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_single_step_task_flagged_when_steps_added(self, task_manager):
        """Original single-step task updated with steps gets flagged."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Originally simple task",
            description="Do the thing.",
        )
        assert task.status == "open"  # Single-step task starts as open

        multi_step_description = """Updated with implementation plan:
1. Research options
2. Implement solution
3. Test thoroughly"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
            auto_decompose=False,
        )

        assert result["steps_detected"] is True
        updated_task = task_manager.get_task(task.id)
        assert updated_task.status == "needs_decomposition"


class TestUpdateTaskNoFalsePositives:
    """Tests for avoiding false positives in step detection on update."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_with_context_notes_no_detection(self, task_manager):
        """Adding context/notes shouldn't trigger step detection."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task with context",
        )

        # Add context that might look like steps but isn't
        context_description = """This task is about fixing the login bug.

Context:
- User reported the issue last week
- It affects Chrome users
- The error appears in the console

Notes: Consider checking the session handler."""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=context_description,
        )

        # Should NOT detect as multi-step
        assert result["steps_detected"] is False
        assert result.get("auto_decomposed") is False

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_with_reproduction_steps_no_detection(self, task_manager):
        """'Steps to reproduce' in bug descriptions shouldn't trigger decomposition."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Bug fix task",
        )

        bug_description = """Login fails intermittently.

Steps to reproduce:
1. Open login page
2. Enter credentials
3. Click submit
4. Observe error

Expected: Login succeeds"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=bug_description,
        )

        # Should NOT detect as multi-step (false positive pattern)
        assert result["steps_detected"] is False

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_with_plain_text_no_detection(self, task_manager):
        """Plain text description shouldn't trigger step detection."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Documentation task",
        )

        plain_description = """Update the README to include installation instructions
and add a section about contributing to the project. The documentation
should be clear and helpful for new users."""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=plain_description,
        )

        assert result["steps_detected"] is False


class TestUpdateTaskStepDetectionBehaviors:
    """Tests for different behavior options on step detection."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_preserves_task_id_after_decomposition(self, task_manager):
        """Parent task should keep same ID after auto-decomposition."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task to update",
        )
        original_id = task.id

        multi_step_description = """1. First
2. Second
3. Third"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
            auto_decompose=True,
        )

        assert result["task"]["id"] == original_id

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_subtasks_have_parent_reference(self, task_manager):
        """Auto-created subtasks should reference the updated task as parent."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Parent task",
        )

        multi_step_description = """1. Step A
2. Step B
3. Step C"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
            auto_decompose=True,
        )

        for subtask in result["subtasks"]:
            full_subtask = task_manager.get_task(subtask["id"])
            assert full_subtask.parent_task_id == task.id

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_respects_workflow_variable(self, task_manager, workflow_state):
        """Update should respect auto_decompose workflow variable."""
        workflow_state.variables["auto_decompose"] = False

        task = task_manager.create_task(
            project_id="test-project",
            title="Task with workflow context",
        )

        multi_step_description = """1. One
2. Two
3. Three"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
            workflow_state=workflow_state,
            # Not explicitly setting auto_decompose - should use workflow variable
        )

        # Should respect workflow variable (False = no auto-decompose)
        assert result["auto_decomposed"] is False
        assert result["steps_detected"] is True
        updated_task = task_manager.get_task(task.id)
        assert updated_task.status == "needs_decomposition"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_update_explicit_param_overrides_workflow(self, task_manager, workflow_state):
        """Explicit auto_decompose parameter should override workflow variable."""
        workflow_state.variables["auto_decompose"] = False

        task = task_manager.create_task(
            project_id="test-project",
            title="Task with explicit override",
        )

        multi_step_description = """1. Alpha
2. Beta
3. Gamma"""

        result = task_manager.update_task_with_step_detection(
            task.id,
            description=multi_step_description,
            auto_decompose=True,  # Explicit override
            workflow_state=workflow_state,
        )

        # Explicit param wins over workflow variable
        assert result["auto_decomposed"] is True
        assert "subtasks" in result


# =============================================================================
# Validation Criteria Interaction Tests (TDD - gt-2725da)
# =============================================================================


class TestValidationCriteriaUndecomposedTasks:
    """Tests for validation criteria blocking on undecomposed tasks."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_cannot_set_validation_criteria_on_needs_decomposition_task(self, task_manager):
        """Tasks with needs_decomposition status cannot have validation criteria set."""
        # Create task with needs_decomposition status
        task = task_manager.create_task(
            project_id="test-project",
            title="Multi-step task",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        # Attempting to set validation criteria should fail
        with pytest.raises(ValueError) as exc_info:
            task_manager.update_task(
                task.id,
                validation_criteria="## Acceptance\n- [ ] All done",
            )

        error_msg = str(exc_info.value).lower()
        assert "decompos" in error_msg or "subtask" in error_msg

    @pytest.mark.slow
    @pytest.mark.integration
    def test_error_message_guides_to_decompose_first(self, task_manager):
        """Error message should guide user to decompose the task first."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task needing decomposition",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        try:
            task_manager.update_task(
                task.id,
                validation_criteria="## Criteria\n- Test",
            )
            pytest.fail("Expected ValueError")
        except ValueError as e:
            error_msg = str(e).lower()
            # Should mention need to decompose
            assert "decompos" in error_msg or "subtask" in error_msg

    @pytest.mark.slow
    @pytest.mark.integration
    def test_can_set_validation_criteria_after_decomposition(self, task_manager):
        """Validation criteria can be set after task is decomposed."""
        # Create task with needs_decomposition status
        task = task_manager.create_task(
            project_id="test-project",
            title="Task to decompose",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        # Add subtasks (decompose)
        task_manager.create_task(
            project_id="test-project",
            title="Subtask 1",
            parent_task_id=task.id,
        )

        # Now should be able to set validation criteria
        updated = task_manager.update_task(
            task.id,
            validation_criteria="## Acceptance\n- [ ] All subtasks complete",
        )
        assert updated.validation_criteria is not None
        assert "All subtasks complete" in updated.validation_criteria


class TestValidationCriteriaDecomposedTasks:
    """Tests for validation criteria on decomposed tasks."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_parent_task_can_have_high_level_criteria(self, task_manager):
        """Parent task can have high-level validation criteria."""
        description = """1. First step
2. Second step
3. Third step"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Parent with criteria",
            description=description,
            auto_decompose=True,
        )

        parent_id = result["parent_task"]["id"]

        # Set high-level criteria on parent
        updated = task_manager.update_task(
            parent_id,
            validation_criteria="## High-Level Acceptance\n- [ ] Feature works end-to-end",
        )

        assert updated.validation_criteria is not None
        assert "High-Level" in updated.validation_criteria

    @pytest.mark.slow
    @pytest.mark.integration
    def test_subtasks_can_each_have_specific_criteria(self, task_manager):
        """Each subtask can have its own specific validation criteria."""
        description = """1. Create model
2. Add API
3. Build UI"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Task with subtasks",
            description=description,
            auto_decompose=True,
        )

        # Set specific criteria on each subtask
        for i, subtask in enumerate(result["subtasks"]):
            updated = task_manager.update_task(
                subtask["id"],
                validation_criteria=f"## Subtask {i + 1} Criteria\n- [ ] Step {i + 1} complete",
            )
            assert updated.validation_criteria is not None
            assert f"Subtask {i + 1}" in updated.validation_criteria


class TestValidationCriteriaOnComplete:
    """Tests for validation criteria behavior on task completion."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_needs_decomposition_cannot_be_marked_complete(self, task_manager):
        """Tasks with needs_decomposition status cannot be marked complete."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Incomplete decomposition",
        )
        task_manager.update_task(task.id, status="needs_decomposition")

        # Should not be able to close (already tested, but verify here too)
        with pytest.raises(ValueError):
            task_manager.update_task(task.id, status="closed")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_decomposed_task_can_be_completed_after_subtasks_done(self, task_manager):
        """Decomposed tasks can be completed after all subtasks are done."""
        description = """1. Step A
2. Step B
3. Step C"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Task to complete",
            description=description,
            auto_decompose=True,
        )

        parent_id = result["parent_task"]["id"]

        # Complete all subtasks
        for subtask in result["subtasks"]:
            task_manager.update_task(subtask["id"], status="in_progress")
            task_manager.update_task(subtask["id"], status="closed")

        # Parent should now be closable
        closed = task_manager.update_task(parent_id, status="closed")
        assert closed.status == "closed"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_validation_criteria_preserved_on_completion(self, task_manager):
        """Validation criteria should be preserved when task is completed."""
        task = task_manager.create_task(
            project_id="test-project",
            title="Task with criteria",
            validation_criteria="## Criteria\n- [ ] Everything works",
        )

        # Complete the task
        task_manager.update_task(task.id, status="in_progress")
        closed = task_manager.update_task(task.id, status="closed")

        # Criteria should still be there
        assert closed.validation_criteria is not None
        assert "Everything works" in closed.validation_criteria


# =============================================================================
# Integration Tests: Full Auto-Decompose Workflows
# =============================================================================


class TestAutoDecomposeHappyPathWorkflow:
    """Integration tests for the happy path: auto-decomposition enabled."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_full_workflow_create_decompose_complete(self, task_manager, dep_manager):
        """Full workflow: create with multi-step -> subtasks created -> complete all."""
        description = """Implement user authentication:
1. Create user model with email/password
2. Add login API endpoint
3. Implement JWT token generation"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Implement auth",
            description=description,
            auto_decompose=True,
        )

        # Verify decomposition occurred
        assert result["auto_decomposed"] is True
        assert result["parent_task"]["status"] == "open"
        assert len(result["subtasks"]) == 3

        parent_id = result["parent_task"]["id"]

        # Complete subtasks in sequence
        for i, subtask in enumerate(result["subtasks"]):
            task_manager.update_task(subtask["id"], status="in_progress")
            task_manager.update_task(subtask["id"], status="closed")

            # Check parent is still open until all done
            parent = task_manager.get_task(parent_id)
            if i < len(result["subtasks"]) - 1:
                assert parent.status == "open"

        # Parent can now be closed
        task_manager.update_task(parent_id, status="in_progress")
        closed_parent = task_manager.update_task(parent_id, status="closed")
        assert closed_parent.status == "closed"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_subtasks_have_sequential_dependencies(self, task_manager, dep_manager):
        """Subtasks should have dependencies on previous steps."""
        description = """Setup pipeline:
1. Install dependencies
2. Configure database
3. Run migrations"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Setup",
            description=description,
            auto_decompose=True,
        )

        subtasks = result["subtasks"]
        assert len(subtasks) == 3

        # First subtask has no blockers
        blockers_0 = dep_manager.get_blockers(subtasks[0]["id"])
        assert len(blockers_0) == 0

        # Second subtask blocked by first
        blockers_1 = dep_manager.get_blockers(subtasks[1]["id"])
        assert len(blockers_1) == 1
        assert blockers_1[0].depends_on == subtasks[0]["id"]

        # Third subtask blocked by second
        blockers_2 = dep_manager.get_blockers(subtasks[2]["id"])
        assert len(blockers_2) == 1
        assert blockers_2[0].depends_on == subtasks[1]["id"]


class TestAutoDecomposeOptOutPathWorkflow:
    """Integration tests for opt-out path: auto_decompose=False."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_opt_out_then_manual_decomposition(self, task_manager):
        """Opt-out creates needs_decomposition, manual subtasks transitions to open."""
        description = """Refactor module:
1. Extract interface
2. Create implementations
3. Update consumers"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Refactor",
            description=description,
            auto_decompose=False,
        )

        # Task has needs_decomposition status (not decomposed)
        assert result["auto_decomposed"] is False
        assert result["task"]["status"] == "needs_decomposition"

        parent_id = result["task"]["id"]

        # Manually add subtasks
        sub1 = task_manager.create_task(
            project_id="test-project",
            title="Extract interface",
            parent_task_id=parent_id,
        )
        sub2 = task_manager.create_task(
            project_id="test-project",
            title="Create implementations",
            parent_task_id=parent_id,
        )

        # Parent transitions to open
        parent = task_manager.get_task(parent_id)
        assert parent.status == "open"

        # Complete subtasks and parent
        task_manager.update_task(sub1.id, status="in_progress")
        task_manager.update_task(sub1.id, status="closed")
        task_manager.update_task(sub2.id, status="in_progress")
        task_manager.update_task(sub2.id, status="closed")

        task_manager.update_task(parent_id, status="in_progress")
        closed = task_manager.update_task(parent_id, status="closed")
        assert closed.status == "closed"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_needs_decomposition_blocks_in_progress(self, task_manager):
        """Tasks with needs_decomposition cannot be set to in_progress."""
        description = """Build feature:
1. Design API
2. Implement backend
3. Add frontend"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Feature",
            description=description,
            auto_decompose=False,
        )

        task_id = result["task"]["id"]

        # Cannot claim without decomposing
        with pytest.raises(ValueError) as exc_info:
            task_manager.update_task(task_id, status="in_progress")

        assert "needs_decomposition" in str(exc_info.value).lower()


class TestAutoDecomposeMixedContentWorkflow:
    """Integration tests for descriptions with steps and other content."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_steps_extracted_with_surrounding_context(self, task_manager):
        """Steps become subtasks, parent retains full description."""
        # Note: extract_steps extracts both numbered and bullet items
        description = """Implement logging system for the application.

1. Add logging library to dependencies
2. Create logger wrapper class
3. Instrument key functions with logging

This will improve debugging and monitoring."""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Add logging",
            description=description,
            auto_decompose=True,
        )

        # Steps become subtasks
        assert result["auto_decomposed"] is True
        assert len(result["subtasks"]) == 3
        assert result["subtasks"][0]["title"] == "Add logging library to dependencies"

        # Parent retains the full original description
        parent = task_manager.get_task(result["parent_task"]["id"])
        assert "Implement logging system" in parent.description
        assert "improve debugging" in parent.description

    @pytest.mark.slow
    @pytest.mark.integration
    def test_reproduction_steps_not_extracted(self, task_manager):
        """Bug reproduction steps should not become subtasks."""
        description = """Button not working

## Steps to Reproduce
1. Click login button
2. Enter credentials
3. Click submit

## Expected
Login succeeds

## Actual
Nothing happens"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Fix login button",
            description=description,
            auto_decompose=True,
        )

        # Reproduction steps are not implementation steps (single task returned)
        assert result["auto_decomposed"] is False
        assert "task" in result  # Not decomposed returns "task" key


class TestAutoDecomposeWorkflowWithVariables:
    """Integration tests for workflow variable control."""

    @pytest.fixture
    def workflow_state_disabled(self):
        """Workflow state with auto_decompose disabled."""
        return WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="execute",
            step_entered_at=datetime.now(UTC),
            variables={"auto_decompose": False},
        )

    @pytest.fixture
    def workflow_state_enabled(self):
        """Workflow state with auto_decompose enabled."""
        return WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="execute",
            step_entered_at=datetime.now(UTC),
            variables={"auto_decompose": True},
        )

    @pytest.mark.slow
    @pytest.mark.integration
    def test_workflow_variable_controls_decomposition(self, task_manager, workflow_state_disabled):
        """Workflow variable can disable auto-decomposition for session."""
        description = """Setup:
1. Install deps
2. Configure
3. Test"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Setup",
            description=description,
            workflow_state=workflow_state_disabled,
        )

        # Variable disabled decomposition
        assert result["auto_decomposed"] is False
        assert result["task"]["status"] == "needs_decomposition"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_explicit_param_overrides_workflow_variable(
        self, task_manager, workflow_state_disabled
    ):
        """Explicit parameter takes precedence over workflow variable."""
        description = """Build:
1. Compile
2. Link
3. Package"""

        result = task_manager.create_task_with_decomposition(
            project_id="test-project",
            title="Build",
            description=description,
            auto_decompose=True,  # Explicit True overrides variable False
            workflow_state=workflow_state_disabled,
        )

        # Explicit param won
        assert result["auto_decomposed"] is True
        assert len(result["subtasks"]) == 3
