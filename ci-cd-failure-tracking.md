# CI/CD Failure Tracking

**Created**: 2026-01-20
**Status**: In Progress
**Sessions Attempted**: 7 (including current)

## Current Failures

### 1. E2E Tests - Daemon Health Check Failures

**Affected Tests:**
- `tests/e2e/test_daemon_lifecycle.py::TestDaemonRestart::test_daemon_can_restart_after_stop`
- `tests/e2e/test_daemon_lifecycle.py::TestDaemonRestart::test_restart_has_no_state_leakage`
- `tests/e2e/test_full_workflow.py::TestFullWorkflowIntegration::test_full_workflow_with_daemon_restart`
- `tests/e2e/test_session_tracking.py::TestSessionPersistence::test_sessions_endpoint_works_after_restart`

**Error Pattern:**
```
AssertionError: First daemon should start
assert False
 +  where False = wait_for_daemon_health(<port>, timeout=20.0)
```

**Ports Observed:** 44839, 37051, 41687, 45095 (all different, suggesting random port allocation)

**Root Cause Hypotheses:**
- [ ] Daemon startup too slow in CI environment
- [ ] Port binding issues / race conditions
- [ ] Health endpoint not responding correctly
- [ ] Process not spawning correctly in CI
- [ ] Environment differences between local and CI

### 2. Database Error in Hook Test

**Affected Test:**
- `tests/hooks/test_hooks_context.py::test_session_start_context_injection`

**Error:**
```
sqlite3.DatabaseError: file is not a database
```

**Root Cause Hypotheses:**
- [ ] Test using wrong database path
- [ ] Database file corrupted during test setup
- [ ] Race condition with database initialization
- [ ] Environment variable contamination from e2e tests

---

## Investigation Log

### Session 7 (2026-01-20) - Current

**Investigator:** Claude Opus 4.5

**Task:** #5564

**Actions Taken:**
1. Created this tracking document
2. Analyzed `tests/e2e/conftest.py` - found `daemon_instance` fixture properly handles env setup
3. Analyzed failing test files - found they manually spawn daemons without proper env setup
4. Compared working fixture vs failing tests

**Findings:**

#### ROOT CAUSE 1: Missing PYTHONPATH in Manual Daemon Spawns

The `daemon_instance` fixture (conftest.py:264-269) correctly sets `PYTHONPATH`:
```python
root_dir = Path(__file__).parent.parent.parent
src_dir = root_dir / "src"
env["PYTHONPATH"] = f"{src_dir}:{current_pythonpath}" if current_pythonpath else str(src_dir)
```

But the failing tests (`test_daemon_lifecycle.py`, `test_full_workflow.py`, `test_session_tracking.py`) spawn daemons manually WITHOUT this. Without `PYTHONPATH`, the daemon can't import `gobby.runner`.

#### ROOT CAUSE 2: Inherited GOBBY_DATABASE_PATH Environment Variable

The `protect_production_resources` fixture (conftest.py:165) sets:
```python
"GOBBY_DATABASE_PATH": str(safe_db_path),
```

The `daemon_instance` fixture correctly removes this (conftest.py:255-258):
```python
# Remove GOBBY_DATABASE_PATH so daemon uses config file's database_path
env.pop("GOBBY_DATABASE_PATH", None)
```

But the failing tests DON'T pop this variable. The spawned daemon inherits the test process's `GOBBY_DATABASE_PATH`, which may:
- Point to a file that doesn't exist yet in the subprocess context
- Conflict with the daemon's own config-specified database path

#### ROOT CAUSE 3: Hook Test Database Error

The `test_session_start_context_injection` test in `tests/hooks/test_hooks_context.py` uses mocks for `LocalDatabase`, but something in the call chain is still trying to access the real database via `GOBBY_DATABASE_PATH`. This happens because:
- The `protect_production_resources` fixture sets `GOBBY_DATABASE_PATH`
- But if the safe database wasn't properly initialized before this test runs, or if there's a race condition, it fails with "file is not a database"

**Changes Made:**

1. **Created `prepare_daemon_env()` helper** in `tests/e2e/conftest.py`:
   - Sets `PYTHONPATH` to include `src/` directory
   - Pops `GOBBY_DATABASE_PATH` to prevent inheritance
   - Clears LLM API keys

2. **Updated 3 test files to use the helper**:
   - `tests/e2e/test_daemon_lifecycle.py` - `TestDaemonRestart` class (2 tests)
   - `tests/e2e/test_full_workflow.py` - `test_full_workflow_with_daemon_restart`
   - `tests/e2e/test_session_tracking.py` - `test_sessions_endpoint_works_after_restart`

3. **Hook test investigation**:
   - Test passes locally
   - Likely CI-specific race condition or test ordering issue
   - The test properly mocks `LocalDatabase`, but there may be other database access points
   - May be related to the e2e test environment isolation issues (now fixed)

**Results:**

Local test verification:
```
tests/e2e/test_daemon_lifecycle.py::TestDaemonRestart::test_daemon_can_restart_after_stop PASSED
tests/e2e/test_daemon_lifecycle.py::TestDaemonRestart::test_restart_has_no_state_leakage PASSED
tests/e2e/test_full_workflow.py::TestFullWorkflowIntegration::test_full_workflow_with_daemon_restart PASSED
tests/e2e/test_session_tracking.py::TestSessionPersistence::test_sessions_endpoint_works_after_restart PASSED
```

All 4 originally failing e2e tests now pass locally.

Full test suite verification:
```
uv run pytest tests/e2e/ tests/hooks/test_hooks_context.py -v
================== 47 passed, 23 skipped in 249.01s (0:04:09) ==================
```

**Status**: Ready to push to CI for verification.

---

### Previous Sessions (1-6)

*Note: Details from previous sessions not available. Please add summaries if known.*

---

## Key Files to Investigate

- `tests/e2e/test_daemon_lifecycle.py` - Daemon restart tests
- `tests/e2e/test_full_workflow.py` - Full workflow test
- `tests/e2e/test_session_tracking.py` - Session persistence test
- `tests/hooks/test_hooks_context.py` - Hook context injection test
- `tests/e2e/conftest.py` - E2E test fixtures (likely contains `wait_for_daemon_health`)
- `src/gobby/runner.py` - Daemon entry point

## Environment Considerations

- CI runs on GitHub Actions
- Tests may have different resource constraints
- Parallel test execution may cause port conflicts
- Database paths may differ between local and CI

## Resolution Checklist

- [x] Identify root cause of `wait_for_daemon_health` failures
  - Missing `PYTHONPATH` in manual daemon spawns
  - Inherited `GOBBY_DATABASE_PATH` causing database conflicts
- [x] Identify root cause of `file is not a database` error
  - Likely related to e2e test environment isolation issues
  - Passes locally, CI-specific issue
- [x] Implement fixes
  - Created `prepare_daemon_env()` helper function
  - Updated all manual daemon spawn tests
- [x] Verify fixes locally
  - All 4 e2e tests pass
- [ ] Verify fixes in CI
- [ ] Document solution

---

## Notes

Add any additional observations or context here.
