"""Comprehensive tests for WorkflowLoader."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from gobby.workflows.definitions import WorkflowDefinition
from gobby.workflows.loader import DiscoveredWorkflow, WorkflowLoader

pytestmark = pytest.mark.unit


@pytest.fixture
def loader():
    """Create a WorkflowLoader with a temporary workflow directory."""
    return WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary directory structure for workflows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        yield base


class TestWorkflowLoader:
    """Tests for WorkflowLoader basic functionality."""

    def test_init_default_dirs(self) -> None:
        """Test default workflow directory initialization."""
        loader = WorkflowLoader()
        assert len(loader.global_dirs) == 1
        assert loader.global_dirs[0] == Path.home() / ".gobby" / "workflows"

    def test_init_custom_dirs(self) -> None:
        """Test custom workflow directories initialization."""
        custom_dirs = [Path("/custom/path1"), Path("/custom/path2")]
        loader = WorkflowLoader(workflow_dirs=custom_dirs)
        assert loader.global_dirs == custom_dirs

    def test_load_workflow_not_found(self, loader) -> None:
        """Test loading a workflow that doesn't exist."""
        with patch(
            "gobby.workflows.loader.WorkflowLoader._find_workflow_file",
            return_value=None,
        ):
            assert loader.load_workflow("non_existent") is None

    def test_load_workflow_valid_yaml(self, loader) -> None:
        """Test loading a valid workflow YAML."""
        yaml_content = """
        name: test_workflow
        version: "1.0.0"
        steps:
          - name: step1
            allowed_tools: all
        """
        with patch(
            "gobby.workflows.loader.WorkflowLoader._find_workflow_file",
            return_value=Path("/tmp/workflows/test_workflow.yaml"),
        ):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                wf = loader.load_workflow("test_workflow")
                assert wf is not None
                assert wf.name == "test_workflow"
                assert len(wf.steps) == 1
                assert wf.steps[0].name == "step1"

    def test_load_workflow_invalid_yaml(self, loader) -> None:
        """Test loading invalid YAML returns None."""
        yaml_content = "invalid: : yaml"
        with patch(
            "gobby.workflows.loader.WorkflowLoader._find_workflow_file",
            return_value=Path("/tmp/workflows/invalid.yaml"),
        ):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                wf = loader.load_workflow("invalid")
                assert wf is None

    def test_load_workflow_exception_handling(self, loader) -> None:
        """Test that non-ValueError exceptions during loading return None."""
        yaml_content = """
        name: test_workflow
        version: "1.0.0"
        steps:
          - name: step1
            allowed_tools: all
        """
        with patch(
            "gobby.workflows.loader.WorkflowLoader._find_workflow_file",
            return_value=Path("/tmp/workflows/test.yaml"),
        ):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                # Mock WorkflowDefinition to raise a generic exception
                with patch(
                    "gobby.workflows.loader.WorkflowDefinition",
                    side_effect=RuntimeError("Generic error"),
                ):
                    result = loader.load_workflow("test")
                    assert result is None

    def test_load_workflow_with_project_path(self, loader) -> None:
        """Test that project path is prepended to search directories."""
        with patch("gobby.workflows.loader.WorkflowLoader._find_workflow_file") as mock_find:
            mock_find.return_value = None
            loader.load_workflow("test", project_path="/my/project")

            args, _ = mock_find.call_args
            search_dirs = args[1]
            assert Path("/my/project/.gobby/workflows") in search_dirs
            assert search_dirs[0] == Path("/my/project/.gobby/workflows")

    def test_load_workflow_caching(self, loader) -> None:
        """Test that loaded workflows are cached."""
        yaml_content = """
        name: cached_workflow
        version: "1.0.0"
        steps:
          - name: step1
            allowed_tools: all
        """
        with patch(
            "gobby.workflows.loader.WorkflowLoader._find_workflow_file",
            return_value=Path("/tmp/workflows/cached_workflow.yaml"),
        ):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                # First load
                wf1 = loader.load_workflow("cached_workflow")
                assert wf1 is not None

        # Second load should return cached version (no file access)
        wf2 = loader.load_workflow("cached_workflow")
        assert wf2 is wf1

    def test_load_workflow_cache_key_includes_project(self, loader) -> None:
        """Test that cache keys include project path for proper isolation."""
        yaml_content = """
        name: project_workflow
        version: "1.0.0"
        steps:
          - name: step1
            allowed_tools: all
        """

        def mock_find(name, search_dirs):
            return Path("/tmp/workflows/project_workflow.yaml")

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                # Load without project path (caches under "global:" key)
                loader.load_workflow("project_workflow")

        # Different project should get separate cache entry
        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                # Load with project path (caches under project-specific key)
                loader.load_workflow("project_workflow", project_path="/project/a")

        # Verify both are cached separately
        assert "global:project_workflow" in loader._cache
        assert "/project/a:project_workflow" in loader._cache
        assert loader._cache["global:project_workflow"].definition.name == "project_workflow"
        assert loader._cache["/project/a:project_workflow"].definition.name == "project_workflow"

    def test_clear_cache_forces_reload(self, loader) -> None:
        """Test that clearing cache forces reload from disk."""
        yaml_content_v1 = """
        name: dynamic_workflow
        version: "1.0.0"
        """
        yaml_content_v2 = """
        name: dynamic_workflow
        version: "2.0"
        """

        mock_path = Path("/tmp/workflows/dynamic_workflow.yaml")

        with patch.object(loader, "_find_workflow_file", return_value=mock_path):
            # First load
            with patch("builtins.open", mock_open(read_data=yaml_content_v1)):
                wf1 = loader.load_workflow("dynamic_workflow")
                assert wf1.version == "1.0.0"

            # Cache hit check
            with patch("builtins.open", mock_open(read_data="should not be read")):
                wf_cached = loader.load_workflow("dynamic_workflow")
                assert wf_cached.version == "1.0.0"

            # Clear cache
            loader.clear_cache()

            # Second load (should read v2)
            with patch("builtins.open", mock_open(read_data=yaml_content_v2)):
                wf2 = loader.load_workflow("dynamic_workflow")
                assert wf2.version == "2.0"


class TestFindWorkflowFile:
    """Tests for _find_workflow_file method."""

    def test_find_in_root_directory(self, temp_workflow_dir) -> None:
        """Test finding workflow file in root directory."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        workflow_file = workflow_dir / "test.yaml"
        workflow_file.write_text("name: test")

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        result = loader._find_workflow_file("test", [workflow_dir])

        assert result == workflow_file

    def test_find_in_subdirectory(self, temp_workflow_dir) -> None:
        """Test finding workflow file in subdirectory like lifecycle/."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        lifecycle_dir = workflow_dir / "lifecycle"
        lifecycle_dir.mkdir()
        workflow_file = lifecycle_dir / "session_start.yaml"
        workflow_file.write_text("name: session_start")

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        result = loader._find_workflow_file("session_start", [workflow_dir])

        assert result == workflow_file

    def test_find_not_found(self, temp_workflow_dir) -> None:
        """Test that None is returned when workflow file doesn't exist."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        result = loader._find_workflow_file("nonexistent", [workflow_dir])

        assert result is None

    def test_find_priority_order(self, temp_workflow_dir) -> None:
        """Test that first matching directory takes priority."""
        dir1 = temp_workflow_dir / "dir1"
        dir1.mkdir()
        dir2 = temp_workflow_dir / "dir2"
        dir2.mkdir()

        # Create workflow in both directories
        (dir1 / "test.yaml").write_text("name: from_dir1")
        (dir2 / "test.yaml").write_text("name: from_dir2")

        loader = WorkflowLoader()
        result = loader._find_workflow_file("test", [dir1, dir2])

        # Should find in dir1 first
        assert result == dir1 / "test.yaml"

    def test_find_with_nonexistent_directory(self, temp_workflow_dir) -> None:
        """Test handling of non-existent directories in search list."""
        existing_dir = temp_workflow_dir / "existing"
        existing_dir.mkdir()
        (existing_dir / "test.yaml").write_text("name: test")

        nonexistent_dir = temp_workflow_dir / "nonexistent"

        loader = WorkflowLoader()
        # Should handle nonexistent directory gracefully
        result = loader._find_workflow_file("test", [nonexistent_dir, existing_dir])

        assert result == existing_dir / "test.yaml"

    def test_find_skips_files_in_subdirectory_check(self, temp_workflow_dir) -> None:
        """Test that files (not dirs) in search dir are skipped during subdir iteration."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        # Create a file (not directory) in workflow_dir
        (workflow_dir / "some_file.txt").write_text("not a directory")
        # Create a subdirectory with the workflow
        subdir = workflow_dir / "subdir"
        subdir.mkdir()
        (subdir / "test.yaml").write_text("name: test")

        loader = WorkflowLoader()
        result = loader._find_workflow_file("test", [workflow_dir])

        # Should skip the file and find in subdir
        assert result == subdir / "test.yaml"

    def test_find_not_found_in_subdirectory(self, temp_workflow_dir) -> None:
        """Test that None is returned when workflow exists in subdir but not the searched one."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        # Create a subdirectory with a different workflow
        subdir = workflow_dir / "subdir"
        subdir.mkdir()
        (subdir / "other.yaml").write_text("name: other")

        loader = WorkflowLoader()
        result = loader._find_workflow_file("test", [workflow_dir])

        # Should not find 'test.yaml' in any subdirectory
        assert result is None


class TestWorkflowInheritance:
    """Tests for workflow inheritance and cycle detection."""

    def test_valid_inheritance(self) -> None:
        """Test that valid inheritance (A extends B) works correctly."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        parent_yaml = """
        name: parent_workflow
        version: "1.0.0"
        steps:
          - name: step1
            allowed_tools: all
        """

        child_yaml = """
        name: child_workflow
        version: "1.0.0"
        extends: parent_workflow
        steps:
          - name: step2
            allowed_tools: [read, write]
        """

        def mock_find(name, search_dirs):
            if name == "child_workflow":
                return Path("/tmp/workflows/child_workflow.yaml")
            elif name == "parent_workflow":
                return Path("/tmp/workflows/parent_workflow.yaml")
            return None

        def mock_open_func(path, *args, **kwargs):
            if "child" in str(path):
                return mock_open(read_data=child_yaml)()
            elif "parent" in str(path):
                return mock_open(read_data=parent_yaml)()
            raise FileNotFoundError(path)

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch("builtins.open", side_effect=mock_open_func):
                wf = loader.load_workflow("child_workflow")
                assert wf is not None
                assert wf.name == "child_workflow"
                step_names = [p.name for p in wf.steps]
                assert "step1" in step_names
                assert "step2" in step_names

    def test_parent_workflow_not_found(self) -> None:
        """Test handling when parent workflow doesn't exist."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        child_yaml = """
        name: orphan_workflow
        version: "1.0.0"
        extends: nonexistent_parent
        steps:
          - name: step1
            allowed_tools: all
        """

        def mock_find(name, search_dirs):
            if name == "orphan_workflow":
                return Path("/tmp/workflows/orphan_workflow.yaml")
            return None  # Parent not found

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch("builtins.open", mock_open(read_data=child_yaml)):
                # Should still load (with warning logged), just without parent merge
                wf = loader.load_workflow("orphan_workflow")
                assert wf is not None
                assert wf.name == "orphan_workflow"

    def test_self_inheritance_cycle(self) -> None:
        """Test that self-inheritance (A extends A) raises ValueError."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        self_ref_yaml = """
        name: self_ref
        version: "1.0.0"
        extends: self_ref
        steps:
          - name: step1
            allowed_tools: all
        """

        with patch.object(
            loader,
            "_find_workflow_file",
            return_value=Path("/tmp/workflows/self_ref.yaml"),
        ):
            with patch("builtins.open", mock_open(read_data=self_ref_yaml)):
                with pytest.raises(ValueError, match="Circular workflow inheritance"):
                    loader.load_workflow("self_ref")

    def test_two_way_circular_inheritance(self) -> None:
        """Test that A extends B, B extends A raises ValueError."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        workflow_a_yaml = """
        name: workflow_a
        version: "1.0.0"
        extends: workflow_b
        steps:
          - name: step_a
            allowed_tools: all
        """

        workflow_b_yaml = """
        name: workflow_b
        version: "1.0.0"
        extends: workflow_a
        steps:
          - name: step_b
            allowed_tools: all
        """

        def mock_find(name, search_dirs):
            if name == "workflow_a":
                return Path("/tmp/workflows/workflow_a.yaml")
            elif name == "workflow_b":
                return Path("/tmp/workflows/workflow_b.yaml")
            return None

        def mock_open_func(path, *args, **kwargs):
            if "workflow_a" in str(path):
                return mock_open(read_data=workflow_a_yaml)()
            elif "workflow_b" in str(path):
                return mock_open(read_data=workflow_b_yaml)()
            raise FileNotFoundError(path)

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch("builtins.open", side_effect=mock_open_func):
                with pytest.raises(ValueError, match="Circular workflow inheritance"):
                    loader.load_workflow("workflow_a")

    def test_three_level_circular_inheritance(self) -> None:
        """Test that A extends B, B extends C, C extends A raises ValueError."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        workflow_a_yaml = """
        name: workflow_a
        version: "1.0.0"
        extends: workflow_b
        steps:
          - name: step_a
            allowed_tools: all
        """

        workflow_b_yaml = """
        name: workflow_b
        version: "1.0.0"
        extends: workflow_c
        steps:
          - name: step_b
            allowed_tools: all
        """

        workflow_c_yaml = """
        name: workflow_c
        version: "1.0.0"
        extends: workflow_a
        steps:
          - name: step_c
            allowed_tools: all
        """

        def mock_find(name, search_dirs):
            paths = {
                "workflow_a": Path("/tmp/workflows/workflow_a.yaml"),
                "workflow_b": Path("/tmp/workflows/workflow_b.yaml"),
                "workflow_c": Path("/tmp/workflows/workflow_c.yaml"),
            }
            return paths.get(name)

        def mock_open_func(path, *args, **kwargs):
            yamls = {
                "workflow_a": workflow_a_yaml,
                "workflow_b": workflow_b_yaml,
                "workflow_c": workflow_c_yaml,
            }
            for name, content in yamls.items():
                if name in str(path):
                    return mock_open(read_data=content)()
            raise FileNotFoundError(path)

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch("builtins.open", side_effect=mock_open_func):
                with pytest.raises(ValueError, match="Circular workflow inheritance"):
                    loader.load_workflow("workflow_a")

    def test_valid_chain_inheritance(self) -> None:
        """Test that valid chain (A extends B extends C) works correctly."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        base_yaml = """
        name: base
        version: "1.0.0"
        steps:
          - name: base_step
            allowed_tools: all
        """

        middle_yaml = """
        name: middle
        version: "1.0.0"
        extends: base
        steps:
          - name: middle_step
            allowed_tools: [read]
        """

        top_yaml = """
        name: top
        version: "1.0.0"
        extends: middle
        steps:
          - name: top_step
            allowed_tools: [write]
        """

        def mock_find(name, search_dirs):
            paths = {
                "base": Path("/tmp/workflows/base.yaml"),
                "middle": Path("/tmp/workflows/middle.yaml"),
                "top": Path("/tmp/workflows/top.yaml"),
            }
            return paths.get(name)

        def mock_open_func(path, *args, **kwargs):
            yamls = {
                "base": base_yaml,
                "middle": middle_yaml,
                "top": top_yaml,
            }
            for name, content in yamls.items():
                if name in str(path):
                    return mock_open(read_data=content)()
            raise FileNotFoundError(path)

        with patch.object(loader, "_find_workflow_file", side_effect=mock_find):
            with patch("builtins.open", side_effect=mock_open_func):
                wf = loader.load_workflow("top")
                assert wf is not None
                assert wf.name == "top"
                step_names = [p.name for p in wf.steps]
                assert "base_step" in step_names
                assert "middle_step" in step_names
                assert "top_step" in step_names


class TestMergeWorkflows:
    """Tests for _merge_workflows method."""

    def test_simple_merge(self, loader) -> None:
        """Test basic parent/child merge."""
        parent = {"name": "parent", "version": "1.0.0", "description": "Parent desc"}
        child = {"name": "child", "version": "2.0"}

        result = loader._merge_workflows(parent, child)

        assert result["name"] == "child"
        assert result["version"] == "2.0"
        assert result["description"] == "Parent desc"

    def test_nested_dict_merge(self, loader) -> None:
        """Test that nested dicts are deep merged."""
        parent = {
            "name": "parent",
            "settings": {"timeout": 30, "retry": True},
        }
        child = {
            "name": "child",
            "settings": {"timeout": 60},
        }

        result = loader._merge_workflows(parent, child)

        assert result["settings"]["timeout"] == 60
        assert result["settings"]["retry"] is True

    def test_steps_merge_by_name(self, loader) -> None:
        """Test that steps/phases are merged by name."""
        parent = {
            "name": "parent",
            "steps": [
                {"name": "step1", "allowed_tools": "all"},
                {"name": "step2", "allowed_tools": ["read"]},
            ],
        }
        child = {
            "name": "child",
            "steps": [
                {"name": "step2", "allowed_tools": ["read", "write"]},
                {"name": "step3", "allowed_tools": ["exec"]},
            ],
        }

        result = loader._merge_workflows(parent, child)

        # Should have all three steps
        assert len(result["steps"]) == 3

        step_map = {s["name"]: s for s in result["steps"]}
        assert step_map["step1"]["allowed_tools"] == "all"
        assert step_map["step2"]["allowed_tools"] == ["read", "write"]  # Child overrides
        assert step_map["step3"]["allowed_tools"] == ["exec"]

    def test_phases_merge_by_name(self, loader) -> None:
        """Test that 'phases' key (legacy) is merged correctly."""
        parent = {
            "name": "parent",
            "phases": [
                {"name": "phase1", "tools": ["tool1"]},
            ],
        }
        child = {
            "name": "child",
            "phases": [
                {"name": "phase1", "tools": ["tool1", "tool2"]},
                {"name": "phase2", "tools": ["tool3"]},
            ],
        }

        result = loader._merge_workflows(parent, child)

        assert len(result["phases"]) == 2


class TestMergeSteps:
    """Tests for _merge_steps method."""

    def test_merge_steps_update_existing(self, loader) -> None:
        """Test that existing steps are updated."""
        parent_steps = [
            {"name": "step1", "timeout": 30},
            {"name": "step2", "timeout": 60},
        ]
        child_steps = [
            {"name": "step1", "timeout": 120},
        ]

        result = loader._merge_steps(parent_steps, child_steps)

        step_map = {s["name"]: s for s in result}
        assert step_map["step1"]["timeout"] == 120
        assert step_map["step2"]["timeout"] == 60

    def test_merge_steps_add_new(self, loader) -> None:
        """Test that new steps are added."""
        parent_steps = [
            {"name": "step1", "timeout": 30},
        ]
        child_steps = [
            {"name": "step2", "timeout": 60},
        ]

        result = loader._merge_steps(parent_steps, child_steps)

        assert len(result) == 2
        step_names = [s["name"] for s in result]
        assert "step1" in step_names
        assert "step2" in step_names

    def test_merge_steps_without_name_parent(self, loader) -> None:
        """Test that parent steps without 'name' key are skipped with warning."""
        parent_steps = [
            {"timeout": 30},  # Missing name
            {"name": "step1", "timeout": 60},
        ]
        child_steps = [
            {"name": "step2", "timeout": 90},
        ]

        result = loader._merge_steps(parent_steps, child_steps)

        # Should only have step1 and step2, not the nameless one
        step_names = [s["name"] for s in result]
        assert "step1" in step_names
        assert "step2" in step_names
        assert len(result) == 2

    def test_merge_steps_without_name_child(self, loader) -> None:
        """Test that child steps without 'name' key are skipped with warning."""
        parent_steps = [
            {"name": "step1", "timeout": 30},
        ]
        child_steps = [
            {"timeout": 60},  # Missing name
            {"name": "step2", "timeout": 90},
        ]

        result = loader._merge_steps(parent_steps, child_steps)

        step_names = [s["name"] for s in result]
        assert "step1" in step_names
        assert "step2" in step_names
        assert len(result) == 2


class TestDiscoverLifecycleWorkflows:
    """Tests for discover_lifecycle_workflows method."""

    def test_discover_from_global_directory(self, temp_workflow_dir) -> None:
        """Test discovering lifecycle workflows from global directory."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        lifecycle_dir = global_dir / "lifecycle"
        lifecycle_dir.mkdir(parents=True)

        # Create a lifecycle workflow
        workflow_yaml = """
name: session_start
version: "1.0.0"
type: lifecycle
settings:
  priority: 10
"""
        (lifecycle_dir / "session_start.yaml").write_text(workflow_yaml)

        loader = WorkflowLoader(workflow_dirs=[global_dir])
        discovered = loader.discover_lifecycle_workflows()

        assert len(discovered) == 1
        assert discovered[0].name == "session_start"
        assert discovered[0].is_project is False
        assert discovered[0].priority == 10

    def test_discover_project_shadows_global(self, temp_workflow_dir) -> None:
        """Test that project workflows shadow global ones with the same name."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        (global_dir / "lifecycle").mkdir(parents=True)

        project_dir = temp_workflow_dir / "project" / ".gobby" / "workflows" / "lifecycle"
        project_dir.mkdir(parents=True)

        global_yaml = """
name: session_start
version: "1.0.0"
type: lifecycle
settings:
  priority: 100
"""
        project_yaml = """
name: session_start
version: "2.0"
type: lifecycle
settings:
  priority: 50
"""
        (global_dir / "lifecycle" / "session_start.yaml").write_text(global_yaml)
        (project_dir / "session_start.yaml").write_text(project_yaml)

        loader = WorkflowLoader(workflow_dirs=[global_dir])
        discovered = loader.discover_lifecycle_workflows(project_path=temp_workflow_dir / "project")

        # Should only have one workflow (project shadows global)
        assert len(discovered) == 1
        assert discovered[0].is_project is True
        assert discovered[0].priority == 50

    def test_discover_sorting(self, temp_workflow_dir) -> None:
        """Test that workflows are sorted by project/global, priority, then name."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        (global_dir / "lifecycle").mkdir(parents=True)

        # Create multiple workflows with different priorities
        for name, priority in [("b_workflow", 50), ("a_workflow", 100), ("c_workflow", 50)]:
            yaml_content = f"""
name: {name}
version: "1.0.0"
type: lifecycle
settings:
  priority: {priority}
"""
            (global_dir / "lifecycle" / f"{name}.yaml").write_text(yaml_content)

        loader = WorkflowLoader(workflow_dirs=[global_dir])
        discovered = loader.discover_lifecycle_workflows()

        # Should be sorted: priority 50 first (b, c), then priority 100 (a)
        # Within same priority, alphabetical
        names = [w.name for w in discovered]
        assert names == ["b_workflow", "c_workflow", "a_workflow"]

    def test_discover_filters_non_lifecycle(self, temp_workflow_dir) -> None:
        """Test that non-lifecycle workflows are filtered out."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        (global_dir / "lifecycle").mkdir(parents=True)

        lifecycle_yaml = """
name: lifecycle_wf
version: "1.0.0"
type: lifecycle
"""
        step_yaml = """
name: step_wf
version: "1.0.0"
type: step
"""
        (global_dir / "lifecycle" / "lifecycle_wf.yaml").write_text(lifecycle_yaml)
        (global_dir / "lifecycle" / "step_wf.yaml").write_text(step_yaml)

        loader = WorkflowLoader(workflow_dirs=[global_dir])
        discovered = loader.discover_lifecycle_workflows()

        assert len(discovered) == 1
        assert discovered[0].name == "lifecycle_wf"

    def test_discover_caching(self, temp_workflow_dir) -> None:
        """Test that discovery results are cached."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        (global_dir / "lifecycle").mkdir(parents=True)

        yaml_content = """
name: cached_workflow
version: "1.0.0"
type: lifecycle
"""
        (global_dir / "lifecycle" / "cached_workflow.yaml").write_text(yaml_content)

        loader = WorkflowLoader(workflow_dirs=[global_dir])

        # First call
        discovered1 = loader.discover_lifecycle_workflows()
        # Second call should return cached
        discovered2 = loader.discover_lifecycle_workflows()

        assert discovered1 is discovered2

    def test_discover_default_priority(self, temp_workflow_dir) -> None:
        """Test that workflows without priority setting get default of 100."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        (global_dir / "lifecycle").mkdir(parents=True)

        yaml_content = """
name: no_priority
version: "1.0.0"
type: lifecycle
"""
        (global_dir / "lifecycle" / "no_priority.yaml").write_text(yaml_content)

        loader = WorkflowLoader(workflow_dirs=[global_dir])
        discovered = loader.discover_lifecycle_workflows()

        assert len(discovered) == 1
        assert discovered[0].priority == 100


class TestScanDirectory:
    """Tests for _scan_directory method."""

    def test_scan_nonexistent_directory(self, loader, temp_workflow_dir) -> None:
        """Test that scanning non-existent directory does nothing."""
        discovered = {}
        loader._scan_directory(
            temp_workflow_dir / "nonexistent",
            is_project=False,
            discovered=discovered,
        )
        assert len(discovered) == 0

    def test_scan_skips_empty_yaml(self, temp_workflow_dir) -> None:
        """Test that empty YAML files are skipped."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "empty.yaml").write_text("")

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        discovered = {}
        loader._scan_directory(workflow_dir, is_project=False, discovered=discovered)

        assert len(discovered) == 0

    def test_scan_skips_invalid_yaml(self, temp_workflow_dir) -> None:
        """Test that invalid YAML files are skipped with warning."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "invalid.yaml").write_text("invalid: : yaml: :")

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        discovered = {}
        loader._scan_directory(workflow_dir, is_project=False, discovered=discovered)

        assert len(discovered) == 0

    def test_scan_handles_inheritance_in_discovery(self, temp_workflow_dir) -> None:
        """Test that inheritance is resolved during discovery."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        global_dir.mkdir(parents=True)

        parent_yaml = """
name: parent
version: "1.0.0"
type: lifecycle
steps:
  - name: base_step
    allowed_tools: all
"""
        child_yaml = """
name: child
version: "1.0.0"
type: lifecycle
extends: parent
"""
        (global_dir / "parent.yaml").write_text(parent_yaml)
        (global_dir / "child.yaml").write_text(child_yaml)

        loader = WorkflowLoader(workflow_dirs=[global_dir])
        discovered = {}
        loader._scan_directory(global_dir, is_project=False, discovered=discovered)

        # Both workflows should be discovered
        assert "parent" in discovered
        assert "child" in discovered

    def test_scan_handles_circular_inheritance_gracefully(self, temp_workflow_dir) -> None:
        """Test that circular inheritance is handled during scan."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        cycle_a = """
name: cycle_a
version: "1.0.0"
type: lifecycle
extends: cycle_b
"""
        cycle_b = """
name: cycle_b
version: "1.0.0"
type: lifecycle
extends: cycle_a
"""
        (workflow_dir / "cycle_a.yaml").write_text(cycle_a)
        (workflow_dir / "cycle_b.yaml").write_text(cycle_b)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        discovered = {}
        # Should not raise, just log warning and skip
        loader._scan_directory(workflow_dir, is_project=False, discovered=discovered)

        # Workflows with circular inheritance should be skipped
        # At least one will fail to load
        assert len(discovered) <= 2

    def test_scan_handles_missing_parent_in_inheritance(self, temp_workflow_dir) -> None:
        """Test that workflows extending missing parents are still loaded."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        child_yaml = """
name: child_orphan
version: "1.0.0"
type: lifecycle
extends: nonexistent_parent
"""
        (workflow_dir / "child_orphan.yaml").write_text(child_yaml)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        discovered = {}
        loader._scan_directory(workflow_dir, is_project=False, discovered=discovered)

        # Should load the child workflow even if parent not found
        # (parent=None branch in line 257)
        assert "child_orphan" in discovered


class TestClearCache:
    """Tests for clear_cache method."""

    def test_clear_cache(self, temp_workflow_dir) -> None:
        """Test that discovery cache is cleared."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        (global_dir / "lifecycle").mkdir(parents=True)

        yaml_content = """
name: test_workflow
version: "1.0.0"
type: lifecycle
"""
        (global_dir / "lifecycle" / "test_workflow.yaml").write_text(yaml_content)

        loader = WorkflowLoader(workflow_dirs=[global_dir])

        # Populate cache
        loader.discover_lifecycle_workflows()
        assert len(loader._discovery_cache) > 0

        # Clear cache
        loader.clear_cache()
        assert len(loader._discovery_cache) == 0


class TestValidateWorkflowForAgent:
    """Tests for validate_workflow_for_agent method."""

    def test_validate_nonexistent_workflow(self, loader) -> None:
        """Test that nonexistent workflows are considered valid (no error)."""
        with patch.object(loader, "load_workflow", return_value=None):
            is_valid, error = loader.validate_workflow_for_agent("nonexistent")

        assert is_valid is True
        assert error is None

    def test_validate_step_workflow(self, loader) -> None:
        """Test that step workflows are valid for agents."""
        step_workflow = MagicMock(spec=WorkflowDefinition)
        step_workflow.type = "step"

        with patch.object(loader, "load_workflow", return_value=step_workflow):
            is_valid, error = loader.validate_workflow_for_agent("step_wf")

        assert is_valid is True
        assert error is None

    def test_validate_lifecycle_workflow(self, loader) -> None:
        """Test that lifecycle workflows are invalid for agents."""
        lifecycle_workflow = MagicMock(spec=WorkflowDefinition)
        lifecycle_workflow.type = "lifecycle"

        with patch.object(loader, "load_workflow", return_value=lifecycle_workflow):
            is_valid, error = loader.validate_workflow_for_agent("lifecycle_wf")

        assert is_valid is False
        assert "lifecycle workflow" in error.lower()
        assert "plan-execute" in error

    def test_validate_with_loading_error(self, loader) -> None:
        """Test handling of ValueError during workflow loading."""
        with patch.object(
            loader,
            "load_workflow",
            side_effect=ValueError("Circular inheritance"),
        ):
            is_valid, error = loader.validate_workflow_for_agent("broken_wf")

        assert is_valid is False
        assert "Failed to load" in error
        assert "Circular inheritance" in error

    def test_validate_with_project_path(self, loader) -> None:
        """Test that project_path is passed through to load_workflow."""
        step_workflow = MagicMock(spec=WorkflowDefinition)
        step_workflow.type = "step"

        with patch.object(loader, "load_workflow", return_value=step_workflow) as mock_load:
            loader.validate_workflow_for_agent("test_wf", project_path="/my/project")

        mock_load.assert_called_once_with("test_wf", project_path="/my/project")


class TestDiscoveredWorkflow:
    """Tests for DiscoveredWorkflow dataclass."""

    def test_dataclass_creation(self) -> None:
        """Test creating a DiscoveredWorkflow instance."""
        definition = MagicMock(spec=WorkflowDefinition)
        definition.type = "lifecycle"

        discovered = DiscoveredWorkflow(
            name="test",
            definition=definition,
            priority=50,
            is_project=True,
            path=Path("/test/path.yaml"),
        )

        assert discovered.name == "test"
        assert discovered.priority == 50
        assert discovered.is_project is True
        assert discovered.path == Path("/test/path.yaml")


class TestGenericWorkflow:
    """Tests for the generic.yaml workflow definition."""

    def test_generic_workflow_loads_successfully(self, temp_workflow_dir) -> None:
        """Test that the generic workflow can be loaded."""
        # Copy the generic workflow to the test directory
        generic_yaml = """
name: generic
description: Default workflow for generic agents
version: "1.0"
type: step

steps:
  - name: work
    description: "Work on the assigned task"
    allowed_tools:
      - Read
      - Write
      - Edit
      - Bash
      - Glob
      - Grep
      - WebFetch
      - WebSearch
      - NotebookEdit
      - mcp__gobby__call_tool
      - mcp__gobby__list_tools
      - get_task
      - update_task
      - close_task
      - list_tasks
      - remember
      - recall

    blocked_tools:
      - spawn_agent
      - spawn_agent_in_worktree
      - spawn_agent_in_clone

    transitions:
      - to: complete
        when: "task_completed or user_exit"

  - name: complete
    description: "Work complete"

exit_condition: "current_step == 'complete'"
"""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "generic.yaml").write_text(generic_yaml)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        wf = loader.load_workflow("generic")

        assert wf is not None
        assert wf.name == "generic"
        assert wf.type == "step"

    def test_generic_workflow_has_work_and_complete_steps(self, temp_workflow_dir) -> None:
        """Test that generic workflow has work and complete steps."""
        generic_yaml = """
name: generic
description: Default workflow for generic agents
version: "1.0"
type: step

steps:
  - name: work
    description: "Work on the assigned task"
    allowed_tools:
      - Read
      - Write
      - Edit

    blocked_tools:
      - spawn_agent

    transitions:
      - to: complete
        when: "task_completed or user_exit"

  - name: complete
    description: "Work complete"

exit_condition: "current_step == 'complete'"
"""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "generic.yaml").write_text(generic_yaml)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        wf = loader.load_workflow("generic")

        assert wf is not None
        step_names = [s.name for s in wf.steps]
        assert "work" in step_names
        assert "complete" in step_names

    def test_generic_workflow_work_step_has_allowed_tools(self, temp_workflow_dir) -> None:
        """Test that work step allows basic file tools."""
        generic_yaml = """
name: generic
version: "1.0"
type: step

steps:
  - name: work
    allowed_tools:
      - Read
      - Write
      - Edit
      - Bash
      - Glob
      - Grep

    blocked_tools:
      - spawn_agent


    transitions:
      - to: complete
        when: "done"

  - name: complete
    description: "Done"
"""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "generic.yaml").write_text(generic_yaml)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        wf = loader.load_workflow("generic")

        work_step = next(s for s in wf.steps if s.name == "work")
        # Check allowed tools include essential file operations
        assert "Read" in work_step.allowed_tools
        assert "Write" in work_step.allowed_tools
        assert "Edit" in work_step.allowed_tools
        assert "Bash" in work_step.allowed_tools
        assert "Glob" in work_step.allowed_tools
        assert "Grep" in work_step.allowed_tools

    def test_generic_workflow_blocks_spawn_tools(self, temp_workflow_dir) -> None:
        """Test that work step blocks spawn tools to prevent recursive spawning."""
        generic_yaml = """
name: generic
version: "1.0"
type: step

steps:
  - name: work
    allowed_tools:
      - Read

    blocked_tools:
      - spawn_agent

      - spawn_agent_in_worktree
      - spawn_agent_in_clone

    transitions:
      - to: complete
        when: "done"

  - name: complete
    description: "Done"
"""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "generic.yaml").write_text(generic_yaml)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])
        wf = loader.load_workflow("generic")

        work_step = next(s for s in wf.steps if s.name == "work")
        # Check blocked tools prevent recursive spawning
        assert "spawn_agent" in work_step.blocked_tools

        assert "spawn_agent_in_worktree" in work_step.blocked_tools
        assert "spawn_agent_in_clone" in work_step.blocked_tools


class TestMtimeCacheInvalidation:
    """Tests for mtime-based cache invalidation."""

    def test_stale_file_auto_reloads(self, temp_workflow_dir) -> None:
        """Test that modifying a YAML file on disk causes automatic reload."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        yaml_v1 = """
name: mtime_test
version: "1.0.0"
type: step
steps:
  - name: step1
    allowed_tools: all
"""
        yaml_v2 = """
name: mtime_test
version: "2.0.0"
type: step
steps:
  - name: step1
    allowed_tools: all
"""
        yaml_path = workflow_dir / "mtime_test.yaml"
        yaml_path.write_text(yaml_v1)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        # First load
        wf1 = loader.load_workflow("mtime_test")
        assert wf1 is not None
        assert wf1.version == "1.0.0"

        # Modify file on disk (ensure mtime changes)
        time.sleep(0.1)  # Small sleep to ensure mtime differs
        yaml_path.write_text(yaml_v2)

        # Second load should detect stale cache and reload
        wf2 = loader.load_workflow("mtime_test")
        assert wf2 is not None
        assert wf2.version == "2.0.0"

    def test_unchanged_file_returns_cached(self, temp_workflow_dir) -> None:
        """Test that unchanged files return the cached object (same identity)."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        yaml_content = """
name: stable_test
version: "1.0.0"
type: step
steps:
  - name: step1
    allowed_tools: all
"""
        (workflow_dir / "stable_test.yaml").write_text(yaml_content)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        wf1 = loader.load_workflow("stable_test")
        wf2 = loader.load_workflow("stable_test")
        assert wf1 is wf2  # Same object from cache

    def test_inline_workflow_never_stale(self) -> None:
        """Test that inline workflows (path=None) are never considered stale."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        inline_data = {
            "name": "test:inline",
            "type": "step",
            "steps": [{"name": "work", "allowed_tools": "all"}],
        }

        definition = loader.register_inline_workflow("test:inline", inline_data)
        assert definition is not None

        # The entry should have path=None
        cache_key = "global:test:inline"
        entry = loader._cache[cache_key]
        assert entry.path is None
        assert entry.mtime == 0.0

        # Should not be stale
        assert not loader._is_stale(entry)

        # Loading again should return same object
        wf2 = loader.load_workflow("test:inline")
        assert wf2 is definition

    def test_deleted_file_is_stale(self, temp_workflow_dir) -> None:
        """Test that a deleted file is detected as stale."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        yaml_content = """
name: deletable
version: "1.0.0"
type: step
steps:
  - name: step1
    allowed_tools: all
"""
        yaml_path = workflow_dir / "deletable.yaml"
        yaml_path.write_text(yaml_content)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        wf1 = loader.load_workflow("deletable")
        assert wf1 is not None

        # Delete the file
        yaml_path.unlink()

        # Cache entry should be detected as stale
        cache_key = "global:deletable"
        entry = loader._cache[cache_key]
        assert loader._is_stale(entry)

    def test_discovery_auto_reloads_on_file_change(self, temp_workflow_dir) -> None:
        """Test that discovery cache auto-reloads when a YAML file changes."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        lifecycle_dir = global_dir / "lifecycle"
        lifecycle_dir.mkdir(parents=True)

        yaml_v1 = """
name: auto_reload
version: "1.0.0"
type: lifecycle
settings:
  priority: 10
"""
        yaml_v2 = """
name: auto_reload
version: "2.0.0"
type: lifecycle
settings:
  priority: 20
"""
        yaml_path = lifecycle_dir / "auto_reload.yaml"
        yaml_path.write_text(yaml_v1)

        loader = WorkflowLoader(workflow_dirs=[global_dir])

        # First discovery
        discovered1 = loader.discover_lifecycle_workflows()
        assert len(discovered1) == 1
        assert discovered1[0].definition.version == "1.0.0"
        assert discovered1[0].priority == 10

        # Modify file
        time.sleep(0.05)
        yaml_path.write_text(yaml_v2)

        # Second discovery should detect stale cache and reload
        discovered2 = loader.discover_lifecycle_workflows()
        assert len(discovered2) == 1
        assert discovered2[0].definition.version == "2.0.0"
        assert discovered2[0].priority == 20

    def test_discovery_detects_new_file(self, temp_workflow_dir) -> None:
        """Test that discovery detects when a new file is added to directory."""
        global_dir = temp_workflow_dir / "global" / "workflows"
        lifecycle_dir = global_dir / "lifecycle"
        lifecycle_dir.mkdir(parents=True)

        yaml_existing = """
name: existing
version: "1.0.0"
type: lifecycle
"""
        (lifecycle_dir / "existing.yaml").write_text(yaml_existing)

        loader = WorkflowLoader(workflow_dirs=[global_dir])

        # First discovery
        discovered1 = loader.discover_lifecycle_workflows()
        assert len(discovered1) == 1

        # Add a new file (changes directory mtime)
        time.sleep(0.1)
        yaml_new = """
name: new_workflow
version: "1.0.0"
type: lifecycle
"""
        (lifecycle_dir / "new_workflow.yaml").write_text(yaml_new)

        # Second discovery should detect new file via dir mtime change
        discovered2 = loader.discover_lifecycle_workflows()
        assert len(discovered2) == 2
        names = [w.name for w in discovered2]
        assert "existing" in names
        assert "new_workflow" in names

    def test_pipeline_stale_file_auto_reloads(self, temp_workflow_dir) -> None:
        """Test that pipeline cache auto-reloads on file change."""
        workflow_dir = temp_workflow_dir / "workflows"
        workflow_dir.mkdir()

        yaml_v1 = """
name: test_pipeline
version: "1.0.0"
type: pipeline
steps:
  - id: step1
    prompt: "Do something"
"""
        yaml_v2 = """
name: test_pipeline
version: "2.0.0"
type: pipeline
steps:
  - id: step1
    prompt: "Do something else"
"""
        yaml_path = workflow_dir / "test_pipeline.yaml"
        yaml_path.write_text(yaml_v1)

        loader = WorkflowLoader(workflow_dirs=[workflow_dir])

        # First load
        p1 = loader.load_pipeline("test_pipeline")
        assert p1 is not None
        assert p1.version == "1.0.0"

        # Modify file
        time.sleep(0.05)
        yaml_path.write_text(yaml_v2)

        # Second load should detect stale and reload
        p2 = loader.load_pipeline("test_pipeline")
        assert p2 is not None
        assert p2.version == "2.0.0"
