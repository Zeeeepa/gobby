"""Merge conflict resolver with tiered resolution strategy.

Implements a four-tier resolution strategy:
1. Git auto-merge (no conflicts)
2. Conflict-only AI resolution (sends only conflict hunks to LLM)
3. Full-file AI resolution (sends entire file for complex conflicts)
4. Human review fallback (marks as needs-human-review)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ResolutionTier(Enum):
    """Resolution strategy tiers, from fastest to most expensive."""

    GIT_AUTO = "git_auto"
    CONFLICT_ONLY_AI = "conflict_only_ai"
    FULL_FILE_AI = "full_file_ai"
    HUMAN_REVIEW = "human_review"


# Alias for spec compatibility
ResolutionStrategy = ResolutionTier


@dataclass
class MergeResult:
    """Result of a merge resolution attempt.

    Attributes:
        success: Whether the merge was fully resolved
        tier: The tier that completed the resolution (or escalated to)
        conflicts: List of conflicts found during merge
        resolved_files: List of files that were successfully resolved
        unresolved_conflicts: List of conflicts that could not be resolved
        needs_human_review: Whether manual intervention is required
    """

    success: bool
    tier: ResolutionTier
    conflicts: list[dict[str, Any]]
    resolved_files: list[str] = field(default_factory=list)
    unresolved_conflicts: list[dict[str, Any]] = field(default_factory=list)
    needs_human_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "tier": self.tier.value,
            "conflicts": self.conflicts,
            "resolved_files": self.resolved_files,
            "unresolved_conflicts": self.unresolved_conflicts,
            "needs_human_review": self.needs_human_review,
        }


# Alias for spec compatibility
ResolutionResult = MergeResult


class MergeResolver:
    """Merge conflict resolver with tiered strategy.

    Attempts resolution in order of increasing complexity/cost:
    1. Git auto-merge
    2. Conflict-only AI resolution
    3. Full-file AI resolution
    4. Human review fallback
    """

    def __init__(
        self,
        conflict_size_threshold: int = 100,
        max_parallel_files: int = 5,
    ):
        """Initialize MergeResolver.

        Args:
            conflict_size_threshold: Lines of conflict above which to escalate to full-file
            max_parallel_files: Maximum files to resolve in parallel
        """
        self.conflict_size_threshold = conflict_size_threshold
        self.max_parallel_files = max_parallel_files
        self._llm_service = None  # LLM service integration point

    async def resolve_file(
        self,
        path: Path | str,
        conflict_hunks: list[Any],
    ) -> "ResolutionResult":
        """Resolve conflicts in a single file using tiered strategy.

        Args:
            path: Path to the file with conflicts
            conflict_hunks: List of ConflictHunk objects or conflict dicts

        Returns:
            ResolutionResult with resolution status
        """
        file_path = str(path) if isinstance(path, Path) else path

        # Convert hunks to conflict dict format
        conflict = {
            "file": file_path,
            "hunks": conflict_hunks,
        }

        # Check if conflict is too large for conflict-only resolution
        total_lines = sum(
            len(getattr(h, "ours", "").split("\n")) + len(getattr(h, "theirs", "").split("\n"))
            if hasattr(h, "ours")
            else 0
            for h in conflict_hunks
        )

        # Tier 2: Try conflict-only if under threshold
        if total_lines <= self.conflict_size_threshold:
            result = await self._resolve_conflicts_only([conflict])
            if result["success"]:
                return ResolutionResult(
                    success=True,
                    tier=ResolutionTier.CONFLICT_ONLY_AI,
                    conflicts=[conflict],
                    resolved_files=[file_path],
                    unresolved_conflicts=[],
                    needs_human_review=False,
                )

        # Tier 3: Full-file resolution
        result = await self._resolve_full_file([conflict])
        if result["success"]:
            return ResolutionResult(
                success=True,
                tier=ResolutionTier.FULL_FILE_AI,
                conflicts=[conflict],
                resolved_files=[file_path],
                unresolved_conflicts=[],
                needs_human_review=False,
            )

        # Tier 4: Human review fallback
        return ResolutionResult(
            success=False,
            tier=ResolutionTier.HUMAN_REVIEW,
            conflicts=[conflict],
            resolved_files=[],
            unresolved_conflicts=[conflict],
            needs_human_review=True,
        )

    async def resolve(
        self,
        worktree_path: str,
        source_branch: str,
        target_branch: str,
        force_tier: ResolutionTier | None = None,
    ) -> MergeResult:
        """Resolve merge conflicts using tiered strategy.

        Args:
            worktree_path: Path to the git worktree
            source_branch: Branch being merged in
            target_branch: Target branch (e.g., main)
            force_tier: Optional tier to force (skips lower tiers)

        Returns:
            MergeResult with resolution status and details
        """
        # Tier 1: Git auto-merge (unless forcing a higher tier)
        if force_tier is None or force_tier == ResolutionTier.GIT_AUTO:
            git_result = await self._git_merge(worktree_path, source_branch, target_branch)

            if git_result["success"]:
                return MergeResult(
                    success=True,
                    tier=ResolutionTier.GIT_AUTO,
                    conflicts=[],
                    resolved_files=[],
                    unresolved_conflicts=[],
                    needs_human_review=False,
                )

            conflicts = git_result.get("conflicts", [])
        else:
            # Skipping git merge, assume conflicts exist
            conflicts = []

        # If forcing full-file AI, skip tier 2
        if force_tier == ResolutionTier.FULL_FILE_AI:
            return await self._try_full_file_resolution(worktree_path, conflicts or [{}])

        # Tier 2: Conflict-only AI resolution
        if conflicts:
            tier2_result = await self._resolve_conflicts_only(conflicts)

            if tier2_result["success"]:
                return MergeResult(
                    success=True,
                    tier=ResolutionTier.CONFLICT_ONLY_AI,
                    conflicts=conflicts,
                    resolved_files=[c.get("file", "") for c in conflicts],
                    unresolved_conflicts=[],
                    needs_human_review=False,
                )

            # Tier 3: Full-file AI resolution
            return await self._try_full_file_resolution(worktree_path, conflicts)

        # No conflicts from git, but no git result - unusual state
        return MergeResult(
            success=True,
            tier=ResolutionTier.GIT_AUTO,
            conflicts=[],
            resolved_files=[],
            unresolved_conflicts=[],
            needs_human_review=False,
        )

    async def _try_full_file_resolution(
        self,
        worktree_path: str,
        conflicts: list[dict[str, Any]],
    ) -> MergeResult:
        """Attempt Tier 3 full-file resolution, fallback to human review."""
        tier3_result = await self._resolve_full_file(conflicts)

        if tier3_result["success"]:
            return MergeResult(
                success=True,
                tier=ResolutionTier.FULL_FILE_AI,
                conflicts=conflicts,
                resolved_files=[c.get("file", "") for c in conflicts],
                unresolved_conflicts=[],
                needs_human_review=False,
            )

        # Tier 4: Human review fallback
        return MergeResult(
            success=False,
            tier=ResolutionTier.HUMAN_REVIEW,
            conflicts=conflicts,
            resolved_files=[],
            unresolved_conflicts=conflicts,
            needs_human_review=True,
        )

    async def _git_merge(
        self,
        worktree_path: str,
        source_branch: str,
        target_branch: str,
    ) -> dict[str, Any]:
        """Attempt git auto-merge.

        Args:
            worktree_path: Path to git worktree
            source_branch: Branch to merge in
            target_branch: Target branch

        Returns:
            Dict with 'success' bool and 'conflicts' list if any
        """
        # This would be implemented with actual git commands
        # For now, return a placeholder that tests can mock
        return {"success": False, "conflicts": []}

    async def _resolve_conflicts_only(
        self,
        conflicts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Resolve conflicts by sending only conflict hunks to LLM.

        Args:
            conflicts: List of conflict dicts with hunks

        Returns:
            Dict with 'success' bool and 'resolutions' list
        """
        # This would be implemented with LLM service integration
        # For now, return a placeholder that tests can mock
        return {"success": False, "resolutions": []}

    async def _resolve_full_file(
        self,
        conflicts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Resolve conflicts by sending full file content to LLM.

        Args:
            conflicts: List of conflict dicts

        Returns:
            Dict with 'success' bool and 'resolutions' list
        """
        # This would be implemented with LLM service integration
        # For now, return a placeholder that tests can mock
        return {"success": False, "resolutions": []}

    async def _resolve_file_conflict(
        self,
        conflict: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve a single file's conflicts.

        Args:
            conflict: Conflict dict for one file

        Returns:
            Dict with 'success' bool
        """
        # Try conflict-only first
        result = await self._resolve_conflicts_only([conflict])
        if result["success"]:
            return {"success": True}

        # Escalate to full-file
        result = await self._resolve_full_file([conflict])
        return result

    async def resolve_conflicts_parallel(
        self,
        worktree_path: str,
        conflicts: list[dict[str, Any]],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Resolve multiple file conflicts in parallel.

        Args:
            worktree_path: Path to git worktree
            conflicts: List of conflicts to resolve

        Returns:
            Tuple of (resolved_files, unresolved_conflicts)
        """
        semaphore = asyncio.Semaphore(self.max_parallel_files)

        async def resolve_with_limit(conflict: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                result = await self._resolve_file_conflict(conflict)
                return {"conflict": conflict, "result": result}

        tasks = [resolve_with_limit(c) for c in conflicts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        resolved_files: list[str] = []
        unresolved: list[dict[str, Any]] = []

        for r in results:
            if isinstance(r, BaseException):
                logger.error(f"Error resolving conflict: {r}")
                continue

            # r is now dict[str, Any] after the isinstance check
            result_dict: dict[str, Any] = r
            if result_dict["result"].get("success"):
                resolved_files.append(result_dict["conflict"].get("file", ""))
            else:
                unresolved.append(result_dict["conflict"])

        return resolved_files, unresolved
