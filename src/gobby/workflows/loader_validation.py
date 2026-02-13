"""Pipeline reference validation helpers for WorkflowLoader.

Extracted from loader.py as part of Strangler Fig decomposition (Wave 2).
"""

import re
from typing import Any


def _validate_pipeline_references(data: dict[str, Any]) -> None:
    """
    Validate that all $step_id.output references in a pipeline refer to earlier steps.

    Args:
        data: Pipeline data dictionary

    Raises:
        ValueError: If a reference points to a non-existent or later step
    """
    steps = data.get("steps", [])
    step_ids = [s.get("id") for s in steps if s.get("id")]

    # Build set of valid step IDs that can be referenced at each position
    valid_at_position: dict[int, set[str]] = {}
    for i in range(len(step_ids)):
        # Steps at position i can only reference steps 0..i-1
        valid_at_position[i] = set(step_ids[:i])

    # Validate references in each step
    for i, step in enumerate(steps):
        step_id = step.get("id", f"step_{i}")
        valid_refs = valid_at_position.get(i, set())

        # Check prompt field
        if "prompt" in step and step["prompt"]:
            refs = _extract_step_refs(step["prompt"])
            _check_refs(refs, valid_refs, step_ids, step_id, "prompt")

        # Check condition field
        if "condition" in step and step["condition"]:
            refs = _extract_step_refs(step["condition"])
            _check_refs(refs, valid_refs, step_ids, step_id, "condition")

        # Check input field
        if "input" in step and step["input"]:
            refs = _extract_step_refs(step["input"])
            _check_refs(refs, valid_refs, step_ids, step_id, "input")

        # Check exec field (might have embedded references)
        if "exec" in step and step["exec"]:
            refs = _extract_step_refs(step["exec"])
            _check_refs(refs, valid_refs, step_ids, step_id, "exec")

    # Validate references in pipeline outputs (can reference any step)
    all_step_ids = set(step_ids)
    outputs = data.get("outputs", {})
    for output_name, output_value in outputs.items():
        if isinstance(output_value, str):
            refs = _extract_step_refs(output_value)
            for ref in refs:
                if ref not in all_step_ids:
                    raise ValueError(
                        f"Pipeline output '{output_name}' references unknown step '{ref}'. "
                        f"Valid steps: {sorted(all_step_ids)}"
                    )


def _extract_step_refs(text: str) -> set[str]:
    """
    Extract step IDs from $step_id.output patterns in text.

    Args:
        text: Text to search for references

    Returns:
        Set of step IDs referenced
    """
    # Match $step_id.output or $step_id.output.field patterns
    # Exclude $inputs.* which are input references, not step references
    pattern = r"\$([a-zA-Z_][a-zA-Z0-9_]*)\.(output|approved|status)"
    matches = re.findall(pattern, text)
    # Filter out 'inputs' which is a special reference
    return {m[0] for m in matches if m[0] != "inputs"}


def _check_refs(
    refs: set[str],
    valid_refs: set[str],
    all_step_ids: list[str],
    current_step: str,
    field_name: str,
) -> None:
    """
    Check that all references are valid.

    Args:
        refs: Set of referenced step IDs
        valid_refs: Set of step IDs that can be referenced (earlier steps)
        all_step_ids: List of all step IDs in the pipeline
        current_step: Current step ID (for error messages)
        field_name: Field name being checked (for error messages)

    Raises:
        ValueError: If any reference is invalid
    """
    for ref in refs:
        if ref not in valid_refs:
            if ref in all_step_ids:
                # It's a forward reference
                raise ValueError(
                    f"Step '{current_step}' {field_name} references step '{ref}' "
                    f"which appears later in the pipeline. Steps can only reference "
                    f"earlier steps. Valid references: {sorted(valid_refs) if valid_refs else '(none)'}"
                )
            else:
                # It's a non-existent step
                raise ValueError(
                    f"Step '{current_step}' {field_name} references unknown step '{ref}'. "
                    f"Valid steps: {sorted(all_step_ids)}"
                )
