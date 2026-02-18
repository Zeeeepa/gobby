Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

-

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl around lines 6 - 9, There are duplicate/off-topic memory entries: remove the generic/non-project memory with id "8445a83b-cf6b-517d-ab75-5693599fd56e" and consolidate the three duplicate FastAPI/WebSocket facts by deleting the redundant entries with ids "7a3886e3-be66-56f7-8dc7-b8ea75b449db" and "aa7846cb-9d6c-5193-84ea-b6c56970ac6d", keeping the single canonical entry "8146a96b-9e41-5216-844a-9ac6d6b7a734" (or merge their tags/metadata into that one if any unique metadata exists).

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 11, The doc mentions a "pop out" button but Phase 1 doesn't implement it and Phase 2 references CanvasPanel.tsx; update the plan to clarify scope by either moving the "pop out" button to Phase 2/3 or explicitly explaining how "pop out" maps to the CanvasPanel side panel and how it differs from AskUserQuestion inline rendering; reference CanvasPanel.tsx and AskUserQuestion in the clarification so readers know where the feature will be implemented and how the UX differs between inline and side-panel/pop-out behaviors.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 199, Update the plan text (near the `CanvasPanel.tsx` mention and the "injected as synthetic user messages" line) to clarify how synthetic canvas interactions are treated: state that these messages are marked as system-generated in conversation storage (not counted as user messages), rendered distinctly in the UI, excluded from user-message counts/analytics and from replay/export as regular user messages, and optionally flagged so agents do not treat them as genuine user intent (i.e., not used as primary user context unless explicitly selected); reference `CanvasPanel.tsx`, `TerminalPanel`, and `ChatPage.tsx` to indicate where this behavior is implemented or mirrored.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 127 - 133, ALLOWED_TAGS currently includes 'a' and 'img', which permit external resource loading and tracking; remove 'a' and 'img' from ALLOWED_TAGS (or alternatively keep them only after adding strict attribute/URL controls) and implement attribute filtering and URL validation: add an ALLOWED_ATTR list (e.g., only class, name, data-* and form attributes) and enforce an ALLOWED_URI_REGEXP or URL validation routine when processing link/image href/src in the sanitizer; if external images/links must be supported, rewrite or proxy URLs server-side (or only allow relative/data: URIs) before rendering.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 150 - 156, Update the "Key behaviors" plan to include accessibility and error-handling requirements: add Accessibility items specifying to set role="region" and aria-label (derived from title) on the canvas container, use aria-live="polite" to announce dynamic updates, and ensure screen-reader announcements for status changes (e.g., when status === 'completed'); add Keyboard items to ensure all interactive elements discovered via the delegated click handler and data-action attributes are keyboard-accessible, manage initial focus on load, and handle focus trapping for modal-like canvases; add Error-handling items to describe showing user-friendly errors for malformed HTML rendering, network failures during interaction submission, timeouts, navigation/refresh during blocking interactions, and to implement double-submission prevention for forms intercepted by the <form data-action="..."> handler; and add Loading-state items to disable interactive elements (including selects and buttons discovered via delegated handlers), show spinner during submission, and re-enable or show error UI on failure.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 17, Update the "**Security?**" section that currently only mentions DOMPurify to cover broader risks and mitigations: add notes about data exfiltration via external resources (e.g., <img> GETs) and block or proxy external requests, call out CSS injection risks and recommend sanitizing/stripping dangerous CSS and using isolation (shadow DOM/iframes) or strict style allowlists, add clickjacking defenses and suggest frame-ancestors CSP or X-Frame-Options, and include a Content Security Policy example for the canvas rendering context (disallow inline scripts/styles, restrict resource origins, disallow javascript: URIs); reference the existing Security heading and DOMPurify mention when adding these items so reviewers can find and expand that exact section.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 193, The plan currently lists dompurify and @types/dompurify without version constraints; update the project's package.json dependencies to pin minimum safe versions for both packages (e.g., set dompurify to a recent secure minimum like >=2.4.0 and @types/dompurify to a compatible minimum such as >=2.2.0) so security fixes and API compatibility are guaranteed; modify the dependency entries for "dompurify" and "@types/dompurify" accordingly and run npm/yarn install and a quick test to verify nothing breaks.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 62 - 64, The spec must require always sanitizing HTML server-side before storing or broadcasting in render_canvas: ensure render_canvas(content: str, ...) invokes server-side sanitization on content and stores the sanitized result in CanvasState and broadcasts the canvas_event with sanitized payload; remove the “optional” qualifier. Also make the blocking wait timeout configurable rather than hardcoded 600s by adding a configurable parameter or global/default constant (e.g., RENDER_CANVAS_TIMEOUT_DEFAULT) used by render_canvas’s blocking path (and documented in the API) so callers can override the timeout for waiting on the asyncio.Event while preserving the same return shapes.

-

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/claude.py at line 420, The Claude provider's generate_text now raises RuntimeError("Generation unavailable (no LLM backend configured)") instead of returning an error string; update all callers and tests that expect a string return to instead catch RuntimeError (or let call_llm handle it) — specifically search for usages of generate_text in the codebase and update those call sites (and related unit tests) to either wrap calls in try/except RuntimeError or to rely on the existing call_llm() exception handling; ensure behavior is consistent with the LiteLLM provider which already raises RuntimeError.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/claude_streaming.py at line 26, Add a short inline comment next to the unused import of gobby.llm.sdk_compat explaining that the import performs a monkey-patch to make parse_message tolerant of unknown/legacy message types for SDK compatibility (so the import is intentional and required); reference the module name gobby.llm.sdk_compat and the patched symbol parse_message in the comment so future maintainers understand the side-effect and why the noqa: F401 is present.

-

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/config.py at line 133, The call to config_store.set_secret(key, str(value), secret_store, source="mcp") indiscriminately stringifies non-string secrets and may lose structure; update the code to validate and handle non-string types before calling config_store.set_secret: if value is already a str pass it through, if it's a dict/list/other structured type serialize it (e.g., using json.dumps with stable settings) or explicitly raise a TypeError to prevent silent corruption, and keep the same parameters (key, secret_store, source="mcp") when invoking config_store.set_secret so callers and logs remain clear.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 582 - 583, The current assignment spawn_result.error = f"Agent spawned but DB record failed: {e}" leaks internal exception details; instead, log the full exception (use the module's logger.exception or logger.error with exception info) and set spawn_result.error to a sanitized user-facing message like "Agent spawned but DB record failed" (optionally include a short error code or correlation id). Update the block around spawn_result.success and spawn_result.error in spawn_agent.py to log the full exception (preserve stack trace) while returning the sanitized message to callers.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 576 - 581, The orphaned-process cleanup currently sends signal.SIGTERM to spawn_result.pid but doesn't verify termination; update the block that calls os.kill(spawn_result.pid, signal.SIGTERM) to wait briefly (e.g., loop with small sleeps up to a timeout) and poll the process (os.kill(pid, 0) or os.waitpid with WNOHANG) to see if it exited, and if it remains alive after the timeout escalate to os.kill(spawn_result.pid, signal.SIGKILL); ensure you catch and log OSError/ProcessLookupError for both SIGTERM and SIGKILL and use logger.info/logger.warning/logger.error accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py around lines 449 - 474, The fnmatch import inside_needs_tool_approval causes repeated imports; move the import to module level by adding "from fnmatch import fnmatch" at the top of the module and remove the local "from fnmatch import fnmatch" line inside the _needs_tool_approval method; ensure the method continues to use fnmatch unchanged and verify references to_tool_approval_config, config.policies, and _approved_tools remain correct.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/configuration.py around lines 155 - 157, The condition in the loop over secret_keys has a redundant truthiness check: update the if-statement that currently reads `if key in flat and flat[key] and flat[key] != "":` to a single non-redundant check such as `if flat.get(key, "") != "":` (or `if key in flat and flat[key] != "":`) to detect non-empty strings before setting `flat[key] = "********"`, keeping references to secret_keys, flat, and key.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/configuration.py around lines 209 - 220, The loop that persists secrets (using _get_secret_store(), config_store.set_secret and config_store.clear_secret over secret_entries) can leave a partial state if one call fails; wrap the entire persistence operation in an explicit transaction or atomic operation so either all secrets are applied or none are (e.g., use a transaction context from the secret store or config store if available, or implement a compensating rollback on error by tracking successfully changed keys and reverting them in an exception handler); ensure you call _get_secret_store() once, begin the transaction, perform set_secret/clear_secret for each key, commit on success and rollback/revert on failure, and propagate the error as the original behavior expects.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/memory.py around lines 224 - 256, The variable name entities_total in rebuild_knowledge_graph is misleading because it counts successfully processed memories rather than entities; rename entities_total to a clearer name such as memories_extracted or successful_count and update all uses (the increment, the return key "memories_extracted", and the local references) to match; ensure consistency with the rebuild_crossrefs pattern (which uses total_created) so callers and logs reflect that the metric is counting memories processed, not extracted entities.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/memory.py at line 237, The handler currently calls server.memory_manager.list_memories(project_id=project_id, limit=500) which silently truncates results; modify the route to accept an optional limit query parameter (parse int from request.args with a sensible max/default) and pass it to memory_manager.list_memories, and also fetch the total count (e.g., via server.memory_manager.count_memories(project_id) or by adapting list_memories to return total) and include a total_memories field in the JSON response alongside the memories; update the endpoint docstring to document the new limit parameter and the total_memories field so callers know when results were truncated.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 37 - 52, The module-level_cache is not protected against concurrent access; add a module-level threading.Lock (e.g., _cache_lock = threading.Lock()) and use it to guard all accesses/updates to _cache in_get_cached and_set_cached so reads and writes (including eviction logic that references_MAX_CACHE_SIZE) are done under the lock; ensure you acquire the lock at the start of _get_cached and _set_cached and release it at the end (use a context manager) so the timestamp check, eviction, and assignment to _cache remain atomic.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 587 - 600, The WorktreeGitManager is being initialized with the worktree path (wt.worktree_path) but its **init** expects the main repository path; change the initialization to pass the repository path from the worktree object (e.g., wt.repository_path or the field that holds the repo root) to WorktreeGitManager(repo_path) and keep delete_worktree(wt.worktree_path, force=True) as-is; retain the existing fallback to server.services.git_manager.delete_worktree if WorktreeGitManager fails.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 601 - 619, The handler _handle_tool_approval_response currently forwards the raw decision to session.provide_approval without validation; update it to validate and normalize decision first (e.g., allowed = {"approve", "reject"}) by extracting decision = str(data.get("decision", "reject")).lower() and checking membership; if invalid, log a warning referencing conversation_id and either default to "reject" or return without calling session.provide_approval; use the existing symbols_handle_tool_approval_response, session.has_pending_approval, and session.provide_approval when implementing this change.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/config_store.py around lines 177 - 190, In clear_secret (which uses config_key_to_secret_name and SecretStore.delete) the except block currently logs a warning but then re-raises the exception, contradicting the "log but don't re-raise" comment; change the handler to catch Exception as e, log the failure including the exception details (e.g., use logging.getLogger(**name**).warning or .exception with exc_info) and do NOT re-raise so the method returns normally after logging; ensure the DB delete remains before the secret_store.delete call and that no raise statement remains in the except block.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/config_store.py around lines 135 - 170, The set_secret function should use the SQLite transaction context manager to avoid orphaned secrets: move the secret_store.set call inside a "with self.db:" transaction block so the DB insert (self.db.execute) runs inside that same context and only commits after secret_store.set succeeds; keep config_key_to_secret_name, secret_store.set/delete and the existing exception handling but remove the pre-insert secret creation (create the secret inside the transaction) and use "with self.db:" around the INSERT/ON CONFLICT execute and the secret_store.set call to ensure atomic behavior.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sync/memories.py around lines 214 - 215, The code uses len(self.memory_manager.list_memories(limit=10000)) to compute db_count which loads up to 10k records; change this to call a storage-level count method (e.g., add and use memory_manager.count_memories()) so counting is done via a COUNT(*) query in the backend; update the MemoryManager interface and all storage implementations to provide count_memories(), then replace the len(...) usage where db_count is set to use self.memory_manager.count_memories() to avoid loading records and remove the arbitrary 10000 limit.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/voice/tts.py around lines 159 - 163, In send_text, the code references a non-existent instance attribute self._logger causing AttributeError; replace self._logger with the module-level logger variable named logger (used elsewhere in the module) so the debug call in send_text uses logger.debug(...) and audit other methods in the class (e.g., send_text and any other places using self._logger) to ensure they also reference logger instead of self._logger.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/observers.py around lines 169 - 177, Do not re-extract task_id from arguments (which can be a ref like '#123') — use the already-resolved task_id produced earlier in this scope; remove the lines assigning task_id = arguments.get("task_id") and instead check and pass the previously-resolved task_id into session_task_manager.link_task(state.session_id, task_id, "worked_on") and into the logger.info/warning calls so the link uses the UUID-resolved value.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_config.py around lines 369 - 381, The fixture function config_registry_with_db lacks a return type hint; update its signature to include an explicit return type that matches create_config_registry's return (prefer the concrete type if available, otherwise use typing.Any or the appropriate Protocol), e.g., annotate def config_registry_with_db(...) -> <ReturnType>: so callers and linters know the expected type; ensure you import Any or the concrete type if needed and keep the existing parameters and return statement unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/package.json at line 12, The postinstall script in package.json uses the Unix-only "cp" which fails on Windows; update the "postinstall" script (the postinstall npm script) to a cross-platform copy solution and add the chosen tool to devDependencies—e.g., add "shx" (or "cpx") to devDependencies and change the postinstall command to use "shx cp" (or the equivalent "cpx" invocation), or replace the script with a short Node.js copy script invoked by postinstall; ensure the package.json postinstall entry and devDependencies are updated together.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx at line 238, The tab definition uses id 'worktrees' while its label is 'Source Control' and it renders <GitHubPage />, causing a naming mismatch; rename the tab id to a consistent identifier such as 'source-control' (or 'github') wherever 'worktrees' is used in the tabs array and any related logic or switch/case that references 'worktrees' so the id, label and component match (update the other similar occurrence as well that defines the same tab); ensure any state, routing, or tests that reference the old 'worktrees' id are updated to the new id.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 69 - 76, The fetch for synthesizing a title currently returns null on non-ok responses and swallows useful info; update the fetch handling around baseUrl/currentSession.id to detect non-ok responses and log them (including status and response text or JSON), and only call sessionsHook.refresh() when a successful data.title exists; also ensure the catch still logs network/errors with context like "Failed to synthesize title" plus the error and response details so failed attempts are visible in logs.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConfigurationPage.tsx around lines 17 - 25, SECRET_MASK is defined but not used and mismatches the literal mask ('********') used elsewhere; update the constant and usages so the mask is consistent: set SECRET_MASK to the server-returned mask ('********') and replace the literal '********' comparison with SECRET_MASK (references: SECRET_MASK constant and the check that currently compares against the literal mask), or if server returns bullets instead, change both the constant and the comparison to match that character; ensure isSecretField remains unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/DashboardPage.css around lines 266 - 269, The hardcoded colors in the health-dot classes (.dash-health-dot--healthy, .dash-health-dot--degraded, .dash-health-dot--unhealthy, .dash-health-dot--unknown) should be switched to use the same CSS variable pattern and fallbacks as the status badges (e.g., var(--status-healthy, #22c55e)); update each class to reference the appropriate --status-... variable with the existing hex as the fallback so theming remains consistent with .dash-status-badge--healthy and its peers.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/GitHubPage.tsx around lines 94 - 139, Replace the long nested ternary rendering inside the GitHubPage component by extracting the tab content into a dedicated lookup or switch: create a mapping (e.g., TAB_CONTENT keyed by activeTab) or a helper function (e.g., renderTabContent(activeTab, sc, setActiveTab)) that returns the appropriate React node (SourceControlOverview, BranchesView, PullRequestsView, WorktreesView, ClonesView, CICDView) using the same props (status, prs, worktrees, ciRuns, fetchCommits, fetchDiff, fetchPrs, fetchPrDetail, deleteWorktree, syncWorktree, cleanupWorktrees, deleteClone, syncClone), then replace the ternary block with the simple loading check (sc.isLoading && !sc.status ? loading : TAB_CONTENT[activeTab] or renderTabContent(activeTab,...)). Ensure activeTab and sc prop names are used exactly as in the diff.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/GitHubPage.tsx around lines 62 - 68, The refresh button in GitHubPage.tsx uses only an icon (RefreshIcon) and a title attribute which is not sufficient for screen readers; update the button (class sc-page__refresh-btn, onClick sc.refresh) to include an accessible label by adding an aria-label="Refresh" or by including visually hidden text (e.g., a span with a screen-reader-only class) inside the button so assistive tech can announce its purpose instead of relying on title text.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/AgentStatusPanel.tsx around lines 69 - 79, The uptime calculation can become NaN when agent.started_at is invalid; update the startTime useMemo to parse and validate agent.started_at (e.g., const parsed = new Date(agent.started_at).getTime()), check isFinite(parsed) (or !Number.isNaN(parsed)), and if invalid fall back to Date.now() so startTime is always a valid number; keep the same dependency on agent.started_at and ensure the useEffect interval logic that uses startTime and calls setUptime remains unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/AgentStatusPanel.tsx around lines 28 - 34, The Close button and the row-selection buttons must not submit surrounding forms and must expose selection state to assistive tech: add type="button" to the Close button (the JSX using onClose and CloseIcon) and to the other buttons in this component (the selection toggle at the block around lines 87-92), and add an accessibility attribute that reflects selection state (e.g., aria-pressed={isSelected} or aria-selected={isSelected}) on the row-selection toggle button, plus an appropriate aria-label/title that includes the selection action; wire the attribute to the component's selection state variable (e.g., isSelected / selectedRow) so it updates when toggled.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 99 - 113, Replace the ad-hoc ID generation in handleFilesSelected with crypto.randomUUID() to produce guaranteed unique IDs: in the handleFilesSelected callback, where you currently set const id = `file-${Date.now()}-${Math.random()...}`, call crypto.randomUUID() (e.g., const id = crypto.randomUUID()) and use that id when pushing into setQueuedFiles; optionally include a small fallback to the existing Date.now()/Math.random() logic for older environments if you need broader browser support.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageItem.tsx around lines 36 - 38, The inline onError handler in MessageItem.tsx directly manipulates the DOM (e.target.style.display) — replace this with React state: add a local useState flag (e.g., hideLogo) in the MessageItem component, change the <img ... onError> to call setHideLogo(true), and conditionally render the <img> only when message.role === 'assistant' && !hideLogo; keep the existing src/alt/className props and ensure the state variable is initialized false and updated via the onError callback to avoid direct DOM writes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageList.tsx around lines 46 - 59, The thinking indicator JSX inside MessageList.tsx (the block gated by isThinking and messages checks) should be extracted into a small reusable component (e.g., ThinkingIndicator) to remove duplicated styling and logic; create a new functional component that renders the logo, "Gobby" label, spinner and "Thinking..." text and accepts no props (or a className prop if needed), replace the inline block in MessageList with <ThinkingIndicator /> and ensure the existing onError handler for the <img> and classes (w-5 h-5, text-muted-foreground, animate-spin, etc.) are preserved so behavior and styling remain identical.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactCodeView.tsx around lines 17 - 24, The Edit button currently toggles editing via setIsEditing regardless of whether prop onChange is provided, which lets users edit but cannot save; update the Button rendering and handler in ArtifactCodeView so the "Edit"/"View" control is only shown or enabled when onChange is defined (reference Button, isEditing, setIsEditing, onChange, and the editor state) — either conditionally render the Button only if onChange exists or make its onClick a no-op/disabled when onChange is undefined and keep label consistent, preventing entry into edit mode when there is no change handler.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactContext.tsx around lines 9 - 15, The useArtifactContext hook currently returns a silent no-op when ArtifactContext is missing; update useArtifactContext to detect missing ctx and, in development only (process.env.NODE_ENV !== 'production'), call console.warn (or use your logger) to surface that ArtifactContext.Provider is not mounted, while still returning a safe fallback for openCodeAsArtifact; reference the useArtifactContext function and the openCodeAsArtifact fallback so you add the warning near the existing early-return path for easier debugging without changing runtime behavior in production.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactImageView.tsx around lines 19 - 29, The component ArtifactImageView currently validates the image source using the regex /^(https?:|data:image\/)/ which rejects relative paths; update the conditional that checks content (the ternary using /^(https?:|data:image\/)/.test(content)) to also allow common relative URL forms (e.g. leading "/", "./", "../") or use a more robust check (e.g. attempt new URL(content, window.location.href) safely) so relative image paths like "/images/foo.png" render; adjust the test to include those patterns and keep the existing data URI and absolute URL checks.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactPanel.tsx around lines 32 - 41, The download currently treats every artifact as text inside handleDownload, causing images to be saved as .txt; update handleDownload to early-return or disable the download for artifact.type === 'image' (so users save via right-click) OR handle images by creating a proper image Blob: detect image content (artifact.type === 'image' and content either a data URL or base64 string), derive the correct MIME (from a data URL prefix or artifact.metadata), decode base64 to a byte array and create new Blob(bytes, { type: mime }), set the file extension accordingly (e.g., .png/.jpg), then createObjectURL/revoke as before; reference handleDownload, artifact.type, artifact.language, content, and the Blob/URL.createObjectURL logic when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 37 - 40, The useMemo hook (data = useMemo(() => rows.slice(1), [rows])) is called after an early return which violates React hooks rules; move the hook (and any other hooks) to the top-level of the ArtifactSheetView component before any conditional returns so hooks are always invoked (e.g., compute data with useMemo and derive headers from rows[0] after hooks are declared, then perform the if (rows.length === 0) return ...). Ensure you still guard access to rows[0] (headers) when rows is empty to avoid undefined reads.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactTextView.tsx around lines 29 - 31, The div currently uses a hardcoded "prose prose-invert prose-sm max-w-none" which forces dark-theme typography and can break contrast in light mode; update the class usage in ArtifactTextView (the div wrapping Markdown and the Markdown render for artifactId) to be theme-aware—either replace "prose-invert" with a Tailwind conditional like "prose prose-sm max-w-none dark:prose-invert" or compute classes via the component's theme prop/context (using clsx or similar) so that "prose-invert" is only applied in dark mode; ensure the Markdown invocation (content and id={`artifact-text-${artifactId}`}) remains unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Textarea.tsx around lines 1 - 33, Add the React namespace import so the namespaced types resolve: update the imports in Textarea (used by setRef, handleChange, and the MutableRef usage) to include the React namespace (e.g., import React along with forwardRef/useCallback/useRef/etc.) so React.ChangeEvent and React.MutableRefObject are defined and the TSX compiles.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/McpHealthCard.tsx around lines 7 - 13, Replace the if-chain in healthClass with an object map lookup: create a const map (e.g., HealthClassMap) mapping 'healthy'|'degraded'|'unhealthy' to their class strings, then return HealthClassMap[health as string] ?? 'unknown' (or use map.get if using Map) so null/unknown values fall back to 'unknown'; keep the function signature healthClass(health: string | null) and ensure type assertion or a typed key union to satisfy TypeScript.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/TasksCard.tsx around lines 64 - 66, Remove the round line cap on the donut segments to prevent overlap artifacts: in TasksCard.tsx locate the SVG segment where strokeDasharray, strokeDashoffset and strokeLinecap are set (the element using strokeDasharray={`${ring.length} ${CIRCUMFERENCE - ring.length}`} and strokeDashoffset={-ring.offset}) and either delete the strokeLinecap prop or set it to "butt" so segment boundaries render cleanly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/TasksCard.tsx around lines 1 - 9, The TaskCounts type declares a unused ready property—either remove ready from TaskCounts (and from Props if only used here) or include it in the donut segments and total calculation; locate the SegmentKey union and TaskCounts interface and then: if removing, delete ready from TaskCounts and any references in consuming code (e.g., Props consumers, rendering logic); if adding, extend SegmentKey or the segments array used by the donut component to include 'ready' and update the total/percentage computation in the component that renders the donut (ensure any functions that compute total counts or map segments—referenced by the component using Props.tasks—include tasks.ready).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 40 - 42, The code in BranchDetail.tsx uses a hardcoded fallback 'main' when currentBranch is falsy before calling fetchDiff(base, branchName); replace this brittle fallback by obtaining the repository's actual default branch (e.g., from repo metadata, a prop, or a config) and use that instead of the literal 'main'. Update the logic in the BranchDetail component to prefer currentBranch, then repository.defaultBranch (or a passed-in defaultBranch prop or a call to the repo metadata API), and only as a last resort fall back to a safe value; ensure the value passed to fetchDiff(base, branchName) comes from that resolved default-branch source.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 35 - 48, Add a loading state for the diff fetch: introduce a boolean state (e.g., isLoadingDiff with setIsLoadingDiff) and update handleViewDiff to set isLoadingDiff true before calling fetchDiff and reset it to false in a finally block; keep existing behavior of toggling via setShowDiff and setDiff on success, and catch errors as before. Also update the diff toggle button to disable or show a spinner when isLoadingDiff is true (use the existing showDiff state to preserve toggle behavior). Ensure you reference handleViewDiff, fetchDiff, setDiff, setShowDiff and showDiff when wiring the new loading state so the UI prevents repeated clicks while the fetch is in progress.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 99 - 105, The Sync button in ClonesView.tsx doesn't show action state feedback; update the button rendering (the JSX using handleSync, actionLoading and clone.id) to conditionally display "Syncing..." when actionLoading === clone.id (matching the Delete button's "Deleting..." behavior), e.g., change the button's children to use a ternary that shows "Syncing..." while disabled and "Sync" otherwise so users get loading feedback during handleSync.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 43 - 61, The filter chips in ClonesView act as toggle buttons but lack aria-pressed; update the <button> elements in the All button and the statuses.map block to include aria-pressed set to a boolean reflecting the current toggle state (for the All button use aria-pressed={statusFilter === null} and for each status button use aria-pressed={statusFilter === s}); ensure you update the buttons rendered by the component that uses statuses, clones, statusFilter and setStatusFilter so screen readers get the correct pressed state.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/DiffViewer.tsx around lines 31 - 47, The mapping over diff.patch.split('\n') in DiffViewer.tsx recomputes class names on every render for each line; wrap the split-and-map (or at least the per-line classification logic that builds className) in a useMemo so the array of rendered line data (or an array of objects like {text, className}) is only recomputed when diff.patch changes; extract the classification into a pure helper (e.g., classifyLine) referenced from useMemo and then render from that memoized array to avoid repeated string concatenation and condition checks on each render.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 16 - 28, The effect in PullRequestDetail using useEffect depends on fetchDetail and will re-run each render if the parent passes an inline function; to fix, ensure the parent memoizes the fetchDetail callback with useCallback (so the function identity is stable) or remove fetchDetail from the dependency array and document the change, or alternatively wrap fetchDetail in a stable ref inside this component (e.g., store the incoming fetchDetail in a useRef and call ref.current(prNumber) inside the effect) so useEffect only depends on prNumber; update references to setLoading/setDetail as needed and keep the behavior of useEffect, fetchDetail, prNumber, setLoading, and setDetail intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 22 - 24, The component currently logs fetchDetail errors to console but never updates UI; add an error state via useState (e.g., error/setError) in the PullRequestDetail component, set setError(e.message || String(e)) inside the .catch of fetchDetail (and clear error when retrying or on successful fetch), and update the JSX conditional rendering to show the error message when error is truthy (replace the current loading/empty flow with the proposed loading → error → detail branches so users see a friendly message instead of an empty panel).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestsView.tsx around lines 78 - 80, The date rendering in PullRequestsView (inside the JSX that reads pr.updated_at) calls toLocaleDateString() without validating the Date; update the code that renders the <td className="sc-text-muted"> for pr.updated_at to construct a Date object, check its validity via isNaN(date.getTime()) (or Number.isNaN), and only call toLocaleDateString() when valid; otherwise render a safe fallback (e.g., empty string or "-") so an invalid updated_at no longer shows "Invalid Date".

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx around lines 18 - 24, The effect in useEffect that calls fetchCommits when status?.current_branch changes is re-running whenever the fetchCommits reference changes; either ensure fetchCommits is stable in the parent (wrap the parent hook's fetchCommits in useCallback so its identity only changes when its true inputs change) or change this component to call the latest function via a ref (store fetchCommits in a ref and call ref.current(status.current_branch, 5)) and keep the effect deps as [status?.current_branch] while still calling setRecentCommits and handling errors; update symbols: useEffect, fetchCommits, status?.current_branch, setRecentCommits accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx around lines 123 - 127, The stale worktree item uses a non-focusable <div> with an onClick, so replace the clickable element with an accessible <button> (or an element with role="button" and keyboard handlers) in the staleWorktrees.map render to allow keyboard activation and focus; update the element that has className "sc-overview__stale-wt" and the onClick that calls onNavigate('worktrees') to be a semantic button, preserve the inner <span>{wt.branch_name}</span> and <StatusBadge status="stale" />, and ensure any existing styles and test expectations are adjusted accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/StatusBadge.tsx around lines 1 - 4, The StatusBadgeProps interface is currently unexported which prevents consumers from typing props when using StatusBadge; export the interface named StatusBadgeProps (the existing interface) so other modules can import it for type-safe consumption alongside the StatusBadge component, ensuring any optional size union and required status string remain unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 44 - 52, handleCleanup currently calls onCleanup(24, false) with hardcoded parameters; make the cleanup threshold configurable by replacing the hardcoded values with a prop or UI control. For a minimal change, add an optional prop cleanupHours?: number (default 24) to the component and use that prop in handleCleanup (call onCleanup(cleanupHours, /*preserve existing boolean behavior or also expose*/ forceCleanupProp ?? false)); alternatively add a small input/dropdown in the confirm UI to set the hours and a checkbox for the boolean flag, and pass those values into onCleanup instead of 24 and false; keep existing state updates (setActionLoading, setConfirmCleanup) as-is.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useArtifacts.ts around lines 24 - 47, The artifact id generation in createArtifact currently truncates the UUID to 8 chars (id variable) which raises collision risk; update createArtifact to use the full crypto.randomUUID() (or a higher-entropy fallback) instead of slicing, or implement a small loop that regenerates ids until it is unique against the artifacts Map before calling setArtifacts and setActiveArtifactId; reference the createArtifact function and the id variable so you modify that generation logic and ensure uniqueness prior to next.set(id, artifact).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useDashboard.ts around lines 35 - 49, The fetchStatus callback currently leaves previous data intact when an error occurs; update fetchStatus so that whenever you set an error (both in the non-ok branch and in the catch block) you also clear stale data by calling setData(null) (or the appropriate empty value your state expects) and optionally clear setLastUpdated (e.g., setLastUpdated(null)); modify the branches that call setError to also call setData and clear/update lastUpdated so stale data isn't shown alongside an error.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 400 - 417, The polling effects for local and GitHub data currently use empty dependency arrays so they only start on mount and won't immediately refetch when projectId changes; update logic so a change to projectId triggers an immediate fetch: add an effect that watches projectId (or include projectId in the existing useEffect deps) and calls fetchLocalRef.current() and fetchGitHubRef.current() when projectId is set, ensuring existing intervals using localPollRef and githubPollRef continue to run (symbols to modify: useEffect blocks around fetchLocalRef/localPollRef and fetchGitHubRef/githubPollRef, and the projectId variable/GITHUB_POLL_MS/LOCAL_POLL_MS).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 138 - 152, fetchStatus currently invokes fetch without cancellation and may update state after unmount; modify fetchStatus to create an AbortController, pass controller.signal to fetch(`${getBaseUrl()}/api/source-control/status?${buildParams()}`), and ensure you abort the controller in a cleanup (e.g., return a cleanup from the effect that calls fetchStatus or useEffect that registers it) so in-flight requests are cancelled on unmount; in the catch block of fetchStatus ignore or handle DOMException/AbortError specifically (avoid calling setStatus/setError when the error.name === 'AbortError') and keep using setStatus/setError for other errors.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 106 - 110, Add a brief explanatory comment above the double-ref pattern to clarify why you have an outer stable ref holding the prop ref and how to access the underlying WebSocket; specifically annotate wsRefStable (which wraps the wsRef prop ref) and show the access pattern wsRefStable.current → .current to get the WebSocket, and do the same style note for conversationIdRef to explain it captures a stable reference to the changing conversationId prop.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/index.css around lines 1249 - 1280, Update the CSS to respect users' reduced-motion preferences by adding a prefers-reduced-motion media query that disables the listening-pulse animation for .listening-pulse (and any use of listening-pulse-anim keyframes) — e.g., inside a @media (prefers-reduced-motion: reduce) block set .listening-pulse { animation: none; transition: none; } and optionally set a static opacity/transform to match the resting state used in the keyframes; ensure the @keyframes listening-pulse-anim remains unchanged or is not applied when reduced motion is requested.

- Verify each finding against the current code and only fix it if needed.

In @web/tailwind.config.ts at line 2, The Tailwind `content` array in tailwind.config.ts is too narrow (currently only './src/components/chat-v2/**/*.{ts,tsx}'); expand it to include all directories with JSX/TSX/HTML/JS files introduced by the PR (for example add globs for './src/**/*.{ts,tsx,js,jsx,html}', './src/components/**/*.{ts,tsx,js,jsx}', and any app/pages or dashboard folders) so Tailwind scans and preserves classes used in dashboard/, chat/ui/, and other new components; update the `content` property in tailwind.config.ts (the content array) accordingly.
