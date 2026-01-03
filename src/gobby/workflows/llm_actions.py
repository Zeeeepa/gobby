"""LLM invocation workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle direct LLM calls from workflows.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def call_llm(
    llm_service: Any,
    template_engine: Any,
    state: Any,
    session: Any,
    prompt: str | None,
    output_as: str | None,
    **extra_context: Any,
) -> dict[str, Any]:
    """Call LLM with a prompt template and store result in variable.

    Args:
        llm_service: LLM service instance
        template_engine: Template engine for rendering
        state: WorkflowState object
        session: Current session object
        prompt: Prompt template string
        output_as: Variable name to store result
        **extra_context: Additional context for template rendering

    Returns:
        Dict with llm_called boolean and output_variable, or error
    """
    if not prompt or not output_as:
        return {"error": "Missing prompt or output_as"}

    if not llm_service:
        logger.warning("call_llm: Missing LLM service")
        return {"error": "Missing LLM service"}

    # Render prompt template
    render_context = {
        "session": session,
        "state": state,
        "variables": state.variables or {},
    }
    # Add extra context
    render_context.update(extra_context)

    try:
        rendered_prompt = template_engine.render(prompt, render_context)
    except Exception as e:
        logger.error(f"call_llm: Template rendering failed for prompt '{prompt[:50]}...': {e}")
        return {"error": f"Template rendering failed: {e}"}

    try:
        provider = llm_service.get_default_provider()
        response = await provider.generate_text(rendered_prompt)

        # Store result
        if not state.variables:
            state.variables = {}
        state.variables[output_as] = response

        return {"llm_called": True, "output_variable": output_as}
    except Exception as e:
        logger.error(f"call_llm: Failed: {e}")
        return {"error": str(e)}
