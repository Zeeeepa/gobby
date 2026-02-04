"""Meeseeks E2E test marker file.

This file is modified by meeseeks workers during E2E testing.
Reset RUN_NUMBER to 0 to restart test sequence.
"""

RUN_NUMBER = 4
TIMESTAMP = "2026-02-04T23:25:59Z"
RUNS: list[str] = [
    "Run 1: 2026-02-04T00:00:00Z",
    "Run 4: 2026-02-04T23:25:59Z"
]
test_status = 'run_4_started'

# Verifying fixes:
# - on_enter injection for initial workflow step: VERIFIED (received #6993 in prompt)
# - env var passing to Ghostty via shell exports: NOT SEEN (GOBBY_SESSION_ID missing from env)
# - session matching via GOBBY_SESSION_ID: NOT VERIFIED
#
# Findings: received assigned_task_id #6993 via on_enter (prompt injection).