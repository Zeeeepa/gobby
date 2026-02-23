# Basic Auth System for Gobby UI

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Auth mode | **Optional, off by default** | Local-first philosophy. No credentials = open UI (today's behavior). Set username+password = auth enforced. |
| Scope | **UI only** | CLI agents (Claude Code, Gemini, Codex) keep working without auth. API + WS remain open. |
| Password storage | **bcrypt hash in secrets table** | Industry standard. Fernet encryption on top = defense in depth. |
| Session mechanism | **Signed cookie (HMAC-SHA256)** | Persistent "remember me" cookie. Session token stored server-side in SQLite. |
| Cookie duration | **30 days (remember me)** / **session-only (default)** | Standard pattern. |

## Summary of Changes

Add a basic username/password auth system to the Gobby web UI:

1. **Backend**: Auth config model, auth middleware, login/logout API endpoints, session table
2. **Frontend**: Login page component, auth state management, "Remember me" checkbox
3. **Config UI**: Username/password fields in the Configuration page (password stored as secret)

---

## 1. Database: Session Table

**New table** in `gobby-hub.db`:

```sql
CREATE TABLE IF NOT EXISTS auth_sessions (
    token TEXT PRIMARY KEY,          -- Random 32-byte hex token
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,        -- UTC datetime
    remember_me INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_auth_sessions_expires ON auth_sessions(expires_at);
```

**File**: `src/gobby/storage/auth.py` (new)

- `AuthStore` class with methods:
  - `create_session(remember_me: bool) -> str` — generate token, insert row, return token
  - `validate_session(token: str) -> bool` — check exists + not expired, clean up expired
  - `delete_session(token: str)` — logout
  - `cleanup_expired()` — delete expired sessions (called on validate)

---

## 2. Backend: Auth Config Model

**File**: `src/gobby/config/app.py`

Add `AuthConfig` Pydantic model and add it to `DaemonConfig`:

```python
class AuthConfig(BaseModel):
    """Basic authentication for the web UI."""
    username: str = Field(default="", description="Username for web UI login. Leave empty to disable auth.")
    password: str = Field(default="", description="Password for web UI login (stored as bcrypt hash in secrets).")
    session_secret: str = Field(default="", description="HMAC signing key for session cookies (auto-generated).")
```

Add to `DaemonConfig`:
```python
auth: AuthConfig = Field(
    default_factory=AuthConfig,
    description="Web UI authentication configuration",
)
```

**Storage notes**:
- `auth.username` → stored in `config_store` as plain text
- `auth.password` → stored in `secrets` table as bcrypt hash (via `$secret:auth_password`)
- `auth.session_secret` → stored in `secrets` table (via `$secret:auth_session_secret`), auto-generated on first login if empty

---

## 3. Backend: Auth Middleware

**File**: `src/gobby/servers/middleware/auth.py` (new)

FastAPI middleware that:

1. Checks if auth is configured (`auth.username` and `auth.password` are non-empty)
2. If not configured → pass through (no auth, today's behavior)
3. If configured, check request path:
   - **Skip auth for**: `/api/auth/login`, `/api/auth/status`, `/api/health`, static assets (`/assets/`)
   - **Require auth for**: all other `/api/*` routes that serve UI data, and the SPA catch-all
4. Auth check: read `gobby_session` cookie → validate token via `AuthStore`
5. If invalid/missing → for SPA routes, serve login page; for API routes, return 401

**Wire into**: `src/gobby/servers/http.py` — add middleware after CORS middleware.

---

## 4. Backend: Auth API Routes

**File**: `src/gobby/servers/routes/auth.py` (new)

```
POST /api/auth/login
  Body: { "username": str, "password": str, "remember_me": bool }
  - Validate username matches config
  - bcrypt.checkpw(password, stored_hash)
  - Create session via AuthStore
  - Set cookie: `gobby_session=<token>; HttpOnly; SameSite=Lax; Path=/`
    - If remember_me: Max-Age=30 days
    - If not: session cookie (no Max-Age)
  - Return: { "ok": true }

POST /api/auth/logout
  - Delete session from AuthStore
  - Clear cookie
  - Return: { "ok": true }

GET /api/auth/status
  - Check cookie validity
  - Return: { "authenticated": bool, "auth_required": bool }
```

**Wire into**: `src/gobby/servers/http.py` — mount `create_auth_router()`.

---

## 5. Backend: Password Hashing on Config Save

**File**: `src/gobby/servers/routes/configuration.py`

Modify the `save_config_values` (`PUT /api/config/values`) endpoint:

- When `auth.password` is being saved and value is not the mask (`********`):
  1. bcrypt hash the plaintext password
  2. Store the hash in the secrets table as `auth_password`
  3. Store `$secret:auth_password` in config_store for `auth.password`
- When `auth.session_secret` is empty, auto-generate a 32-byte random hex string and store as `auth_session_secret` secret

---

## 6. Frontend: Login Page Component

**File**: `web/src/components/LoginPage.tsx` (new)

Simple centered login form:
- Username input
- Password input
- "Remember me" checkbox
- Submit button
- Error message display (invalid credentials)
- Calls `POST /api/auth/login`
- On success, triggers page reload or state update to show main app

**Styling**: `web/src/components/LoginPage.css` (new) — matches existing dark theme.

---

## 7. Frontend: Auth State Management

**File**: `web/src/hooks/useAuth.ts` (new)

```typescript
function useAuth() {
  const [authState, setAuthState] = useState<{
    loading: boolean
    authenticated: boolean
    authRequired: boolean
  }>({ loading: true, authenticated: false, authRequired: false })

  // On mount: GET /api/auth/status
  // Returns { loading, authenticated, authRequired, login(), logout() }
}
```

---

## 8. Frontend: App.tsx Integration

**File**: `web/src/App.tsx`

Wrap the main app with auth gate:

```tsx
function App() {
  const { loading, authenticated, authRequired } = useAuth()

  if (loading) return <LoadingSpinner />
  if (authRequired && !authenticated) return <LoginPage onSuccess={() => refetch()} />

  // ... existing app content
}
```

Minimal change — just an early return before the existing render tree.

---

## 9. Frontend: Config Page — Auth Section

**File**: `web/src/components/ConfigurationPage.tsx`

The auth fields (`auth.username`, `auth.password`) should already render via the schema-driven form since we're adding them to `DaemonConfig`. The existing `SECRET_PATTERNS` list already includes `password`, so `auth.password` will automatically be treated as a secret field (masked input, stored via secrets API).

**Verify**: The schema-driven rendering in ConfigurationPage already handles nested objects. `auth.username` and `auth.password` should appear under an "Auth" section automatically.

Only change needed: ensure `auth.session_secret` is hidden from the UI (add to a hidden/internal fields list, or mark it with `json_schema_extra={"ui_hidden": True}` in the Pydantic model).

---

## Files to Create/Modify

### New Files (4)
| File | Purpose |
|------|---------|
| `src/gobby/storage/auth.py` | AuthStore — session CRUD + cleanup |
| `src/gobby/servers/middleware/auth.py` | FastAPI auth middleware |
| `src/gobby/servers/routes/auth.py` | Login/logout/status API routes |
| `web/src/components/LoginPage.tsx` | Login page UI |
| `web/src/components/LoginPage.css` | Login page styles |
| `web/src/hooks/useAuth.ts` | Auth state hook |

### Modified Files (4)
| File | Change |
|------|--------|
| `src/gobby/config/app.py` | Add `AuthConfig` model + field on `DaemonConfig` |
| `src/gobby/servers/http.py` | Mount auth middleware + auth router |
| `src/gobby/servers/routes/configuration.py` | bcrypt hash password on save |
| `web/src/App.tsx` | Auth gate wrapper |

---

## Implementation Order

1. `AuthConfig` in `config/app.py` (model first)
2. `AuthStore` in `storage/auth.py` (session table)
3. Auth routes in `routes/auth.py` (login/logout/status)
4. Password hashing in `routes/configuration.py`
5. Auth middleware in `middleware/auth.py`
6. Wire middleware + router in `http.py`
7. `useAuth` hook (frontend)
8. `LoginPage` component + CSS (frontend)
9. Auth gate in `App.tsx`

---

## Verification Steps

1. **No auth configured** (default): UI loads normally, no login page, all routes work — zero regression
2. **Set username + password** via Config UI: password field masked, saved as bcrypt hash in secrets table
3. **Reload browser**: login page appears, existing API calls from CLI agents still work
4. **Login with correct creds**: cookie set, redirected to main app
5. **Login with wrong creds**: error message shown
6. **Remember me checked**: cookie persists after browser close (30-day expiry)
7. **Remember me unchecked**: cookie is session-only, gone after browser close
8. **Logout**: cookie cleared, redirected to login page
9. **Expired session**: redirected to login page on next request
10. **Remove credentials from config**: auth disabled, UI open again
