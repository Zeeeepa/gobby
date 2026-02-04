# Changelog

All notable changes to Gobby are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.11] - 2025-02-04

### Improvements

- Add `mode: self` to `spawn_agent` for in-session workflow activation (#6909)
- Make commit task ID format dynamic based on project name (#6904)
- Change task ID format from `[#N]` to `gobby#N` then to `gobby-#N` (#6898, #6902)

### Bug Fixes

- Fix 54 failing tests (#6912)
- Fix mypy no-any-return errors (#6910)
- Fix worktree tools: orphaned records and MCP type coercion (#6905)
- Fix transcript parsing crash when JSON line is not an object (#1)

### Documentation

- Document gobby-projects-v2 plan (#6907)
- Create gobby-plugins internal MCP server plan (#6903)

### Internal

- Improve task lifecycle tool enforcement (#6876, #6877)
- Remove `init_project` from stdio MCP server (#6897)
- Block workflow-restricted tools in MCP `call_tool` (#6896)
- Block 'review' status in `update_task` (#6875)
- Decouple gobby-skills and gobby-artifacts from task_manager (#6873)
- Exclude deprecated workflows from `gobby install` (#6911)

## [0.2.10] - 2025-02-01

### Major Features

#### Multi-CLI Adapter Support
- Add Cursor, Windsurf, and Copilot session support (#6140)
- Implement proper Copilot, Windsurf, and Cursor adapters (#6857-#6860)
- Add auto-installation for Cursor, Windsurf, Copilot (#6867)
- Add hook dispatchers for Cursor, Windsurf, Copilot
- Centralize `machine_id` in base adapter (#6842)

#### Pipeline System
- Add WebSocket streaming for pipeline execution (#6798)
- Register gobby-pipelines MCP server in daemon (#6797)
- Implement template rendering in pipeline `_render_step` (#6796)

#### Agent Improvements
- Add unified agent file with named workflows (#6847)
- Auto-detect current branch as `base_branch` (#6852)
- Load and persist inline workflows from agent definitions (#6849, #6850)
- Handle None name in inline workflow registration (#6848)
- Use `close_terminal` MCP tool for agent shutdown (#6839)
- Validate workflow exists before spawning (#6834)
- Use effective_workflow from agent definition (#6837)

### Bug Fixes

- Fix 76 mypy type errors and pytest collection issue (#6861)
- Fix 27 code quality issues from CodeRabbit review (#6856)
- Add missing `step_variables` column to test mock schema (#6854)
- Fix machine_id test mock paths and E2E workflow setup
- Resolve bandit and pip-audit security issues (#6862)
- Replace CursorAdapter stub with proper hooks implementation (#6863)
- Fix sandbox to pass `GOBBY_MACHINE_ID` env var (#6841)
- Include `~/.gobby/` in sandbox read paths for machine_id access (#6840)
- Allow Tailscale IP access in Vite config (#6843)

### Documentation

- Add Cursor, Windsurf, Copilot to CLI guides (#6868)
- Fix README CLI config to use `gobby install` (#6866)
- Update README with native CLI adapter details (#6865)
- Mark CLI adapters plan as complete (#6864)

### Internal

- Multiple test fixes for production code changes (#6869, #6871)
- Align test suite with production code changes

## [0.2.9] - 2025-01-30

### Improvements

- Skip CI on dev branch pushes - only run full CI on main and PRs (#6615)
- Add `debug_echo_context` toggle to echo additionalContext to terminal (#6606, #6607)
- Add artifact stats to `gobby status` display (#6585)
- Wire up artifact capture in hook manager (#6581)
- Wire up `gobby-artifacts` in internal registry (#1)
- Add `api_key` auth mode to `ClaudeLLMProvider` (#6568)
- Allow task management MCP calls in plan mode (#6592)
- Add trigger-based filtering to Gemini `on_pre_compact` (#6588)
- Add centralized `paths.py` utility for stable path resolution (#6598)

### Bug Fixes

- Fix hook validation order - schema check before commit check (#6614)
- Fix daemon stop/restart timeout by implementing proper shutdown (#6609)
- Fix mypy errors and test failures (#6613, #6605)
- Fix TYPE_CHECKING import and remove test_output.txt (#6610)
- Fix progressive disclosure enforcement for `call_tool` (#6576)
- Fix response consistency in `get_tool_schema` (#6586)
- Fix `session_id` resolution, schema nesting, and worker model (#6578)
- Fix return value and exception handling in `_artifacts.py` (#6577)
- Fix TypeBox syntax, add security section, and fix SDK image content (#6575)
- Fix model consistency, error handling, and encoding issues (#6571)
- Fix workflow lifecycle safety and test async generator (#6570)
- Fix context accumulation, db lifecycle, and force parameter issues (#6566)
- Fix security and consistency issues in event handlers and workflow tools (#6556)
- Preserve lifecycle variables when activating step workflows (#6591)
- Fix test for `suggest_next_task` leaf task support (#6590)
- Fix type annotation inconsistency in `resolve_session_task_value` (#6595)
- Fix bandit B110 try-except-pass in `_tool.py` (#6593)
- Fix colon syntax in progressive disclosure error message (#6579)
- Remove `os.environ` mutation from `_setup_litellm` (#6584)
- Fix bundled template test paths (#6616)

### Documentation

- Document lifecycle workflow blocking and hook data (#6589)
- Update artifacts docs to use `gobby-artifacts` server (#6580)

### Internal

- Remove service unpacking in HTTPServer, use ServiceContainer (#6611)
- Add `_mcp_db_manager` property and fix hook test (#6612)
- Legacy cleanup, Memory decomposition, and Runner DI
- Remove redundant context from compact handoff (#6608)
- Rename `_types.py` to `_resolution.py` in workflows (#6604)
- Add debug logging for invalid workflow files (#6603)
- Extract pre-created session and response composition helpers (#6602)
- Extract `_prepare_image_data` helper in `claude.py` (#6600)
- Extract `_format_summary_context` helper in `claude.py` (#6599)
- Refactor `end_workflow` to accept loader parameter (#6596)
- Update db docstring to match DatabaseProtocol type annotation (#6594)
- Remove `worker_model` from `auto-task-claude` workflow (#6582)
- Export `EDIT_TOOLS` from `event_handlers` package (#6569)
- Decompose `workflows.py` and `event_handlers.py` packages

## [0.2.8] - 2025-01-29

### Improvements

- Refactored Gemini spawn to use preflight+resume pattern (#6532)
- Applied sandbox config in Gemini terminal spawn (#6534)
- Added `session_ref` to `additionalContext` for hooks (#6546, #6547, #6548)
- Optimized hook metadata token usage with first-hook tracking (#6549)
- Disabled PreCompress hook handling for Gemini (#6533)
- Added database fallback to `kill_agent` for session lookup (#6455)
- `work-task-gemini` workflow now supports tasks without file edits (#6529)
- Excluded `.gobby/` files from `had_edits` tracking (#6541)
- Excluded `.gobby/` files from CI/CD and pre-commit triggers (#6543)
- Standardized `session_id` to accept `#N` format across all MCP tools (#6459)
- Refactored messaging tools to database-primary architecture (#6456)
- Added database fallback to `send_to_parent` for Gemini agents (#6451)
- CLI hooks now copied to worktrees and clones during isolation setup (#6448)
- Added `workflow_name` and `agent_depth` to session metadata cache (#6443)
- Extracted workflow activation into `_auto_activate_workflow` helper (#6441)
- Namespaced `gobby_context` key to avoid silent overwrites (#6438)
- Pass `parent_task_id` to `suggest_next_task` in find_work step (#6444)
- Updated meeseeks model to `gemini-3-pro-preview`

### Bug Fixes

- Fixed memory duplicates, NULL project_id, and JSONL export (#6553)
- Return graceful responses for hook errors instead of HTTP 500 (#6539)
- Fixed session ID vs external ID clarification in context injection (#6536)
- Fixed workflow instructions for Gemini tool calling (#6535)
- Fixed spawn_agent opening two terminal windows on macOS (#6531)
- Fixed template, error handling, and documentation issues (#6544)
- Fixed failing tests in test_cli.py and test_skill_sync.py (#6542)
- Fixed newline corruption in get_current_session references
- Fixed syntax error in session messages coverage test
- Fixed async lock, template conditionals, and workflow transitions (#6450)
- Fixed documentation drift, caching issues, and workflow config errors (#6460)
- Fixed async/blocking issues and code quality problems (#6458)
- Fixed 8 failing tests (#6464)
- Fixed session ID documentation and cleaned up legacy skills (#6478)
- Fixed Gemini spawn test env assertions for explicit validation (#6442)
- Fixed syntax errors in session CRUD tools

### Documentation

- Documented agent lifecycle and shutdown mechanisms (#6540)
- Added Codex app-server hook parity plan (#6552)
- Added personal workspace plan for project-optional tasks (#6545)
- Added remote access implementation plan (#6461)
- Added missing param docs to `register_session` docstring (#6440)

### Internal

- Multiple code quality fixes across files (#6462, #6463, #6465, #6466, #6469, #6470)
- Added pytest markers and test return type hints (#6524)
- Normalized timestamps to include timezone offsets (#6471)
- Replaced f-string logs with structured logging in hook dispatcher and workflow activation (#6439, #6447)
- Added `@pytest.mark.unit` decorator to `TestToolNameNormalization` (#6449)

## [0.2.7] - 2025-01-28

### Major Features

#### Unified Spawn Agent API
- New unified `spawn_agent` MCP tool replacing legacy spawn tools
- `IsolationHandler` abstraction with `CurrentIsolationHandler`, `WorktreeIsolationHandler`, and `CloneIsolationHandler`
- `SpawnExecutor` for unified spawn dispatch across all isolation modes
- `generic.yaml` agent and workflow definitions as reference implementations
- Deprecation warnings added to `spawn_agent_in_worktree`, `spawn_agent_in_clone`, and `start_agent`

#### Agent Sandboxing
- `SandboxConfig` models for agent spawning with network and filesystem controls
- Sandbox resolvers for CLI-specific configuration (Claude, Gemini, Codex)
- Sandbox params in `spawn_agent` MCP tool and `build_cli_command`
- `sandboxed.yaml` example agent demonstrating sandbox configuration
- Integration and unit tests for sandbox functionality

#### Project-Scoped Session References
- Database schema for project-scoped session sequential numbers
- CLI integration for displaying `#N` style session refs
- MCP tools and display updates for session refs
- Migration 77 for session seq_num backfill

#### Database Migration V2 Baseline
- Flattened baseline schema (BASELINE_SCHEMA_V2) for fresh installs
- `use_flattened_baseline` config option (defaults to True)
- `schema_dump.sql` for schema documentation
- Migration documentation updates

### Architecture Refactoring

#### Memory Module Decomposition
- New `ingestion/` package for memory ingestion pipeline
- New `services/` package with `CrossrefService`
- New `search/` package with `SearchCoordinator`
- `MemoryManager` updated as facade for extracted components

#### Session Tools Decomposition
- New `sessions/` package under `mcp_proxy/tools/`
- Extracted `_messages.py`, `_handoff.py`, `_crud.py`, `_commits.py` modules
- Created `_factory.py` for tool registry construction
- Deleted monolithic `session_messages.py`

#### Task Enforcement Decomposition
- New `enforcement/` package under `workflows/`
- Extracted `blocking.py`, `commit_policy.py`, `task_policy.py`, `handlers.py`
- Removed facade pattern in favor of direct imports

#### Codex Adapter Decomposition
- New `codex_impl/` package under `adapters/`
- Extracted `adapter.py`, `client.py`, `types.py`, `protocol.py`
- Removed `codex.py` facade

#### Other Refactoring
- Endpoints decomposition for `tools.py` (discovery, server, execution, registry)
- `ActionExecutor.register_defaults` refactored to use external handlers
- `safe_evaluator.py` module for workflow evaluation
- Extended `git_utils.py` with additional helpers
- Config module cleanup: removed deprecated prompt fields, added prompt_path pattern

### Bug Fixes

- Fixed `delete_task` recursion bug when parent task depends on children (#6366)
- Fixed config tests for `prompt_path` refactor (#6367)
- Fixed `mock_memory_manager.get_related` to use `AsyncMock` (#6368)
- Fixed mypy type errors in 4 files (#6365)
- Fixed pytest failures from config refactor and async/sync mismatches (#6362)
- Fixed task lifecycle tools returning `success: true` on errors (#6197)
- Fixed stop hook to use task ref and single newline (#6165)
- Fixed race conditions, error handling in various modules (#6326)
- Fixed import errors after enforcement refactor (#6347)

### Documentation

- Added `search.md` guide for unified search functionality (#6364)
- Added `configuration.md` guide for daemon configuration (#6363)
- Comprehensive documentation guide updates (#6350-#6361)
- Updated doctor skill with Phase 5 Security Audit section
- Created `usage` skill for token and cost reporting
- Added unified `spawn_agent` API design document
- Added sandboxing documentation
- Added migration documentation updates

### Improvements

- `/gobby` router skill and `/g` alias for quick skill access
- Skill category support (`core`, etc.) with `alwaysApply` frontmatter
- Model extraction from Claude and Gemini transcript messages
- Session message format updated to show Ref before ID
- Meeseeks-box spawn instructions include workflow activation prompt

### Internal

- Multiple code quality fixes across 50+ files
- Removed backward compatibility shims from config and spawn modules
- Cleaned up unused re-exports and deprecated parameters
- Added nosec B110 annotations for intentional exception silencing
- Reorganized plans directory and cleaned deprecated files

## [0.2.6] - 2025-01-26

### Major Features

#### Skills System (Complete Overhaul)
- New `gobby-skills` MCP server with full CRUD operations (`list_skills`, `get_skill`, `search_skills`, `install_skill`, `remove_skill`, `update_skill`)
- `SkillLoader` supporting filesystem, GitHub repos, and ZIP archive imports
- `SkillManager` coordinator with change notification pattern
- `SkillSearch` with TF-IDF backend and hybrid search (TF-IDF + embeddings)
- `EmbeddingProvider` abstraction for semantic search
- Full CLI command group (`gobby skills list/show/install/remove/update/new/validate/doc`)
- YAML frontmatter parser for SKILL.md files per [Agent Skills specification](https://agentskills.io)
- Skill directory structure support (scripts/, references/, assets/)
- Auto-sync bundled skills to database on daemon start
- Core skill injection into session-start hook
- Skill hints in hook error messages

#### Clone-Based Parallel Orchestration
- New `gobby-clones` MCP server for isolated parallel development
- `CloneGitManager` for git clone operations
- `spawn_agent_in_clone` tool for running agents in isolated clones
- `merge_clone_to_target` tool with conflict detection
- Clone storage layer with database migration
- Clone CLI commands (`gobby clones list/create/delete`)
- Updated `parallel-orchestrator` and `sequential-orchestrator` workflows

#### Conductor System (Autonomous Orchestration)
- `ConductorLoop` main daemon for autonomous task orchestration
- `TaskMonitor` for stale/blocked task detection
- `AgentWatcher` for stuck agent detection
- `AlertDispatcher` with logging and optional callme integration
- `ConductorConfig` for token budget management
- `SessionTokenTracker` with model column in sessions
- Conductor CLI commands (`gobby conductor start/stop/status`)
- Token metrics in `gobby-metrics` MCP server
- `TokenTracker` using LiteLLM pricing utilities

#### Inter-Agent Communication
- Inter-agent messaging MCP tools
- Blocking wait tools for task completion (`wait_for_task`, `wait_for_tasks`)
- `approve_and_cleanup` orchestration tool
- Handoff payload extended with `active_skills` field
- Session memory extraction workflow action

#### Task System Improvements
- Skill-based task expansion via `/gobby-expand` skill
- New expansion MCP tools replacing legacy `expand_task`
- `expansion_status` field in Task model
- `depends_on` parameter in `create_task`
- Dependency checking in `delete_task`
- Auto-claim task when creating with `session_id`
- Edit history tracking for task enforcement
- Configurable task lifecycle policies via workflow variables
- Lazy evaluation for `session_has_dirty_files` and `task_has_commits`

#### Unified Search
- Unified search abstraction with TF-IDF fallback
- Hybrid search combining TF-IDF and embeddings
- Semantic tool search via `search_tools`
- Automatic re-indexing on skill changes

### Breaking Changes

- **Default ports changed** from 8765/8766 to 60887/60888 (GOBBY leetspeak)
- **Removed `no_commit_needed`** escape hatch from `close_task` - commits are now required for tracked file changes
- **Legacy task expansion system removed** - use skill-based expansion via `/gobby-expand`
- **Deprecated parameters removed** from `SkillSearch`

### Improvements

- Progressive disclosure via MCP server instructions (`build_gobby_instructions()`)
- Standardized `HTTPException.detail` to dict format
- Auto-enrich MCP execution errors with tool schema
- Improved hook error message formatting for readability
- Block tools action to prevent Claude Code task ID collision
- Plan mode detection from UI-based activation
- Workflow shadowing visibility and error handling
- Priority display in active workflows
- Workflow activation prompt in meeseeks-box spawn instructions
- Agent spawning fixes (task_id resolution and terminal mode)
- Session ID injection into agent context
- Timestamps normalization in tasks.jsonl to RFC 3339 format
- Skill backup logic for existing installations
- CLI status output now shows Skills
- `/gobby` router skill and `/g` alias for quick access
- Top-level `alwaysApply` and `category` support in skill parser and storage

### Bug Fixes

- Fixed task_claimed state not cleared after close_task
- Fixed task_claimed incorrectly cleared on failed close_task
- Fixed premature task claim clearing
- Fixed orphaned tool_results in transcript handling
- Fixed async loop errors in skills and cleanup tests
- Fixed mypy type errors in skills module
- Fixed pytest markers, exit code assertions
- Fixed HTTP error handling, cache pricing, timeouts, and clone deletion
- Fixed MCP errors now properly signaled with isError flag
- Fixed os.close mock in test_spawn_handles_fork_error
- Fixed hook-specific output to only use valid hookEventName values
- Fixed session_id documentation in starting-sessions skill
- Fixed claim_task usage instead of update_task for claiming tasks
- Fixed indexing blocking in index_skills sync wrapper
- Fixed coroutine construction deferred to executor thread in sync search wrapper
- Fixed timezone handling and null safety in conductor monitors
- Fixed uncommitted changes check before requiring justification
- Fixed multiple caplog tests with enable_log_propagation fixture

### Documentation

- Updated ROADMAP.md with current status and planned work
- Added orchestration-v2.md with clone-based parallel agents
- Added comprehensive skills guide
- Added gobby-skills to Internal MCP Servers table
- Added Autonomous Task Orchestration section to CLAUDE.md
- Added Worktree Agent Mode section to GEMINI.md
- Created gobby-clones skill documentation
- Created gobby-merge skill documentation
- Added spawned agent protocol documentation
- Slimmed GEMINI.md and AGENTS.md to match CLAUDE.md structure
- Added skills reference folder for GitHub users
- Added PyPI installation instructions
- Updated error messages to recommend `close_task(commit_sha=...)`

### Testing

- Added E2E tests for autonomous mode and worktree merge
- Added E2E test for token budget throttling
- Added E2E test for parallel clone orchestration
- Added E2E test for sequential review loop
- Added E2E test for inter-agent messaging
- Comprehensive tests for skills install and remove commands
- Fixed 36+ failing tests across the test suite

### Internal

- Removed redundant imports and unused code
- Consolidated LLM calls through `LiteLLMExecutor`
- Changed migration log level from INFO to DEBUG
- Skip CI for docs-only changes
- Added nosec comments to suppress bandit warnings
- Multiple code quality fixes across 50+ files

## [0.2.5] - Previous Release

See git history for changes prior to 0.2.6.
