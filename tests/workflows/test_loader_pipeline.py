"""Tests for WorkflowLoader.load_pipeline() method.

TDD tests for loading pipeline workflows.
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

from gobby.workflows.definitions import PipelineDefinition, WorkflowDefinition
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

    @pytest.mark.asyncio
    async def test_load_valid_pipeline(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("test-pipeline")

        assert result is not None
        assert isinstance(result, PipelineDefinition)
        assert result.name == "test-pipeline"
        assert result.type == "pipeline"
        assert len(result.steps) == 2

    @pytest.mark.asyncio
    async def test_load_pipeline_not_found(self, loader) -> None:
        """Test loading non-existent pipeline returns None."""
        result = await loader.load_pipeline("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_pipeline_wrong_type(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("step-workflow")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_pipeline_project_path_priority(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("deploy", project_path=temp_workflow_dir / "project")

        assert result is not None
        assert result.description == "Project-specific deploy"

    @pytest.mark.asyncio
    async def test_load_pipeline_with_inputs_outputs(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("parameterized")

        assert result is not None
        assert "files" in result.inputs
        assert "mode" in result.inputs
        assert result.inputs["mode"]["default"] == "fast"
        assert result.outputs["result"] == "$final.output"

    @pytest.mark.asyncio
    async def test_load_pipeline_with_approval(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("approval-pipeline")

        assert result is not None
        assert len(result.steps) == 2
        deploy_step = result.get_step("deploy")
        assert deploy_step is not None
        assert deploy_step.approval is not None
        assert deploy_step.approval.required is True
        assert deploy_step.approval.message == "Approve deployment?"

    @pytest.mark.asyncio
    async def test_load_pipeline_with_webhooks(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("webhook-pipeline")

        assert result is not None
        assert result.webhooks is not None
        assert result.webhooks.on_complete is not None
        assert result.webhooks.on_complete.url == "https://example.com/done"

    @pytest.mark.asyncio
    async def test_load_pipeline_inheritance(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("child-pipeline")

        assert result is not None
        assert result.name == "child-pipeline"
        # Should have inherited env input with overridden default
        assert result.inputs["env"]["default"] == "production"

    @pytest.mark.asyncio
    async def test_load_pipeline_caching(self, loader, temp_workflow_dir) -> None:
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
        result1 = await loader.load_pipeline("cached-pipeline")
        # Second load without file change should return cached version
        result2 = await loader.load_pipeline("cached-pipeline")

        assert result1 is result2  # Same object from cache

    @pytest.mark.asyncio
    async def test_load_pipeline_cache_invalidation(self, loader, temp_workflow_dir) -> None:
        """Test that modified pipelines are reloaded (cache invalidated via mtime)."""
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
        result1 = await loader.load_pipeline("cached-pipeline")
        assert result1 is not None
        assert result1.name == "cached-pipeline"

        # Modify the file
        pipeline_path.write_text(pipeline_yaml.replace("cached", "modified"))
        # Ensure mtime is updated (handles filesystems with 1-second resolution)
        future_time = time.time() + 1
        os.utime(pipeline_path, (future_time, future_time))

        # Second load should detect staleness and return fresh version
        result2 = await loader.load_pipeline("cached-pipeline")
        assert result2 is not None
        assert result2.name == "modified-pipeline"
        assert result1 is not result2

    @pytest.mark.asyncio
    async def test_load_pipeline_invalid_yaml(self, loader, temp_workflow_dir) -> None:
        """Test that invalid YAML returns None."""
        invalid_yaml = """
name: invalid
type: pipeline
steps: [this is: : not valid yaml
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "invalid.yaml"
        pipeline_path.write_text(invalid_yaml)

        result = await loader.load_pipeline("invalid")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_pipeline_missing_type(self, loader, temp_workflow_dir) -> None:
        """Test that YAML without type field returns None (defaults to step)."""
        no_type_yaml = """
name: no-type
steps:
  - name: work
    allowed_tools: all
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "no-type.yaml"
        pipeline_path.write_text(no_type_yaml)

        result = await loader.load_pipeline("no-type")
        # Should return None because it's not type: pipeline
        assert result is None


class TestValidatePipelineReferences:
    """Tests for _validate_pipeline_references method."""

    @pytest.mark.asyncio
    async def test_valid_back_reference(self, loader, temp_workflow_dir) -> None:
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
        result = await loader.load_pipeline("valid-refs")
        assert result is not None
        assert len(result.steps) == 2

    @pytest.mark.asyncio
    async def test_rejects_forward_reference(self, loader, temp_workflow_dir) -> None:
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
            await loader.load_pipeline("forward-ref")
        assert "step2" in str(exc_info.value)
        assert "later" in str(exc_info.value).lower() or "forward" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_rejects_nonexistent_reference(self, loader, temp_workflow_dir) -> None:
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
            await loader.load_pipeline("nonexistent-ref")
        assert "doesnotexist" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validates_prompt_references(self, loader, temp_workflow_dir) -> None:
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
        result = await loader.load_pipeline("prompt-refs")
        assert result is not None

    @pytest.mark.asyncio
    async def test_validates_condition_references(self, loader, temp_workflow_dir) -> None:
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
        result = await loader.load_pipeline("condition-refs")
        assert result is not None

    @pytest.mark.asyncio
    async def test_validates_input_references(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("input-refs")
        assert result is not None

    @pytest.mark.asyncio
    async def test_validates_output_references(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("output-refs")
        assert result is not None

    @pytest.mark.asyncio
    async def test_rejects_invalid_output_reference(self, loader, temp_workflow_dir) -> None:
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
            await loader.load_pipeline("bad-output-refs")
        assert "missing_step" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_allows_inputs_reference(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("inputs-ref")
        assert result is not None

    @pytest.mark.asyncio
    async def test_multiple_refs_all_valid(self, loader, temp_workflow_dir) -> None:
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

        result = await loader.load_pipeline("multi-refs")
        assert result is not None

    @pytest.mark.asyncio
    async def test_multiple_refs_one_invalid(self, loader, temp_workflow_dir) -> None:
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
            await loader.load_pipeline("mixed-refs")
        assert "step3" in str(exc_info.value)


class TestLoadWorkflowPipelineIntegration:
    """Tests for load_workflow() auto-detecting and handling pipelines."""

    @pytest.mark.asyncio
    async def test_load_workflow_auto_detects_pipeline(self, loader, temp_workflow_dir) -> None:
        """Test that load_workflow() auto-detects type=pipeline."""
        pipeline_yaml = """
name: auto-detect
type: pipeline
steps:
  - id: step1
    exec: echo hello
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "auto-detect.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = await loader.load_workflow("auto-detect")

        assert result is not None
        assert isinstance(result, PipelineDefinition)
        assert result.type == "pipeline"

    @pytest.mark.asyncio
    async def test_load_workflow_validates_pipeline_references(
        self, loader, temp_workflow_dir
    ) -> None:
        """Test that load_workflow() validates references for pipelines."""
        pipeline_yaml = """
name: validate-refs
type: pipeline
steps:
  - id: step1
    prompt: Use $step2.output
  - id: step2
    exec: echo hello
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "validate-refs.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # Should fail due to forward reference
        with pytest.raises(ValueError) as exc_info:
            await loader.load_workflow("validate-refs")
        assert "step2" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_load_workflow_returns_workflow_definition_for_step(
        self, loader, temp_workflow_dir
    ) -> None:
        """Test that load_workflow() returns WorkflowDefinition for step type."""
        workflow_yaml = """
name: step-workflow
type: step
steps:
  - name: work
    allowed_tools: all
"""
        workflow_path = temp_workflow_dir / "global" / "workflows" / "step-workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        result = await loader.load_workflow("step-workflow")

        assert result is not None
        assert isinstance(result, WorkflowDefinition)
        assert result.type == "step"

    @pytest.mark.asyncio
    async def test_load_workflow_returns_workflow_definition_for_lifecycle(
        self, loader, temp_workflow_dir
    ) -> None:
        """Test that load_workflow() returns WorkflowDefinition for lifecycle type."""
        workflow_yaml = """
name: lifecycle-workflow
type: lifecycle
triggers:
  on_session_start: []
"""
        workflow_path = temp_workflow_dir / "global" / "workflows" / "lifecycle-workflow.yaml"
        workflow_path.write_text(workflow_yaml)

        result = await loader.load_workflow("lifecycle-workflow")

        assert result is not None
        assert isinstance(result, WorkflowDefinition)
        assert result.type == "lifecycle"

    @pytest.mark.asyncio
    async def test_load_workflow_pipeline_with_valid_refs(self, loader, temp_workflow_dir) -> None:
        """Test load_workflow() succeeds for pipeline with valid references."""
        pipeline_yaml = """
name: valid-pipeline
type: pipeline
steps:
  - id: analyze
    exec: ./analyze.sh
  - id: report
    prompt: Generate report from $analyze.output
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "valid-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = await loader.load_workflow("valid-pipeline")

        assert result is not None
        assert isinstance(result, PipelineDefinition)
        assert len(result.steps) == 2


class TestDiscoverPipelineWorkflows:
    """Tests for discover_pipeline_workflows() method."""

    @pytest.mark.asyncio
    async def test_discovers_pipelines_in_global_dir(self, loader, temp_workflow_dir) -> None:
        """Test that pipelines in global workflows dir are discovered."""
        pipeline_yaml = """
name: global-pipeline
type: pipeline
steps:
  - id: step1
    exec: echo global
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "global-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = await loader.discover_pipeline_workflows()

        assert len(result) == 1
        assert result[0].name == "global-pipeline"
        assert result[0].is_project is False
        assert result[0].definition.type == "pipeline"

    @pytest.mark.asyncio
    async def test_discovers_pipelines_in_project_dir(self, loader, temp_workflow_dir) -> None:
        """Test that pipelines in project workflows dir are discovered."""
        pipeline_yaml = """
name: project-pipeline
type: pipeline
steps:
  - id: step1
    exec: echo project
"""
        project_workflows = temp_workflow_dir / "project" / ".gobby" / "workflows"
        pipeline_path = project_workflows / "project-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = await loader.discover_pipeline_workflows(
            project_path=temp_workflow_dir / "project"
        )

        # Should find the project pipeline
        project_pipelines = [p for p in result if p.is_project]
        assert len(project_pipelines) == 1
        assert project_pipelines[0].name == "project-pipeline"

    @pytest.mark.asyncio
    async def test_project_shadows_global_pipeline(self, loader, temp_workflow_dir) -> None:
        """Test that project pipelines shadow global pipelines with same name."""
        # Global pipeline
        global_yaml = """
name: deploy
type: pipeline
description: Global deploy
steps:
  - id: step1
    exec: echo global
"""
        global_path = temp_workflow_dir / "global" / "workflows" / "deploy.yaml"
        global_path.write_text(global_yaml)

        # Project pipeline with same name
        project_yaml = """
name: deploy
type: pipeline
description: Project deploy
steps:
  - id: step1
    exec: echo project
"""
        project_workflows = temp_workflow_dir / "project" / ".gobby" / "workflows"
        project_path = project_workflows / "deploy.yaml"
        project_path.write_text(project_yaml)

        result = await loader.discover_pipeline_workflows(
            project_path=temp_workflow_dir / "project"
        )

        # Should only have one "deploy" pipeline (project shadows global)
        deploy_pipelines = [p for p in result if p.name == "deploy"]
        assert len(deploy_pipelines) == 1
        assert deploy_pipelines[0].is_project is True
        assert deploy_pipelines[0].definition.description == "Project deploy"

    @pytest.mark.asyncio
    async def test_ignores_non_pipeline_workflows(self, loader, temp_workflow_dir) -> None:
        """Test that step/lifecycle workflows are not returned."""
        # Pipeline workflow
        pipeline_yaml = """
name: my-pipeline
type: pipeline
steps:
  - id: step1
    exec: echo pipeline
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "my-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        # Step workflow (should be ignored)
        step_yaml = """
name: my-step
type: step
steps:
  - name: work
    allowed_tools: all
"""
        step_path = temp_workflow_dir / "global" / "workflows" / "my-step.yaml"
        step_path.write_text(step_yaml)

        # Lifecycle workflow (should be ignored)
        lifecycle_yaml = """
name: my-lifecycle
type: lifecycle
triggers:
  on_session_start: []
"""
        lifecycle_dir = temp_workflow_dir / "global" / "workflows" / "lifecycle"
        lifecycle_dir.mkdir(parents=True, exist_ok=True)
        lifecycle_path = lifecycle_dir / "my-lifecycle.yaml"
        lifecycle_path.write_text(lifecycle_yaml)

        result = await loader.discover_pipeline_workflows()

        # Should only find the pipeline
        assert len(result) == 1
        assert result[0].name == "my-pipeline"
        assert result[0].definition.type == "pipeline"

    @pytest.mark.asyncio
    async def test_returns_discovered_workflow_structure(self, loader, temp_workflow_dir) -> None:
        """Test that result has correct DiscoveredWorkflow structure."""
        pipeline_yaml = """
name: structured-pipeline
type: pipeline
settings:
  priority: 50
steps:
  - id: step1
    exec: echo test
"""
        pipeline_path = temp_workflow_dir / "global" / "workflows" / "structured-pipeline.yaml"
        pipeline_path.write_text(pipeline_yaml)

        result = await loader.discover_pipeline_workflows()

        assert len(result) == 1
        discovered = result[0]
        # Check DiscoveredWorkflow fields
        assert discovered.name == "structured-pipeline"
        assert discovered.priority == 50
        assert discovered.is_project is False
        assert discovered.path == pipeline_path
        assert isinstance(discovered.definition, PipelineDefinition)

    @pytest.mark.asyncio
    async def test_discovers_multiple_pipelines(self, loader, temp_workflow_dir) -> None:
        """Test discovering multiple pipelines."""
        for i in range(3):
            pipeline_yaml = f"""
name: pipeline-{i}
type: pipeline
steps:
  - id: step1
    exec: echo {i}
"""
            path = temp_workflow_dir / "global" / "workflows" / f"pipeline-{i}.yaml"
            path.write_text(pipeline_yaml)

        result = await loader.discover_pipeline_workflows()

        assert len(result) == 3
        names = {p.name for p in result}
        assert names == {"pipeline-0", "pipeline-1", "pipeline-2"}
