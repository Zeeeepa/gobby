from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from gobby.workflows.loader import WorkflowLoader


@pytest.fixture
def loader():
    return WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])


class TestWorkflowLoader:
    def test_load_workflow_not_found(self, loader):
        with patch("gobby.workflows.loader.WorkflowLoader._find_workflow_file", return_value=None):
            assert loader.load_workflow("non_existent") is None

    def test_load_workflow_valid_yaml(self, loader):
        yaml_content = """
        name: test_workflow
        version: "1.0"
        steps:
          - name: step1
            allowed_tools: all
        """
        # Mock finding the file
        with patch(
            "gobby.workflows.loader.WorkflowLoader._find_workflow_file",
            return_value=Path("/tmp/workflows/test_workflow.yaml"),
        ):
            # Mock opening the file
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                wf = loader.load_workflow("test_workflow")
                assert wf is not None
                assert wf.name == "test_workflow"
                assert len(wf.steps) == 1
                assert wf.steps[0].name == "step1"

    def test_load_workflow_invalid_yaml(self, loader):
        yaml_content = "invalid: : yaml"
        with patch(
            "gobby.workflows.loader.WorkflowLoader._find_workflow_file",
            return_value=Path("/tmp/workflows/invalid.yaml"),
        ):
            with patch("builtins.open", mock_open(read_data=yaml_content)):
                # loader should catch exception and return None
                wf = loader.load_workflow("invalid")
                assert wf is None

    def test_load_workflow_with_project_path(self, loader):
        # Verify project path search order logic
        # Implementation searches project_path first.
        # We can mock _find_workflow_file to check args, or test logic inside _find_workflow_file by integration?
        # Let's mock _find_workflow_file and verify it was called with project dir

        with patch("gobby.workflows.loader.WorkflowLoader._find_workflow_file") as mock_find:
            mock_find.return_value = None
            loader.load_workflow("test", project_path="/my/project")

            # Check calling args
            args, _ = mock_find.call_args
            # first arg is name, second is search_dirs
            search_dirs = args[1]
            assert Path("/my/project/.gobby/workflows") in search_dirs
            assert search_dirs[0] == Path("/my/project/.gobby/workflows")

    @pytest.mark.skip(reason="incomplete test - needs mocking of _scan_directory or glob")
    def test_discover_lifecycle_workflows(self, loader):
        # Helper to setup mocks for scanning
        # This is complex because it involves globbing and parsing multiple files.
        # We can mock _scan_directory or glob.
        pass  # Skip complex discovery test for now, or mock _scan_directory


class TestWorkflowInheritance:
    """Tests for workflow inheritance and cycle detection."""

    def test_valid_inheritance(self):
        """Test that valid inheritance (A extends B) works correctly."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        parent_yaml = """
        name: parent_workflow
        version: "1.0"
        steps:
          - name: step1
            allowed_tools: all
        """

        child_yaml = """
        name: child_workflow
        version: "1.0"
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
                # Should have phases from both parent and child
                step_names = [p.name for p in wf.steps]
                assert "step1" in step_names
                assert "step2" in step_names

    def test_self_inheritance_cycle(self):
        """Test that self-inheritance (A extends A) raises ValueError."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        self_ref_yaml = """
        name: self_ref
        version: "1.0"
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

    def test_two_way_circular_inheritance(self):
        """Test that A extends B, B extends A raises ValueError."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        workflow_a_yaml = """
        name: workflow_a
        version: "1.0"
        extends: workflow_b
        steps:
          - name: step_a
            allowed_tools: all
        """

        workflow_b_yaml = """
        name: workflow_b
        version: "1.0"
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

    def test_three_level_circular_inheritance(self):
        """Test that A extends B, B extends C, C extends A raises ValueError."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        workflow_a_yaml = """
        name: workflow_a
        version: "1.0"
        extends: workflow_b
        steps:
          - name: step_a
            allowed_tools: all
        """

        workflow_b_yaml = """
        name: workflow_b
        version: "1.0"
        extends: workflow_c
        steps:
          - name: step_b
            allowed_tools: all
        """

        workflow_c_yaml = """
        name: workflow_c
        version: "1.0"
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

    def test_valid_chain_inheritance(self):
        """Test that valid chain (A extends B extends C) works correctly."""
        loader = WorkflowLoader(workflow_dirs=[Path("/tmp/workflows")])

        base_yaml = """
        name: base
        version: "1.0"
        steps:
          - name: base_step
            allowed_tools: all
        """

        middle_yaml = """
        name: middle
        version: "1.0"
        extends: base
        steps:
          - name: middle_step
            allowed_tools: [read]
        """

        top_yaml = """
        name: top
        version: "1.0"
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
                # Should have phases from all three levels
                step_names = [p.name for p in wf.steps]
                assert "base_step" in step_names
                assert "middle_step" in step_names
                assert "top_step" in step_names
