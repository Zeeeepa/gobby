# Orchestration: comms-critical-fixes

## Status: RUNNING

## Configuration

| Key | Value |
|-----|-------|
| Epic | #10955 — Comms: Critical Fixes from Code Review |
| Epic ID | a1427999-6e54-4711-8d81-8afa110bf3e1 |
| Cron Job | cj-89732f483318 |
| Cron Interval | 300s (5m) |
| Isolation | worktree |
| Dev Agent | python-dev (gemini / provider-default, terminal) |
| QA Agent | qa-reviewer (claude / opus, terminal) |
| Agent Timeout | 1200s |
| Max Concurrent | 10 |
| Merge Target | 0.3.2 |
| Created | 2026-03-29T05:20:45Z |

## Subtasks (9)

| Ref | Title | Status |
|-----|-------|--------|
| #10956 | Fix webhook HMAC re-serialization and Slack url_verification | open |
| #10957 | Teams: add tenant validation and service URL allowlist | open |
| #10958 | Fix destination resolution and broken update_channel endpoint | open |
| #10959 | Fix Discord heartbeat, email IMAP mark-seen, and SMTP reconnect | open |
| #10960 | Add cascade delete for channels and expose public manager API | open |
| #10961 | Add retry logic, rate limit handling, and protocol compliance across adapters | open |
| #10962 | Add router rule caching and LRU thread map eviction | open |
| #10923 | Discord gateway adapter missing heartbeat/ACK implementation | open |
| #10880 | Communications Integrations UI | open |

## Log

- 2026-03-29T05:20:45Z — Orchestration created, first tick triggered
