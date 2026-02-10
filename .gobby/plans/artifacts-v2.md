# Artifacts V2 — Active Artifacts for Agents and Users

## Overview

Transform gobby-artifacts from a passive auto-capture system into an active primitive that agents produce and users consume. Add write tools, schema enhancements, curation capabilities, and a web UI for browsing.

## Constraints

- Follow existing MCP tool patterns in `src/gobby/mcp_proxy/tools/artifacts.py`
- Reuse `LocalArtifactManager` storage methods — don't duplicate storage logic
- Schema changes via migration in `src/gobby/storage/migrations.py`
- Keep backward compatibility — existing artifacts must continue to work
- No breaking changes to existing 4 read-only tools
- Web UI must follow existing design patterns (multi-panel layout, REST hooks, design tokens)

## Phase 1: Schema Enhancements

**Goal**: Add title, task_id, and tags to the artifact data model

**Tasks:**
- [ ] Add `title` and `task_id` columns to `session_artifacts` table (category: code)
  - New migration adding `title TEXT` and `task_id TEXT` columns
  - Add index on `task_id` for efficient task-artifact queries
  - Update `Artifact` dataclass with new optional fields
  - Update `create_artifact()` to accept `title` and `task_id` params
  - Update `to_dict()` / `from_row()` for new fields
- [ ] Add artifact tags junction table (category: code)
  - New `artifact_tags` table: `(artifact_id TEXT, tag TEXT, PRIMARY KEY (artifact_id, tag))`
  - Foreign key to `session_artifacts` with CASCADE DELETE
  - Add `add_tag()`, `remove_tag()`, `get_tags()` methods to `LocalArtifactManager`
  - Add `list_by_tag()` method to query artifacts by tag

## Phase 2: Agent Write Tools

**Goal**: Let agents explicitly create, delete, and tag artifacts via MCP

**Tasks:**
- [ ] Add `save_artifact` MCP tool (depends: Phase 1)
  - Parameters: `content` (required), `session_id` (required), `artifact_type` (optional — auto-classify if omitted), `title` (optional), `task_id` (optional), `metadata` (optional dict), `source_file` (optional), `line_start`/`line_end` (optional)
  - Wraps `LocalArtifactManager.create_artifact()`
  - Auto-classifies via `classify_artifact()` when type not provided
  - Returns created artifact dict
- [ ] Add `delete_artifact` MCP tool (depends: Phase 1)
  - Parameters: `artifact_id` (required)
  - Wraps `LocalArtifactManager.delete_artifact()`
  - Returns success/failure
- [ ] Add `tag_artifact` and `untag_artifact` MCP tools (depends: Phase 1)
  - `tag_artifact(artifact_id, tag)` — add a tag
  - `untag_artifact(artifact_id, tag)` — remove a tag
  - Wraps new `LocalArtifactManager` tag methods
- [ ] Add `list_artifacts_by_task` MCP tool (depends: Phase 1)
  - Parameters: `task_id` (required), `artifact_type` (optional)
  - Query artifacts linked to a specific task
  - Enables "show me everything produced for task #123"

## Phase 3: Enhanced Read Tools

**Goal**: Improve existing read tools with new fields and filters

**Tasks:**
- [ ] Update existing MCP tools to include title, task_id, and tags in responses (depends: Phase 1)
  - `list_artifacts` and `search_artifacts` should accept `task_id` filter and `tag` filter
  - All tool responses should include `title`, `task_id`, and `tags` fields
  - `get_timeline` should include new fields
- [ ] Add `export_artifact` CLI command (depends: Phase 2)
  - `gobby artifacts export ARTIFACT_ID [--output PATH]`
  - Writes artifact content to file (stdout if no --output)
  - Respects artifact type for file extension

## Phase 4: Classifier and Docs Alignment

**Goal**: Fix type mismatches and add missing artifact types

**Tasks:**
- [ ] Add `diff` and `plan` artifact types to classifier (category: code)
  - Add `DIFF` and `PLAN` to `ArtifactType` enum
  - `diff` detection: unified diff patterns (`^@@`, `^---`, `^+++`, `^diff --git`)
  - `plan` detection: numbered lists with action verbs, markdown headers with "Plan"/"Phase"/"Step"
  - Insert detection before `text` fallback in `classify_artifact()`
- [ ] Update docs/guides/artifacts.md to match actual types (category: docs)
  - Align documented types with real `ArtifactType` enum values
  - Add examples for new `save_artifact` tool
  - Document tagging workflow
  - Update MCP tool reference section

## Phase 5: Auto-capture Enhancements

**Goal**: Make passive capture smarter with new fields

**Tasks:**
- [ ] Enhance auto-capture hook with task inference (depends: Phase 1)
  - When capturing artifacts, look up session's currently active task (claimed, in_progress)
  - Auto-set `task_id` on captured artifacts
  - Auto-generate title from content (first line of code, error type, filename, etc.)
- [ ] Update CLI to display new fields (depends: Phase 1)
  - Show title in `list` and `timeline` output
  - Show task ref in `list` output
  - Show tags in `show` output

## Phase 6: REST API for Web UI

**Goal**: Add HTTP endpoints that the web frontend can consume

**Tasks:**
- [ ] Create `src/gobby/servers/routes/artifacts.py` REST router (depends: Phase 1)
  - `GET /artifacts` — list with query params: `session_id`, `task_id`, `artifact_type`, `tag`, `limit`, `offset`
  - `GET /artifacts/search?q=query` — full-text search with optional filters
  - `GET /artifacts/{artifact_id}` — get single artifact
  - `GET /artifacts/timeline/{session_id}` — chronological artifacts for a session
  - `DELETE /artifacts/{artifact_id}` — delete artifact
  - `POST /artifacts/{artifact_id}/tags` — add tag (body: `{"tag": "..."}`)
  - `DELETE /artifacts/{artifact_id}/tags/{tag}` — remove tag
  - `GET /artifacts/stats` — aggregate stats (count by type, by session, by tag)
  - Mount router in `src/gobby/servers/http.py`
  - Follow pattern from `routes/memory.py` (closest analog)

## Phase 7: Web UI — Artifacts Panel

**Goal**: Replace the ComingSoonPage with a full artifact browsing experience

**Tasks:**
- [ ] Create `useArtifacts` hook (depends: Phase 6) (category: code)
  - Fetch artifacts via REST API (`/artifacts`, `/artifacts/search`)
  - State: `artifacts[]`, `selectedArtifact`, `filters`, `isLoading`, `stats`
  - Filter support: type, session, task, tag, search query
  - Pagination: limit/offset with load-more
  - CRUD: delete, tag/untag
  - Follow pattern from existing hooks (useCallback + useEffect + fetch)
- [ ] Create ArtifactsPage component with sidebar + detail layout (depends: Phase 6) (category: code)
  - **Sidebar (left)**:
    - Search input with debounced FTS query
    - Filter chips: by type (code, error, diff, etc.), by session, by tag
    - Artifact list: each item shows icon-by-type, title (or truncated content), type badge, timestamp, session ref
    - Group by: date (Today / Yesterday / This Week / Older) or by session
    - Stats bar at bottom: total count, breakdown by type
  - **Detail panel (right)**:
    - Artifact header: title, type badge, session link, task link, created timestamp
    - Content viewer: syntax-highlighted code (Prism), formatted errors, rendered markdown for plans, raw text fallback
    - Tags section: display tags as chips, add/remove tags inline
    - Actions: copy content, export to file, delete, open in session timeline
    - Empty state when nothing selected
  - Replace `<ComingSoonPage title="Artifacts" />` in App.tsx
- [ ] Add artifact type icons and styling (depends: Phase 6) (category: code)
  - Icon per type: code (brackets), error (warning), diff (split), file_path (file), structured_data (braces), text (document), plan (list), command_output (terminal)
  - Type-specific color coding for badges
  - CSS following existing design tokens
