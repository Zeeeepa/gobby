"""
Git hook management for automatic task sync.
"""

import stat
from pathlib import Path

import click

GIT_HOOK_SCRIPTS = {
    "pre-commit": '''#!/bin/sh
# Gobby task sync hook - export tasks before commit
# Installed by: gobby tasks hooks install

# Only run if gobby is installed and daemon is running
if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --export --quiet 2>/dev/null || true
fi
''',
    "post-merge": '''#!/bin/sh
# Gobby task sync hook - import tasks after merge/pull
# Installed by: gobby tasks hooks install

# Only run if gobby is installed and daemon is running
if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --import --quiet 2>/dev/null || true
fi
''',
    "post-checkout": '''#!/bin/sh
# Gobby task sync hook - import tasks on branch switch
# Installed by: gobby tasks hooks install

# $3 is 1 if this was a branch checkout (vs file checkout)
if [ "$3" = "1" ]; then
    if command -v gobby >/dev/null 2>&1; then
        gobby tasks sync --import --quiet 2>/dev/null || true
    fi
fi
''',
}


def _resolve_gitdir(git_path: Path, base_dir: Path) -> Path:
    """Resolve the actual .git directory, handling worktrees/submodules.

    When .git is a file (worktree/submodule), it contains a "gitdir: <path>" line.
    This function reads that file and resolves the path.

    Args:
        git_path: Path to .git (file or directory)
        base_dir: The directory containing .git (for relative path resolution)

    Returns:
        The resolved .git directory path
    """
    if git_path.is_dir():
        return git_path

    # .git is a file - read and parse gitdir reference
    content = git_path.read_text().strip()
    if not content.startswith("gitdir:"):
        raise click.ClickException(f"Invalid .git file format: {git_path}")

    gitdir_value = content[len("gitdir:") :].strip()
    gitdir_path = Path(gitdir_value)

    # Resolve relative paths against the base directory
    if not gitdir_path.is_absolute():
        gitdir_path = (base_dir / gitdir_path).resolve()

    return gitdir_path


def _find_git_hooks_dir() -> Path:
    """Find the .git/hooks directory, handling worktrees and submodules."""
    git_path = Path(".git")
    base_dir = Path.cwd()

    if not git_path.exists():
        for parent in [base_dir] + list(base_dir.parents):
            if (parent / ".git").exists():
                git_path = parent / ".git"
                base_dir = parent
                break
        else:
            raise click.ClickException("Not in a git repository")

    git_dir = _resolve_gitdir(git_path, base_dir)
    return git_dir / "hooks"


@click.group("hooks")
def hooks_cmd() -> None:
    """Git hook management for automatic task sync."""
    pass


@hooks_cmd.command("install")
@click.option("--force", is_flag=True, help="Overwrite existing hooks")
def hooks_install(force: bool) -> None:
    """Install git hooks for automatic task sync.

    Installs hooks for:
    - pre-commit: Export tasks before commit
    - post-merge: Import tasks after pull/merge
    - post-checkout: Import tasks on branch switch
    """
    hooks_dir = _find_git_hooks_dir()
    hooks_dir.mkdir(exist_ok=True)

    installed = []
    skipped = []

    for hook_name, script in GIT_HOOK_SCRIPTS.items():
        hook_path = hooks_dir / hook_name

        if hook_path.exists() and not force:
            # Check if it's our hook
            content = hook_path.read_text()
            if "gobby tasks" in content.lower():
                skipped.append(f"{hook_name} (already installed)")
            else:
                skipped.append(f"{hook_name} (existing hook, use --force to overwrite)")
            continue

        hook_path.write_text(script)
        # Make executable (owner only)
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR)
        installed.append(hook_name)

    if installed:
        click.echo(f"Installed git hooks: {', '.join(installed)}")
    if skipped:
        click.echo(f"Skipped: {', '.join(skipped)}")
    if not installed and not skipped:
        click.echo("No hooks to install")


@hooks_cmd.command("uninstall")
def hooks_uninstall() -> None:
    """Remove gobby git hooks."""
    hooks_dir = _find_git_hooks_dir()
    removed = []

    for hook_name in GIT_HOOK_SCRIPTS.keys():
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text()
            if "gobby tasks" in content.lower():
                hook_path.unlink()
                removed.append(hook_name)

    if removed:
        click.echo(f"Removed git hooks: {', '.join(removed)}")
    else:
        click.echo("No gobby hooks found to remove")


@hooks_cmd.command("status")
def hooks_status() -> None:
    """Show status of gobby git hooks."""
    hooks_dir = _find_git_hooks_dir()
    click.echo(f"Git hooks directory: {hooks_dir}\n")

    for hook_name in GIT_HOOK_SCRIPTS.keys():
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            content = hook_path.read_text()
            if "gobby tasks" in content.lower():
                click.echo(f"  {hook_name}: installed (gobby)")
            else:
                click.echo(f"  {hook_name}: exists (not gobby)")
        else:
            click.echo(f"  {hook_name}: not installed")
