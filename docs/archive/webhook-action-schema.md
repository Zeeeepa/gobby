# Webhook Workflow Action Schema

## Overview

This document defines the schema for webhook actions in Gobby workflows. Webhook actions allow workflows to make HTTP requests to external services during execution.

## Action Name

```yaml
action: webhook
```

## Schema Definition

### Required Fields (one of)

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Direct HTTP(S) URL to call |
| `webhook_id` | string | Reference to a registered webhook in config |

**Note:** Exactly one of `url` or `webhook_id` must be provided.

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `method` | enum | `POST` | HTTP method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE` |
| `headers` | dict | `{"Content-Type": "application/json"}` | Request headers (supports interpolation) |
| `payload` | string/dict | `null` | Request body template (supports interpolation) |
| `timeout` | int | `30` | Request timeout in seconds (1-300) |
| `retry` | object | `null` | Retry configuration (see below) |
| `on_success` | string | `null` | Action to execute on 2xx response |
| `on_failure` | string | `null` | Action to execute after all retries exhausted |
| `capture_response` | object | `null` | Variables to capture from response (see below) |

### Retry Configuration

```yaml
retry:
  max_attempts: 3          # Total attempts including first (1-10)
  backoff_seconds: 2       # Base backoff delay (doubles each retry)
  retry_on_status:         # HTTP status codes to retry on
    - 429                  # Rate limited
    - 500                  # Server error
    - 502                  # Bad gateway
    - 503                  # Service unavailable
    - 504                  # Gateway timeout
```

### Response Capture

```yaml
capture_response:
  status_var: "webhook_status"      # Variable for HTTP status code
  body_var: "webhook_body"          # Variable for response body (parsed as JSON if possible)
  headers_var: "webhook_headers"    # Variable for response headers dict
```

## Variable Interpolation

All string fields support variable interpolation using `${...}` syntax:

| Syntax | Description | Example |
|--------|-------------|---------|
| `${var}` | Workflow state variable | `${session_id}` |
| `${context.var}` | Workflow context variable | `${context.user_prompt}` |
| `${secrets.VAR}` | Secret from secure storage | `${secrets.SLACK_TOKEN}` |
| `${env.VAR}` | Environment variable | `${env.API_URL}` |

**Security:** Values from `${secrets.*}` are:
- Never logged in plaintext
- Redacted in error messages
- Not stored in workflow state

## Examples

### Example 1: Simple POST Webhook

```yaml
steps:
  - name: notify
    on_enter:
      - action: webhook
        url: "https://hooks.slack.com/services/xxx"
        payload:
          text: "Session ${session_id} started"
```

### Example 2: Webhook with Retry and Error Handling

```yaml
on_session_end:
  - action: webhook
    url: "https://api.example.com/events"
    method: POST
    headers:
      Authorization: "Bearer ${secrets.API_TOKEN}"
      X-Session-Id: "${session_id}"
    payload:
      event: "session_ended"
      summary: "${context.summary}"
    timeout: 10
    retry:
      max_attempts: 3
      backoff_seconds: 2
      retry_on_status: [429, 500, 502, 503]
    on_failure: log_webhook_failure
```

### Example 3: Chained Webhooks Using Captured Response

```yaml
steps:
  - name: create_ticket
    on_enter:
      - action: webhook
        url: "https://api.jira.com/issue"
        method: POST
        headers:
          Authorization: "Bearer ${secrets.JIRA_TOKEN}"
        payload:
          project: "DEV"
          summary: "${context.task_title}"
        capture_response:
          body_var: "jira_response"
          status_var: "jira_status"

      # Use captured response in next webhook
      - action: webhook
        url: "https://hooks.slack.com/services/xxx"
        payload:
          text: "Created ticket: ${jira_response.key}"
        when: "${jira_status} == 201"
```

### Example 4: Using Registered Webhook

```yaml
# In ~/.gobby/config.yaml:
# webhooks:
#   slack_alerts:
#     url: "https://hooks.slack.com/services/xxx"
#     headers:
#       Content-Type: "application/json"

on_error:
  - action: webhook
    webhook_id: "slack_alerts"
    payload:
      text: "Workflow error: ${error_message}"
```

## URL Validation

- Only `http://` and `https://` schemes are allowed
- Other schemes (ftp://, file://, etc.) are rejected with a clear error
- URL must be well-formed (validated at parse time)

## Error Handling

| Error Type | Behavior |
|------------|----------|
| Network error | Retry if retry configured, else fail |
| Timeout | Retry if retry configured, else fail |
| HTTP 4xx (except 429) | Fail immediately (no retry) |
| HTTP 429 | Retry with backoff if configured |
| HTTP 5xx | Retry if status in retry_on_status |
| Invalid URL | Fail at parse time with clear error |
| Missing url/webhook_id | Fail at parse time |

## Logging

- Request: Log URL and method (not headers/payload with secrets)
- Response: Log status code and timing
- Retry: Log attempt number and backoff delay
- Secrets: All `${secrets.*}` values redacted as `[REDACTED]`

## Integration Points

1. **ActionExecutor**: Register `webhook` handler in `actions.py`
2. **WebhookExecutor**: New class in `src/gobby/workflows/webhook_executor.py`
3. **Config**: Webhook registry in `~/.gobby/config.yaml` under `webhooks:`
4. **Secrets**: Integration with existing secrets storage (if available) or env vars
