"""E2E tests verifying TDD triplet ordering across all creation paths."""

import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager
from gobby.tasks.spec_parser import (
    CheckboxItem,
    HeadingNode,
    TaskHierarchyBuilder,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = LocalDatabase(str(db_path))

    # Create tasks table
    db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 2,
            task_type TEXT DEFAULT 'task',
            parent_task_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            test_strategy TEXT,
            complexity_score INTEGER,
            estimated_subtasks INTEGER,
            expansion_context TEXT,
            validation_criteria TEXT,
            validation_status TEXT DEFAULT 'pending',
            validation_feedback TEXT,
            use_external_validator INTEGER DEFAULT 0,
            validation_fail_count INTEGER DEFAULT 0,
            validation_override_reason TEXT,
            created_in_session_id TEXT,
            closed_in_session_id TEXT,
            closed_commit_sha TEXT,
            closed_at TEXT,
            closed_reason TEXT,
            assignee TEXT,
            labels TEXT DEFAULT '[]',
            workflow_name TEXT,
            verification TEXT,
            sequence_order INTEGER,
            commits TEXT,
            escalated_at TEXT,
            escalation_reason TEXT,
            github_issue_number INTEGER,
            github_pr_number INTEGER,
            github_repo TEXT,
            linear_issue_id TEXT,
            linear_team_id TEXT,
            seq_num INTEGER,
            path_cache TEXT
        )
    """)

    # Create task_dependencies table
    db.execute("""
        CREATE TABLE IF NOT EXISTS task_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            depends_on TEXT NOT NULL,
            dep_type TEXT DEFAULT 'blocks',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            FOREIGN KEY (depends_on) REFERENCES tasks(id),
            UNIQUE(task_id, depends_on, dep_type)
        )
    """)

    # Create seq_num counter table
    db.execute("""
        CREATE TABLE IF NOT EXISTS task_seq_counters (
            project_id TEXT PRIMARY KEY,
            next_seq_num INTEGER DEFAULT 1
        )
    """)

    return db


@pytest.fixture
def task_manager(temp_db):
    """Create a task manager with the temp database."""
    return LocalTaskManager(temp_db)


@pytest.fixture
def dep_manager(temp_db):
    """Create a dependency manager with the temp database."""
    return TaskDependencyManager(temp_db)


class TestTDDTripletStructure:
    """Test that TDD triplets are created with correct structure."""

    def test_spec_parser_creates_triplet_as_siblings(self, task_manager, dep_manager):
        """spec_parser._create_tdd_triplet creates 3 sibling tasks."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        tasks = builder._create_tdd_triplet(
            title="Add user login",
            parent_task_id=None,
            description="Login functionality",
        )

        # Should create 3 tasks
        assert len(tasks) == 3

        # All should be siblings (same parent - None in this case)
        assert tasks[0].parent_task_id is None
        assert tasks[1].parent_task_id is None
        assert tasks[2].parent_task_id is None

        # Verify titles
        assert tasks[0].title == "Write tests for: Add user login"
        assert tasks[1].title == "Implement: Add user login"
        assert tasks[2].title == "Refactor: Add user login"

    def test_spec_parser_creates_triplet_with_parent(self, task_manager, dep_manager):
        """spec_parser._create_tdd_triplet creates siblings under specified parent."""
        # Create a parent task first
        parent = task_manager.create_task(
            title="Epic: Authentication",
            project_id="test-project",
            task_type="epic",
        )

        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        tasks = builder._create_tdd_triplet(
            title="Add user login",
            parent_task_id=parent.id,
            description="Login functionality",
        )

        # All should be siblings under the parent
        assert tasks[0].parent_task_id == parent.id
        assert tasks[1].parent_task_id == parent.id
        assert tasks[2].parent_task_id == parent.id

    def test_spec_parser_wires_correct_dependencies(self, task_manager, dep_manager):
        """spec_parser._create_tdd_triplet wires dependencies correctly."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        tasks = builder._create_tdd_triplet(
            title="Add user login",
            parent_task_id=None,
            description="Login functionality",
        )

        red, green, blue = tasks

        # Green should be blocked by red
        green_deps = dep_manager.get_all_dependencies(green.id)
        assert len(green_deps) == 1
        assert green_deps[0].depends_on == red.id
        assert green_deps[0].dep_type == "blocks"

        # Blue should be blocked by green
        blue_deps = dep_manager.get_all_dependencies(blue.id)
        assert len(blue_deps) == 1
        assert blue_deps[0].depends_on == green.id
        assert blue_deps[0].dep_type == "blocks"

        # Red should have no blocking dependencies
        red_deps = dep_manager.get_all_dependencies(red.id)
        assert len(red_deps) == 0


class TestTDDReadyTaskOrdering:
    """Test that suggest_next_task returns TDD tasks in correct order."""

    def test_ready_tasks_returns_red_first(self, task_manager, dep_manager):
        """When all TDD tasks are open, only red should be ready."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        tasks = builder._create_tdd_triplet(
            title="Add user login",
            parent_task_id=None,
            description="Login functionality",
        )

        red, green, blue = tasks

        # Get ready tasks
        ready = task_manager.list_ready_tasks(project_id="test-project")

        # Only red should be ready (green and blue are blocked)
        ready_ids = [t.id for t in ready]
        assert red.id in ready_ids
        assert green.id not in ready_ids
        assert blue.id not in ready_ids

    def test_ready_tasks_returns_green_after_red_closed(self, task_manager, dep_manager):
        """After closing red, green should be ready."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        tasks = builder._create_tdd_triplet(
            title="Add user login",
            parent_task_id=None,
            description="Login functionality",
        )

        red, green, blue = tasks

        # Close red
        task_manager.update_task(red.id, status="closed")

        # Get ready tasks
        ready = task_manager.list_ready_tasks(project_id="test-project")

        # Green should now be ready, blue still blocked
        ready_ids = [t.id for t in ready]
        assert green.id in ready_ids
        assert blue.id not in ready_ids

    def test_ready_tasks_returns_blue_after_green_closed(self, task_manager, dep_manager):
        """After closing red and green, blue should be ready."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        tasks = builder._create_tdd_triplet(
            title="Add user login",
            parent_task_id=None,
            description="Login functionality",
        )

        red, green, blue = tasks

        # Close red and green
        task_manager.update_task(red.id, status="closed")
        task_manager.update_task(green.id, status="closed")

        # Get ready tasks
        ready = task_manager.list_ready_tasks(project_id="test-project")

        # Blue should now be ready
        ready_ids = [t.id for t in ready]
        assert blue.id in ready_ids


class TestTDDCheckboxProcessing:
    """Test TDD triplets created from checkboxes."""

    def test_checkbox_creates_triplet(self, task_manager, dep_manager):
        """Processing a checkbox in TDD mode creates a triplet."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        checkbox = CheckboxItem(
            text="Add validation",
            checked=False,
            line_number=1,
            indent_level=0,
            raw_line="- [ ] Add validation",
        )

        created_tasks = []
        builder._process_checkbox(
            checkbox=checkbox,
            parent_task_id=None,
            created_tasks=created_tasks,
        )

        # Should create 3 tasks
        assert len(created_tasks) == 3
        assert created_tasks[0].title == "Write tests for: Add validation"
        assert created_tasks[1].title == "Implement: Add validation"
        assert created_tasks[2].title == "Refactor: Add validation"


class TestTDDHeadingProcessing:
    """Test TDD triplets created from headings."""

    def test_h4_heading_creates_triplet(self, task_manager, dep_manager):
        """Processing an H4 heading in TDD mode creates a triplet."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        heading = HeadingNode(
            text="Add middleware",
            level=4,
            line_start=1,
            line_end=5,
            content="Auth middleware",
        )

        created_tasks = []
        builder._process_heading(
            heading=heading,
            parent_task_id=None,
            checkbox_lookup={},
            created_tasks=created_tasks,
        )

        # Should create 3 tasks
        assert len(created_tasks) == 3
        assert created_tasks[0].title == "Write tests for: Add middleware"
        assert created_tasks[1].title == "Implement: Add middleware"
        assert created_tasks[2].title == "Refactor: Add middleware"

    def test_epic_heading_no_triplet(self, task_manager, dep_manager):
        """H2/H3 headings (epics) don't create triplets."""
        builder = TaskHierarchyBuilder(
            task_manager=task_manager,
            project_id="test-project",
            tdd_mode=True,
        )

        heading = HeadingNode(
            text="Phase 1",
            level=2,
            line_start=1,
            line_end=10,
            content="Phase overview",
        )

        created_tasks = []
        builder._process_heading(
            heading=heading,
            parent_task_id=None,
            checkbox_lookup={},
            created_tasks=created_tasks,
        )

        # Should create 1 epic, not a triplet
        assert len(created_tasks) == 1
        assert created_tasks[0].title == "Phase 1"
