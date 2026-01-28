# Rename diagnostic to doctor with security audit

## Overview

Rename the `diagnostic` skill to `doctor` and add security audit checks inspired by Clawdbot's `doctor` command. Default behavior shows help; users choose functional, security, or all checks via flags. Also create a `/gobby usage` skill that leverages existing metrics infrastructure.

**Background**: The current diagnostic skill runs functional tests (phases 1-4). This plan adds Phase 5 (security audit) and restructures the subcommands for clarity.

## Constraints

- Keep existing phases 1-4 functional tests intact (no regression)
- Security checks must be non-destructive (read-only)
- Usage skill must use existing `gobby-metrics` MCP tools
- Model extraction fix required for accurate cost reporting

## Phase 1: Rename Skill Directory

**Goal**: Rename diagnostic skill to doctor with updated metadata

**Tasks:**
- [ ] Rename `src/gobby/install/shared/skills/diagnostic/` directory to `doctor/` (category: config)
- [ ] Update skill name from `diagnostic` to `doctor` in SKILL.md frontmatter (category: config, depends: Rename diagnostic directory)
- [ ] Update skill description with new trigger phrases in SKILL.md (category: config, depends: Update skill name)
- [ ] Update skill header from `/gobby-diagnostic` to `/gobby doctor` (category: config, depends: Update skill description)

## Phase 2: Restructure Subcommands

**Goal**: Update subcommand structure to match new flag-based interface

**Tasks:**
- [ ] Replace `--quick` subcommand with `--functional` (phases 1-3, no worktree/clone) (category: config, depends: Phase 1)
- [ ] Replace `--full` subcommand with `--all` (functional + security + resource-heavy) (category: config, depends: Replace --quick subcommand)
- [ ] Add `--security` subcommand for phase 5 only (category: config, depends: Replace --full subcommand)
- [ ] Update default `/gobby doctor` behavior to show help with available options (category: config, depends: Add --security subcommand)

## Phase 3: Add Security Audit Phase

**Goal**: Implement Phase 5 security checks in SKILL.md

**Tasks:**
- [ ] Add Phase 5 section header and overview after Phase 4 (category: config, depends: Phase 2)
- [ ] Add check 5.1: File permissions for config.yaml, .mcp.json, gobby-hub.db (0o600) (category: config, depends: Add Phase 5 section header)
- [ ] Add check 5.2: Scan for plaintext secrets in llm_providers.api_keys (category: config, depends: Add check 5.1)
- [ ] Add check 5.3: HTTP binding check for 0.0.0.0 daemon binding (category: config, depends: Add check 5.2)
- [ ] Add check 5.4: Validate webhook endpoints use HTTPS (category: config, depends: Add check 5.3)
- [ ] Add check 5.5: Warn if logging.level is DEBUG (category: config, depends: Add check 5.4)
- [ ] Add check 5.6: Warn if hook_extensions.plugins.enabled is true (category: config, depends: Add check 5.5)
- [ ] Add check 5.7: Validate remote MCP server URLs use HTTPS (category: config, depends: Add check 5.6)
- [ ] Add check 5.8: List skills with `allowed-tools: ["*"]` as warning (category: config, depends: Add check 5.7)
- [ ] Update output format to include Phase 5 in summary (category: config, depends: Add check 5.8)

## Phase 4: Fix Model Extraction in Transcripts

**Goal**: Extract model from Claude Code transcripts for accurate cost reporting

**Tasks:**
- [ ] Add `model` field to ParsedMessage dataclass in `src/gobby/sessions/transcripts/base.py` (category: code)
- [ ] Update `_extract_usage()` in `src/gobby/sessions/transcripts/claude.py` to return model (category: code, depends: Add model field to ParsedMessage)
- [ ] Update SessionMessageProcessor in `src/gobby/sessions/processor.py` to capture model (category: code, depends: Update _extract_usage in claude.py)

## Phase 5: Create Usage Skill

**Goal**: Create /gobby usage skill for token and budget reporting

**Tasks:**
- [ ] Create `src/gobby/install/shared/skills/usage/` directory (category: config, depends: Phase 4)
- [ ] Create SKILL.md with frontmatter (name, description, category, triggers) (category: config, depends: Create usage directory)
- [ ] Add `--today` subcommand for today's usage summary (category: config, depends: Create SKILL.md with frontmatter)
- [ ] Add `--week` subcommand for last 7 days summary (category: config, depends: Add --today subcommand)
- [ ] Add `--budget` subcommand for budget status only (category: config, depends: Add --week subcommand)
- [ ] Add output format section with example display (category: config, depends: Add --budget subcommand)
- [ ] Document MCP tool calls: `gobby-metrics.get_usage_report()`, `get_budget_status()` (category: config, depends: Add output format section)

## Task Mapping

<!-- Updated after task creation -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|

## Sources

- Clawdbot research: security audit pattern for doctor command
- Existing diagnostic skill: `src/gobby/install/shared/skills/diagnostic/SKILL.md`
- Metrics infrastructure: `gobby-metrics.get_usage_report()`, `gobby-metrics.get_budget_status()`
