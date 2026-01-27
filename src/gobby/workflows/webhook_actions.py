"""Webhook workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle webhook HTTP request execution from workflows.
"""

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

if TYPE_CHECKING:
    from gobby.workflows.definitions import WorkflowState
    from gobby.workflows.templates import TemplateEngine

logger = logging.getLogger(__name__)


async def execute_webhook(
    template_engine: "TemplateEngine",
    state: "WorkflowState",
    config: Any | None,
    url: str | None = None,
    webhook_id: str | None = None,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | str | None = None,
    timeout: int = 30,
    retry: dict[str, Any] | None = None,
    capture_response: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a webhook HTTP request.

    Args:
        template_engine: Template engine for interpolation
        state: WorkflowState for variables/artifacts access
        config: Daemon config for webhook_secrets
        url: Target URL for the request
        webhook_id: ID of a pre-configured webhook (alternative to url)
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        headers: Request headers dict
        payload: Request body as dict or string
        timeout: Request timeout in seconds
        retry: Retry configuration dict
        capture_response: Response capture config

    Returns:
        Dict with success status, status_code, and captured response data.
    """
    from gobby.workflows.webhook import WebhookAction
    from gobby.workflows.webhook_executor import WebhookExecutor

    # Build kwargs dict for WebhookAction
    webhook_kwargs: dict[str, Any] = {
        "method": method,
        "timeout": timeout,
    }
    if url:
        webhook_kwargs["url"] = url
    if webhook_id:
        webhook_kwargs["webhook_id"] = webhook_id
    if headers:
        webhook_kwargs["headers"] = headers
    if payload:
        webhook_kwargs["payload"] = payload
    if retry:
        webhook_kwargs["retry"] = retry
    if capture_response:
        webhook_kwargs["capture_response"] = capture_response

    try:
        # Parse WebhookAction from kwargs to validate config
        webhook_action = WebhookAction.from_dict(webhook_kwargs)
    except ValueError as e:
        logger.error(f"Invalid webhook action config: {e}")
        return {"success": False, "error": str(e)}

    # Build context for variable interpolation
    interpolation_context: dict[str, Any] = {}
    if state.variables:
        interpolation_context["state"] = {"variables": state.variables}
    if state.artifacts:
        interpolation_context["artifacts"] = state.artifacts

    # Get secrets from config if available
    secrets: dict[str, str] = {}
    if config:
        secrets = getattr(config, "webhook_secrets", {})

    # Create executor with template engine for payload interpolation
    executor = WebhookExecutor(
        template_engine=template_engine,
        secrets=secrets,
    )

    # Execute the webhook
    if webhook_action.url:
        result = await executor.execute(
            url=webhook_action.url,
            method=webhook_action.method,
            headers=webhook_action.headers,
            payload=webhook_action.payload,
            timeout=webhook_action.timeout,
            retry_config=webhook_action.retry.to_dict() if webhook_action.retry else None,
            context=interpolation_context,
        )
    elif webhook_action.webhook_id:
        # webhook_id execution requires a registry which would be configured
        # at the daemon level - for now we return an error if no registry
        logger.warning("webhook_id execution not yet supported without registry")
        return {"success": False, "error": "webhook_id requires configured webhook registry"}
    else:
        return {"success": False, "error": "Either url or webhook_id is required"}

    # Capture response into workflow variables if configured
    if webhook_action.capture_response:
        if not state.variables:
            state.variables = {}

        capture = webhook_action.capture_response
        if capture.status_var and result.status_code is not None:
            state.variables[capture.status_var] = result.status_code
        if capture.body_var and result.body is not None:
            # Try to parse as JSON, fall back to raw string
            json_body = result.json_body()
            state.variables[capture.body_var] = json_body if json_body else result.body
        if capture.headers_var and result.headers is not None:
            state.variables[capture.headers_var] = result.headers

    # Sanitize URL for logging (remove query params which may contain secrets)
    def _sanitize_url(url: str | None) -> str:
        if not url:
            return "<no-url>"
        try:
            parsed = urlparse(url)
            # Remove query string for logging
            sanitized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            return sanitized or url
        except Exception:
            return "<invalid-url>"

    sanitized_url = _sanitize_url(webhook_action.url)

    # Log outcome
    if result.success:
        logger.info(
            f"Webhook {webhook_action.method} {sanitized_url} succeeded: {result.status_code}"
        )
    else:
        logger.warning(
            f"Webhook {webhook_action.method} {sanitized_url} failed: "
            f"{result.error or result.status_code}"
        )

    return {
        "success": result.success,
        "status_code": result.status_code,
        "error": result.error,
        "body": result.body if result.success else None,
    }


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None


async def handle_webhook(
    context: Any, config: Any | None = None, **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for execute_webhook.

    Note: config is passed via closure from register_defaults.
    """
    return await execute_webhook(
        template_engine=context.template_engine,
        state=context.state,
        config=config,
        url=kwargs.get("url"),
        webhook_id=kwargs.get("webhook_id"),
        method=kwargs.get("method", "POST"),
        headers=kwargs.get("headers"),
        payload=kwargs.get("payload"),
        timeout=kwargs.get("timeout", 30),
        retry=kwargs.get("retry"),
        capture_response=kwargs.get("capture_response"),
    )
