"""
CLI commands for managing Gobby pipelines.
"""

import json
import logging
from pathlib import Path

import click

from gobby.workflows.loader import WorkflowLoader

logger = logging.getLogger(__name__)


def get_workflow_loader() -> WorkflowLoader:
    """Get workflow loader instance."""
    return WorkflowLoader()


def get_project_path() -> Path | None:
    """Get current project path if in a gobby project."""
    cwd = Path.cwd()
    if (cwd / ".gobby").exists():
        return cwd
    return None


@click.group()
def pipelines() -> None:
    """Manage Gobby pipelines."""
    pass


@pipelines.command("list")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def list_pipelines(ctx: click.Context, json_format: bool) -> None:
    """List available pipeline definitions."""
    loader = get_workflow_loader()
    project_path = get_project_path()

    discovered = loader.discover_pipeline_workflows(
        project_path=str(project_path) if project_path else None
    )

    if json_format:
        pipeline_list = []
        for wf in discovered:
            pipeline_list.append(
                {
                    "name": wf.name,
                    "description": wf.definition.description,
                    "is_project": wf.is_project,
                    "path": str(wf.path),
                    "step_count": len(wf.definition.steps),
                }
            )
        click.echo(json.dumps({"pipelines": pipeline_list, "count": len(pipeline_list)}, indent=2))
        return

    if not discovered:
        click.echo("No pipelines found.")
        return

    click.echo(f"Found {len(discovered)} pipeline(s):\n")
    for wf in discovered:
        source_tag = "[project]" if wf.is_project else ""
        step_count = len(wf.definition.steps)
        click.echo(f"  {wf.name} ({step_count} steps) {source_tag}")
        if wf.definition.description:
            click.echo(f"    {wf.definition.description[:80]}")


@pipelines.command("show")
@click.argument("name")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def show_pipeline(ctx: click.Context, name: str, json_format: bool) -> None:
    """Show pipeline definition details."""
    loader = get_workflow_loader()

    pipeline = loader.load_pipeline(name)
    if not pipeline:
        click.echo(f"Pipeline '{name}' not found.", err=True)
        raise SystemExit(1)

    if json_format:
        pipeline_dict = {
            "name": pipeline.name,
            "description": pipeline.description,
            "steps": [
                {
                    "id": step.id,
                    "exec": step.exec,
                    "prompt": step.prompt,
                    "invoke_pipeline": step.invoke_pipeline,
                    "condition": step.condition,
                }
                for step in pipeline.steps
            ],
            "inputs": pipeline.inputs,
            "outputs": pipeline.outputs,
        }
        click.echo(json.dumps(pipeline_dict, indent=2, default=str))
        return

    click.echo(f"Pipeline: {pipeline.name}")
    if pipeline.description:
        click.echo(f"Description: {pipeline.description}")

    if pipeline.inputs:
        click.echo("\nInputs:")
        for input_name, input_def in pipeline.inputs.items():
            required = input_def.get("required", False)
            req_tag = " (required)" if required else ""
            click.echo(f"  - {input_name}{req_tag}")
            if input_def.get("description"):
                click.echo(f"      {input_def['description']}")

    click.echo(f"\nSteps ({len(pipeline.steps)}):")
    for step in pipeline.steps:
        step_type = "exec" if step.exec else "prompt" if step.prompt else "pipeline"
        click.echo(f"  - {step.id} ({step_type})")
        if step.exec:
            cmd_preview = step.exec[:60] + "..." if len(step.exec) > 60 else step.exec
            click.echo(f"      {cmd_preview}")
        elif step.prompt:
            prompt_preview = step.prompt[:60] + "..." if len(step.prompt) > 60 else step.prompt
            click.echo(f"      {prompt_preview}")
        elif step.invoke_pipeline:
            click.echo(f"      invoke: {step.invoke_pipeline}")
        if step.condition:
            click.echo(f"      condition: {step.condition}")

    if pipeline.outputs:
        click.echo("\nOutputs:")
        for output_name, output_expr in pipeline.outputs.items():
            click.echo(f"  - {output_name}: {output_expr}")
