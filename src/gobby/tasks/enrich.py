"""
Task Enrichment Module.

Provides data structures and services for enriching tasks with additional context,
research findings, and validation criteria.
"""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnrichmentResult:
    """Result of task enrichment containing enhanced context and metadata.

    Attributes:
        task_id: The ID of the enriched task
        category: Task category (code, document, research, config, test, manual)
        complexity_score: Estimated complexity (1=low, 2=medium, 3=high)
        research_findings: Summary of research and analysis performed
        suggested_subtask_count: Recommended number of subtasks
        validation_criteria: Generated acceptance criteria for completion
        mcp_tools_used: List of MCP tools used during enrichment
    """

    task_id: str
    category: str | None = None
    complexity_score: int | None = None
    research_findings: str | None = None
    suggested_subtask_count: int | None = None
    validation_criteria: str | None = None
    mcp_tools_used: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "task_id": self.task_id,
            "category": self.category,
            "complexity_score": self.complexity_score,
            "research_findings": self.research_findings,
            "suggested_subtask_count": self.suggested_subtask_count,
            "validation_criteria": self.validation_criteria,
            "mcp_tools_used": self.mcp_tools_used,
        }


class TaskEnricher:
    """Service for enriching tasks with additional context and metadata.

    Uses LLM calls and MCP tools to gather information and enhance task
    descriptions with implementation guidance.
    """

    # Category keywords for classification
    CATEGORY_KEYWORDS: dict[str, list[str]] = {
        "test": [
            "test",
            "tests",
            "testing",
            "unit test",
            "integration test",
            "e2e",
            "pytest",
            "coverage",
        ],
        "code": [
            "implement",
            "add",
            "create",
            "build",
            "feature",
            "method",
            "function",
            "class",
            "api",
            "endpoint",
            "fix",
            "bug",
            "refactor",
        ],
        "document": [
            "document",
            "documentation",
            "readme",
            "docs",
            "write up",
            "spec",
            "specification",
        ],
        "research": [
            "research",
            "investigate",
            "explore",
            "analyze",
            "study",
            "evaluate",
            "compare",
        ],
        "config": [
            "config",
            "configuration",
            "setup",
            "install",
            "configure",
            "environment",
            "settings",
        ],
        "manual": [
            "manual",
            "review",
            "approve",
            "check",
            "verify",
            "validate manually",
        ],
    }

    # Complexity indicators
    HIGH_COMPLEXITY_KEYWORDS = [
        "refactor",
        "overhaul",
        "redesign",
        "architecture",
        "complete",
        "entire",
        "all",
        "comprehensive",
        "oauth",
        "jwt",
        "authentication",
        "security",
        "migration",
        "database",
        "schema",
    ]
    MEDIUM_COMPLEXITY_KEYWORDS = [
        "add",
        "implement",
        "create",
        "integrate",
        "update",
        "modify",
        "extend",
    ]

    def __init__(self) -> None:
        """Initialize the task enricher."""
        pass

    def _categorize_task(self, title: str, description: str | None) -> str:
        """Categorize task based on title and description keywords.

        Args:
            title: Task title
            description: Task description

        Returns:
            Category string (code, document, research, config, test, manual)
        """
        text = f"{title} {description or ''}".lower()

        # Check each category's keywords
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    return category

        # Default to "code" if no specific category found
        return "code"

    def _estimate_complexity(self, title: str, description: str | None) -> int:
        """Estimate task complexity based on title and description.

        Args:
            title: Task title
            description: Task description

        Returns:
            Complexity score (1=low, 2=medium, 3=high)
        """
        text = f"{title} {description or ''}".lower()

        # Check for high complexity indicators
        for keyword in self.HIGH_COMPLEXITY_KEYWORDS:
            if keyword in text:
                return 3  # High complexity

        # Check for medium complexity indicators
        for keyword in self.MEDIUM_COMPLEXITY_KEYWORDS:
            if keyword in text:
                return 2  # Medium complexity

        # Check description length as another indicator
        desc_len = len(description or "")
        if desc_len > 300:
            return 3  # Long description suggests high complexity
        elif desc_len > 100:
            return 2  # Medium description suggests medium complexity

        return 1  # Default to low complexity

    def _suggest_subtask_count(self, complexity: int, description: str | None) -> int:
        """Suggest number of subtasks based on complexity.

        Args:
            complexity: Complexity score (1-3)
            description: Task description

        Returns:
            Suggested number of subtasks
        """
        # Base suggestions on complexity
        if complexity == 3:
            base_count = 5
        elif complexity == 2:
            base_count = 3
        else:
            base_count = 2

        # Adjust based on description content
        if description:
            # Count list items, bullet points, or numbered items
            list_items = len(re.findall(r"^[\s]*[-*•\d]+[.)]?\s", description, re.MULTILINE))
            if list_items > base_count:
                base_count = min(list_items, 10)  # Cap at 10

        return max(base_count, 1)

    # Validation criteria templates by category
    VALIDATION_TEMPLATES: dict[str, str] = {
        "test": (
            "## Deliverable\n"
            "- [ ] Tests are written and passing\n\n"
            "## Functional Requirements\n"
            "- [ ] Test coverage meets project standards\n"
            "- [ ] All edge cases are covered\n"
            "- [ ] Tests are well-documented\n\n"
            "## Verification\n"
            "- [ ] All tests pass\n"
            "- [ ] No regressions introduced"
        ),
        "code": (
            "## Deliverable\n"
            "- [ ] Implementation is complete and functional\n\n"
            "## Functional Requirements\n"
            "- [ ] Code follows project conventions\n"
            "- [ ] Error handling is implemented\n"
            "- [ ] Edge cases are handled\n\n"
            "## Verification\n"
            "- [ ] Existing tests pass\n"
            "- [ ] New tests added if applicable\n"
            "- [ ] Code review approved"
        ),
        "document": (
            "## Deliverable\n"
            "- [ ] Documentation is written and complete\n\n"
            "## Functional Requirements\n"
            "- [ ] Documentation is clear and accurate\n"
            "- [ ] Examples are provided where helpful\n"
            "- [ ] Formatting follows project standards\n\n"
            "## Verification\n"
            "- [ ] Documentation reviewed for accuracy\n"
            "- [ ] Links and references are valid"
        ),
        "research": (
            "## Deliverable\n"
            "- [ ] Research findings documented\n\n"
            "## Functional Requirements\n"
            "- [ ] Analysis is thorough and well-reasoned\n"
            "- [ ] Recommendations are actionable\n\n"
            "## Verification\n"
            "- [ ] Findings reviewed by stakeholders"
        ),
        "config": (
            "## Deliverable\n"
            "- [ ] Configuration is complete and working\n\n"
            "## Functional Requirements\n"
            "- [ ] Configuration is documented\n"
            "- [ ] Environment-specific values are handled\n\n"
            "## Verification\n"
            "- [ ] Configuration tested in target environment\n"
            "- [ ] No sensitive values exposed"
        ),
        "manual": (
            "## Deliverable\n"
            "- [ ] Manual task completed\n\n"
            "## Verification\n"
            "- [ ] Results documented\n"
            "- [ ] Stakeholders notified"
        ),
    }

    def _generate_validation_criteria(
        self,
        title: str,
        description: str | None,
        category: str,
        complexity: int,
        code_context: str | None,
    ) -> str:
        """Generate validation criteria based on task analysis.

        Args:
            title: Task title
            description: Task description
            category: Task category
            complexity: Complexity score (1-3)
            code_context: Optional code context

        Returns:
            Validation criteria string
        """
        # Start with base template for category
        base_template = self.VALIDATION_TEMPLATES.get(category, self.VALIDATION_TEMPLATES["code"])
        criteria_parts = [base_template]

        # Add task-specific criteria based on title/description
        text = f"{title} {description or ''}".lower()

        # Add specific criteria based on detected patterns
        specific_criteria = []

        # API-related tasks
        if "api" in text or "endpoint" in text:
            specific_criteria.append("- [ ] API endpoint responds correctly")
            specific_criteria.append("- [ ] Response format matches specification")

        # Authentication-related tasks
        if "auth" in text or "login" in text or "authentication" in text:
            specific_criteria.append("- [ ] Security best practices followed")
            specific_criteria.append("- [ ] Authentication flow tested end-to-end")

        # Database-related tasks
        if "database" in text or "migration" in text or "schema" in text:
            specific_criteria.append("- [ ] Database migrations applied successfully")
            specific_criteria.append("- [ ] Data integrity maintained")

        # Performance-related tasks
        if "performance" in text or "optimize" in text or "speed" in text:
            specific_criteria.append("- [ ] Performance benchmarks met")
            specific_criteria.append("- [ ] No performance regressions")

        # Add specific criteria if any found
        if specific_criteria:
            criteria_parts.append("\n## Task-Specific Requirements")
            criteria_parts.extend(specific_criteria)

        # For complex tasks, add additional review criteria
        if complexity >= 3:
            criteria_parts.append("\n## High Complexity Review")
            criteria_parts.append("- [ ] Architecture reviewed")
            criteria_parts.append("- [ ] Security implications considered")
            criteria_parts.append("- [ ] Performance impact assessed")

        # Include code context summary if provided
        if code_context:
            functions = re.findall(r"def\s+(\w+)", code_context)
            classes = re.findall(r"class\s+(\w+)", code_context)
            if functions or classes:
                criteria_parts.append("\n## Code Context")
                if classes:
                    criteria_parts.append(f"- [ ] Changes to {', '.join(classes[:3])} classes reviewed")
                if functions:
                    criteria_parts.append(f"- [ ] Changes to {', '.join(functions[:3])} functions tested")

        return "\n".join(criteria_parts)

    def _generate_research_findings(
        self,
        title: str,
        description: str | None,
        code_context: str | None,
        project_context: str | None,
        category: str,
    ) -> str:
        """Generate research findings summary.

        Args:
            title: Task title
            description: Task description
            code_context: Provided code context
            project_context: Project information
            category: Task category

        Returns:
            Research findings summary string
        """
        findings = []

        # Add category-based findings
        findings.append(f"Task categorized as: {category}")

        # Extract keywords from title/description
        text = f"{title} {description or ''}".lower()
        keywords = []

        # Look for common code-related terms
        code_terms = [
            "function",
            "method",
            "class",
            "module",
            "api",
            "endpoint",
            "database",
            "query",
            "service",
            "controller",
            "model",
            "view",
            "handler",
            "manager",
            "task",
            "session",
            "user",
            "auth",
        ]
        for term in code_terms:
            if term in text:
                keywords.append(term)

        if keywords:
            findings.append(f"Relevant concepts: {', '.join(keywords[:5])}")

        # Include code context summary if provided
        if code_context:
            # Extract function/class names from code context
            functions = re.findall(r"def\s+(\w+)", code_context)
            classes = re.findall(r"class\s+(\w+)", code_context)
            if functions:
                findings.append(f"Code context includes functions: {', '.join(functions[:5])}")
            if classes:
                findings.append(f"Code context includes classes: {', '.join(classes[:5])}")

        # Include project context if provided
        if project_context:
            findings.append("Project context provided for implementation guidance")

        # Generate a summary
        if not findings:
            findings.append("Basic enrichment performed")

        return ". ".join(findings)

    async def enrich(
        self,
        task_id: str,
        title: str,
        description: str | None = None,
        code_context: str | None = None,
        project_context: str | None = None,
        enable_code_research: bool = True,
        enable_web_research: bool = False,
        enable_mcp_tools: bool = False,
        generate_validation: bool = True,
    ) -> EnrichmentResult:
        """Enrich a task with additional context and metadata.

        Args:
            task_id: The task ID to enrich
            title: Task title
            description: Optional existing description
            code_context: Relevant code snippets or references
            project_context: Information about the codebase
            enable_code_research: Enable code context gathering (default: True)
            enable_web_research: Enable web research for external context (default: False)
            enable_mcp_tools: Enable MCP tools for additional research (default: False)
            generate_validation: Generate validation criteria (default: True)

        Returns:
            EnrichmentResult with enhanced task information
        """
        # Categorize the task
        category = self._categorize_task(title, description)

        # Estimate complexity
        complexity = self._estimate_complexity(title, description)

        # Suggest subtask count
        subtask_count = self._suggest_subtask_count(complexity, description)

        # Generate research findings if code research is enabled
        research_findings = None
        if enable_code_research:
            research_findings = self._generate_research_findings(
                title=title,
                description=description,
                code_context=code_context,
                project_context=project_context,
                category=category,
            )

        # Generate validation criteria if enabled
        validation_criteria = None
        if generate_validation:
            validation_criteria = self._generate_validation_criteria(
                title=title,
                description=description,
                category=category,
                complexity=complexity,
                code_context=code_context,
            )

        # Track MCP tools used (placeholder for future implementation)
        mcp_tools_used = None
        if enable_mcp_tools:
            mcp_tools_used = []  # Will be populated when MCP tools are actually called

        return EnrichmentResult(
            task_id=task_id,
            category=category,
            complexity_score=complexity,
            research_findings=research_findings,
            suggested_subtask_count=subtask_count,
            validation_criteria=validation_criteria,
            mcp_tools_used=mcp_tools_used,
        )
