"""
CLI commands for managing Gobby workflows.
"""

import json
import logging
from pathlib import Path

import click
import yaml

from gobby.cli.utils import resolve_session_id
from gobby.storage.database import LocalDatabase
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


def get_workflow_loader() -> WorkflowLoader:
    """Get workflow loader instance."""
    return WorkflowLoader()


def get_state_manager() -> WorkflowStateManager:
    """Get workflow state manager instance."""
    db = LocalDatabase()
    return WorkflowStateManager(db)


def get_project_path() -> Path | None:
    """Get current project path if in a gobby project."""
    cwd = Path.cwd()
    if (cwd / ".gobby").exists():
        return cwd
    return None


@click.group()
def workflows() -> None:
    """Manage Gobby workflows."""
    pass


@workflows.command("list")
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
    loader = get_workflow_loader()
    project_path = get_project_path() if not global_only else None

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

                wf_type = data.get("type", "step")
                description = data.get("description", "")

                # Filter by type unless --all
                if not show_all and wf_type != "lifecycle":
                    pass  # Show all by default now

                workflows.append(
                    {
                        "name": name,
                        "type": wf_type,
                        "description": description,
                        "source": "project" if is_project else "global",
                        "path": str(yaml_path),
                    }
                )
                seen_names.add(name)

            except Exception as e:
                logger.warning(f"Failed to load workflow from {yaml_path}: {e}")

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
        type_tag = f"({wf['type']})"
        click.echo(f"  {wf['name']} {type_tag} {source_tag}")
        if wf["description"]:
            click.echo(f"    {wf['description'][:80]}")


@workflows.command("show")
@click.argument("name")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def show_workflow(ctx: click.Context, name: str, json_format: bool) -> None:
    """Show workflow details."""
    loader = get_workflow_loader()
    project_path = get_project_path()

    definition = loader.load_workflow(name, project_path)
    if not definition:
        click.echo(f"Workflow '{name}' not found.", err=True)
        raise SystemExit(1)

    if json_format:
        click.echo(json.dumps(definition.dict(), indent=2, default=str))
        return

    click.echo(f"Workflow: {definition.name}")
    click.echo(f"Type: {definition.type}")
    if definition.description:
        click.echo(f"Description: {definition.description}")
    if definition.version:
        click.echo(f"Version: {definition.version}")

    if definition.steps:
        click.echo(f"\nSteps ({len(definition.steps)}):")
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
                        f" (+{len(step.allowed_tools) - 5})" if len(step.allowed_tools) > 5 else ""
                    )
                    click.echo(f"      Allowed tools: {', '.join(tools)}{more}")
            if step.blocked_tools:
                click.echo(f"      Blocked tools: {', '.join(step.blocked_tools[:5])}")

    if definition.triggers:
        click.echo("\nTriggers:")
        for trigger_name, actions in definition.triggers.items():
            click.echo(f"  {trigger_name}: {len(actions)} action(s)")


@workflows.command("status")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def workflow_status(ctx: click.Context, session_id: str | None, json_format: bool) -> None:
    """Show current workflow state for a session."""
    state_manager = get_state_manager()

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
                    "artifacts": list(state.artifacts.keys()) if state.artifacts else [],
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

    if state.artifacts:
        click.echo(f"Artifacts: {', '.join(state.artifacts.keys())}")

    if state.task_list:
        click.echo(f"Task progress: {state.current_task_index + 1}/{len(state.task_list)}")


@workflows.command("set")
@click.argument("name")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--step", "-p", "initial_step", help="Initial step (defaults to first)")
@click.pass_context
def set_workflow(
    ctx: click.Context, name: str, session_id: str | None, initial_step: str | None
) -> None:
    """Activate a workflow for a session."""
    from datetime import UTC, datetime

    from gobby.workflows.definitions import WorkflowState

    loader = get_workflow_loader()
    state_manager = get_state_manager()
    project_path = get_project_path()

    # Load workflow
    definition = loader.load_workflow(name, project_path)
    if not definition:
        click.echo(f"Workflow '{name}' not found.", err=True)
        raise SystemExit(1)

    if definition.type == "lifecycle":
        click.echo(f"Workflow '{name}' is a lifecycle workflow (auto-runs on events).", err=True)
        click.echo("Use 'gobby workflows set' only for step-based workflows.", err=True)
        raise SystemExit(1)

    # Get session
    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

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
        step = definition.steps[0].name if definition.steps else "default"

    # Create state
    state = WorkflowState(
        session_id=session_id,
        workflow_name=name,
        step=step,
        initial_step=step,  # Track for reset functionality
        step_entered_at=datetime.now(UTC),
        step_action_count=0,
        total_action_count=0,
        artifacts={},
        observations=[],
        reflection_pending=False,
        context_injected=False,
        variables={},
        task_list=None,
        current_task_index=0,
        files_modified_this_task=0,
    )

    state_manager.save_state(state)
    click.echo(f"✓ Activated workflow '{name}' for session {session_id[:12]}...")
    click.echo(f"  Starting step: {step}")


@workflows.command("clear")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def clear_workflow(ctx: click.Context, session_id: str | None, force: bool) -> None:
    """Clear/deactivate workflow for a session."""
    state_manager = get_state_manager()

    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {session_id[:12]}...")
        return

    if not force:
        click.confirm(
            f"Clear workflow '{state.workflow_name}' from session?",
            abort=True,
        )

    state_manager.delete_state(session_id)
    click.echo(f"✓ Cleared workflow from session {session_id[:12]}...")


@workflows.command("step")
@click.argument("step_name")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip exit condition checks")
@click.pass_context
def set_step(ctx: click.Context, step_name: str, session_id: str | None, force: bool) -> None:
    """Manually transition to a step (escape hatch)."""
    from datetime import UTC, datetime

    loader = get_workflow_loader()
    state_manager = get_state_manager()
    project_path = get_project_path()

    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {session_id[:12]}...", err=True)
        raise SystemExit(1)

    # Load workflow to validate step
    definition = loader.load_workflow(state.workflow_name, project_path)
    if not definition:
        click.echo(f"Workflow '{state.workflow_name}' not found.", err=True)
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


@workflows.command("reset")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def reset_workflow(ctx: click.Context, session_id: str | None, force: bool) -> None:
    """Reset workflow to initial step (escape hatch)."""
    from datetime import UTC, datetime

    state_manager = get_state_manager()

    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {session_id[:12]}...", err=True)
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


@workflows.command("disable")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--reason", "-r", help="Reason for disabling")
@click.pass_context
def disable_workflow(ctx: click.Context, session_id: str | None, reason: str | None) -> None:
    """Temporarily disable workflow enforcement (escape hatch)."""
    state_manager = get_state_manager()

    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {session_id[:12]}...", err=True)
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


@workflows.command("enable")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.pass_context
def enable_workflow(ctx: click.Context, session_id: str | None) -> None:
    """Re-enable a disabled workflow."""
    state_manager = get_state_manager()

    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {session_id[:12]}...", err=True)
        raise SystemExit(1)

    if not state.disabled:
        click.echo(f"Workflow '{state.workflow_name}' is not disabled.")
        return

    state.disabled = False
    state.disabled_reason = None

    state_manager.save_state(state)
    click.echo(f"✓ Re-enabled workflow '{state.workflow_name}'")
    click.echo(f"  Current step: {state.step}")


@workflows.command("artifact")
@click.argument("artifact_type")
@click.argument("file_path")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.pass_context
def mark_artifact(
    ctx: click.Context, artifact_type: str, file_path: str, session_id: str | None
) -> None:
    """Mark an artifact as complete (plan, spec, test, etc.)."""
    state_manager = get_state_manager()

    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {session_id[:12]}...", err=True)
        raise SystemExit(1)

    # Update artifacts
    state.artifacts[artifact_type] = file_path
    state_manager.save_state(state)

    click.echo(f"✓ Marked '{artifact_type}' artifact complete: {file_path}")
    if len(state.artifacts) > 1:
        click.echo(f"  All artifacts: {', '.join(state.artifacts.keys())}")


@workflows.command("import")
@click.argument("source")
@click.option("--name", "-n", help="Override workflow name")
@click.option("--global", "-g", "is_global", is_flag=True, help="Install to global directory")
@click.pass_context
def import_workflow(ctx: click.Context, source: str, name: str | None, is_global: bool) -> None:
    """Import a workflow from a file or URL."""
    import shutil
    from urllib.parse import urlparse

    # Determine if URL or file
    parsed = urlparse(source)
    is_url = parsed.scheme in ("http", "https")

    if is_url:
        click.echo("URL import not yet implemented. Download the file and import locally.")
        raise SystemExit(1)

    # File import
    source_path = Path(source)
    if not source_path.exists():
        click.echo(f"File not found: {source}", err=True)
        raise SystemExit(1)

    if not source_path.suffix == ".yaml":
        click.echo("Workflow file must have .yaml extension.", err=True)
        raise SystemExit(1)

    # Validate it's a valid workflow
    try:
        with open(source_path) as f:
            data = yaml.safe_load(f)

        if not data or "name" not in data:
            click.echo("Invalid workflow: missing 'name' field.", err=True)
            raise SystemExit(1)

    except yaml.YAMLError as e:
        click.echo(f"Invalid YAML: {e}", err=True)
        raise SystemExit(1) from None

    # Determine destination
    workflow_name = name or data.get("name", source_path.stem)
    filename = f"{workflow_name}.yaml"

    if is_global:
        dest_dir = Path.home() / ".gobby" / "workflows"
    else:
        project_path = get_project_path()
        if not project_path:
            click.echo("Not in a gobby project. Use --global to install globally.", err=True)
            raise SystemExit(1)
        dest_dir = project_path / ".gobby" / "workflows"

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    if dest_path.exists():
        click.confirm(f"Workflow '{workflow_name}' already exists. Overwrite?", abort=True)

    shutil.copy(source_path, dest_path)
    click.echo(f"✓ Imported workflow '{workflow_name}' to {dest_path}")


@workflows.command("reload")
@click.pass_context
def reload_workflows(ctx: click.Context) -> None:
    """Reload workflow definitions from disk."""
    import httpx
    import psutil

    from gobby.config.app import load_config

    # Try to tell daemon to reload
    try:
        config = load_config()
        port = config.daemon_port

        # Check if running
        is_running = False
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = proc.cmdline()
                    if "gobby" in cmdline and "start" in cmdline:
                        is_running = True
                        break
                    # Also check for "python -m gobby start" or similar
                    if len(cmdline) >= 2 and cmdline[1].endswith("gobby") and "start" in cmdline:
                        is_running = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            # Fallback to connection attempt
            is_running = True

        if is_running:
            try:
                response = httpx.post(
                    f"http://localhost:{port}/admin/workflows/reload", timeout=2.0
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        click.echo("✓ Triggered daemon workflow reload")
                        return
                    else:
                        click.echo(f"Daemon reload failed: {data.get('message')}", err=True)
                else:
                    click.echo(f"Daemon returned status {response.status_code}", err=True)
            except httpx.ConnectError:
                # Daemon not actually running or listening
                pass
            except Exception as e:
                click.echo(f"Failed to communicate with daemon: {e}", err=True)
    except Exception as e:
        logger.debug(f"Error checking daemon status: {e}")

    # Fallback: Clear local cache (useful if running in same process or just validating)
    # This also helps if the user just wants to verify the command runs
    loader = get_workflow_loader()
    loader.clear_cache()
    click.echo("✓ Cleared local workflow cache")


@workflows.command("audit")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option(
    "--type",
    "-t",
    "event_type",
    help="Filter by event type (tool_call, rule_eval, transition, approval)",
)
@click.option("--result", "-r", help="Filter by result (allow, block, transition)")
@click.option("--limit", "-n", default=50, help="Maximum entries to show (default: 50)")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def audit_workflow(
    ctx: click.Context,
    session_id: str | None,
    event_type: str | None,
    result: str | None,
    limit: int,
    json_format: bool,
) -> None:
    """View workflow audit log (explainability/debugging)."""
    from gobby.storage.workflow_audit import WorkflowAuditManager

    audit_manager = WorkflowAuditManager()

    try:
        session_id = resolve_session_id(session_id)
    except click.ClickException as e:
        raise SystemExit(1) from e

    entries = audit_manager.get_entries(
        session_id=session_id,
        event_type=event_type,
        result=result,
        limit=limit,
    )

    if not entries:
        click.echo(f"No audit entries found for session {session_id[:12]}...")
        return

    if json_format:
        output = []
        for entry in entries:
            output.append(
                {
                    "id": entry.id,
                    "timestamp": entry.timestamp.isoformat(),
                    "step": entry.step,
                    "event_type": entry.event_type,
                    "tool_name": entry.tool_name,
                    "rule_id": entry.rule_id,
                    "condition": entry.condition,
                    "result": entry.result,
                    "reason": entry.reason,
                    "context": entry.context,
                }
            )
        click.echo(json.dumps(output, indent=2))
        return

    # Human-readable output
    click.echo(f"Audit log for session {session_id[:12]}... ({len(entries)} entries)\n")

    for entry in entries:
        # Format: [timestamp] RESULT event_type
        timestamp_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        result_color = {
            "allow": "green",
            "block": "red",
            "transition": "yellow",
            "approved": "green",
            "rejected": "red",
            "pending": "yellow",
        }.get(entry.result, "white")

        click.echo(f"[{timestamp_str}] ", nl=False)
        click.secho(entry.result.upper(), fg=result_color, nl=False)
        click.echo(f" {entry.event_type}")

        click.echo(f"  Step: {entry.step}")

        if entry.tool_name:
            click.echo(f"  Tool: {entry.tool_name}")
        if entry.rule_id:
            click.echo(f"  Rule: {entry.rule_id}")
        if entry.condition:
            click.echo(f"  Condition: {entry.condition}")
        if entry.reason:
            click.echo(f"  Reason: {entry.reason}")

        click.echo()  # Blank line between entries


@workflows.command("set-var")
@click.argument("name")
@click.argument("value")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def set_variable(
    ctx: click.Context, name: str, value: str, session_id: str | None, json_format: bool
) -> None:
    """Set a workflow variable for the current session.

    Variables are session-scoped (not persisted to YAML files).

    Examples:

        gobby workflows set-var session_epic #47

        gobby workflows set-var is_worktree true

        gobby workflows set-var max_retries 5
    """
    from datetime import UTC, datetime

    from gobby.workflows.definitions import WorkflowState

    state_manager = get_state_manager()

    if not session_id:
        db = LocalDatabase()
        row = db.fetchone(
            "SELECT id FROM sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        )
        if row:
            session_id = row["id"]
        else:
            click.echo("No active session found. Specify --session ID.", err=True)
            raise SystemExit(1)

    if session_id is None:
        raise click.ClickException("Session ID is required")

    # Parse value type
    parsed_value: str | int | float | bool | None
    if value.lower() == "null" or value.lower() == "none":
        parsed_value = None
    elif value.lower() == "true":
        parsed_value = True
    elif value.lower() == "false":
        parsed_value = False
    else:
        # Try int, then float, then string
        try:
            parsed_value = int(value)
        except ValueError:
            try:
                parsed_value = float(value)
            except ValueError:
                parsed_value = value

    # Get or create state
    state = state_manager.get_state(session_id)
    if not state:
        state = WorkflowState(
            session_id=session_id,
            workflow_name="__lifecycle__",
            step="",
            step_entered_at=datetime.now(UTC),
            variables={},
        )

    # Set the variable
    state.variables[name] = parsed_value
    state_manager.save_state(state)

    if json_format:
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "session_id": session_id,
                    "variable": name,
                    "value": parsed_value,
                    "all_variables": state.variables,
                },
                indent=2,
            )
        )
    else:
        value_display = repr(parsed_value) if isinstance(parsed_value, str) else str(parsed_value)
        click.echo(f"✓ Set {name} = {value_display}")
        click.echo(f"  Session: {session_id[:12]}...")


@workflows.command("get-var")
@click.argument("name", required=False)
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def get_variable(
    ctx: click.Context, name: str | None, session_id: str | None, json_format: bool
) -> None:
    """Get workflow variable(s) for the current session.

    If NAME is provided, shows that specific variable.
    If NAME is omitted, shows all variables.

    Examples:

        gobby workflows get-var session_epic

        gobby workflows get-var
    """
    state_manager = get_state_manager()

    if not session_id:
        db = LocalDatabase()
        row = db.fetchone(
            "SELECT id FROM sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        )
        if row:
            session_id = row["id"]
        else:
            click.echo("No active session found. Specify --session ID.", err=True)
            raise SystemExit(1)

    if session_id is None:
        raise click.ClickException("Session ID is required")

    state = state_manager.get_state(session_id)
    variables = state.variables if state else {}

    if name:
        # Get specific variable
        exists = name in variables
        value = variables.get(name)

        if json_format:
            click.echo(
                json.dumps(
                    {
                        "success": True,
                        "session_id": session_id,
                        "variable": name,
                        "value": value,
                        "exists": exists,
                    },
                    indent=2,
                )
            )
        else:
            if exists:
                value_display = repr(value) if isinstance(value, str) else str(value)
                click.echo(f"{name} = {value_display}")
            else:
                click.echo(f"{name}: not set")
    else:
        # Get all variables
        if json_format:
            click.echo(
                json.dumps(
                    {
                        "success": True,
                        "session_id": session_id,
                        "variables": variables,
                    },
                    indent=2,
                )
            )
        else:
            if variables:
                click.echo(f"Variables for session {session_id[:12]}...:\n")
                for var_name, var_value in sorted(variables.items()):
                    value_display = (
                        repr(var_value) if isinstance(var_value, str) else str(var_value)
                    )
                    click.echo(f"  {var_name} = {value_display}")
            else:
                click.echo(f"No variables set for session {session_id[:12]}...")
