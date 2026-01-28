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


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None

if __name__ != "__main__":
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from gobby.workflows.actions import ActionContext


async def handle_call_llm(context: "ActionContext", **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for call_llm."""
    if context.session_manager is None:
        return {"error": "Session manager not available"}

    session = context.session_manager.get(context.session_id)
    if session is None:
        return {"error": f"Session not found: {context.session_id}"}

    return await call_llm(
        llm_service=context.llm_service,
        template_engine=context.template_engine,
        state=context.state,
        session=session,
        prompt=kwargs.get("prompt"),
        output_as=kwargs.get("output_as"),
        **{k: v for k, v in kwargs.items() if k not in ("prompt", "output_as")},
    )
