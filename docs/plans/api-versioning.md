# API Versioning and Robustness Plan

This plan outlines the steps to introduce versioning (`/api/v1.0`) to the Gobby Daemon API, replacing the current flat structure. This is a **breaking change** prioritized for codebase cleanliness.

## Goal
Migrate all API endpoints from root-level prefixes (e.g., `/mcp`, `/sessions`) to a versioned namespace: `/api/v1.0/...`.

## 1. Constants and Configuration
*   **File**: `src/gobby/servers/routes/__init__.py` (or new `constants.py`)
*   **Change**: Define `API_V1_PREFIX = "/api/v1.0"`.

## 2. Server Update
*   **File**: `src/gobby/servers/http.py`
*   **Method**: `_register_routes`
*   **Change**: Wrap the inclusion of routers to use the prefix.
    ```python
    # Before
    app.include_router(create_mcp_router())
    
    # After
    from gobby.servers.routes import API_V1_PREFIX
    api_v1_router = APIRouter(prefix=API_V1_PREFIX)
    api_v1_router.include_router(create_mcp_router()) # resulting in /api/v1.0/mcp/...
    # ... include others ...
    app.include_router(api_v1_router)
    ```
    *Alternative*: Pass `prefix` to `create_mcp_router` if flexible, but nesting routers is cleaner for grouping.

## 3. Client and SDK Updates
*   **File**: `src/gobby/utils/daemon_client.py` (and potentially others like `GobbyClient` if exists)
*   **Change**: Update the base URL or request construction to include `/api/v1.0`.

## 4. Test Updates
*   **Scope**: Global `grep` for `/mcp/`, `/sessions/`, `/hooks/`, etc.
*   **Action**: Update all test fixtures and hardcoded URL strings to use the new prefix or a shared test constant.
*   **Affected Files**:
    *   `tests/servers/test_http_server.py`
    *   `tests/e2e/*`
    *   `tests/cli/*`

## 5. Backward Compatibility (Optional but recommended for transitions)
*   Since the user requested "clean codebase", we will **not** keep 301 Redirects for the old paths unless tests fail catastrophically and debugging becomes blocked. We will aim for a clean cut.

## Execution Order
1.  Define Constant.
2.  Update Server mounting.
3.  Update Client.
4.  Fix Tests (bulk update).
