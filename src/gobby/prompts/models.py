"""
Prompt template data models.

Contains dataclasses for representing prompt templates with metadata.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class VariableSpec:
    """Specification for a template variable.

    Attributes:
        type: Variable type (str, int, bool, list, dict)
        default: Default value if not provided
        description: Human-readable description
        required: Whether the variable must be provided
    """

    type: Literal["str", "int", "bool", "list", "dict"] = "str"
    default: Any = None
    description: str = ""
    required: bool = False


@dataclass
class PromptTemplate:
    """A loaded prompt template with metadata.

    Attributes:
        name: Template identifier (e.g., "expansion/system")
        description: Human-readable description
        variables: Variable specifications from frontmatter
        content: Raw template content (with Jinja2 syntax)
        source_path: Path the template was loaded from (None for fallbacks)
        version: Template version for compatibility checking
    """

    name: str
    description: str = ""
    variables: dict[str, VariableSpec] = field(default_factory=dict)
    content: str = ""
    source_path: Path | None = None
    version: str = "1.0"

    @classmethod
    def from_frontmatter(
        cls,
        name: str,
        frontmatter: dict[str, Any],
        content: str,
        source_path: Path | None = None,
    ) -> "PromptTemplate":
        """Create a PromptTemplate from parsed frontmatter.

        Args:
            name: Template name/path
            frontmatter: Parsed YAML frontmatter
            content: Template content after frontmatter
            source_path: Source file path

        Returns:
            PromptTemplate instance
        """
        # Parse variables from frontmatter
        variables: dict[str, VariableSpec] = {}
        if "variables" in frontmatter:
            for var_name, var_spec in frontmatter["variables"].items():
                if isinstance(var_spec, dict):
                    variables[var_name] = VariableSpec(
                        type=var_spec.get("type", "str"),
                        default=var_spec.get("default"),
                        description=var_spec.get("description", ""),
                        required=var_spec.get("required", False),
                    )
                else:
                    # Simple form: just a default value
                    variables[var_name] = VariableSpec(default=var_spec)

        return cls(
            name=name,
            description=frontmatter.get("description", ""),
            variables=variables,
            content=content,
            source_path=source_path,
            version=frontmatter.get("version", "1.0"),
        )

    def get_default_context(self) -> dict[str, Any]:
        """Get default values for all variables.

        Returns:
            Dict of variable names to their default values
        """
        return {name: spec.default for name, spec in self.variables.items()}

    def validate_context(self, context: dict[str, Any]) -> list[str]:
        """Validate that required variables are provided.

        Args:
            context: Context dict being passed to render

        Returns:
            List of error messages (empty if valid)
        """
        errors: list[str] = []
        for name, spec in self.variables.items():
            if spec.required and name not in context:
                errors.append(f"Required variable '{name}' not provided")
        return errors
