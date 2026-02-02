"""Tests for WorkflowLoader.load_pipeline() method.

TDD tests for loading pipeline workflows.
"""

import tempfile
from pathlib import Path

import pytest

from gobby.workflows.definitions import PipelineDefinition
from gobby.workflows.loader import WorkflowLoader

pytestmark = pytest.mark.unit


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary directory structure for workflows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        # Create workflow directories
        (base / "global" / "workflows").mkdir(parents=True)
        (base / "project" / ".gobby" / "workflows").mkdir(parents=True)
        yield base


@pytest.fixture
def loader(temp_workflow_dir):
    """Create a WorkflowLoader with test directories."""
    return WorkflowLoader(workflow_dirs=[temp_workflow_dir / "global" / "workflows"])


class TestLoadPipeline:
    """Tests for load_pipeline method."""

    def test_load_valid_pipeline(self, loader, temp_workflow_dir) -> None:
        """Test loading a valid pipeline YAML returns PipelineDefinition."""
        pipeline_yaml = """
name: test-pipeline
type: pipeline
description: A test pipeline
steps:
  - id: step1
    exec: echo hello
  - id: step2
    exec: echo world
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "test-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("test-pipeline")

        assert result is not None
        assert isinstance(result, PipelineDefinition)
        assert result.name == "test-pipeline"
        assert result.type == "pipeline"
        assert len(result.steps) == 2

    def test_load_pipeline_not_found(self, loader) -> None:
        """Test loading non-existent pipeline returns None."""
        result = loader.load_pipeline("nonexistent")
        assert result is None

    def test_load_pipeline_wrong_type(self, loader, temp_workflow_dir) -> None:
        """Test loading a step workflow via load_pipeline returns None."""
        workflow_yaml = """
name: step-workflow
type: step
steps:
  - name: work
    allowed_tools: all
"""
        workflow_path = temp_workflow_dir / "global" / "workflows" / "step-workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        result = loader.load_pipeline("step-workflow")
        assert result is None

    def test_load_pipeline_project_path_priority(self, loader, temp_workflow_dir) -> None:
        """Test that project-specific pipelines take priority over global."""
        # Global pipeline
        global_yaml = """
name: deploy
type: pipeline
steps:
  - id: step1
    exec: echo global
"""
        global_path = temp_workflow_dir / "global" / "workflows" / "deploy.yaml"
        global_path.write_text(global_yaml)

        # Project pipeline (should override)
        project_yaml = """
name: deploy
type: pipeline
description: Project-specific deploy
steps:
  - id: step1
    exec: echo project
"""
        project_path = temp_workflow_dir / "project" / ".gobby" / "workflows" / "deploy.yaml"
        project_path.write_text(project_yaml)

        result = loader.load_pipeline("deploy", project_path=temp_workflow_dir / "project")

        assert result is not None
        assert result.description == "Project-specific deploy"

    def test_load_pipeline_with_inputs_outputs(self, loader, temp_workflow_dir) -> None:
        """Test loading pipeline with inputs and outputs schema."""
        pipeline_yaml = """
name: parameterized
type: pipeline
inputs:
  files:
    type: array
    description: Files to process
  mode:
    type: string
    default: fast
outputs:
  result: $final.output
steps:
  - id: final
    exec: echo done
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "parameterized.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("parameterized")

        assert result is not None
        assert "files" in result.inputs
        assert "mode" in result.inputs
        assert result.inputs["mode"]["default"] == "fast"
        assert result.outputs["result"] == "$final.output"

    def test_load_pipeline_with_approval(self, loader, temp_workflow_dir) -> None:
        """Test loading pipeline with approval gates."""
        pipeline_yaml = """
name: approval-pipeline
type: pipeline
steps:
  - id: test
    exec: pytest
  - id: deploy
    exec: ./deploy.sh
    approval:
      required: true
      message: Approve deployment?
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "approval-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("approval-pipeline")

        assert result is not None
        assert len(result.steps) == 2
        deploy_step = result.get_step("deploy")
        assert deploy_step is not None
        assert deploy_step.approval is not None
        assert deploy_step.approval.required is True
        assert deploy_step.approval.message == "Approve deployment?"

    def test_load_pipeline_with_webhooks(self, loader, temp_workflow_dir) -> None:
        """Test loading pipeline with webhook configuration."""
        pipeline_yaml = """
name: webhook-pipeline
type: pipeline
webhooks:
  on_complete:
    url: https://example.com/done
    method: POST
steps:
  - id: work
    exec: echo working
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "webhook-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("webhook-pipeline")

        assert result is not None
        assert result.webhooks is not None
        assert result.webhooks.on_complete is not None
        assert result.webhooks.on_complete.url == "https://example.com/done"

    def test_load_pipeline_inheritance(self, loader, temp_workflow_dir) -> None:
        """Test pipeline inheritance via extends field."""
        # Base pipeline
        base_yaml = """
name: base-pipeline
type: pipeline
inputs:
  env:
    type: string
    default: staging
steps:
  - id: setup
    exec: echo setup
"""
        base_path = temp_workflow_dir / "global" / "workflows" / "base-pipeline.yaml"
        base_path.write_text(base_yaml)

        # Child pipeline extends base
        child_yaml = """
name: child-pipeline
type: pipeline
extends: base-pipeline
inputs:
  env:
    default: production
steps:
  - id: deploy
    exec: echo deploy
"""
        child_path = temp_workflow_dir / "global" / "workflows" / "child-pipeline.yaml"
        child_path.write_text(child_yaml)

        result = loader.load_pipeline("child-pipeline")

        assert result is not None
        assert result.name == "child-pipeline"
        # Should have inherited env input with overridden default
        assert result.inputs["env"]["default"] == "production"

    def test_load_pipeline_caching(self, loader, temp_workflow_dir) -> None:
        """Test that pipelines are cached after first load."""
        pipeline_yaml = """
name: cached-pipeline
type: pipeline
steps:
  - id: step1
    exec: echo cached
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "cached-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # First load
        result1 = loader.load_pipeline("cached-pipeline")
        # Modify the file
        pipeline_path.write_text(pipeline_yaml.replace("cached", "modified"))
        # Second load should return cached version
        result2 = loader.load_pipeline("cached-pipeline")

        assert result1 is result2  # Same object from cache

    def test_load_pipeline_invalid_yaml(self, loader, temp_workflow_dir) -> None:
        """Test that invalid YAML returns None."""
        invalid_yaml = """
name: invalid
type: pipeline
steps: [this is: : not valid yaml
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "invalid.yaml"
        pipeline_path.write_text(invalid_yaml)

        result = loader.load_pipeline("invalid")
        assert result is None

    def test_load_pipeline_missing_type(self, loader, temp_workflow_dir) -> None:
        """Test that YAML without type field returns None (defaults to step)."""
        no_type_yaml = """
name: no-type
steps:
  - name: work
    allowed_tools: all
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "no-type.yaml"
        pipeline_path.write_text(no_type_yaml)

        result = loader.load_pipeline("no-type")
        # Should return None because it's not type: pipeline
        assert result is None


class TestValidatePipelineReferences:
    """Tests for _validate_pipeline_references method."""

    def test_valid_back_reference(self, loader, temp_workflow_dir) -> None:
        """Test that $earlier_step.output references are accepted."""
        pipeline_yaml = """
name: valid-refs
type: pipeline
steps:
  - id: step1
    exec: echo hello
  - id: step2
    prompt: Process the output from $step1.output
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "valid-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # Should load successfully - references are valid
        result = loader.load_pipeline("valid-refs")
        assert result is not None
        assert len(result.steps) == 2

    def test_rejects_forward_reference(self, loader, temp_workflow_dir) -> None:
        """Test that $later_step.output (forward ref) is rejected."""
        pipeline_yaml = """
name: forward-ref
type: pipeline
steps:
  - id: step1
    prompt: Use output from $step2.output
  - id: step2
    exec: echo hello
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "forward-ref.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # Should fail - step1 references step2 which comes later
        with pytest.raises(ValueError) as exc_info:
            loader.load_pipeline("forward-ref")
        assert "step2" in str(exc_info.value)
        assert "later" in str(exc_info.value).lower() or "forward" in str(exc_info.value).lower()

    def test_rejects_nonexistent_reference(self, loader, temp_workflow_dir) -> None:
        """Test that $nonexistent.output is rejected."""
        pipeline_yaml = """
name: nonexistent-ref
type: pipeline
steps:
  - id: step1
    prompt: Use output from $doesnotexist.output
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "nonexistent-ref.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # Should fail - doesnotexist is not a valid step
        with pytest.raises(ValueError) as exc_info:
            loader.load_pipeline("nonexistent-ref")
        assert "doesnotexist" in str(exc_info.value)

    def test_validates_prompt_references(self, loader, temp_workflow_dir) -> None:
        """Test that references in prompt fields are validated."""
        pipeline_yaml = """
name: prompt-refs
type: pipeline
steps:
  - id: analyze
    exec: ./analyze.sh
  - id: report
    prompt: |
      Generate a report based on:
      - Analysis: $analyze.output
      - Summary: $analyze.output.summary
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "prompt-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # Should load successfully - all references are to earlier steps
        result = loader.load_pipeline("prompt-refs")
        assert result is not None

    def test_validates_condition_references(self, loader, temp_workflow_dir) -> None:
        """Test that references in condition fields are validated."""
        pipeline_yaml = """
name: condition-refs
type: pipeline
steps:
  - id: test
    exec: pytest
  - id: deploy
    exec: ./deploy.sh
    condition: $test.output.exit_code == 0
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "condition-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # Should load successfully
        result = loader.load_pipeline("condition-refs")
        assert result is not None

    def test_validates_input_references(self, loader, temp_workflow_dir) -> None:
        """Test that references in input fields are validated."""
        pipeline_yaml = """
name: input-refs
type: pipeline
steps:
  - id: step1
    exec: echo start
  - id: step2
    exec: process
    input: $step1.output
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "input-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("input-refs")
        assert result is not None

    def test_validates_output_references(self, loader, temp_workflow_dir) -> None:
        """Test that references in pipeline outputs are validated."""
        pipeline_yaml = """
name: output-refs
type: pipeline
outputs:
  result: $final.output
  summary: $analyze.output.summary
steps:
  - id: analyze
    exec: ./analyze.sh
  - id: final
    exec: ./finish.sh
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "output-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("output-refs")
        assert result is not None

    def test_rejects_invalid_output_reference(self, loader, temp_workflow_dir) -> None:
        """Test that invalid references in outputs are rejected."""
        pipeline_yaml = """
name: bad-output-refs
type: pipeline
outputs:
  result: $missing_step.output
steps:
  - id: step1
    exec: echo hello
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "bad-output-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        with pytest.raises(ValueError) as exc_info:
            loader.load_pipeline("bad-output-refs")
        assert "missing_step" in str(exc_info.value)

    def test_allows_inputs_reference(self, loader, temp_workflow_dir) -> None:
        """Test that $inputs.field references are allowed (not step refs)."""
        pipeline_yaml = """
name: inputs-ref
type: pipeline
inputs:
  target:
    type: string
steps:
  - id: step1
    exec: echo $inputs.target
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "inputs-ref.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("inputs-ref")
        assert result is not None

    def test_multiple_refs_all_valid(self, loader, temp_workflow_dir) -> None:
        """Test pipeline with multiple valid references."""
        pipeline_yaml = """
name: multi-refs
type: pipeline
steps:
  - id: step1
    exec: echo one
  - id: step2
    exec: echo two
  - id: step3
    prompt: Combine $step1.output and $step2.output
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "multi-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = loader.load_pipeline("multi-refs")
        assert result is not None

    def test_multiple_refs_one_invalid(self, loader, temp_workflow_dir) -> None:
        """Test that one invalid ref among valid ones is caught."""
        pipeline_yaml = """
name: mixed-refs
type: pipeline
steps:
  - id: step1
    exec: echo one
  - id: step2
    prompt: Use $step1.output and $step3.output
  - id: step3
    exec: echo three
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "mixed-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        with pytest.raises(ValueError) as exc_info:
            loader.load_pipeline("mixed-refs")
        assert "step3" in str(exc_info.value)
