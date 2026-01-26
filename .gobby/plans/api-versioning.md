# API Versioning Migration

## Overview

Migrate all Gobby daemon API endpoints from root-level prefixes (`/admin`, `/sessions`, `/mcp`, `/hooks`, `/plugins`, `/webhooks`) to a versioned namespace: `/api/v1.0/...`. This is a **breaking change** with no backward compatibility - prioritizing a clean codebase.

## Constraints

- **Breaking change**: No redirects or backward compatibility shims
- **Clean migration**: All URLs updated atomically to avoid mixed states
- **Test coverage**: Must maintain 80% coverage threshold after migration

## Phase 1: Foundation

**Goal**: Establish the versioning constant and infrastructure.

**Tasks:**
- [ ] Add API_V1_PREFIX constant to routes/__init__.py (category: code)

## Phase 2: Server Migration

**Goal**: Update HTTP server to mount all routers under the versioned prefix.

**Tasks:**
- [ ] Update HTTPServer._register_routes to use versioned router (category: code, depends: Phase 1)
- [ ] Update MCP server mount path to /api/v1.0/mcp (category: code, depends: Phase 1)

## Phase 3: Client Updates

**Goal**: Update all internal clients to use the new versioned endpoints.

**Tasks:**
- [ ] Update DaemonClient base URL handling (category: code, depends: Phase 2)
- [ ] Update GobbyAPIClient endpoint paths (category: code, depends: Phase 2)
- [ ] Update hook_dispatcher.py health check URLs (category: code, depends: Phase 2)
- [ ] Update daemon_control.py health check URL (category: code, depends: Phase 2)

## Phase 4: Test Migration

**Goal**: Update all test files to use versioned endpoints.

**Tasks:**
- [ ] Update tests/servers/ URL patterns (category: refactor, depends: Phase 2)
- [ ] Update tests/e2e/ URL patterns (category: refactor, depends: Phase 2)
- [ ] Update tests/hooks/ URL patterns (category: refactor, depends: Phase 2)
- [ ] Update tests/cli/ URL patterns (category: refactor, depends: Phase 2)
- [ ] Update tests/utils/ URL patterns (category: refactor, depends: Phase 2)
- [ ] Update tests/mcp_proxy/ URL patterns (category: refactor, depends: Phase 2)

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|

---

## Implementation Details

### API_V1_PREFIX Constant

Location: `src/gobby/servers/routes/__init__.py`

```python
API_V1_PREFIX = "/api/v1.0"
```

### HTTPServer Changes

Location: `src/gobby/servers/http.py` - `_register_routes` method

```python
from gobby.servers.routes import API_V1_PREFIX

api_v1_router = APIRouter(prefix=API_V1_PREFIX)
api_v1_router.include_router(create_admin_router(self))
api_v1_router.include_router(create_sessions_router(self))
# ... include all routers
app.include_router(api_v1_router)
```

MCP mount changes:
```python
app.mount("/api/v1.0/mcp", mcp_app)  # was: app.mount("/mcp", mcp_app)
```

### URL Pattern Changes

| Before | After |
|--------|-------|
| `/admin/status` | `/api/v1.0/admin/status` |
| `/sessions/*` | `/api/v1.0/sessions/*` |
| `/mcp/*` | `/api/v1.0/mcp/*` |
| `/hooks/*` | `/api/v1.0/hooks/*` |

### Critical Files

**Source (10 files):**
1. `src/gobby/servers/routes/__init__.py` - Add constant
2. `src/gobby/servers/http.py` - Router mounting (lines 417, 469-491)
3. `src/gobby/utils/daemon_client.py` - DaemonClient URLs
4. `src/gobby/tui/api_client.py` - GobbyAPIClient endpoints
5. `src/gobby/install/claude/hooks/hook_dispatcher.py` - Health check
6. `src/gobby/install/gemini/hooks/hook_dispatcher.py` - Health check
7. `src/gobby/mcp_proxy/daemon_control.py` - Health check
8. `src/gobby/mcp_proxy/stdio.py` - Status endpoint
9. `src/gobby/utils/status.py` - Health check
10. `src/gobby/cli/daemon.py` - Status check

**Tests (10+ files):**
- `tests/servers/test_http_server.py`
- `tests/servers/test_mcp_routes.py`
- `tests/servers/test_sessions_routes.py`
- `tests/servers/test_http_coverage.py`
- `tests/e2e/conftest.py`
- `tests/e2e/test_*.py`
- `tests/hooks/test_*.py`
- `tests/cli/test_*.py`
- `tests/utils/test_utils_daemon_client.py`
- `tests/mcp_proxy/test_*.py`

## Verification

1. **All tests pass**: `uv run pytest tests/ -v`
2. **Coverage maintained**: `uv run pytest --cov=src/gobby --cov-fail-under=80`
3. **Type check passes**: `uv run mypy src/`
4. **Manual verification**: Start daemon and verify `/api/v1.0/admin/status` returns 200
