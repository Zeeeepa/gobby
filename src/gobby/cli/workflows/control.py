"""Session state control commands for workflows."""

from datetime import UTC, datetime

import click

from gobby.cli.workflows import common
from gobby.workflows.definitions import WorkflowDefinition, WorkflowState


@click.command("set")
@click.argument("name")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--step", "-p", "initial_step", help="Initial step (defaults to first)")
@click.pass_context
def set_workflow(
    ctx: click.Context, name: str, session_id: str | None, initial_step: str | None
) -> None:
    """Activate a workflow for a session."""
    loader = common.get_workflow_loader()
    state_manager = common.get_state_manager()
    project_path = common.get_project_path()

    # Load workflow
    definition = loader.load_workflow_sync(name, project_path)
    if not definition:
        click.echo(f"Workflow '{name}' not found.", err=True)
        raise SystemExit(1)

    if not isinstance(definition, WorkflowDefinition):
        click.echo(f"'{name}' is a pipeline, not a step-based workflow.", err=True)
        click.echo("Use 'gobby pipelines run' for pipelines.", err=True)
        raise SystemExit(1)

    if definition.enabled:
        click.echo(f"Workflow '{name}' is always-on (auto-runs on events).", err=True)
        click.echo("Use 'gobby workflows set' only for on-demand workflows.", err=True)
        raise SystemExit(1)

    # Get session
    session_id = common.resolve_session_id(session_id)

    # Check for existing workflow
    existing = state_manager.get_state(session_id)
    if existing:
        click.echo(f"Session already has workflow '{existing.workflow_name}' active.")
        click.echo("Use 'gobby workflows clear' first to remove it.")
        raise SystemExit(1)

    # Determine initial step
    if initial_step:
        if not any(s.name == initial_step for s in definition.steps):
            click.echo(f"Step '{initial_step}' not found in workflow.", err=True)
            raise SystemExit(1)
        step = initial_step
    else:
        if not definition.steps:
            click.echo(f"Workflow '{name}' has no steps defined.", err=True)
            raise SystemExit(1)
        step = definition.steps[0].name

    # Create state
    state = WorkflowState(
        session_id=session_id,
        workflow_name=name,
        step=step,
        initial_step=step,  # Track for reset functionality
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        total_action_count=0,
        observations=[],
        reflection_pending=False,
        context_injected=False,
        variables={},
        task_list=None,
        current_task_index=0,
        files_modified_this_task=0,
    )

    state_manager.save_state(state)
    click.echo(f"✓ Activated workflow '{name}' for session {common.truncate_id(session_id)}")
    click.echo(f"  Starting step: {step}")


@click.command("clear")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def clear_workflow(ctx: click.Context, session_id: str | None, force: bool) -> None:
    """Clear/deactivate workflow for a session."""
    state_manager = common.get_state_manager()

    session_id = common.resolve_session_id(session_id)

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {common.truncate_id(session_id)}")
        return

    if not force:
        click.confirm(
            f"Clear workflow '{state.workflow_name}' from session?",
            abort=True,
        )

    state_manager.delete_state(session_id)
    click.echo(f"✓ Cleared workflow from session {common.truncate_id(session_id)}")


@click.command("step")
@click.argument("step_name")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip exit condition checks")
@click.pass_context
def set_step(ctx: click.Context, step_name: str, session_id: str | None, force: bool) -> None:
    """Manually transition to a step (escape hatch)."""
    loader = common.get_workflow_loader()
    state_manager = common.get_state_manager()
    project_path = common.get_project_path()

    session_id = common.resolve_session_id(session_id)

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {common.truncate_id(session_id)}", err=True)
        raise SystemExit(1)

    # Load workflow to validate step
    definition = loader.load_workflow_sync(state.workflow_name, project_path)
    if not definition:
        click.echo(f"Workflow '{state.workflow_name}' not found.", err=True)
        raise SystemExit(1)

    if not isinstance(definition, WorkflowDefinition):
        click.echo(f"'{state.workflow_name}' is a pipeline, not a step-based workflow.", err=True)
        raise SystemExit(1)

    if not any(s.name == step_name for s in definition.steps):
        click.echo(f"Step '{step_name}' not found in workflow.", err=True)
        click.echo(f"Available steps: {', '.join(s.name for s in definition.steps)}")
        raise SystemExit(1)

    if not force and state.step != step_name:
        click.echo(f"⚠️  Manual step transition from '{state.step}' to '{step_name}'")
        click.confirm("This skips normal exit conditions. Continue?", abort=True)

    old_step = state.step
    state.step = step_name
    state.step_entered_at = datetime.now(UTC)
    state.step_action_count = 0

    state_manager.save_state(state)
    click.echo(f"✓ Transitioned from '{old_step}' to '{step_name}'")


@click.command("reset")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def reset_workflow(ctx: click.Context, session_id: str | None, force: bool) -> None:
    """Reset workflow to initial step (escape hatch)."""
    state_manager = common.get_state_manager()

    session_id = common.resolve_session_id(session_id)

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {common.truncate_id(session_id)}", err=True)
        raise SystemExit(1)

    # Determine initial step
    initial_step = state.initial_step or state.step
    if state.step == initial_step:
        click.echo(f"Workflow is already at initial step '{initial_step}'")
        return

    if not force:
        click.echo(f"⚠️  Reset workflow from '{state.step}' to initial step '{initial_step}'")
        click.confirm("This will clear all step state and variables. Continue?", abort=True)

    # Reset state
    state.step = initial_step
    state.step_entered_at = datetime.now(UTC)
    state.step_action_count = 0
    state.variables = {}
    state.approval_pending = False
    state.approval_condition_id = None
    state.approval_prompt = None
    state.disabled = False
    state.disabled_reason = None

    state_manager.save_state(state)
    click.echo(f"✓ Reset workflow to initial step '{initial_step}'")


@click.command("disable")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--reason", "-r", help="Reason for disabling")
@click.pass_context
def disable_workflow(ctx: click.Context, session_id: str | None, reason: str | None) -> None:
    """Temporarily disable workflow enforcement (escape hatch)."""
    state_manager = common.get_state_manager()

    session_id = common.resolve_session_id(session_id)

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {common.truncate_id(session_id)}", err=True)
        raise SystemExit(1)

    if state.disabled:
        click.echo(f"Workflow '{state.workflow_name}' is already disabled.")
        return

    state.disabled = True
    state.disabled_reason = reason

    state_manager.save_state(state)
    click.echo(f"✓ Disabled workflow '{state.workflow_name}'")
    click.echo("  Tool restrictions and step enforcement are now suspended.")
    click.echo("  Use 'gobby workflows enable' to re-enable.")


@click.command("enable")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.pass_context
def enable_workflow(ctx: click.Context, session_id: str | None) -> None:
    """Re-enable a disabled workflow."""
    state_manager = common.get_state_manager()

    session_id = common.resolve_session_id(session_id)

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {common.truncate_id(session_id)}", err=True)
        raise SystemExit(1)

    if not state.disabled:
        click.echo(f"Workflow '{state.workflow_name}' is not disabled.")
        return

    state.disabled = False
    state.disabled_reason = None

    state_manager.save_state(state)
    click.echo(f"✓ Re-enabled workflow '{state.workflow_name}'")
    click.echo(f"  Current step: {state.step}")
