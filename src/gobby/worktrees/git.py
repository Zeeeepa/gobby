"""Git worktree operations manager."""

from __future__ import annotations

import logging
import subprocess  # nosec B404 - subprocess needed for git worktree operations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    path: str
    branch: str | None
    commit: str
    is_bare: bool = False
    is_detached: bool = False
    locked: bool = False
    prunable: bool = False


@dataclass
class WorktreeStatus:
    """Status of a worktree including changes and sync state."""

    has_uncommitted_changes: bool
    has_staged_changes: bool
    has_untracked_files: bool
    ahead: int  # Commits ahead of upstream
    behind: int  # Commits behind upstream
    branch: str | None
    commit: str | None


@dataclass
class GitOperationResult:
    """Result of a git operation."""

    success: bool
    message: str
    output: str | None = None
    error: str | None = None


class WorktreeGitManager:
    """
    Manager for git worktree operations.

    Provides methods to create, delete, and manage git worktrees.
    All operations are performed relative to a base repository path.
    """

    def __init__(self, repo_path: str | Path):
        """
        Initialize with base repository path.

        Args:
            repo_path: Path to the main git repository
        """
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

    def _run_git(
        self,
        args: list[str],
        cwd: str | Path | None = None,
        timeout: int = 30,
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

    def create_worktree(
        self,
        worktree_path: str | Path,
        branch_name: str,
        base_branch: str = "main",
        create_branch: bool = True,
    ) -> GitOperationResult:
        """
        Create a new git worktree.

        Args:
            worktree_path: Path where worktree will be created
            branch_name: Name of the branch for the worktree
            base_branch: Branch to base the new branch on (if create_branch=True)
            create_branch: Whether to create a new branch or use existing

        Returns:
            GitOperationResult with success status and message
        """
        worktree_path = Path(worktree_path)

        # Check if path already exists
        if worktree_path.exists():
            return GitOperationResult(
                success=False,
                message=f"Path already exists: {worktree_path}",
            )

        # Ensure parent directory exists
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if create_branch:
                # Create worktree with new branch based on base_branch
                # First, fetch to ensure we have latest refs
                fetch_result = self._run_git(["fetch", "origin", base_branch], timeout=60)
                if fetch_result.returncode != 0:
                    return GitOperationResult(
                        success=False,
                        message=f"Failed to fetch origin/{base_branch}: {fetch_result.stderr}",
                        error=fetch_result.stderr,
                    )

                # Create worktree with new branch
                result = self._run_git(
                    [
                        "worktree",
                        "add",
                        "-b",
                        branch_name,
                        str(worktree_path),
                        f"origin/{base_branch}",
                    ],
                    timeout=60,
                )
            else:
                # Use existing branch
                result = self._run_git(
                    ["worktree", "add", str(worktree_path), branch_name],
                    timeout=60,
                )

            if result.returncode == 0:
                return GitOperationResult(
                    success=True,
                    message=f"Created worktree at {worktree_path}",
                    output=result.stdout,
                )
            else:
                return GitOperationResult(
                    success=False,
                    message=f"Failed to create worktree: {result.stderr}",
                    error=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return GitOperationResult(
                success=False,
                message="Git command timed out",
            )
        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error creating worktree: {e}",
                error=str(e),
            )

    def delete_worktree(
        self,
        worktree_path: str | Path,
        force: bool = False,
        delete_branch: bool = False,
        branch_name: str | None = None,
    ) -> GitOperationResult:
        """
        Delete a git worktree.

        Args:
            worktree_path: Path to the worktree to delete
            force: Force removal even if dirty
            delete_branch: Also delete the associated branch
            branch_name: Optional explicit branch name (if not provided, attempts to discover)

        Returns:
            GitOperationResult with success status and message
        """
        worktree_path = Path(worktree_path)

        try:
            # Get branch name before removal (for optional branch deletion)
            if delete_branch and not branch_name:
                try:
                    status = self.get_worktree_status(worktree_path)
                    if status:
                        branch_name = status.branch
                except Exception:
                    # nosec B110 - ignore errors getting status, we just won't have the branch name
                    pass

            # Remove worktree
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(worktree_path))

            result = self._run_git(args, timeout=30)

            if result.returncode != 0:
                return GitOperationResult(
                    success=False,
                    message=f"Failed to remove worktree: {result.stderr}",
                    error=result.stderr,
                )

            # Optionally delete the branch
            if delete_branch and branch_name:
                branch_result = self._run_git(
                    ["branch", "-D" if force else "-d", branch_name],
                    timeout=10,
                )

                if branch_result.returncode != 0:
                    return GitOperationResult(
                        success=True,  # Worktree removed, but branch deletion failed
                        message=f"Worktree removed, but failed to delete branch: {branch_result.stderr}",
                        error=branch_result.stderr,
                    )

            return GitOperationResult(
                success=True,
                message=f"Deleted worktree at {worktree_path}"
                + (f" and branch {branch_name}" if delete_branch and branch_name else ""),
                output=result.stdout,
            )

        except subprocess.TimeoutExpired:
            return GitOperationResult(
                success=False,
                message="Git command timed out",
            )
        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error deleting worktree: {e}",
                error=str(e),
            )

    def sync_from_main(
        self,
        worktree_path: str | Path,
        base_branch: str = "main",
        strategy: Literal["rebase", "merge"] = "rebase",
    ) -> GitOperationResult:
        """
        Sync worktree with base branch.

        Args:
            worktree_path: Path to the worktree
            base_branch: Branch to sync from
            strategy: Sync strategy (rebase or merge)

        Returns:
            GitOperationResult with success status and message
        """
        worktree_path = Path(worktree_path)

        if not worktree_path.exists():
            return GitOperationResult(
                success=False,
                message=f"Worktree path does not exist: {worktree_path}",
            )

        try:
            # Fetch latest from origin
            fetch_result = self._run_git(
                ["fetch", "origin", base_branch],
                cwd=worktree_path,
                timeout=60,
            )
            if fetch_result.returncode != 0:
                return GitOperationResult(
                    success=False,
                    message=f"Failed to fetch: {fetch_result.stderr}",
                    error=fetch_result.stderr,
                )

            # Perform rebase or merge
            if strategy == "rebase":
                sync_result = self._run_git(
                    ["rebase", f"origin/{base_branch}"],
                    cwd=worktree_path,
                    timeout=120,
                )
            else:
                sync_result = self._run_git(
                    ["merge", f"origin/{base_branch}", "--no-edit"],
                    cwd=worktree_path,
                    timeout=120,
                )

            if sync_result.returncode != 0:
                # Check if there are conflicts
                if "CONFLICT" in sync_result.stdout or "CONFLICT" in sync_result.stderr:
                    return GitOperationResult(
                        success=False,
                        message=f"Sync failed due to conflicts. Run 'git {strategy} --abort' to cancel.",
                        error=sync_result.stderr or sync_result.stdout,
                    )
                return GitOperationResult(
                    success=False,
                    message=f"Failed to {strategy}: {sync_result.stderr}",
                    error=sync_result.stderr,
                )

            return GitOperationResult(
                success=True,
                message=f"Successfully synced with origin/{base_branch} using {strategy}",
                output=sync_result.stdout,
            )

        except subprocess.TimeoutExpired:
            return GitOperationResult(
                success=False,
                message="Git command timed out",
            )
        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error syncing worktree: {e}",
                error=str(e),
            )

    def get_worktree_status(
        self,
        worktree_path: str | Path,
    ) -> WorktreeStatus | None:
        """
        Get status of a worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            WorktreeStatus or None if path is not valid
        """
        worktree_path = Path(worktree_path)

        if not worktree_path.exists():
            return None

        try:
            # Get current branch
            branch_result = self._run_git(
                ["branch", "--show-current"],
                cwd=worktree_path,
                timeout=5,
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None

            # Get current commit
            commit_result = self._run_git(
                ["rev-parse", "--short", "HEAD"],
                cwd=worktree_path,
                timeout=5,
            )
            commit = commit_result.stdout.strip() if commit_result.returncode == 0 else None

            # Get status (porcelain for parsing)
            status_result = self._run_git(
                ["status", "--porcelain"],
                cwd=worktree_path,
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

            # Get ahead/behind count
            ahead = 0
            behind = 0

            if branch:
                # Try to get upstream info
                upstream_result = self._run_git(
                    ["rev-list", "--count", "--left-right", f"origin/{branch}...HEAD"],
                    cwd=worktree_path,
                    timeout=10,
                )
                if upstream_result.returncode == 0:
                    parts = upstream_result.stdout.strip().split("\t")
                    if len(parts) == 2:
                        behind = int(parts[0])
                        ahead = int(parts[1])

            return WorktreeStatus(
                has_uncommitted_changes=has_uncommitted,
                has_staged_changes=has_staged,
                has_untracked_files=has_untracked,
                ahead=ahead,
                behind=behind,
                branch=branch,
                commit=commit,
            )

        except Exception as e:
            logger.error(f"Error getting worktree status: {e}")
            return None

    def list_worktrees(self) -> list[WorktreeInfo]:
        """
        List all worktrees for this repository.

        Returns:
            List of WorktreeInfo objects
        """
        try:
            result = self._run_git(
                ["worktree", "list", "--porcelain"],
                timeout=10,
            )

            if result.returncode != 0:
                logger.error(f"Failed to list worktrees: {result.stderr}")
                return []

            worktrees = []
            current: dict[str, str | bool] = {}

            for line in result.stdout.split("\n"):
                if not line:
                    if current:
                        worktrees.append(
                            WorktreeInfo(
                                path=str(current.get("worktree", "")),
                                branch=current.get("branch"),  # type: ignore
                                commit=str(current.get("HEAD", "")),
                                is_bare=bool(current.get("bare")),
                                is_detached=bool(current.get("detached")),
                                locked=bool(current.get("locked")),
                                prunable=bool(current.get("prunable")),
                            )
                        )
                        current = {}
                    continue

                if line.startswith("worktree "):
                    current["worktree"] = line[9:]
                elif line.startswith("HEAD "):
                    current["HEAD"] = line[5:]
                elif line.startswith("branch "):
                    # refs/heads/branch-name -> branch-name
                    branch_ref = line[7:]
                    if branch_ref.startswith("refs/heads/"):
                        current["branch"] = branch_ref[11:]
                    else:
                        current["branch"] = branch_ref
                elif line == "bare":
                    current["bare"] = True
                elif line == "detached":
                    current["detached"] = True
                elif line.startswith("locked"):
                    current["locked"] = True
                elif line.startswith("prunable"):
                    current["prunable"] = True

            # Handle last entry
            if current:
                worktrees.append(
                    WorktreeInfo(
                        path=str(current.get("worktree", "")),
                        branch=current.get("branch"),  # type: ignore
                        commit=str(current.get("HEAD", "")),
                        is_bare=bool(current.get("bare")),
                        is_detached=bool(current.get("detached")),
                        locked=bool(current.get("locked")),
                        prunable=bool(current.get("prunable")),
                    )
                )

            return worktrees

        except Exception as e:
            logger.error(f"Error listing worktrees: {e}")
            return []

    def prune_worktrees(self) -> GitOperationResult:
        """
        Prune stale worktree entries.

        Returns:
            GitOperationResult with success status
        """
        try:
            result = self._run_git(["worktree", "prune"], timeout=30)

            if result.returncode == 0:
                return GitOperationResult(
                    success=True,
                    message="Pruned stale worktree entries",
                    output=result.stdout,
                )
            else:
                return GitOperationResult(
                    success=False,
                    message=f"Failed to prune: {result.stderr}",
                    error=result.stderr,
                )

        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error pruning worktrees: {e}",
                error=str(e),
            )

    def lock_worktree(
        self,
        worktree_path: str | Path,
        reason: str | None = None,
    ) -> GitOperationResult:
        """
        Lock a worktree to prevent accidental pruning.

        Args:
            worktree_path: Path to the worktree
            reason: Optional reason for locking

        Returns:
            GitOperationResult with success status
        """
        args = ["worktree", "lock", str(worktree_path)]
        if reason:
            args.extend(["--reason", reason])

        try:
            result = self._run_git(args, timeout=10)

            if result.returncode == 0:
                return GitOperationResult(
                    success=True,
                    message=f"Locked worktree at {worktree_path}",
                )
            else:
                return GitOperationResult(
                    success=False,
                    message=f"Failed to lock: {result.stderr}",
                    error=result.stderr,
                )

        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error locking worktree: {e}",
                error=str(e),
            )

    def unlock_worktree(self, worktree_path: str | Path) -> GitOperationResult:
        """
        Unlock a worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            GitOperationResult with success status
        """
        try:
            result = self._run_git(
                ["worktree", "unlock", str(worktree_path)],
                timeout=10,
            )

            if result.returncode == 0:
                return GitOperationResult(
                    success=True,
                    message=f"Unlocked worktree at {worktree_path}",
                )
            else:
                return GitOperationResult(
                    success=False,
                    message=f"Failed to unlock: {result.stderr}",
                    error=result.stderr,
                )

        except Exception as e:
            return GitOperationResult(
                success=False,
                message=f"Error unlocking worktree: {e}",
                error=str(e),
            )

    def get_default_branch(self) -> str:
        """
        Get the default branch for the repository.

        Tries multiple methods to detect the default branch:
        1. Check origin/HEAD symbolic ref (most reliable for cloned repos)
        2. Check for common default branch names (main, master, develop)
        3. Fall back to "main" if detection fails

        Returns:
            Default branch name (e.g., "main", "master", "develop")
        """
        # Method 1: Try to get the default branch from origin/HEAD
        try:
            result = self._run_git(
                ["symbolic-ref", "refs/remotes/origin/HEAD"],
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Output is like "refs/remotes/origin/main"
                ref = result.stdout.strip()
                if ref.startswith("refs/remotes/origin/"):
                    branch = ref[len("refs/remotes/origin/") :]
                    logger.debug(f"Detected default branch from origin/HEAD: {branch}")
                    return branch
        except Exception:
            pass  # nosec B110 - method 1 failed, try next method

        # Method 2: Check which common default branches exist
        for branch in ["main", "master", "develop"]:
            try:
                # Check if the branch exists locally or remotely
                result = self._run_git(
                    ["rev-parse", "--verify", f"refs/heads/{branch}"],
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.debug(f"Detected default branch from local ref: {branch}")
                    return branch

                # Check remote
                result = self._run_git(
                    ["rev-parse", "--verify", f"refs/remotes/origin/{branch}"],
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.debug(f"Detected default branch from remote ref: {branch}")
                    return branch
            except Exception:
                continue  # nosec B112 - try next branch if current one fails

        # Method 3: Fall back to "main"
        logger.debug("Could not detect default branch, falling back to 'main'")
        return "main"
