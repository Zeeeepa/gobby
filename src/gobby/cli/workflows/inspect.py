"""Inspection commands for workflows."""

import json
import logging

import click
import yaml

from gobby.cli.utils import resolve_session_id
from gobby.cli.workflows import common
from gobby.workflows.definitions import WorkflowDefinition

logger = logging.getLogger(__name__)


@click.command("list")
@click.option(
    "--all", "-a", "show_all", is_flag=True, help="Show all workflows including step-based"
)
@click.option("--global", "-g", "global_only", is_flag=True, help="Show only global workflows")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def list_workflows(
    ctx: click.Context, show_all: bool, global_only: bool, json_format: bool
) -> None:
    """List available workflows."""
    loader = common.get_workflow_loader()
    project_path = common.get_project_path() if not global_only else None

    # Build search directories
    search_dirs = list(loader.global_dirs)
    if project_path:
        project_dir = project_path / ".gobby" / "workflows"
        search_dirs.insert(0, project_dir)

    workflows = []
    seen_names = set()

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        is_project = (
            search_dir == (project_path / ".gobby" / "workflows") if project_path else False
        )

        for yaml_path in search_dir.glob("*.yaml"):
            name = yaml_path.stem
            if name in seen_names:
                continue  # Project shadows global

            try:
                with open(yaml_path) as f:
                    data = yaml.safe_load(f)

                if not data:
                    continue

                wf_enabled = data.get("enabled", True)
                description = data.get("description", "")

                # Filter by type unless --all
                if not show_all and not wf_enabled:
                    continue

                workflows.append(
                    {
                        "name": name,
                        "enabled": wf_enabled,
                        "description": description,
                        "source": "project" if is_project else "global",
                        "path": str(yaml_path),
                    }
                )
                seen_names.add(name)

            except (OSError, yaml.YAMLError) as exc:
                logger.warning(
                    "Failed to load workflow",
                    extra={"path": str(yaml_path)},
                    exc_info=True,
                )

    if json_format:
        click.echo(json.dumps({"workflows": workflows, "count": len(workflows)}, indent=2))
        return

    if not workflows:
        click.echo("No workflows found.")
        click.echo(f"Search directories: {[str(d) for d in search_dirs]}")
        return

    click.echo(f"Found {len(workflows)} workflow(s):\n")
    for wf in workflows:
        source_tag = f"[{wf['source']}]" if wf["source"] == "project" else ""
        enabled_tag = "(enabled)" if wf["enabled"] else "(on-demand)"
        click.echo(f"  {wf['name']} {enabled_tag} {source_tag}")
        if wf["description"]:
            click.echo(f"    {wf['description'][:80]}")


@click.command("show")
@click.argument("name")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def show_workflow(ctx: click.Context, name: str, json_format: bool) -> None:
    """Show workflow details."""
    loader = common.get_workflow_loader()
    project_path = common.get_project_path()

    definition = loader.load_workflow_sync(name, project_path)
    if not definition:
        click.echo(f"Workflow '{name}' not found.", err=True)
        raise SystemExit(1)

    if json_format:
        click.echo(json.dumps(definition.dict(), indent=2, default=str))
        return

    click.echo(f"Workflow: {definition.name}")
    click.echo(f"Enabled: {getattr(definition, 'enabled', False)}")
    if definition.description:
        click.echo(f"Description: {definition.description}")
    if definition.version:
        click.echo(f"Version: {definition.version}")

    if definition.steps:
        click.echo(f"\nSteps ({len(definition.steps)}):")
        if isinstance(definition, WorkflowDefinition):
            for step in definition.steps:
                click.echo(f"  - {step.name}")
                if step.description:
                    click.echo(f"      {step.description}")
                if step.allowed_tools:
                    if step.allowed_tools == "all":
                        click.echo("      Allowed tools: all")
                    else:
                        tools = step.allowed_tools[:5]
                        more = (
                            f" (+{len(step.allowed_tools) - 5})"
                            if len(step.allowed_tools) > 5
                            else ""
                        )
                        click.echo(f"      Allowed tools: {', '.join(tools)}{more}")
                if step.blocked_tools:
                    click.echo(f"      Blocked tools: {', '.join(step.blocked_tools[:5])}")
        else:
            # PipelineDefinition
            for pstep in definition.steps:
                click.echo(f"  - {pstep.id}")
                if pstep.exec:
                    click.echo(f"      exec: {pstep.exec[:60]}...")
                elif pstep.prompt:
                    click.echo(f"      prompt: {pstep.prompt[:60]}...")

    if isinstance(definition, WorkflowDefinition) and definition.triggers:
        click.echo("\nTriggers:")
        for trigger_name, actions in definition.triggers.items():
            click.echo(f"  {trigger_name}: {len(actions)} action(s)")


@click.command("status")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def workflow_status(ctx: click.Context, session_id: str | None, json_format: bool) -> None:
    """Show current workflow state for a session."""
    state_manager = common.get_state_manager()

    if not session_id:
        try:
            session_id = resolve_session_id(None)
        except click.ClickException as e:
            # Re-raise to match expected behavior or exit
            raise SystemExit(1) from e
    else:
        try:
            session_id = resolve_session_id(session_id)
        except click.ClickException as e:
            raise SystemExit(1) from e

    state = state_manager.get_state(session_id)

    if not state:
        if json_format:
            click.echo(json.dumps({"session_id": session_id, "has_workflow": False}))
        else:
            click.echo(f"No workflow active for session: {session_id[:12]}...")
        return

    if json_format:
        click.echo(
            json.dumps(
                {
                    "session_id": session_id,
                    "has_workflow": True,
                    "workflow_name": state.workflow_name,
                    "step": state.step,
                    "step_action_count": state.step_action_count,
                    "total_action_count": state.total_action_count,
                    "reflection_pending": state.reflection_pending,
                    "disabled": state.disabled,
                    "disabled_reason": state.disabled_reason,
                    "updated_at": state.updated_at.isoformat() if state.updated_at else None,
                },
                indent=2,
            )
        )
        return

    click.echo(f"Session: {session_id[:12]}...")
    click.echo(f"Workflow: {state.workflow_name}")
    click.echo(f"Step: {state.step}")
    click.echo(f"Actions in step: {state.step_action_count}")
    click.echo(f"Total actions: {state.total_action_count}")

    if state.disabled:
        click.echo(f"⚠️  DISABLED{f': {state.disabled_reason}' if state.disabled_reason else ''}")
        click.echo("   Use 'gobby workflows enable' to re-enable enforcement.")

    if state.reflection_pending:
        click.echo("⚠️  Reflection pending")

    if state.task_list:
        click.echo(f"Task progress: {state.current_task_index + 1}/{len(state.task_list)}")
