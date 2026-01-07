"""
Criteria generation for task expansion.

This module provides:
- PatternCriteriaInjector: Detects patterns from labels/descriptions and injects criteria
- CriteriaGenerator: Shared criteria generator for both structured and LLM expansion
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.config.app import PatternCriteriaConfig, ProjectVerificationConfig
    from gobby.storage.tasks import Task
    from gobby.tasks.context import ExpansionContext

logger = logging.getLogger(__name__)


class PatternCriteriaInjector:
    """Injects pattern-specific validation criteria into task expansion.

    Detects patterns from:
    - Task labels (e.g., 'strangler-fig', 'tdd')
    - Description keywords (e.g., 'using strangler fig pattern')

    Then injects appropriate criteria templates with placeholders replaced
    by actual verification commands from project config.
    """

    def __init__(
        self,
        pattern_config: PatternCriteriaConfig,
        verification_config: ProjectVerificationConfig | None = None,
    ):
        """Initialize the injector.

        Args:
            pattern_config: Pattern criteria configuration with templates
            verification_config: Project verification commands for placeholder substitution
        """
        self.pattern_config = pattern_config
        self.verification_config = verification_config

    def detect_patterns(
        self,
        task: Task,
        labels: list[str] | None = None,
    ) -> list[str]:
        """Detect which patterns apply to a task.

        Args:
            task: The task to analyze
            labels: Optional explicit labels (overrides task.labels)

        Returns:
            List of detected pattern names
        """
        detected: list[str] = []
        task_labels = labels if labels is not None else (task.labels or [])

        # Normalize labels to lowercase for matching
        normalized_labels = [label.lower() for label in task_labels]

        # Check labels first (direct match)
        for pattern_name in self.pattern_config.patterns.keys():
            if pattern_name.lower() in normalized_labels:
                if pattern_name not in detected:
                    detected.append(pattern_name)
                    logger.debug(f"Detected pattern '{pattern_name}' from task labels")

        # Check description keywords
        description = (task.description or "").lower()
        title = (task.title or "").lower()
        text_to_search = f"{title} {description}"

        for pattern_name, keywords in self.pattern_config.detection_keywords.items():
            if pattern_name in detected:
                continue  # Already detected from labels

            for keyword in keywords:
                if keyword.lower() in text_to_search:
                    detected.append(pattern_name)
                    logger.debug(
                        f"Detected pattern '{pattern_name}' from keyword '{keyword}' in description"
                    )
                    break

        return detected

    def _get_placeholder_values(self) -> dict[str, str]:
        """Get placeholder values from verification config.

        Returns:
            Dict mapping placeholder names to their values
        """
        values: dict[str, str] = {}

        if self.verification_config:
            if self.verification_config.unit_tests:
                values["unit_tests"] = self.verification_config.unit_tests
            if self.verification_config.type_check:
                values["type_check"] = self.verification_config.type_check
            if self.verification_config.lint:
                values["lint"] = self.verification_config.lint
            if self.verification_config.integration:
                values["integration"] = self.verification_config.integration

            # Add any custom verification commands
            for name, cmd in self.verification_config.custom.items():
                values[name] = cmd

        return values

    def _substitute_placeholders(
        self,
        template: str,
        extra_values: dict[str, str] | None = None,
    ) -> str:
        """Substitute placeholders in a template string.

        Args:
            template: Template string with {placeholder} syntax
            extra_values: Additional values to substitute

        Returns:
            String with placeholders replaced
        """
        values = self._get_placeholder_values()
        if extra_values:
            values.update(extra_values)

        # Use a regex to find placeholders and replace only those we have values for
        def replace_placeholder(match: re.Match[str]) -> str:
            key = match.group(1)
            return values.get(key, match.group(0))  # Keep original if no value

        return re.sub(r"\{(\w+)\}", replace_placeholder, template)

    def inject(
        self,
        task: Task,
        context: ExpansionContext | None = None,
        labels: list[str] | None = None,
        extra_placeholders: dict[str, str] | None = None,
    ) -> str:
        """Generate pattern-specific criteria markdown for a task.

        Args:
            task: The task to generate criteria for
            context: Optional expansion context (unused currently, for future extensibility)
            labels: Optional explicit labels (overrides task.labels)
            extra_placeholders: Additional placeholder values for substitution

        Returns:
            Markdown-formatted criteria string, empty if no patterns detected
        """
        detected_patterns = self.detect_patterns(task, labels)

        if not detected_patterns:
            return ""

        sections: list[str] = []

        for pattern_name in detected_patterns:
            templates = self.pattern_config.patterns.get(pattern_name, [])
            if not templates:
                continue

            criteria_lines: list[str] = []
            for template in templates:
                substituted = self._substitute_placeholders(template, extra_placeholders)
                criteria_lines.append(f"- [ ] {substituted}")

            if criteria_lines:
                # Format pattern name nicely (e.g., "strangler-fig" -> "Strangler-Fig Pattern")
                pattern_title = pattern_name.replace("-", " ").title()
                section = f"## {pattern_title} Pattern Criteria\n\n" + "\n".join(criteria_lines)
                sections.append(section)

        return "\n\n".join(sections)

    def inject_for_labels(
        self,
        labels: list[str],
        task: Task | None = None,
        extra_placeholders: dict[str, str] | None = None,
    ) -> str:
        """Generate criteria based on explicit labels without a full task.

        This is a convenience method when you only have labels and optionally a task.

        Args:
            labels: List of pattern labels
            task: Optional task for additional context
            extra_placeholders: Additional placeholder values

        Returns:
            Markdown-formatted criteria string
        """
        if task:
            return self.inject(task, labels=labels, extra_placeholders=extra_placeholders)

        # Create minimal criteria from labels only
        sections: list[str] = []
        normalized_labels = [label.lower() for label in labels]

        for pattern_name in self.pattern_config.patterns.keys():
            if pattern_name.lower() not in normalized_labels:
                continue

            templates = self.pattern_config.patterns.get(pattern_name, [])
            if not templates:
                continue

            criteria_lines: list[str] = []
            for template in templates:
                substituted = self._substitute_placeholders(template, extra_placeholders)
                criteria_lines.append(f"- [ ] {substituted}")

            if criteria_lines:
                pattern_title = pattern_name.replace("-", " ").title()
                section = f"## {pattern_title} Pattern Criteria\n\n" + "\n".join(criteria_lines)
                sections.append(section)

        return "\n\n".join(sections)


class CriteriaGenerator:
    """Shared criteria generator for both structured and LLM expansion.

    Generates validation criteria by combining:
    - Pattern-specific criteria (from labels/description)
    - Verification command criteria (from project config)
    - File-specific criteria (when relevant files provided)

    Can be used by:
    - TaskExpander (LLM expansion)
    - TaskHierarchyBuilder (structured expansion)
    """

    def __init__(
        self,
        pattern_config: PatternCriteriaConfig,
        verification_config: ProjectVerificationConfig | None = None,
    ):
        """Initialize the generator.

        Args:
            pattern_config: Pattern criteria configuration with templates
            verification_config: Project verification commands configuration
        """
        self.pattern_injector = PatternCriteriaInjector(
            pattern_config=pattern_config,
            verification_config=verification_config,
        )
        self.verification_config = verification_config

    def generate(
        self,
        title: str,
        description: str | None = None,
        labels: list[str] | None = None,
        relevant_files: list[str] | None = None,
        verification_commands: dict[str, str] | None = None,
    ) -> str:
        """Generate validation criteria markdown.

        Args:
            title: Task title
            description: Task description
            labels: Optional labels for pattern detection
            relevant_files: Optional list of relevant file paths
            verification_commands: Optional verification commands override

        Returns:
            Markdown-formatted validation criteria string
        """
        criteria_parts: list[str] = []

        # 1. Pattern-specific criteria from labels
        if labels:
            pattern_criteria = self.pattern_injector.inject_for_labels(
                labels=labels,
                extra_placeholders=verification_commands,
            )
            if pattern_criteria:
                criteria_parts.append(pattern_criteria)

        # 2. File-specific criteria
        if relevant_files and description:
            text_to_check = (title + " " + (description or "")).lower()
            matching_files = [f for f in relevant_files if f.lower() in text_to_check]
            if matching_files:
                file_criteria = ["## File Requirements", ""]
                for f in matching_files:
                    file_criteria.append(f"- [ ] `{f}` is correctly modified/created")
                criteria_parts.append("\n".join(file_criteria))

        # 3. Verification command criteria
        verification = self._get_verification_commands(verification_commands)
        if verification:
            verification_criteria = ["## Verification", ""]
            for name, cmd in verification.items():
                if name in ["unit_tests", "type_check", "lint"]:
                    verification_criteria.append(f"- [ ] `{cmd}` passes")
            if len(verification_criteria) > 2:  # Has items beyond header
                criteria_parts.append("\n".join(verification_criteria))

        return "\n\n".join(criteria_parts) if criteria_parts else ""

    def _get_verification_commands(
        self,
        override: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Get verification commands from config or override.

        Args:
            override: Optional override commands

        Returns:
            Dict of verification command name -> command
        """
        if override:
            return override

        commands: dict[str, str] = {}
        if self.verification_config:
            if self.verification_config.unit_tests:
                commands["unit_tests"] = self.verification_config.unit_tests
            if self.verification_config.type_check:
                commands["type_check"] = self.verification_config.type_check
            if self.verification_config.lint:
                commands["lint"] = self.verification_config.lint
            if self.verification_config.integration:
                commands["integration"] = self.verification_config.integration
            for name, cmd in self.verification_config.custom.items():
                commands[name] = cmd
        return commands
