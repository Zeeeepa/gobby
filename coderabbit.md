Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl around lines 1 - 3, Consolidate the three overlapping memory entries by keeping the canonical combined fact (id "8146a96b-9e41-5216-844a-9ac6d6b7a734") and remove the two redundant entries (ids "7a3886e3-be66-56f7-8dc7-b8ea75b449db" and "aa7846cb-9d6c-5193-84ea-b6c56970ac6d"); ensure the remaining record accurately represents the combined content ("The Gobby daemon uses FastAPI for HTTP and a custom WebSocket server for real-time events") and update its updated_at timestamp if needed to reflect the consolidation.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/installers/mcp_config.py around lines 499 - 504, The installer entry for the "playwright" MCP currently uses an unpinned package string "@playwright/mcp@latest" in the args array; replace that with a pinned version (for example "@playwright/mcp@0.0.64") to avoid mismatches with playwright-core. Update the args value in the installer dict for "name": "playwright" (the entry with "command": "npx" and "args": [...]) to use the chosen fixed semver instead of "@latest", and ensure any tests or docs that reference this installer reflect the pinned version.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/config/app.py around lines 54 - 77, Add strict validation for allowed policy values by enforcing that ToolApprovalPolicy.policy and ToolApprovalConfig.default_policy only accept "auto", "approve_once", or "always_ask"; implement this by either changing the field types to a Literal["auto","approve_once","always_ask"] or adding Pydantic validators (e.g. @validator on ToolApprovalPolicy.policy and ToolApprovalConfig.default_policy) that check the value against the allowed set and raise ValueError with a clear message when invalid; ensure tests/logging reflect the validation error.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/config/voice.py around lines 43 - 58, The numeric voice fields (elevenlabs_stability, elevenlabs_similarity_boost, elevenlabs_style, elevenlabs_speed) declare valid ranges in their descriptions but lack Pydantic range constraints; update their Field(...) calls to include ge and le so Pydantic enforces them (set ge=0.0 and le=1.0 for stability, similarity_boost, style; set ge=0.5 and le=2.0 for speed) while keeping existing defaults and descriptions to ensure invalid values are rejected at validation time.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/sdk_compat.py around lines 28 - 32, The string match on MessageParseError is fragile; instead catch MessageParseError (the except block around parsing in sdk_compat.py) and always log a warning including the exception and the offending data (use logger.warning with exc_info or include str(e) and the msg_type computed from data) so unexpected wording changes are visible, but still return None for unknown/unsupported message types; keep the existing msg_type computation (data.get("type", "?") if isinstance(data, dict) else "?") and replace logger.debug with logger.warning(..., exc_info=e) while keeping the return None behavior, and add a unit test targeting the parser function that simulates a MessageParseError from the pinned SDK to assert we return None and emit a warning log.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/config.py around lines 129 - 135, The code currently coerces secret values with str(value) before calling config_store.set_secret (see SecretStoreCls, config_store.set_secret, key, value), which can produce unexpected representations for complex types; update the logic to validate the type of value before storing: if value is a str or primitive (int/float/bool) store as-is, for dict/list/other complex types either reject with a clear error or serialize safely (e.g., JSON) before passing to config_store.set_secret, and add a unit-check/log message to make the behavior explicit.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 556 - 571, The DB write for agent_runs (runner.run_storage.create called with run_id=spawn_result.run_id, parent_session_id, provider, etc.) currently only logs on exception which can leave a running agent without a DB record; update this to handle failures robustly by retrying the write a few times (e.g., 2-3 backoff attempts) and if still failing either mark the spawn as failed and propagate an error to the caller or return a response flag/exception indicating the DB failure instead of silently succeeding — implement this by wrapping runner.run_storage.create in a retry loop, on final failure change spawn_result.success to False (or raise a SpawnFailedError) and include the DB error message in the returned response/log (replace the current lone logger.error call) so callers/polling logic like poll_agent_status can detect and handle the inconsistent state.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/runner.py around lines 242 - 249, The synchronous import_sync() call on memory_sync_manager inside __init__ blocks startup for large files; either (A) move the import_sync() call out of __init__ into the async run() method and ensure it runs before the code that performs the initial export, or (B) convert import_sync() into an async method (e.g., async import_sync()) and await it where it’s currently called so I/O won’t block the event loop; if you intentionally require synchronous ordering, add a clear comment in __init__ above the import_sync() call explaining why the import must complete before the initial export to avoid regressions.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py around lines 449 - 474, Move the local import "from fnmatch import fnmatch" out of the_needs_tool_approval method to the module level so fnmatch is imported once at module import time; update the top of the file to include "from fnmatch import fnmatch" and delete the inline import inside the _needs_tool_approval function (referencing the function name_needs_tool_approval and the variable fnmatch to locate the change).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/configuration.py around lines 679 - 686, The restoration of secret flags (loop over request.config_secret_keys calling config_store.db.execute with "UPDATE config_store SET is_secret = 1 WHERE key = ?") is executed outside a transaction; change it so the update loop runs inside the same transactional context as the import (begin/commit or using the DB connection/transaction context manager) so that failures roll back and leave the database consistent, and ensure exceptions during import trigger rollback rather than leaving partially-applied is_secret updates.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/projects.py at line 18, SYSTEM_PROJECT_NAMES is missing "_global" which leaves that hidden project unprotected from deletion; update the frozenset assigned to SYSTEM_PROJECT_NAMES (the set currently containing "_orphaned", "_migrated", "_personal", "gobby") to include the string "_global" so it matches HIDDEN_PROJECT_NAMES and prevents deletion—modify the definition of SYSTEM_PROJECT_NAMES in the projects storage module accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/sessions.py around lines 623 - 626, The generated title from provider.generate_text can end up empty after title = title.strip().strip('"').strip("'"), so before calling server.session_manager.update_title(session_id, title) validate that the final title is non-empty; if it is empty, either skip calling update_title or set a fallback (e.g., "Untitled Session" or a localized default) and then call update_title with the fallback, ensuring you operate on the cleaned title variable and reference session_id when updating.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 553 - 579, The endpoint uses POST for deletion; change the route decorator from router.post("/worktrees/{worktree_id}/delete") to router.delete("/worktrees/{worktree_id}") (and do the analogous change for the clones endpoint currently defined as POST "/clones/{id}/delete") so the handler functions (e.g., delete_worktree) use the DELETE HTTP verb and more canonical resource URL; update any client calls/tests and OpenAPI docs that reference the old POST paths to the new DELETE paths to avoid breaking consumers.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 20 - 36, The module-level_cache currently is an unbounded dict and can grow indefinitely; add a MAX_CACHE_SIZE constant (e.g., MAX_CACHE_SIZE = 1000) and switch _cache to an LRU-backed structure (collections.OrderedDict or collections.deque/OrderedDict pattern) and update_get_cached/_set_cached to maintain recency (move_to_end on hits) and perform eviction when inserting if len(_cache) > MAX_CACHE_SIZE; also consider removing expired entries on access in _get_cached to avoid retaining stale keys (use _GITHUB_TTL/_GIT_TTL to determine expiry) and ensure any mutation is thread-safe if this module is used concurrently.

-

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 275 - 316, The branch_name path param is used directly in _run_git inside list_branch_commits, allowing command-injection-style refs; validate and sanitize before calling _run_git by rejecting or normalizing unsafe values (e.g., ensure branch_name matches a strict ref regex such as allowed chars [A-Za-z0-9._/\\-]+, disallow whitespace, leading '-' or metacharacters like ';', '|', '&', '`', '$', and sequences like '..' or '--'), or alternatively verify the ref exists with a safe git command (e.g., git rev-parse --verify) and only proceed if valid; apply the same validation to the base and head parameters used by the /diff endpoint (validate/verify in the diff handler) so only acceptable ref strings reach _run_git.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/config_store.py around lines 172 - 176, The current clear_secret method (clear_secret, which uses config_key_to_secret_name and SecretStore.delete) can leave the system in an inconsistent state if deleting from the DB fails after the secret is removed; change the logic to perform the DB deletion first and only delete the secret from SecretStore after the DB operation succeeds, or wrap both operations in a single transactional unit (begin/commit/rollback) so that if self.db.execute("DELETE FROM config_store WHERE key = ?", (key,)) fails the SecretStore.delete is not executed (or both are rolled back); update clear_secret to use a transaction on self.db or reverse the delete order accordingly and ensure exceptions are properly propagated/handled.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/migrations.py around lines 932 - 936, In the rows loop inside migrations.py where you compute new_id (using old_id, content, normalized and _MEMORY_UUID_NAMESPACE), guard against empty/whitespace content by treating normalized == "" as a special case: when content is None or normalized is empty, set new_id to old_id (instead of computing uuid.uuid5 on the empty string) so multiple empty memories don’t collide; otherwise compute new_id = str(uuid.uuid5(_MEMORY_UUID_NAMESPACE, normalized)). Also ensure any UPDATE logic skips or handles cases where new_id == old_id to avoid unnecessary DB operations.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/projects.py around lines 137 - 180, The ensure_exists function currently does a separate get(project_id) then INSERT which can race and hit UNIQUE constraints; change it to perform a single upsert/conditional insert inside a transaction: execute an INSERT OR IGNORE (or INSERT ... ON CONFLICT(id) DO NOTHING) into the projects table with (id, name, repo_path, created_at, updated_at), then immediately call self.get(project_id) to return the project; after the insert-if-missing, if self.get(project_id) is still None, query by name to detect a name collision (e.g. SELECT id FROM projects WHERE name = ?) and raise/return a clear error or handle it according to project policy, ensuring all DB writes are in a transaction scope so concurrent calls cannot both create the same id and that UNIQUE name violations are detected and handled instead of letting the INSERT raise.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sync/memories.py around lines 204 - 221, The current import gate uses a simple count comparison (file_count and db_count from self.memory_manager.list_memories) which can miss updates or deletions; change the logic so we only auto-import when the DB is clearly empty (db_count == 0) or implement a content-based check: compute a stable fingerprint (e.g., checksum) of memories_file and compare against a stored/imported fingerprint in MemoryManager, or compare per-memory IDs/timestamps returned by list_memories to detect differences before importing; update the condition that references file_count, db_count, memories_file, and self.memory_manager.list_memories accordingly.

- Verify each finding against the current code and only fix it if needed.

In @tests/storage/test_storage_agents.py around lines 175 - 176, Add a new unit test that verifies the create method respects a provided run_id: implement test_create_agent_run_with_custom_id which calls LocalAgentRunManager.create with parent_session_id=sample_session["id"], provider="claude", prompt="Custom ID test", and run_id set to a custom string (e.g., "custom-run-12345"), then assert agent_run.id == custom string; reference the existing agent_manager.create usage and agent_run.id assertions to mirror style and placement alongside other tests.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 52 - 80, The useEffect that references sessionsHook.sessions (inside the useEffect block with wasStreamingRef, isStreaming, titleSynthesisCountRef, and conversationId) needs the sessions array explicitly in its dependency list to avoid stale references; update the dependency array to include sessionsHook.sessions (or destructure const sessions = sessionsHook.sessions above the effect and include sessions in the deps) so the effect re-runs when the sessions list changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx at line 238, The tab definition uses id: 'worktrees' but label: 'GitHub', causing inconsistency; change the tab id to 'github' in the tabs array (replace id: 'worktrees' with id: 'github') and update any places that check activeTab === 'worktrees' to activeTab === 'github' (e.g., the activeTab comparison in App.tsx) so the ID matches the visible label and routing/debug checks.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConfigurationPage.tsx around lines 17 - 23, Update the secret-detection and masking to be more comprehensive: add additional entries like 'secret', 'credentials', 'private_key', 'client_secret', 'client_key' (and common variants) to the SECRET_PATTERNS array used by isSecretField, and extract the hard-coded mask string ('________') into a shared constant (e.g., SECRET_MASK) near SECRET_PATTERNS so the mask is not a magic string; update any masking logic in ConfigurationPage (the code that currently uses '________') to reference SECRET_MASK.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/GitHubPage.tsx around lines 13 - 20, TABS contains a requiresGitHub flag that is never used; update the GitHubPage component's tab rendering logic (the code that maps/creates the tab UI from TABS) to check each tab.requiresGitHub against the current GitHub availability state (e.g., a prop/state like isGitHubConnected or similar) and either disable the Tab UI (visually and keyboard/inactive) or hide it entirely when GitHub is unavailable; make sure to reference TABS and SubTab when locating the mapping code and update the Tab/TabButton rendering to reflect disabled state and not trigger navigation when requiresGitHub is true but the connection is missing.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.css around lines 344 - 368, Add keyboard focus styles for the icon buttons to improve accessibility: update the CSS for .workflows-action-icon (and similarly .workflows-action-btn) to include :focus and :focus-visible rules that provide a clear visible indicator (e.g., outline or box-shadow and a contrasting background/border color) instead of removing the native outline; also add a focused variant for .workflows-action-icon--danger matching its hover state so danger buttons receive an appropriate focus style. Ensure the focus styles are as prominent as hover (but distinct) and don't rely solely on color.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 140 - 146, The handleYamlEdit callback risks leaving yamlLoading true if exportYaml throws; wrap the await exportYaml(wf.id) call in a try/catch/finally: in try setYamlEditorWf and await exportYaml, in catch handle or log the error (e.g., surface a toast or processLogger) and setYamlContent('') or leave previous state as appropriate, and in finally call setYamlLoading(false) so the loading flag is always cleared; update references to handleYamlEdit, exportYaml, setYamlLoading, setYamlEditorWf, and setYamlContent accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 679 - 711, Detect and prevent accidental loss by tracking a "dirty" flag when yamlContent changes (e.g., setDirty(true) inside the onChange handler used by CodeMirrorEditor) and replace direct onClose calls (overlay onClick and the Cancel button) with a wrapper function (e.g., attemptClose) that: if dirty and not saving, shows a confirmation dialog (or otherwise asks user to discard changes) and only calls onClose when confirmed (or when not dirty); ensure handleSave clears dirty (setDirty(false)) after successful save so subsequent closes behave normally. Use the existing symbols yamlContent, onChange, CodeMirrorEditor, handleSave, onClose, saving and loading to find where to add the dirty state and the attemptClose logic.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 148 - 158, The YAML parsing in handleYamlSave uses yaml.load(yamlContent) which can be unsafe and also currently accepts arrays because typeof [] === 'object'; change the load call to explicitly use the JSON_SCHEMA (e.g., yaml.load(yamlContent, { schema: yaml.JSON_SCHEMA })) to restrict parsing to JSON types and then validate the result is a non-null plain object (use a check like parsed && typeof parsed === 'object' && !Array.isArray(parsed')) before calling updateWorkflow on yamlEditorWf; keep references to handleYamlSave, yamlContent, yamlEditorWf and updateWorkflow when making this change so the subsequent name/description/definition_json logic remains correct.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/AgentStatusPanel.tsx around lines 68 - 79, The uptime is being computed from the component-local startTime (startTime, setUptime, uptime) so it resets on remounts and doesn't reflect the agent's actual runtime; update AgentStatusPanel to read the agent's real start timestamp (e.g., agent.started_at or a startedAt prop) instead of initializing startTime via useState, compute elapsed from that server-provided timestamp inside the useEffect that sets setUptime, and keep the interval/cleanup logic (clearInterval) unchanged so the displayed uptime is stable and accurate across remounts.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 271 - 275, In ChatInput's render (the JSX mapping that returns the four <span> bars), remove the Math.random() usage to avoid non-deterministic heights; instead generate fixed heights once (e.g., in the ChatInput component using useMemo or useState) or replace inline styles with deterministic CSS classes/animations (see proposed .voicebar-N and @keyframes) and apply those classes to the span elements (the mapped span in ChatInput). Ensure the heights/animation delays are stable across renders by referencing the memoized array (or CSS classes) rather than calling Math.random() inside the map.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 387 - 395, The SpinnerIcon component applies two animations (Tailwind's CSS class "animate-spin" and the SVG's internal <animateTransform>), which is redundant; remove the SVG <animateTransform> element inside function SpinnerIcon so the spinner relies solely on the "animate-spin" CSS class for rotation, leaving the <svg> element, its <circle> and attributes (cx, cy, r, strokeDasharray, strokeDashoffset) intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 88 - 102, The component leaks blob URLs created in handleFilesSelected because they are not revoked on unmount; modify the component to track active preview URLs (e.g., a ref like previewUrlsRef) when creating URLs in handleFilesSelected and revoke each via URL.revokeObjectURL in a cleanup effect (useEffect with []): on unmount iterate previewUrlsRef.current and revoke them; also update removeFile to remove revoked URLs from that ref when a file is deleted so you don't double-revoke and to avoid stale closure issues by reading queuedFiles from state or using the ref where needed.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatPage.tsx around lines 37 - 38, The ChatPage component currently applies inline styles on the root div (the element returned in ChatPage.tsx) for background and color; extract those styles into a CSS rule (e.g., .chat-page or .chatPageContainer) in the component stylesheet or global CSS, move the background: '#0a0a0a' and color: '#e5e5e5' into that rule, and update the JSX to replace the inline style prop with the className so the div uses the new CSS class instead of inline styles.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageItem.tsx around lines 42 - 44, The render uses message.timestamp.toLocaleTimeString() which can throw if timestamp is not a Date; update the MessageItem component to defensively handle timestamp by checking its type (e.g., if message.timestamp instanceof Date) or parsing strings via new Date(message.timestamp) and verifying !isNaN(date.getTime()) before calling toLocaleTimeString(); if the timestamp is invalid or undefined, render a safe fallback (empty string or a localized "unknown" placeholder) so MessageItem no longer throws at runtime.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageList.tsx around lines 16 - 21, The current useEffect in MessageList (the effect that reads scrollRef.current and sets el.scrollTop = el.scrollHeight when messages or isThinking change) force-scrolls every update and disrupts users who scrolled up; change it to first detect whether the user is already near the bottom (e.g., compute distance = el.scrollHeight - el.scrollTop - el.clientHeight and only auto-scroll if distance < a small threshold like 100px) and otherwise do nothing, and add an onScroll handler (ensure your ScrollArea forwards onScroll) to update a local isUserAtBottom flag that the effect can check instead of always scrolling; reference scrollRef, useEffect, messages, isThinking, ScrollArea, and the onScroll handler when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 83 - 123, The JSON.stringify call in ToolResultContent when building resultStr can throw on circular references; wrap the serialization in a try/catch (or call a safeStringify helper) so the component never crashes: attempt JSON.stringify(call.result, null, 2) inside try, and on error fall back to a safe representation such as util.inspect(call.result) or String(call.result) (or a replacer-based JSON serializer) and assign that to resultStr; update ToolResultContent (and any helper you add) to use this safe serialization before using parseReadOutput or rendering.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/styles.css around lines 12 - 20, Several selectors (.message-content code, .message-content pre, and other places using #0d0d0d, #1a1a1a, #262626, #737373, #a3a3a3, #e5e5e5, #3b82f6) use hardcoded colors; replace them with CSS variables (e.g., --bg-code, --bg-pre, --muted, --text, --accent) defined in a common scope (like :root or a theme container) or reference Tailwind theme tokens/classes instead, update the rules in styles.css to use the variables (var(--bg-code), etc.) or Tailwind utilities so colors are centralized and easier to change, and ensure fallback values are provided for compatibility.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 19 - 27, The useEffect block calling fetchCommits lacks rejection handling and can leave loading true; update the effect that uses fetchCommits, setLoading, setDiff, setShowDiff and setCommits to append a .catch(err => setError(err)) (or otherwise set an error state) and ensure loading is cleared in a .finally(() => setLoading(false)) so loading is always reset on success or failure; also address the dependency issue by either documenting that fetchCommits must be memoized by the parent with useCallback or removing fetchCommits from the dependency array if it is stable to avoid unintended re-renders.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 29 - 38, The handleViewDiff function lacks loading and error handling around the async fetchDiff call; update it to set a local loading state (e.g., isLoadingDiff) before calling fetchDiff and clear it in finally, wrap fetchDiff in try/catch to set an error state (e.g., diffError) on failure, and only call setDiff/setShowDiff when the fetch succeeds; also ensure UI uses isLoadingDiff and diffError to render a spinner/error message and disable toggling while loading; reference handleViewDiff, fetchDiff, setShowDiff, setDiff, diff, currentBranch and branchName when making these changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchesView.tsx around lines 51 - 53, The span rendering the worktree badge uses inline styles; replace the inline style object on the span with a dedicated CSS class (e.g., add 'sc-badge--worktree' alongside the existing "sc-badge sc-badge--sm") and move the background and color rules (#1e1b4b and #a78bfa) into your stylesheet/module used by BranchesView.tsx; update the JSX to remove the style prop and ensure the new class is defined in the component's CSS/SCSS so styling remains consistent with other badges.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 21 - 32, Both handleDelete and handleSync lack error-safe cleanup: if onDelete or onSync rejects the actionLoading state (and confirmDelete for delete) never resets. Wrap the await calls in try/finally blocks inside handleDelete and handleSync so setActionLoading(null) always runs in finally; additionally ensure handleDelete resets setConfirmDelete(null) in the finally block as well; keep onDelete/onSync errors propagated or optionally log them but do not skip the finally cleanup.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 24 - 27, The current direct type assertions for body, htmlUrl, reviewers, and labels can mask malformed API responses; replace them with defensive runtime validation: check typeof detail?.body === 'string' before assigning body, typeof detail?.html_url === 'string' for htmlUrl, and use Array.isArray(detail?.requested_reviewers) plus per-item shape checks (e.g., item && typeof item.login === 'string') to build reviewers, likewise for labels validate Array.isArray(detail?.labels) and each item has name/color strings; you can factor these checks into small helpers (e.g., safeString(field), safeArrayOfObjects(field, predicate)) and use those in PullRequestDetail.tsx to ensure safe defaults and avoid silent failures.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 16 - 22, The effect calling fetchDetail(prNumber) lacks error handling and can suffer a race where a slower earlier fetch overwrites a newer one; update the useEffect to (1) guard against stale responses by tracking a local requestId or using an AbortController and cancelling/ignoring results from prior requests, (2) wrap the async fetch in try/catch/finally so errors are caught and logged/set into state (e.g., setError) and loading is set to false in finally, and (3) only call setDetail when the requestId/abort signal confirms the response matches the current prNumber; modify the existing useEffect, fetchDetail usage, and state updates (setLoading, setDetail) accordingly to implement these checks.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestsView.tsx around lines 24 - 27, The selected PR is not cleared when the filter changes, so the details panel can show a PR that no longer appears in the list; update handleFilterChange to reset the selection before fetching new PRs (e.g., call the selection state updater like setSelectedPr(null) or setSelectedPrId(undefined) or clearSelection() depending on the component's selection state) and then call fetchPrs(f === 'all' ? 'all' : f) so the UI and list stay in sync.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx around lines 18 - 22, The useEffect that calls fetchCommits when status?.current_branch changes needs error handling and a race-condition guard: wrap the async fetch (invoked via fetchCommits) so you catch and log or handle errors before calling setRecentCommits, and add an isMounted/aborted flag (e.g., let cancelled = false; set cancelled = true in cleanup) to prevent calling setRecentCommits after the component unmounts or branch changes; update the useEffect cleanup to set the flag and ensure fetchCommits’ promise checks the flag before calling setRecentCommits.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx around lines 104 - 109, The PR list items rendered in the prs.map (the element with className "sc-overview__pr" using onClick={() => onNavigate('prs')}) are not keyboard accessible; update these interactive cells by either converting the <div> to a semantic <button> or adding accessibility handlers: set role="button", tabIndex={0}, and add an onKeyDown handler that triggers onNavigate('prs') for Enter/Space. Apply the same change to the similar stale worktrees rendering (the corresponding clickable items for stale worktrees) so both lists are keyboard-navigable and accessible.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/StatusBadge.tsx around lines 27 - 36, The StatusBadge lookup is case-sensitive so API values like "Success" won't match STATUS_COLORS; update the component (StatusBadge) to normalize the lookup key (e.g., const key = status?.toLowerCase() or similar) when indexing STATUS_COLORS but keep the rendered text as the original status if desired; ensure the fallback still works (STATUS_COLORS[key] || { bg:..., color:... }) and handle null/undefined status safely.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 25 - 36, The handlers handleDelete and handleSync need robust cleanup on rejection: wrap the await calls to onDelete(id) and onSync(id) in try/finally so setActionLoading(null) is always executed even if the promise rejects, and also move setConfirmDelete(null) into the finally block of handleDelete; keep setting loading before the try and rethrow or allow errors to propagate after finally if desired.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 38 - 43, handleCleanup currently awaits onCleanup(24, false) without ensuring cleanup state resets if onCleanup rejects; wrap the await in a try/finally (or try/catch/finally) inside handleCleanup so that setActionLoading(null) and setConfirmCleanup(false) always run regardless of errors, referencing the handleCleanup function and the setActionLoading, setConfirmCleanup, and onCleanup symbols to locate the code.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 55 - 67, The map callback in WorktreesView recalculates counts by calling worktrees.filter(...) for each status on every render; compute the counts once with useMemo (e.g., build a statusCounts map/dictionary from worktrees using reduce) depending on [worktrees], then replace worktrees.filter(...).length with a lookup like statusCounts[s]; keep using statuses, statusFilter, and setStatusFilter as-is so the UI logic is unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 390 - 411, The initial fetch effects and the polling effects cause fetchLocal/fetchGitHub to run immediately and then again when their intervals start; to avoid the duplicate immediate call, perform the initial fetch (call fetchLocal and fetchGitHub) first and only start the corresponding intervals afterward: move interval creation into the .then/await continuation of the initial fetch or replace setInterval with setTimeout for the first scheduled run, referencing fetchLocal, fetchGitHub, localPollRef, githubPollRef, LOCAL_POLL_MS and GITHUB_POLL_MS in the useEffect hooks so the interval is only created after the initial fetch completes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 136 - 146, The fetchStatus function in useSourceControl.ts currently clears error on success (setError(null)) but only logs on failure; update the catch block in fetchStatus to call setError with the caught error (or a normalized message) and optionally clear/adjust setStatus on failure so consumers can detect errors consistently; keep the existing setError(null) on success and ensure you reference fetchStatus, setError, setStatus, buildParams and getBaseUrl when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 168 - 175, Current code passes an external URL to MicVAD.new via the onnxWASMBasePath option (onnxWASMBasePath: '<https://cdn.jsdelivr.net/npm/onnxruntime-web@1.24.1/dist/>'), please self-host the ONNX WASM artifacts instead: during your build pipeline copy the files from node_modules/onnxruntime-web/dist/ into your app's static assets, update the MicVAD.new config to point onnxWASMBasePath to that local asset path (or set ort.env.wasm.wasmPaths to the bundled location) and ensure any worker/CSP paths match so the VAD worker loads from your domain rather than the jsDelivr CDN.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 601 - 619, The handler _handle_tool_approval_response currently forwards the raw decision value to session.provide_approval which may accept only specific tokens; validate the decision before calling provide_approval by allowing only the expected values (e.g., "approve" and "reject"), mapping any allowed synonyms if needed, and defaulting/normalizing to "reject" for invalid or missing values; if an invalid decision is received, log a warning that includes conversation_id and the invalid value and do not call provide_approval with unexpected inputs.

- Verify each finding against the current code and only fix it if needed.

In @tests/memory/test_manager.py around lines 122 - 123, Move the inline import of uuid out of the test body and add it to the module-level imports at the top of the file so the module imports are consistent with other tests; update the test that currently calls uuid.UUID(memory.id) to simply use the already-imported uuid (remove the inline "import uuid" line) so the call to uuid.UUID(...) continues to validate the UUID format but the import is centralized.

- Verify each finding against the current code and only fix it if needed.

In @tests/storage/test_memory_manager.py around lines 32 - 33, Move the local import of uuid out of the test body to the module-level imports in tests/storage/test_memory_manager.py so the symbol uuid is available for all tests; update the top-of-file import block to include "import uuid" and remove the inline "import uuid" so the usage uuid.UUID(memory.id) remains unchanged and validation still happens.

- Verify each finding against the current code and only fix it if needed.

In @tests/storage/test_storage_memories.py around lines 29 - 31, Move the inline "import uuid" out of the test body to the module-level imports and remove the inline import; update the test that currently calls uuid.UUID(memory.id) to rely on the top-level uuid import (i.e., keep the validation call uuid.UUID(memory.id) but delete the inline import statement) so the standard-library import follows Python conventions and the test remains unchanged otherwise.

- Verify each finding against the current code and only fix it if needed.

In @memory-snapshot.md around lines 1 - 420, This file (memory-snapshot.md) is a UI accessibility tree snapshot/test fixture (e.g., contains the "Memory" heading and node tree like generic [ref=e3] and button "Knowledge graph" [ref=e434]); add a top-of-file header comment clarifying its purpose (test fixture vs. generated artifact), move the file into an appropriate test-fixtures directory (e.g., tests/fixtures or web/tests) if it’s a committed fixture, or ensure it is excluded via .gitignore if it’s generated, and update any README or test harness referencing memory-snapshot.md (or the "Memory" snapshot) to point to the new location.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/DashboardPage.tsx around lines 30 - 32, The Refresh button currently calls refresh directly and has no UI feedback; add a local loading state (e.g., isRefreshing via useState) in the DashboardPage component, replace the onClick to call a wrapper function (e.g., handleRefresh) that sets isRefreshing=true, awaits refresh(), and in finally sets isRefreshing=false, and update the button to show a spinner or change its label to "Refreshing…" and be disabled (and include aria-busy/aria-disabled) while isRefreshing is true to prevent duplicate clicks.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/CodeBlock.tsx around lines 44 - 48, The handleCopy function in CodeBlock uses navigator.clipboard.writeText without error handling; wrap the writeText call in a try/catch inside handleCopy (or handle promise rejection) so failures are caught, log or surface the error via the same logging/notification mechanism used elsewhere, and ensure setCopied is only set true on success (and reset/notify on failure). Reference handleCopy and navigator.clipboard.writeText in CodeBlock to implement this consistent clipboard error handling pattern.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ThinkingBlock.tsx around lines 14 - 24, The collapsible header div in ThinkingBlock.tsx is only clickable by mouse; add keyboard accessibility by giving that div tabIndex={0}, role="button", and an onKeyDown handler that listens for Enter and Space keys and calls setExpanded(!expanded) (or toggles via setExpanded(prev => !prev)), while preventing default for Space to avoid page scroll; keep the existing onClick behavior and use the existing expanded and setExpanded identifiers.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactContext.tsx around lines 9 - 15, The fallback in useArtifactContext silently returns a no-op when ArtifactContext is missing; add a development-only warning to help catch missing providers by checking process.env.NODE_ENV === 'development' and calling console.warn (e.g. with message 'useArtifactContext called without ArtifactContext.Provider') before returning the { openCodeAsArtifact: () => {} } fallback in the useArtifactContext function.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactImageView.tsx around lines 20 - 25, The img src is set directly from the content prop in ArtifactImageView which can enable XSS via malicious URI schemes; fix by validating content before rendering: in the ArtifactImageView component, parse the content with the URL constructor (or test a regex) and only allow https:, http: and safe data:image MIME types (e.g., data:image/png;base64…) — explicitly reject javascript:, vbscript:, file:, and other unsafe schemes; if validation fails, do not set src (or render a safe placeholder / fallback image) and optionally log/debug the rejection so callers can handle it.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactPanel.tsx around lines 20 - 21, ArtifactPanel currently reads const currentVersion = artifact.versions[artifact.currentVersionIndex] and falls back to '' via const content = currentVersion?.content ?? '' which hides out-of-bounds errors; add validation for artifact.currentVersionIndex before indexing (e.g., check it's a number and within 0 <= index < artifact.versions.length), clamp or default to the last/first version as appropriate, and emit a warning/log when the index is invalid so the issue is visible (reference artifact.currentVersionIndex, artifact.versions, currentVersion, and content inside the ArtifactPanel component).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactPanel.tsx around lines 23 - 25, The handleCopy function currently calls navigator.clipboard.writeText(content) without handling rejections; update handleCopy (in ArtifactPanel.tsx) to await or then/catch the promise from navigator.clipboard.writeText(content) and handle errors by showing user feedback (e.g., call an existing toast/notification utility or set local error state) and optionally log the error for debugging; ensure the function remains memoized with useCallback and keeps content in its dependency array.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 7 - 30, The parseCSV function currently splits text on '\n' only, leaving '\r' in values for CRLF files; update parseCSV to normalize CRLFs before splitting (e.g., replace all '\r\n' and lone '\r' with '\n' or trim '\r' from each line) so the variable lines and subsequent parsing logic produce clean cell strings; ensure the change is applied at the start of parseCSV (before const lines = text.trim().split('\n')) and preserves existing handling of quoted fields in the loop.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 39 - 50, The problem is that `data` is recreated each render via `rows.slice(1)` so the `useMemo` for `sorted` is ineffective; fix it by stabilizing `data` (or by computing `sorted` directly from `rows`) — e.g., compute `data` with useMemo: make `data` = useMemo(() => rows.slice(1), [rows]) (or move the slice into the same useMemo as `sorted` and depend on `rows` instead of `data`) so that `sorted`'s dependencies (`data`, `sortCol`, `sortAsc`) are stable and memoization works for `sorted`.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactVersionBar.tsx around lines 15 - 35, The two icon-only navigation buttons (the Button elements that call onSetVersion with currentVersionIndex - 1 and + 1 and render ChevronLeftIcon / ChevronRightIcon) need accessible labels: add descriptive aria-label attributes such as aria-label="Previous version" on the left button and aria-label="Next version" on the right button so screen readers announce their purpose (ensure the labels reflect any localization strategy if used); keep the existing disabled logic tied to currentVersionIndex and versions.length unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ResizeHandle.tsx around lines 16 - 37, The resize logic only handles mouse events; add touch support by implementing an onTouchStart analog to handleMouseDown that reads touch.clientX (use touches[0].clientX), sets isDragging.current, startX.current, and startWidth.current, and registers document touchmove and touchend listeners that mirror handleMouseMove and handleMouseUp behavior (calculate delta from touch.clientX, call onResize(newWidth) with the same minWidth/maxWidth clamp); ensure the touch handlers remove their listeners on touchend and that both mouse and touch listeners are cleaned up to avoid leaks (update references to handleMouseMove, handleMouseUp, startX, startWidth, isDragging, onResize, panelWidth, minWidth, maxWidth accordingly).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Input.tsx around lines 8 - 24, The Input component rendered by forwardRef (Input) currently only changes visual styling when the error prop is truthy; add an aria-invalid attribute on the <input> element so assistive tech is informed of the error state (set aria-invalid to true when error is truthy, e.g., aria-invalid={!!error} or aria-invalid={error ? "true" : "false"} as appropriate) while leaving the rest of the props/ref handling unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Select.tsx around lines 84 - 98, ChevronDownIcon and CheckIcon are purely decorative SVGs but lack aria-hidden, so update both functions (ChevronDownIcon and CheckIcon) to add aria-hidden="true" on the root <svg> element to prevent screen readers from announcing them while leaving visual behavior unchanged; ensure the attribute is present on both SVGs in Select.tsx.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Select.tsx around lines 47 - 51, The Viewport currently forces a fixed height via the class 'h-[var(--radix-select-trigger-height)]' when position === 'popper'; remove that height constraint from SelectPrimitive.Viewport and instead set the Radix-recommended max-height on the SelectPrimitive.Content (add class 'max-h-[var(--radix-select-content-available-height)]'), and ensure the Viewport handles overflow (e.g., add 'overflow-y-auto' or rely on ScrollUp/ScrollDownButtons) so the dropdown can expand correctly when using position="popper".

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Textarea.tsx around lines 9 - 19, The Textarea forwardRef currently casts ref to a RefObject and recreates textareaRef when ref is falsy which breaks callback refs and causes unstable dependencies; change to a stable internal ref and a single stable ref-setter that forwards to both the internal ref and the incoming ref (handle object refs and function refs) so consumers can pass callback refs and the ref identity doesn’t change each render; update the useEffect to use the stable internalRef (e.g., internalRef.current) instead of a recreated textareaRef and remove textareaRef from the dependency list, keeping symbols: Textarea, forwardRef, internalRef, textareaRef (replace with setter), and the useEffect that adjusts el.style.height.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Tooltip.tsx around lines 5 - 7, Export TooltipPrimitive.Portal as TooltipPortal so consumers can render tooltip content in a portal to avoid clipping by overflow containers: add an export re-exporting TooltipPrimitive.Portal (e.g., export const TooltipPortal = TooltipPrimitive.Portal) alongside TooltipProvider, Tooltip, and TooltipTrigger in Tooltip.tsx so callers can opt into portal rendering for robust positioning.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/McpHealthCard.tsx around lines 15 - 17, McpHealthCard currently calls Object.entries(mcpServers) which will throw if mcpServers is undefined; update the McpHealthCard component to defensively handle undefined by defaulting mcpServers to an empty object (or early-return) before calling Object.entries — e.g., ensure the variable passed to Object.entries is (mcpServers ?? {}) or check if mcpServers is falsy and set entries = [] so the connected calculation (entries.filter(...).length) and any downstream rendering safely handle the initial/failed-load state.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/SessionsCard.tsx around lines 26 - 36, Define a narrow segment key type and use it when indexing sessions: add a type alias like SegmentKey = typeof SEGMENTS[number]['key'] (ensure SEGMENTS is strongly typed, e.g. declared as const) and replace sessions[key as keyof typeof sessions] with sessions[key as SegmentKey]; this restricts the index to only the SEGMENTS keys rather than the broader keyof typeof sessions (which includes "total") and improves type safety for the map in the render block that iterates SEGMENTS.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/TasksCard.tsx around lines 1 - 10, Props.tasks defines a unused ready field so ready-state tasks are not shown; choose one fix: either add a ready segment to SEGMENTS (append { key: 'ready', label: 'Ready', color: '...' }) and include tasks.ready in the total calculation and donut data generation (references: SEGMENTS, total, and the donut/chart data building code), or remove ready from the Props interface so it matches SEGMENTS and total; update whichever symbols you change (Props, SEGMENTS, total, and the donut data creation) to keep types and rendering in sync.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useArtifacts.ts around lines 25 - 26, The artifactsRef local ref in useArtifacts (artifactsRef and its assignment artifactsRef.current = artifacts) is unused and should be removed; delete the useRef(artifacts) declaration and the artifactsRef.current = artifacts line inside useArtifacts, and if the original intent was to access the latest artifacts inside callbacks, replace usages (or add) with a properly-scoped React ref named e.g. artifactsRef that is read in callbacks (or use the artifacts prop directly) so there are no unused variables left.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useArtifacts.ts at line 18, The module-level mutable counter nextId is unsafe for SSR and long-lived instances; remove nextId and generate IDs inside the hook instead (in useArtifacts) using a per-instance, SSR-safe mechanism such as React's useId() (import from 'react') or, if React <18, call crypto.randomUUID() in the hook initialization to produce a stable id for that hook instance; update any code that referenced nextId to use the new per-instance id and eliminate the module-level variable to avoid cross-request collisions.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useDashboard.ts around lines 43 - 48, The hook useDashboard currently leaves stale dashboard data when an HTTP error occurs; update the error branches in the fetch logic (the else where setError(`HTTP ${response.status}` is called and the catch block where setError(String(e)) is called) to also clear or reset the stored data via setData(null) or an empty state to avoid showing outdated metrics; optionally implement a retry/failure counter or timeout logic in useDashboard to only clear data after repeated failures if you want to avoid brief network blips wiping the UI.
