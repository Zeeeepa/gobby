"""Git integrity verification for bundled content.

Detects modifications to bundled YAML/MD files (workflows, skills, prompts,
rules, agents) by checking git status of the shared content directory.

In dev mode (``is_dev_mode()``), integrity checks are skipped entirely —
file edits are expected.  In production mode, any git-tracked modifications
or untracked files in the shared directory are flagged as tampered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from gobby.utils.git import run_git_command

logger = logging.getLogger(__name__)

# Maps subdirectory names under install/shared/ to content type names
# used by sync_bundled_content_to_db's sync_targets.
CONTENT_TYPE_DIRS: dict[str, str] = {
    "skills": "skills",
    "prompts": "prompts",
    "rules": "rules",
    "agents": "agents",
    "workflows": "workflows",
}


@dataclass
class IntegrityResult:
    """Result of a bundled-content integrity check."""

    clean_files: list[str] = field(default_factory=list)
    dirty_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    git_available: bool = True

    @property
    def all_clean(self) -> bool:
        """True when no dirty or untracked files were found."""
        return not self.dirty_files and not self.untracked_files


def verify_bundled_integrity(install_dir: Path) -> IntegrityResult:
    """Verify git integrity of bundled content under *install_dir*/shared/.

    Checks for:
    - Modified tracked files (staged and unstaged) via ``git diff``
    - Untracked files via ``git ls-files --others``

    If *install_dir* is not inside a git repository (e.g. installed via
    package), returns ``git_available=False`` and sync proceeds normally.

    Args:
        install_dir: The ``src/gobby/install`` directory (parent of ``shared/``).

    Returns:
        An :class:`IntegrityResult` with lists of clean, dirty, and untracked
        files relative to the repo root.
    """
    result = IntegrityResult()
    shared_dir = install_dir / "shared"

    if not shared_dir.is_dir():
        result.errors.append(f"Shared directory not found: {shared_dir}")
        result.git_available = False
        return result

    # Find the repo root so we can scope git commands
    repo_root = run_git_command(["git", "rev-parse", "--show-toplevel"], cwd=shared_dir)
    if repo_root is None:
        # Not a git repo — installed package context
        result.git_available = False
        return result

    repo_root_path = Path(repo_root)

    # Relative path of shared/ from repo root for scoping git commands
    try:
        rel_shared = shared_dir.resolve().relative_to(repo_root_path.resolve())
    except ValueError:
        result.errors.append(f"Shared dir {shared_dir} is not under repo root {repo_root_path}")
        result.git_available = False
        return result

    rel_shared_str = str(rel_shared)

    # Only check the content-type subdirs (skills, prompts, rules, agents, workflows)
    content_dirs = [f"{rel_shared_str}/{d}" for d in CONTENT_TYPE_DIRS]

    # 1. Unstaged modifications
    unstaged = run_git_command(
        ["git", "diff", "--name-only", "HEAD", "--"] + content_dirs,
        cwd=repo_root,
    )

    # 2. Staged modifications
    staged = run_git_command(
        ["git", "diff", "--cached", "--name-only", "--"] + content_dirs,
        cwd=repo_root,
    )

    # 3. Untracked files
    untracked = run_git_command(
        ["git", "ls-files", "--others", "--exclude-standard", "--"] + content_dirs,
        cwd=repo_root,
    )

    dirty: set[str] = set()
    if unstaged:
        dirty.update(f.strip() for f in unstaged.splitlines() if f.strip())
    if staged:
        dirty.update(f.strip() for f in staged.splitlines() if f.strip())

    result.dirty_files = sorted(dirty)

    if untracked:
        result.untracked_files = sorted(f.strip() for f in untracked.splitlines() if f.strip())

    # Build clean file list from tracked files minus dirty ones
    all_tracked = run_git_command(
        ["git", "ls-files", "--"] + content_dirs,
        cwd=repo_root,
    )
    if all_tracked:
        all_set = {f.strip() for f in all_tracked.splitlines() if f.strip()}
        result.clean_files = sorted(all_set - dirty)

    return result


def get_dirty_content_types(dirty_files: list[str], install_dir: Path) -> set[str]:
    """Map dirty file paths to content type names.

    Given a list of paths relative to the repo root (as returned by
    :func:`verify_bundled_integrity`), determine which content types
    (``"workflows"``, ``"skills"``, etc.) are affected.

    Args:
        dirty_files: File paths relative to repo root.
        install_dir: The ``src/gobby/install`` directory.

    Returns:
        Set of content type names (e.g. ``{"workflows", "skills"}``).
    """
    shared_dir = install_dir / "shared"
    try:
        repo_root = run_git_command(["git", "rev-parse", "--show-toplevel"], cwd=shared_dir)
    except Exception:
        repo_root = None

    if repo_root is None:
        return set()

    repo_root_path = Path(repo_root)
    try:
        rel_shared = str(shared_dir.resolve().relative_to(repo_root_path.resolve()))
    except ValueError:
        return set()

    affected: set[str] = set()
    for fpath in dirty_files:
        # fpath is relative to repo root, e.g. "src/gobby/install/shared/workflows/foo.yaml"
        if not fpath.startswith(rel_shared + "/"):
            continue
        # Strip the shared prefix to get e.g. "workflows/foo.yaml"
        remainder = fpath[len(rel_shared) + 1 :]
        # First path component is the content-type directory
        subdir = remainder.split("/", 1)[0]
        if subdir in CONTENT_TYPE_DIRS:
            affected.add(CONTENT_TYPE_DIRS[subdir])

    return affected
