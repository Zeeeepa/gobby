"""Git clone operations manager.

Provides operations for managing full git clones, distinct from worktrees.
"""

from __future__ import annotations

import logging
import shutil
import subprocess  # nosec B404 - subprocess needed for git clone operations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class CloneStatus:
    """Status of a git clone including changes and sync state."""

    has_uncommitted_changes: bool
    has_staged_changes: bool
    has_untracked_files: bool
    branch: str | None
    commit: str | None


@dataclass
class GitOperationResult:
    """Result of a git operation."""

    success: bool
    message: str
    output: str | None = None
    error: str | None = None


class CloneGitManager:
    """
    Manager for git clone operations.

    Provides methods to shallow clone, sync, and delete git clones.
    Unlike worktrees which share a .git directory, clones are full
    repository copies suitable for isolated or cross-machine development.
    """

    def __init__(self, repo_path: str | Path):
        """
        Initialize with base repository path.

        Args:
            repo_path: Path to the reference repository (for getting remote URL)

        Raises:
            ValueError: If the repository path does not exist
        """
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

    def _run_git(
        self,
        args: list[str],
        cwd: str | Path | None = None,
        timeout: int = 60,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a git command.

        Args:
            args: Git command arguments (without 'git' prefix)
            cwd: Working directory (defaults to repo_path)
            timeout: Command timeout in seconds
            check: Raise exception on non-zero exit

        Returns:
            CompletedProcess with stdout/stderr
        """
        if cwd is None:
            cwd = self.repo_path

        cmd = ["git"] + args
        logger.debug(f"Running: {' '.join(cmd)} in {cwd}")

        try:
            result = subprocess.run(  # nosec B603 B607 - cmd built from hardcoded git arguments
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"Git command timed out: {' '.join(cmd)}")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {' '.join(cmd)}, stderr: {e.stderr}")
            raise

    def get_remote_url(self, remote: str = "origin") -> str | None:
        """
        Get the remote URL for the repository.

        Args:
            remote: Remote name (default: origin)

        Returns:
            Remote URL or None if not found
        """
        try:
            result = self._run_git(
                ["remote", "get-url", remote],
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def shallow_clone(
        self,
        remote_url: str,
        clone_path: str | Path,
        branch: str = "main",
        depth: int = 1,
    ) -> GitOperationResult:
        """
        Create a shallow clone of a repository.

        Args:
            remote_url: URL of the remote repository (HTTPS or SSH)
            clone_path: Path where clone will be created
            branch: Branch to clone
            depth: Clone depth (default: 1 for shallowest)

        Returns:
            GitOperationResult with success status and message
        """
        clone_path = Path(clone_path)

        # Check if path already exists
        if clone_path.exists():
            return GitOperationResult(
                success=False,
                message=f"Path already exists: {clone_path}",
            )

        # Ensure parent directory exists
        clone_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Build clone command
            cmd = [
                "git",
                "clone",
                "--depth",
                str(depth),
                "--single-branch",
                "-b",
                branch,
                remote_url,
                str(clone_path),
            ]

            logger.debug(f"Running: {' '.join(cmd)}")

            result = subprocess.run(  # nosec B603 B607 - cmd built from hardcoded git arguments
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for clone
            )

            if result.returncode == 0:
                return GitOperationResult(
                    success=True,
                    message=f"Successfully cloned to {clone_path}",
                    output=result.stdout,
                )
            else:
                return GitOperationResult(
                    success=False,
                    message=f"Clone failed: {result.stderr}",
                    error=result.stderr,
                )

        except subprocess.TimeoutExpired:
            # Clean up partial clone
            if clone_path.exists():
                shutil.rmtree(clone_path, ignore_errors=True)
            return GitOperationResult(
                success=False,
                message="Git clone timed out",
            )
        except Exception as e:
            # Clean up partial clone
            if clone_path.exists():
                shutil.rmtree(clone_path, ignore_errors=True)
            return GitOperationResult(
                success=False,
                message=f"Error cloning repository: {e}",
                error=str(e),
            )

    def sync_clone(
        self,
        clone_path: str | Path,
        direction: Literal["pull", "push", "both"] = "pull",
        remote: str = "origin",
    ) -> GitOperationResult:
        """
        Sync a clone with its remote.

        Args:
            clone_path: Path to the clone directory
            direction: Sync direction ("pull", "push", or "both")
            remote: Remote name (default: origin)

        Returns:
            GitOperationResult with success status and message
        """
        clone_path = Path(clone_path)

        if not clone_path.exists():
            return GitOperationResult(
                success=False,
                message=f"Clone path does not exist: {clone_path}",
            )

        try:
            if direction in ("pull", "both"):
                # Pull changes
                pull_result = self._run_git(
                    ["pull", remote],
                    cwd=clone_path,
                    timeout=120,
                )
                if pull_result.returncode != 0:
                    return GitOperationResult(
                        success=False,
                        message=f"Pull failed: {pull_result.stderr or pull_result.stdout}",
                        error=pull_result.stderr or pull_result.stdout,
                    )

            if direction in ("push", "both"):
                # Push changes
                push_result = self._run_git(
                    ["push", remote],
                    cwd=clone_path,
                    timeout=120,
                )
                if push_result.returncode != 0:
                    return GitOperationResult(
                        success=False,
                        message=f"Push failed: {push_result.stderr}",
                        error=push_result.stderr,
                    )

            return GitOperationResult(
                success=True,
                message=f"Successfully synced ({direction}) with {remote}",
            )

        except subprocess.TimeoutExpired:
            return GitOperationResult(
                success=False,
                message="Git sync timed out",
            )
        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error syncing clone: {e}",
                error=str(e),
            )

    def delete_clone(
        self,
        clone_path: str | Path,
        force: bool = False,
    ) -> GitOperationResult:
        """
        Delete a clone directory.

        Args:
            clone_path: Path to the clone directory
            force: Force deletion even if there are uncommitted changes

        Returns:
            GitOperationResult with success status and message
        """
        clone_path = Path(clone_path)

        if not clone_path.exists():
            return GitOperationResult(
                success=True,
                message=f"Clone already does not exist: {clone_path}",
            )

        try:
            # Check for uncommitted changes unless force
            if not force:
                status = self.get_clone_status(clone_path)
                if status and status.has_uncommitted_changes:
                    return GitOperationResult(
                        success=False,
                        message="Clone has uncommitted changes. Use force=True to delete anyway.",
                    )

            # Remove the directory
            shutil.rmtree(clone_path)

            return GitOperationResult(
                success=True,
                message=f"Deleted clone at {clone_path}",
            )

        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error deleting clone: {e}",
                error=str(e),
            )

    def get_clone_status(
        self,
        clone_path: str | Path,
    ) -> CloneStatus | None:
        """
        Get status of a clone.

        Args:
            clone_path: Path to the clone directory

        Returns:
            CloneStatus or None if path is not valid
        """
        clone_path = Path(clone_path)

        if not clone_path.exists():
            return None

        try:
            # Get current branch
            branch_result = self._run_git(
                ["branch", "--show-current"],
                cwd=clone_path,
                timeout=5,
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None

            # Get current commit
            commit_result = self._run_git(
                ["rev-parse", "--short", "HEAD"],
                cwd=clone_path,
                timeout=5,
            )
            commit = commit_result.stdout.strip() if commit_result.returncode == 0 else None

            # Get status (porcelain for parsing)
            status_result = self._run_git(
                ["status", "--porcelain"],
                cwd=clone_path,
                timeout=10,
            )

            has_staged = False
            has_uncommitted = False
            has_untracked = False

            if status_result.returncode == 0:
                for line in status_result.stdout.split("\n"):
                    if not line:
                        continue
                    index_status = line[0] if len(line) > 0 else " "
                    worktree_status = line[1] if len(line) > 1 else " "

                    if index_status != " " and index_status != "?":
                        has_staged = True
                    if worktree_status != " " and worktree_status != "?":
                        has_uncommitted = True
                    if index_status == "?" or worktree_status == "?":
                        has_untracked = True

            return CloneStatus(
                has_uncommitted_changes=has_uncommitted,
                has_staged_changes=has_staged,
                has_untracked_files=has_untracked,
                branch=branch,
                commit=commit,
            )

        except Exception as e:
            logger.error(f"Error getting clone status: {e}")
            return None
