"""
Task validation module.

Handles validating task completion against acceptance criteria
using LLM providers.

Multi-strategy context gathering:
1. Current uncommitted changes (staged + unstaged)
2. Multi-commit window (last N commits, configurable)
3. File-based analysis (read files mentioned in criteria)
4. Codebase grep for test files related to the task
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gobby.config.app import TaskValidationConfig
from gobby.llm import LLMService

logger = logging.getLogger(__name__)

# Default number of commits to look back when gathering context
DEFAULT_COMMIT_WINDOW = 10
DEFAULT_MAX_CHARS = 50000


def get_last_commit_diff(max_chars: int = DEFAULT_MAX_CHARS) -> str | None:
    """Get diff from the most recent commit.

    Args:
        max_chars: Maximum characters to return (truncates if larger)

    Returns:
        Diff string from HEAD~1..HEAD, or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1..HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        diff = result.stdout
        if len(diff) > max_chars:
            diff = diff[:max_chars] + "\n\n... [diff truncated] ..."

        return diff

    except Exception as e:
        logger.debug(f"Failed to get last commit diff: {e}")
        return None


def get_recent_commits(n: int = DEFAULT_COMMIT_WINDOW) -> list[dict[str, str]]:
    """Get list of recent commits with SHA and subject.

    Args:
        n: Number of commits to retrieve

    Returns:
        List of dicts with 'sha' and 'subject' keys
    """
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--pretty=format:%H|%s"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                sha, subject = line.split("|", 1)
                commits.append({"sha": sha, "subject": subject})

        return commits

    except Exception as e:
        logger.debug(f"Failed to get recent commits: {e}")
        return []


def get_multi_commit_diff(
    commit_count: int = DEFAULT_COMMIT_WINDOW,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """Get combined diff from the last N commits.

    Args:
        commit_count: Number of commits to include in diff
        max_chars: Maximum characters to return

    Returns:
        Combined diff string, or None if not available
    """
    try:
        # Get diff from HEAD~N to HEAD
        result = subprocess.run(
            ["git", "diff", f"HEAD~{commit_count}..HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        diff = result.stdout
        if len(diff) > max_chars:
            diff = diff[:max_chars] + "\n\n... [diff truncated] ..."

        return diff

    except Exception as e:
        logger.debug(f"Failed to get multi-commit diff: {e}")
        return None


def get_commits_since(since_sha: str, max_chars: int = DEFAULT_MAX_CHARS) -> str | None:
    """Get diff from a specific commit SHA to HEAD.

    Args:
        since_sha: Starting commit SHA
        max_chars: Maximum characters to return

    Returns:
        Diff string, or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "diff", f"{since_sha}..HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        diff = result.stdout
        if len(diff) > max_chars:
            diff = diff[:max_chars] + "\n\n... [diff truncated] ..."

        return diff

    except Exception as e:
        logger.debug(f"Failed to get commits since {since_sha}: {e}")
        return None


def extract_file_patterns_from_text(text: str) -> list[str]:
    """Extract file paths and patterns from text (criteria, description, title).

    Looks for:
    - Explicit file paths (src/foo/bar.py, tests/test_foo.py)
    - Module references (gobby.tasks.validation -> src/gobby/tasks/validation.py)
    - Test patterns (test_validation -> tests/**/test_validation*.py)

    Args:
        text: Text to search for file patterns

    Returns:
        List of file path patterns (may include globs)
    """
    patterns: set[str] = set()

    # Match explicit file paths like src/foo/bar.py or ./tests/test_x.py
    file_path_re = re.compile(r'[./]?[\w\-]+(?:/[\w\-]+)*\.\w+')
    for match in file_path_re.findall(text):
        # Skip URLs and common false positives
        if not match.startswith("http") and not match.startswith("www."):
            patterns.add(match.lstrip("./"))

    # Match module references like gobby.tasks.validation
    module_re = re.compile(r'\b(gobby(?:\.\w+)+)\b')
    for match in module_re.findall(text):
        # Convert module path to file path
        file_path = "src/" + match.replace(".", "/") + ".py"
        patterns.add(file_path)

    # Extract test file hints from test_ prefixed words
    test_re = re.compile(r'\btest_(\w+)\b')
    for match in test_re.findall(text):
        patterns.add(f"tests/**/test_{match}*.py")

    # Extract class/function names and look for their definitions
    class_re = re.compile(r'\b([A-Z][a-zA-Z0-9]+(?:Manager|Validator|Plugin|Handler|Service))\b')
    for match in class_re.findall(text):
        # These could be in any .py file, add as grep pattern hint
        patterns.add(f"**/{''.join(c if c.islower() else '_' + c.lower() for c in match).lstrip('_')}*.py")

    return list(patterns)


def find_matching_files(
    patterns: list[str],
    base_dir: str | Path = ".",
    max_files: int = 10,
) -> list[Path]:
    """Find files matching the given patterns.

    Args:
        patterns: List of file path patterns (may include globs)
        base_dir: Base directory to search from
        max_files: Maximum number of files to return

    Returns:
        List of Path objects for matching files
    """
    base = Path(base_dir)
    found: list[Path] = []

    for pattern in patterns:
        if len(found) >= max_files:
            break

        # Handle glob patterns
        if "*" in pattern:
            try:
                matches = list(base.glob(pattern))
                for match in matches[:max_files - len(found)]:
                    if match.is_file() and match not in found:
                        found.append(match)
            except Exception as e:
                logger.debug(f"Failed to glob pattern {pattern}: {e}")
        else:
            # Direct file path
            path = base / pattern
            if path.is_file() and path not in found:
                found.append(path)

    return found


def read_files_content(
    files: list[Path],
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Read content from multiple files.

    Args:
        files: List of file paths to read
        max_chars: Maximum total characters to return

    Returns:
        Concatenated file contents with headers
    """
    content_parts: list[str] = []
    total_chars = 0

    for file_path in files:
        if total_chars >= max_chars:
            content_parts.append("\n... [additional files truncated] ...")
            break

        try:
            content = file_path.read_text(encoding="utf-8")
            remaining = max_chars - total_chars

            if len(content) > remaining:
                content = content[:remaining] + "\n... [file truncated] ..."

            content_parts.append(f"=== {file_path} ===\n{content}\n")
            total_chars += len(content)

        except Exception as e:
            logger.debug(f"Failed to read {file_path}: {e}")
            content_parts.append(f"=== {file_path} ===\n(Error reading file: {e})\n")

    return "\n".join(content_parts)


def get_validation_context_smart(
    task_title: str,
    validation_criteria: str | None = None,
    task_description: str | None = None,
    commit_window: int = DEFAULT_COMMIT_WINDOW,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """Gather validation context using multiple strategies.

    Strategies (in order):
    1. Current uncommitted changes (staged + unstaged)
    2. Multi-commit window diff (last N commits)
    3. File-based analysis (read files mentioned in criteria)

    Args:
        task_title: Task title for context
        validation_criteria: Validation criteria text
        task_description: Task description text
        commit_window: Number of commits to look back
        max_chars: Maximum characters to return

    Returns:
        Validation context string, or None if nothing found
    """
    context_parts: list[str] = []
    remaining_chars = max_chars

    # Strategy 1: Current uncommitted changes
    try:
        unstaged = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        staged = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if staged.stdout.strip():
            content = staged.stdout[:remaining_chars // 2]
            context_parts.append(f"=== STAGED CHANGES ===\n{content}")
            remaining_chars -= len(content)

        if unstaged.stdout.strip():
            content = unstaged.stdout[:remaining_chars // 2]
            context_parts.append(f"=== UNSTAGED CHANGES ===\n{content}")
            remaining_chars -= len(content)

    except Exception as e:
        logger.debug(f"Failed to get uncommitted changes: {e}")

    # Strategy 2: Multi-commit window
    if remaining_chars > 5000:  # Only if we have room
        multi_diff = get_multi_commit_diff(commit_window, remaining_chars // 2)
        if multi_diff:
            # Get commit list for context
            commits = get_recent_commits(commit_window)
            commit_summary = "\n".join(
                f"  - {c['sha'][:8]}: {c['subject'][:60]}" for c in commits[:5]
            )

            context_parts.append(
                f"=== RECENT COMMITS (last {commit_window}) ===\n"
                f"{commit_summary}\n\n"
                f"=== COMBINED DIFF ===\n{multi_diff}"
            )
            remaining_chars -= len(multi_diff) + len(commit_summary)

    # Strategy 3: File-based analysis
    if remaining_chars > 2000:
        # Extract file patterns from task info
        search_text = f"{task_title} {validation_criteria or ''} {task_description or ''}"
        patterns = extract_file_patterns_from_text(search_text)

        if patterns:
            files = find_matching_files(patterns, max_files=5)
            if files:
                file_content = read_files_content(files, remaining_chars)
                context_parts.append(f"=== RELEVANT FILES ===\n{file_content}")

    if not context_parts:
        return None

    combined = "\n\n".join(context_parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n... [context truncated] ..."

    return combined


def get_git_diff(max_chars: int = 50000, fallback_to_last_commit: bool = True) -> str | None:
    """Get changes from git for validation.

    First checks for uncommitted changes (staged + unstaged).
    If none found and fallback_to_last_commit is True, returns the last commit's diff.

    Args:
        max_chars: Maximum characters to return (truncates if larger)
        fallback_to_last_commit: If True, fall back to last commit diff when no uncommitted changes

    Returns:
        Combined diff string, or None if not in git repo or no changes
    """
    try:
        # Get unstaged changes
        unstaged = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Get staged changes
        staged = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if unstaged.returncode != 0 and staged.returncode != 0:
            return None

        diff_parts = []
        if staged.stdout.strip():
            diff_parts.append("=== STAGED CHANGES ===\n" + staged.stdout)
        if unstaged.stdout.strip():
            diff_parts.append("=== UNSTAGED CHANGES ===\n" + unstaged.stdout)

        # If no uncommitted changes, try last commit
        if not diff_parts and fallback_to_last_commit:
            last_commit_diff = get_last_commit_diff(max_chars)
            if last_commit_diff:
                return f"=== LAST COMMIT ===\n{last_commit_diff}"
            return None

        if not diff_parts:
            return None

        combined = "\n".join(diff_parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n\n... [diff truncated] ..."

        return combined

    except Exception as e:
        logger.debug(f"Failed to get git diff: {e}")
        return None


@dataclass
class ValidationResult:
    """Result of task validation."""

    status: Literal["valid", "invalid", "pending"]
    feedback: str | None = None


class TaskValidator:
    """Validates task completion using LLM."""

    def __init__(self, config: TaskValidationConfig, llm_service: LLMService):
        self.config = config
        self.llm_service = llm_service

    async def gather_validation_context(self, file_paths: list[str]) -> str:
        """
        Gather context for validation from files.

        Args:
            file_paths: List of absolute file paths to read.

        Returns:
            Concatenated file contents.
        """
        context: list[str] = []
        for path in file_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                    context.append(f"--- {path} ---\n{content}\n")
            except Exception as e:
                logger.warning(f"Failed to read file {path} for validation: {e}")
                context.append(f"--- {path} ---\n(Error reading file: {e})\n")
        return "\n".join(context)

    async def validate_task(
        self,
        task_id: str,
        title: str,
        description: str | None,
        changes_summary: str,
        validation_criteria: str | None = None,
        context_files: list[str] | None = None,
    ) -> ValidationResult:
        """
        Validate task completion.

        Args:
            task_id: Task ID
            title: Task title
            description: Task description (used as fallback if no validation_criteria)
            changes_summary: Summary of changes made (files, diffs, etc.)
            validation_criteria: Specific criteria to validate against (optional)
            context_files: List of files to read for context (optional)

        Returns:
            ValidationResult with status and feedback
        """
        if not self.config.enabled:
            return ValidationResult(status="pending", feedback="Validation disabled")

        if not description and not validation_criteria:
            logger.warning(f"Cannot validate task {task_id}: missing description and criteria")
            return ValidationResult(
                status="pending", feedback="Missing task description and validation criteria"
            )

        logger.info(f"Validating task {task_id}: {title}")

        # Gather context if provided
        file_context = ""
        if context_files:
            file_context = await self.gather_validation_context(context_files)

        # Build prompt
        criteria_text = (
            f"Validation Criteria:\n{validation_criteria}"
            if validation_criteria
            else f"Task Description:\n{description}"
        )

        # Detect if changes_summary is a git diff
        is_git_diff = changes_summary.startswith("Git diff") or "@@" in changes_summary

        if is_git_diff:
            changes_section = (
                "Code Changes (git diff):\n"
                "Analyze these ACTUAL code changes to verify the implementation.\n\n"
                f"{changes_summary}\n\n"
            )
        else:
            changes_section = f"Changes Summary:\n{changes_summary}\n\n"

        base_prompt = (
            "Validate if the following changes satisfy the requirements.\n\n"
            f"Task: {title}\n"
            f"{criteria_text}\n\n"
            f"{changes_section}"
            "IMPORTANT: Return ONLY a JSON object, nothing else. No explanation, no preamble.\n"
            'Format: {"status": "valid", "feedback": "..."} or {"status": "invalid", "feedback": "..."}\n'
        )

        if file_context:
            # Truncate file context to 50k chars to avoid exceeding LLM context limits
            base_prompt += f"File Context:\n{file_context[:50000]}\n"

        prompt = self.config.prompt or base_prompt

        try:
            provider = self.llm_service.get_provider(self.config.provider)
            response_content = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.config.system_prompt,
                model=self.config.model,
            )

            import json
            import re

            if not response_content or not response_content.strip():
                logger.warning(f"Empty LLM response for task {task_id} validation")
                return ValidationResult(
                    status="pending", feedback="Validation failed: Empty response from LLM"
                )

            content = response_content.strip()
            logger.debug(f"Validation LLM response for {task_id}: {content[:200]}...")

            # Try to find JSON in code block
            json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_block:
                content = json_block.group(1)
            else:
                # If no code block, try to find { ... }
                json_obj = re.search(r"(\{.*\})", content, re.DOTALL)
                if json_obj:
                    content = json_obj.group(1)

            result_data = json.loads(content)

            return ValidationResult(
                status=result_data.get("status", "pending"), feedback=result_data.get("feedback")
            )

        except Exception as e:
            logger.error(f"Failed to validate task {task_id}: {e}")
            return ValidationResult(status="pending", feedback=f"Validation failed: {str(e)}")

    async def generate_criteria(
        self,
        title: str,
        description: str | None = None,
    ) -> str | None:
        """
        Generate validation criteria from task title and description.

        Args:
            title: Task title
            description: Task description (optional)

        Returns:
            Generated validation criteria string, or None if generation fails
        """
        if not self.config.enabled:
            return None

        # Use custom prompt from config, or default
        if self.config.criteria_prompt:
            prompt = self.config.criteria_prompt.format(
                title=title,
                description=description or "(no description)",
            )
        else:
            prompt = f"""Generate validation criteria for the following task.

Task: {title}
Description: {description or "(no description)"}

Requirements for good criteria:
1. **Objectively verifiable** - Can be checked with a yes/no answer
2. **Specific** - Include concrete values, file paths, or behaviors (no vague terms like "appropriate" or "reasonable")
3. **Actionable** - Each criterion maps to something that can be tested or inspected
4. **Complete** - Cover the full scope of the task including edge cases and error handling
5. **Structured** - Use markdown checkboxes for easy tracking

Format your response as:
# <Task Title Summary>

## Deliverable
- [ ] Primary output (file, class, function, etc.)

## Functional Requirements
- [ ] Specific behavior 1
- [ ] Specific behavior 2

## Edge Cases / Error Handling
- [ ] How errors are handled
- [ ] Boundary conditions

## Verification
- [ ] How to verify completion (tests pass, command works, etc.)

Use concrete examples: "timeout defaults to 30 seconds" not "timeout has a reasonable default".
"""

        try:
            provider = self.llm_service.get_provider(self.config.provider)
            response = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.config.criteria_system_prompt,
                model=self.config.model,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate validation criteria: {e}")
            return None
