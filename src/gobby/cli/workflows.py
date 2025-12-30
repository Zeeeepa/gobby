"""
CLI commands for managing Gobby workflows.
"""

import json
import logging
from pathlib import Path

import click
import yaml

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
def workflow() -> None:
    """Manage Gobby workflows."""
    pass


@workflow.command("list")
@click.option("--all", "show_all", is_flag=True, help="Show all workflows including phase-based")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def list_workflows(ctx: click.Context, show_all: bool, json_format: bool) -> None:
    """List available workflows."""
    loader = get_workflow_loader()
    project_path = get_project_path()

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

        is_project = search_dir == (project_path / ".gobby" / "workflows") if project_path else False

        for yaml_path in search_dir.glob("*.yaml"):
            name = yaml_path.stem
            if name in seen_names:
                continue  # Project shadows global

            try:
                with open(yaml_path) as f:
                    data = yaml.safe_load(f)

                if not data:
                    continue

                wf_type = data.get("type", "phase")
                description = data.get("description", "")

                # Filter by type unless --all
                if not show_all and wf_type != "lifecycle":
                    pass  # Show all by default now

                workflows.append({
                    "name": name,
                    "type": wf_type,
                    "description": description,
                    "source": "project" if is_project else "global",
                    "path": str(yaml_path),
                })
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
        source_tag = f"[{wf['source']}]" if wf['source'] == 'project' else ""
        type_tag = f"({wf['type']})"
        click.echo(f"  {wf['name']} {type_tag} {source_tag}")
        if wf['description']:
            click.echo(f"    {wf['description'][:80]}")


@workflow.command("show")
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

    if definition.phases:
        click.echo(f"\nPhases ({len(definition.phases)}):")
        for phase in definition.phases:
            click.echo(f"  - {phase.name}")
            if phase.description:
                click.echo(f"      {phase.description}")
            if phase.allowed_tools:
                tools = phase.allowed_tools[:5]
                more = f" (+{len(phase.allowed_tools) - 5})" if len(phase.allowed_tools) > 5 else ""
                click.echo(f"      Allowed tools: {', '.join(tools)}{more}")
            if phase.blocked_tools:
                click.echo(f"      Blocked tools: {', '.join(phase.blocked_tools[:5])}")

    if definition.triggers:
        click.echo(f"\nTriggers:")
        for trigger_name, actions in definition.triggers.items():
            click.echo(f"  {trigger_name}: {len(actions)} action(s)")


@workflow.command("status")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def workflow_status(ctx: click.Context, session_id: str | None, json_format: bool) -> None:
    """Show current workflow state for a session."""
    state_manager = get_state_manager()

    if not session_id:
        # Try to find the most recent active session
        db = LocalDatabase()
        row = db.fetchone(
            "SELECT id FROM sessions WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        )
        if row:
            session_id = row["id"]
        else:
            click.echo("No active session found. Specify --session ID.", err=True)
            raise SystemExit(1)

    state = state_manager.get_state(session_id)

    if not state:
        if json_format:
            click.echo(json.dumps({"session_id": session_id, "has_workflow": False}))
        else:
            click.echo(f"No workflow active for session: {session_id[:12]}...")
        return

    if json_format:
        click.echo(json.dumps({
            "session_id": session_id,
            "has_workflow": True,
            "workflow_name": state.workflow_name,
            "phase": state.phase,
            "phase_action_count": state.phase_action_count,
            "total_action_count": state.total_action_count,
            "reflection_pending": state.reflection_pending,
            "artifacts": list(state.artifacts.keys()) if state.artifacts else [],
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        }, indent=2))
        return

    click.echo(f"Session: {session_id[:12]}...")
    click.echo(f"Workflow: {state.workflow_name}")
    click.echo(f"Phase: {state.phase}")
    click.echo(f"Actions in phase: {state.phase_action_count}")
    click.echo(f"Total actions: {state.total_action_count}")

    if state.reflection_pending:
        click.echo("⚠️  Reflection pending")

    if state.artifacts:
        click.echo(f"Artifacts: {', '.join(state.artifacts.keys())}")

    if state.task_list:
        click.echo(f"Task progress: {state.current_task_index + 1}/{len(state.task_list)}")


@workflow.command("set")
@click.argument("name")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--phase", "-p", "initial_phase", help="Initial phase (defaults to first)")
@click.pass_context
def set_workflow(
    ctx: click.Context, name: str, session_id: str | None, initial_phase: str | None
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
        click.echo("Use 'gobby workflow set' only for phase-based workflows.", err=True)
        raise SystemExit(1)

    # Get session
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

    # Check for existing workflow
    existing = state_manager.get_state(session_id)
    if existing:
        click.echo(f"Session already has workflow '{existing.workflow_name}' active.")
        click.echo("Use 'gobby workflow clear' first to remove it.")
        raise SystemExit(1)

    # Determine initial phase
    if initial_phase:
        if not any(p.name == initial_phase for p in definition.phases):
            click.echo(f"Phase '{initial_phase}' not found in workflow.", err=True)
            raise SystemExit(1)
        phase = initial_phase
    else:
        phase = definition.phases[0].name if definition.phases else "default"

    # Create state
    state = WorkflowState(
        session_id=session_id,
        workflow_name=name,
        phase=phase,
        phase_entered_at=datetime.now(UTC),
        phase_action_count=0,
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
    click.echo(f"  Starting phase: {phase}")


@workflow.command("clear")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def clear_workflow(ctx: click.Context, session_id: str | None, force: bool) -> None:
    """Clear/deactivate workflow for a session."""
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


@workflow.command("phase")
@click.argument("phase_name")
@click.option("--session", "-s", "session_id", help="Session ID (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip exit condition checks")
@click.pass_context
def set_phase(
    ctx: click.Context, phase_name: str, session_id: str | None, force: bool
) -> None:
    """Manually transition to a phase (escape hatch)."""
    from datetime import UTC, datetime

    loader = get_workflow_loader()
    state_manager = get_state_manager()
    project_path = get_project_path()

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

    state = state_manager.get_state(session_id)
    if not state:
        click.echo(f"No workflow active for session: {session_id[:12]}...", err=True)
        raise SystemExit(1)

    # Load workflow to validate phase
    definition = loader.load_workflow(state.workflow_name, project_path)
    if not definition:
        click.echo(f"Workflow '{state.workflow_name}' not found.", err=True)
        raise SystemExit(1)

    if not any(p.name == phase_name for p in definition.phases):
        click.echo(f"Phase '{phase_name}' not found in workflow.", err=True)
        click.echo(f"Available phases: {', '.join(p.name for p in definition.phases)}")
        raise SystemExit(1)

    if not force and state.phase != phase_name:
        click.echo(f"⚠️  Manual phase transition from '{state.phase}' to '{phase_name}'")
        click.confirm("This skips normal exit conditions. Continue?", abort=True)

    old_phase = state.phase
    state.phase = phase_name
    state.phase_entered_at = datetime.now(UTC)
    state.phase_action_count = 0

    state_manager.save_state(state)
    click.echo(f"✓ Transitioned from '{old_phase}' to '{phase_name}'")


@workflow.command("import")
@click.argument("source")
@click.option("--name", "-n", help="Override workflow name")
@click.option("--global", "is_global", is_flag=True, help="Install to global directory")
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
        raise SystemExit(1)

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
