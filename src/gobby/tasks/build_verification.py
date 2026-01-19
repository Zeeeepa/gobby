"""Build verification for Task System V2.

Provides build/test command detection and execution before LLM validation.
"""

import logging
import subprocess  # nosec B404 - subprocess needed for build commands
from dataclasses import dataclass
from pathlib import Path

from gobby.tasks.validation_models import Issue, IssueSeverity, IssueType

logger = logging.getLogger(__name__)

# Default timeout for build commands (5 minutes)
DEFAULT_BUILD_TIMEOUT = 300


@dataclass
class BuildResult:
    """Result of a build verification check.

    Attributes:
        success: Whether the build/test command succeeded.
        skipped: Whether the build check was skipped.
        command: The command that was executed (if any).
        stdout: Standard output from the command.
        stderr: Standard error from the command.
        returncode: Exit code from the command.
        error: Error message if the command failed to run.
    """

    success: bool
    skipped: bool = False
    command: str | None = None
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    error: str | None = None

    def to_issue(self) -> Issue | None:
        """Convert a failed build result to a structured Issue.

        Returns:
            Issue object if build failed, None if successful.
        """
        if self.success:
            return None

        # Determine title based on error type
        error_lower = (self.error or "").lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            title = f"Build timeout: {self.command}"
            details = self.error or "Build timed out"
        else:
            title = f"Build failed: {self.command}"
            details = self.stderr or self.stdout or self.error or "Unknown error"

        return Issue(
            issue_type=IssueType.TEST_FAILURE,
            severity=IssueSeverity.BLOCKER,
            title=title,
            details=details,
            suggested_fix="Fix the failing tests or build errors before proceeding.",
        )


def detect_build_command(project_path: Path) -> str | None:
    """Auto-detect the appropriate build/test command for a project.

    Checks for common project configuration files and returns the
    corresponding test command.

    Args:
        project_path: Path to the project directory.

    Returns:
        Build/test command string, or None if not detected.
    """
    # Check in priority order
    if (project_path / "package.json").exists():
        return "npm test"

    if (project_path / "pyproject.toml").exists():
        return "uv run pytest"

    if (project_path / "Cargo.toml").exists():
        return "cargo test"

    if (project_path / "go.mod").exists():
        return "go test ./..."

    return None


def run_build_check(
    command: str,
    cwd: Path,
    timeout: int = DEFAULT_BUILD_TIMEOUT,
) -> BuildResult:
    """Execute a build/test command and return the result.

    Args:
        command: The build/test command to execute.
        cwd: Working directory for the command.
        timeout: Maximum execution time in seconds.

    Returns:
        BuildResult with command output and status.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,  # nosec B602 - build/test commands require shell features
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        return BuildResult(
            success=result.returncode == 0,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    except subprocess.TimeoutExpired:
        return BuildResult(
            success=False,
            command=command,
            error=f"Build timeout after {timeout} seconds",
        )

    except Exception as e:
        return BuildResult(
            success=False,
            command=command,
            error=str(e),
        )


class BuildVerifier:
    """Build verification manager.

    Handles build/test execution with configuration options for
    enabling/disabling and custom commands.
    """

    def __init__(
        self,
        enabled: bool = True,
        build_command: str | None = None,
        timeout: int = DEFAULT_BUILD_TIMEOUT,
    ):
        """Initialize BuildVerifier.

        Args:
            enabled: Whether build verification is enabled.
            build_command: Custom build command (auto-detected if None).
            timeout: Maximum execution time in seconds.
        """
        self.enabled = enabled
        self.build_command = build_command
        self.timeout = timeout

    def check(self, cwd: Path) -> BuildResult:
        """Run build verification check.

        Args:
            cwd: Working directory for the build command.

        Returns:
            BuildResult with command output and status.
        """
        # Skip if disabled
        if not self.enabled:
            return BuildResult(success=True, skipped=True)

        # Determine command to use
        command = self.build_command
        if command is None:
            command = detect_build_command(cwd)

        # Skip if no command detected
        if command is None:
            logger.debug(f"No build command detected for {cwd}, skipping")
            return BuildResult(success=True, skipped=True)

        # Run the build check
        logger.info(f"Running build check: {command}")
        return run_build_check(command, cwd, self.timeout)
