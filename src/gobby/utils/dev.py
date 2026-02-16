"""Dev mode detection utility."""

from pathlib import Path


def is_dev_mode(project_path: Path | None = None) -> bool:
    """Detect if running inside the gobby source repo.

    When the project IS the gobby source repo, bundled resources are editable
    directly (no copies needed). This is used to gate write access to
    scope='bundled' records in the database.

    Args:
        project_path: Path to check (defaults to cwd)

    Returns:
        True if the path is inside the gobby source repo
    """
    path = project_path or Path.cwd()
    return (path / "src" / "gobby" / "install" / "shared").is_dir()
