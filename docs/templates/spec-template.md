# Spec Writing Guide

This guide helps you create structured specification documents that can be
parsed into Gobby tasks using `gobby tasks parse-spec` or the `parse_spec` MCP tool.

## Output Location

Write specs to: `docs/plans/{feature-name}.md`

## Document Structure

### 1. YAML Frontmatter

Track spec status and metadata:

```yaml
---
title: '{Feature Name}'
slug: '{feature-slug}'
created: '{YYYY-MM-DD}'
status: 'draft'  # draft, in-progress, complete
stepsCompleted: []
files_to_modify: []
code_patterns: []
---
```

### 2. Title and Overview

```markdown
# {Feature Name}

## Overview

### Problem Statement

[What problem exists? Who is affected? What's the impact?]

### Solution

[How does this feature solve the problem? What's the approach?]

### Scope

**In Scope:**
- [Specific functionality to implement]
- [Changes to existing behavior]

**Out of Scope:**
- [What this spec explicitly does NOT cover]
- [Future work deferred to later specs]
```

### 3. Architecture

**Required section.** Document the technical design:

```markdown
## Architecture

### Component Diagram

[ASCII diagram or description of component relationships]

### Data Flow

[How data moves through the system]

### Key Abstractions

[New classes, interfaces, or patterns introduced]
```

### 4. Codebase Patterns

Reference existing patterns to follow:

```markdown
## Codebase Patterns

### Existing Patterns to Follow

[Describe patterns already in the codebase that this feature should match]

### Files to Reference

| File | Purpose |
| :--- | :--- |
| `src/gobby/tasks/expansion.py` | Example of LLM tool integration |
| `src/gobby/storage/tasks.py` | Database access patterns |
```

### 5. Design Decisions

```markdown
## Design Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| Storage backend | SQLite | Already in use, no new dependencies |
| API style | REST | Matches existing endpoints |
```

### 6. Phased Implementation

Break work into phases. Each phase should be independently shippable or testable.

```markdown
## Phase 1: [Phase Name]

**Goal**: [One sentence outcome]

**Files:**
- `path/to/new/file.py` - [What it does]
- `path/to/modify.py` - [What changes]

**Tasks:**
- [ ] First task with clear action verb
- [ ] Second task (depends: #1)
- [ ] Third task (depends: #2)
- [ ] Documentation task (parallel - no deps)

**Acceptance Criteria:**
- [ ] Criterion that proves phase is complete
- [ ] Another measurable outcome
```

### 7. Task Dependencies

Use explicit dependency notation in task descriptions:

| Notation | Meaning |
| :--- | :--- |
| `(depends: #N)` | Blocked by task N |
| `(depends: #N, #M)` | Blocked by tasks N and M |
| `(depends: Phase N)` | Blocked by all tasks in Phase N |
| `(parallel)` or no annotation | Can run alongside others |

Task numbers (#N) refer to the sequential order tasks appear in the spec.
After `parse_spec` runs, these become actual task references.

### 8. Parallel Work Tracks

Group independent work that can happen simultaneously:

```markdown
**Track A: Backend**
- [ ] API endpoint
- [ ] Database layer

**Track B: Frontend (parallel with Track A)**
- [ ] UI component
- [ ] State management
```

### 9. External Dependencies

```markdown
## Dependencies

### External Dependencies
- [Library X v2.0+] - [Why needed]
- [API access to Y] - [What for]

### Blockers
- [Other spec/feature that must complete first]
```

### 10. Testing Strategy

```markdown
## Testing Strategy

### Unit Tests
- [What modules need unit tests]
- [Coverage expectations]

### Integration Tests
- [End-to-end scenarios to test]

### Manual Verification
- [Steps to manually verify the feature works]
```

### 11. Task Mapping

Include an empty mapping table. `parse_spec` populates this, and agents maintain it:

```markdown
## Task Mapping

<!-- Populated by parse_spec, maintained by agents -->

| Task # | Checkbox | Status |
| :--- | :--- | :--- |
```

### 12. Completion Instructions

Always include clear completion instructions:

```markdown
## Completion Instructions

When completing a task:
1. Make all code changes
2. Run tests: `uv run pytest path/to/tests -v`
3. Commit with task reference: `git commit -m "[#N] description"`
4. Close the task: `gobby tasks close #N --commit-sha <sha>`
5. Update the checkbox above to `[x]`

Never close a task without committing first unless it's a non-code task.
```

## Task Granularity Guidelines

Each checkbox should be:

- **Atomic**: Completable in one session (< 2 hours of work)
- **Testable**: Has clear pass/fail criteria
- **Verb-led**: Starts with action verb (Add, Create, Implement, Update, Remove)
- **Scoped**: References specific files/functions when possible

**Good examples:**
- `- [ ] Add TaskEnricher class to src/gobby/tasks/enrich.py`
- `- [ ] Create database migration for category field`
- `- [ ] Update CLAUDE.md with new task workflow`

**Bad examples:**
- `- [ ] Implement enrichment` (too vague)
- `- [ ] Fix bugs` (not specific)
- `- [ ] Make it work` (no clear criteria)

## Complete Example

```markdown
---
title: 'User Authentication'
slug: 'user-auth'
created: '2025-01-12'
status: 'draft'
stepsCompleted: []
files_to_modify:
  - src/auth/jwt.py
  - src/auth/middleware.py
  - src/api/routes/auth.py
code_patterns:
  - middleware pattern from src/gobby/hooks/
---

# User Authentication

## Overview

### Problem Statement

All API endpoints are currently public. This blocks the multi-tenant feature
and exposes user data to unauthorized access.

### Solution

Add JWT-based authentication with HTTP-only cookies for token storage.
Existing endpoints will require authentication via a decorator.

### Scope

**In Scope:**
- JWT token generation and validation
- Login/logout endpoints
- Auth middleware for protected routes
- Decorator for route protection

**Out of Scope:**
- User registration (separate spec)
- OAuth/social login (future)
- Role-based access control (future)

## Architecture

### Component Diagram

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │───>│  Middleware │───>│   Routes    │
└─────────────┘    └─────────────┘    └─────────────┘
                          │
                   ┌──────┴──────┐
                   │  JWT Module │
                   └─────────────┘
```

### Data Flow

1. Client sends credentials to /auth/login
2. Server validates, generates JWT, sets HTTP-only cookie
3. Subsequent requests include cookie automatically
4. Middleware validates JWT before route handler

## Codebase Patterns

### Existing Patterns to Follow

- Middleware pattern from `src/gobby/hooks/hook_manager.py`
- Route registration from `src/gobby/servers/http.py`

### Files to Reference

| File | Purpose |
| :--- | :--- |
| `src/gobby/hooks/hook_manager.py` | Middleware chaining pattern |
| `src/gobby/servers/http.py` | FastAPI route registration |

## Design Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| Auth method | JWT | Stateless, works with existing API |
| Token storage | HTTP-only cookie | Secure, automatic on requests |
| Token expiry | 24 hours | Balance security and UX |

## Phase 1: Foundation

**Goal**: Basic JWT auth working end-to-end.

**Files:**
- `src/auth/jwt.py` - Token generation and validation
- `src/auth/middleware.py` - Request authentication
- `src/api/routes/auth.py` - Login/logout endpoints

**Tasks:**
- [ ] Create JWT utility module with sign/verify functions
- [ ] Add auth middleware that validates tokens (depends: #1)
- [ ] Create login endpoint returning JWT (depends: #1)
- [ ] Create logout endpoint that clears cookie (depends: #2)
- [ ] Add tests for auth flow (depends: #3, #4)

**Acceptance Criteria:**
- [ ] Can login with valid credentials and receive token
- [ ] Invalid credentials return 401
- [ ] Logout clears the auth cookie

## Phase 2: Protected Routes

**Goal**: Existing endpoints require authentication.

**Tasks:**
- [ ] Add @requires_auth decorator (depends: Phase 1)
- [ ] Apply decorator to task endpoints (depends: #6)
- [ ] Apply decorator to session endpoints (depends: #6)
- [ ] Update API documentation (parallel)

**Acceptance Criteria:**
- [ ] Unauthenticated requests to protected routes return 401
- [ ] Authenticated requests succeed as before

## Dependencies

### External Dependencies
- PyJWT library (already in dependencies)

### Blockers
- None

## Testing Strategy

### Unit Tests
- JWT sign/verify functions
- Middleware token extraction
- Decorator behavior

### Integration Tests
- Full login flow
- Protected route access
- Token expiry handling

### Manual Verification
1. Start server: `uv run gobby start`
2. Attempt protected endpoint without auth (expect 401)
3. Login via POST /auth/login
4. Retry protected endpoint (expect success)
5. Logout and verify token cleared

## Task Mapping

| Task # | Checkbox | Status |
| :--- | :--- | :--- |

## Completion Instructions

When completing a task:
1. Make all code changes
2. Run tests: `uv run pytest tests/auth/ -v`
3. Commit with task reference: `git commit -m "[#N] description"`
4. Close the task: `gobby tasks close #N --commit-sha <sha>`
5. Update the checkbox above to `[x]`
```

## After Writing Your Spec

1. Review the spec for completeness and clear dependencies
2. Run `gobby tasks parse-spec docs/plans/{feature}.md` to create tasks
3. Verify task structure with `gobby tasks list --tree`
4. Optionally enrich tasks: `gobby tasks enrich #N --cascade`
5. Optionally expand complex tasks: `gobby tasks expand #N`
6. Optionally apply TDD to code tasks: `gobby tasks apply-tdd #N --cascade`
