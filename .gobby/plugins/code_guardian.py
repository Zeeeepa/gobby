"""
Code Guardian Plugin - Example Gobby Plugin

This plugin demonstrates the full capabilities of the Gobby plugin system:
- Hook handlers for BEFORE_TOOL and AFTER_TOOL events
- Event blocking for code quality enforcement
- Auto-fix capabilities with ruff
- Workflow actions and conditions for integration with workflows

Installation:
    1. Copy this file to ~/.gobby/plugins/code_guardian.py
    2. Enable in ~/.gobby/config.yaml:
       hook_extensions:
         plugins:
           enabled: true
           plugins:
             code-guardian:
               enabled: true
               config:
                 checks: [ruff, mypy]
                 block_on_error: true
                 auto_fix: true
    3. Restart gobby daemon: gobby stop && gobby start

Configuration Options:
    checks: list[str] - Enabled checkers ("ruff", "mypy")
    block_on_error: bool - Block Edit/Write on lint failures (default: true)
    auto_fix: bool - Auto-format with ruff before blocking (default: true)
    file_patterns: list[str] - Glob patterns for files to check (default: ["*.py"])
    ignore_paths: list[str] - Paths to skip (default: [".venv", "__pycache__"])
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - subprocess needed for code linting commands
from pathlib import Path
from typing import Any

from gobby.hooks.events import HookEvent, HookEventType, HookResponse
from gobby.hooks.plugins import HookPlugin, hook_handler


class CodeGuardianPlugin(HookPlugin):
    """
    Enforces code quality by running linters on file modifications.

    Pre-handlers (priority 10) intercept Edit/Write tools and run checks.
    Post-handlers (priority 60) log results and can inject context.
    """

    name = "code-guardian"
    version = "1.0.0"
    description = "Code quality guardian - runs linters on file changes"

    def __init__(self) -> None:
        super().__init__()
        # Configuration with defaults
        self.checks: list[str] = ["ruff"]
        self.block_on_error: bool = True
        self.auto_fix: bool = True
        self.file_patterns: list[str] = ["*.py"]
        self.ignore_paths: list[str] = [".venv", "__pycache__", "node_modules"]
        # Rules to exclude from auto-fix (F401=unused imports, F811=redefinition)
        # These are commonly "wrong" during multi-step refactoring
        self.auto_fix_exclude_rules: list[str] = ["F401", "F811"]

        # State tracking
        self._last_check_results: dict[str, Any] = {}
        self._files_checked: int = 0
        self._files_blocked: int = 0

    def on_load(self, config: dict[str, Any]) -> None:
        """Initialize plugin with configuration."""
        self.checks = config.get("checks", self.checks)
        self.block_on_error = config.get("block_on_error", self.block_on_error)
        self.auto_fix = config.get("auto_fix", self.auto_fix)
        self.file_patterns = config.get("file_patterns", self.file_patterns)
        self.ignore_paths = config.get("ignore_paths", self.ignore_paths)
        self.auto_fix_exclude_rules = config.get(
            "auto_fix_exclude_rules", self.auto_fix_exclude_rules
        )

        self.logger.info(
            f"Code Guardian loaded: checks={self.checks}, "
            f"block_on_error={self.block_on_error}, auto_fix={self.auto_fix}"
        )

        # Register workflow actions
        self.register_action("run_linter", self._action_run_linter)
        self.register_action("format_code", self._action_format_code)

        # Register workflow conditions
        self.register_condition("passes_lint", self._condition_passes_lint)
        self.register_condition("has_type_errors", self._condition_has_type_errors)

    def on_unload(self) -> None:
        """Cleanup on plugin unload."""
        self.logger.info(
            f"Code Guardian stats: checked={self._files_checked}, blocked={self._files_blocked}"
        )

    # =========================================================================
    # Hook Handlers
    # =========================================================================

    @hook_handler(HookEventType.BEFORE_TOOL, priority=10)
    def check_before_write(self, event: HookEvent) -> HookResponse | None:
        """
        Pre-handler: Intercept Edit/Write tools and run linters.

        Returns HookResponse with decision="deny" to block the tool,
        or None to allow it to proceed.
        """
        tool_name = event.data.get("tool_name", "")
        tool_input = event.data.get("tool_input", {})

        # Only intercept Edit and Write tools
        if tool_name not in ("Edit", "Write"):
            return None

        # Get the file path being modified
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return None

        path = Path(file_path)

        # Skip non-Python files (or files not matching patterns)
        if not self._should_check_file(path):
            return None

        # For Write tool, we check the content being written
        # For Edit tool, the file will be modified - we check after
        if tool_name == "Write":
            content = tool_input.get("content", "")
            return self._check_content(path, content)

        # For Edit, we'll check in the post-handler after the edit is applied
        return None

    @hook_handler(HookEventType.AFTER_TOOL, priority=60)
    def report_after_tool(self, event: HookEvent, core_response: HookResponse | None) -> None:
        """
        Post-handler: Log results and track statistics.

        Post-handlers receive both the event and the core response.
        They cannot block; return value is ignored.
        """
        tool_name = event.data.get("tool_name", "")
        tool_input = event.data.get("tool_input", {})

        # Only care about Edit/Write
        if tool_name not in ("Edit", "Write"):
            return

        file_path = tool_input.get("file_path", "")
        if not file_path:
            return

        path = Path(file_path)
        if not self._should_check_file(path):
            return

        # For Edit tool, run checks on the modified file
        if tool_name == "Edit" and path.exists():
            self._files_checked += 1
            errors = self._run_checks(path)

            if errors:
                self._last_check_results[str(path)] = {
                    "status": "failed",
                    "errors": errors,
                }
                self.logger.warning(f"Post-edit lint issues in {path.name}: {len(errors)} error(s)")

                # Try auto-fix if enabled
                if self.auto_fix and "ruff" in self.checks:
                    self._run_ruff_fix(path)
            else:
                self._last_check_results[str(path)] = {"status": "passed"}

    # =========================================================================
    # Check Logic
    # =========================================================================

    def _should_check_file(self, path: Path) -> bool:
        """Determine if a file should be checked."""
        # Check file patterns
        matches_pattern = any(path.match(pattern) for pattern in self.file_patterns)
        if not matches_pattern:
            return False

        # Check ignore paths
        path_str = str(path)
        for ignore in self.ignore_paths:
            if ignore in path_str:
                return False

        return True

    def _check_content(self, path: Path, content: str) -> HookResponse | None:
        """
        Check content before it's written to a file.

        For Write operations, we validate the content syntax/style
        before allowing the write.
        """
        self._files_checked += 1

        # For syntax checking content before write, we'd need to write to a temp file
        # For simplicity, we'll check after the file is written in post-handler
        # But we can do basic checks here

        # Check for obvious issues (placeholder for real checks)
        issues: list[str] = []

        # Example: Check for debug prints
        if "print(" in content and "def " in content:
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.lstrip()
                if stripped.startswith("print(") and "# noqa" not in line:
                    issues.append(f"Line {i}: Debug print statement found")

        if issues and self.block_on_error:
            self._files_blocked += 1
            return HookResponse(
                decision="deny",
                reason=f"Code Guardian blocked write: {len(issues)} issue(s) found",
                metadata={
                    "plugin": self.name,
                    "issues": issues[:5],  # Limit to first 5
                    "file": str(path),
                },
            )

        return None

    def _run_checks(self, path: Path) -> list[str]:
        """Run configured checkers on a file."""
        errors: list[str] = []

        if "ruff" in self.checks:
            errors.extend(self._run_ruff_check(path))

        if "mypy" in self.checks:
            errors.extend(self._run_mypy_check(path))

        return errors

    def _run_ruff_check(self, path: Path) -> list[str]:
        """Run ruff linter on a file."""
        if not shutil.which("ruff"):
            self.logger.debug("ruff not found in PATH, skipping")
            return []

        try:
            result = subprocess.run(  # nosec B603 B607 - hardcoded ruff command
                ["ruff", "check", "--output-format=concise", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0 and result.stdout:
                return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]

        except subprocess.TimeoutExpired:
            self.logger.warning(f"ruff timed out on {path}")
        except Exception as e:
            self.logger.error(f"ruff check failed: {e}")

        return []

    def _run_ruff_fix(self, path: Path) -> bool:
        """Run ruff --fix on a file, excluding configured rules."""
        if not shutil.which("ruff"):
            return False

        try:
            # Build command with excluded rules
            cmd = ["ruff", "check", "--fix"]
            for rule in self.auto_fix_exclude_rules:
                cmd.extend(["--ignore", rule])
            cmd.append(str(path))

            result = subprocess.run(  # nosec B603 - cmd built from hardcoded ruff arguments
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                self.logger.info(f"ruff auto-fixed {path.name}")
                return True

        except Exception as e:
            self.logger.error(f"ruff fix failed: {e}")

        return False

    def _run_mypy_check(self, path: Path) -> list[str]:
        """Run mypy type checker on a file."""
        if not shutil.which("mypy"):
            self.logger.debug("mypy not found in PATH, skipping")
            return []

        try:
            result = subprocess.run(  # nosec B603 B607 - hardcoded mypy command
                ["mypy", "--no-error-summary", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0 and result.stdout:
                return [
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip() and ": error:" in line
                ]

        except subprocess.TimeoutExpired:
            self.logger.warning(f"mypy timed out on {path}")
        except Exception as e:
            self.logger.error(f"mypy check failed: {e}")

        return []

    # =========================================================================
    # Workflow Actions
    # =========================================================================

    async def _action_run_linter(
        self,
        context: dict[str, Any],
        files: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Workflow action: Run linter on specified files.

        Usage in workflow YAML:
            - action: plugin:code-guardian:run_linter
              files: ["src/main.py", "src/utils.py"]

        Args:
            context: Workflow context
            files: List of file paths to check (optional, uses context if not provided)

        Returns:
            Dict with results: {"passed": bool, "errors": list, "files_checked": int}
        """
        target_files = files or context.get("files", [])
        all_errors: list[str] = []
        checked = 0

        for file_path in target_files:
            path = Path(file_path)
            if path.exists() and self._should_check_file(path):
                errors = self._run_checks(path)
                all_errors.extend(errors)
                checked += 1

        return {
            "passed": len(all_errors) == 0,
            "errors": all_errors,
            "files_checked": checked,
        }

    async def _action_format_code(
        self,
        context: dict[str, Any],
        files: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Workflow action: Format code files with ruff.

        Usage in workflow YAML:
            - action: plugin:code-guardian:format_code
              files: ["src/"]

        Args:
            context: Workflow context
            files: List of file/directory paths to format

        Returns:
            Dict with results: {"formatted": int, "errors": list}
        """
        target_files = files or context.get("files", [])
        formatted = 0
        errors: list[str] = []

        if not shutil.which("ruff"):
            return {"formatted": 0, "errors": ["ruff not found in PATH"]}

        for file_path in target_files:
            path = Path(file_path)
            try:
                result = subprocess.run(  # nosec B603 B607 - hardcoded ruff command
                    ["ruff", "format", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    formatted += 1
                else:
                    errors.append(f"{path}: {result.stderr.strip()}")
            except Exception as e:
                errors.append(f"{path}: {e}")

        return {"formatted": formatted, "errors": errors}

    # =========================================================================
    # Workflow Conditions
    # =========================================================================

    def _condition_passes_lint(self, file_path: str | None = None) -> bool:
        """
        Workflow condition: Check if file(s) pass linting.

        Usage in workflow YAML:
            when: "plugin_code_guardian_passes_lint()"

        Note: Condition names are transformed to use underscores when registered.
        """
        if file_path:
            result = self._last_check_results.get(file_path)
            return result is not None and result.get("status") == "passed"

        # If no specific file, check if any recent checks failed
        for result in self._last_check_results.values():
            if result.get("status") == "failed":
                return False
        return True

    def _condition_has_type_errors(self, file_path: str | None = None) -> bool:
        """
        Workflow condition: Check if file has type errors (mypy).

        Usage in workflow YAML:
            when: "plugin_code_guardian_has_type_errors()"
        """
        if file_path:
            path = Path(file_path)
            if path.exists():
                errors = self._run_mypy_check(path)
                return len(errors) > 0
        return False


# For dynamic discovery, the class must be importable
__all__ = ["CodeGuardianPlugin"]
