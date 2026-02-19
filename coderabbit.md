Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/skills/worktree-manager/SKILL.md around lines 343 - 357, The examples for Ghostty, iTerm2, and tmux show the --dangerously-skip-permissions flag before the Security Considerations section; add a brief inline warning immediately before the first appearance of "--dangerously-skip-permissions" (e.g., above the Ghostty example) that flags the security risk and links or references the Security Considerations section (or its anchor) so readers must see the warning before copying the command; ensure the warning text is concise and clearly references the flag string "--dangerously-skip-permissions" so reviewers can locate and verify the change.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/skills/worktree-manager/templates/worktree.json around lines 1 - 3, The $comment value in the JSON template contains an inconsistent project path string; verify whether this template is meant for Claude or Gemini projects and either update the $comment string to reflect the correct project location for this template or add a clarifying note that it is intentionally pointing to a cross-tool path; locate the "$comment" key in the worktree JSON template and replace or clarify the quoted path text accordingly so it matches the package's intended usage.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 66 - 79, The design omits canvas lifecycle and cleanup, so update CanvasState and the canvas management logic to prevent leaks: add expires_at: datetime and completed: bool fields to CanvasState, ensure the code that handles interactions (uses pending_event and interaction_result) marks completed=True and removes the entry from_pending_canvases once an interaction finishes, implement a background sweeper that periodically removes entries whose expires_at < now (and cancels/sets pending_event to unblock blocking agents), and ensure session teardown clears all canvases for a given conversation_id; reference CanvasState, _pending_canvases, pending_event, interaction_result, expires_at, and completed when making these changes.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 62 - 64, Add rate limiting to canvas handling: define constants MAX_CANVASES_PER_CONVERSATION, MAX_CANVAS_SIZE, MAX_RENDER_RATE and enforce them in render_canvas (and when creating CanvasState) by (1) counting active canvases in _pending_canvases filtered by conversation_id and rejecting when >= MAX_CANVASES_PER_CONVERSATION (include separate check for blocking canvases if needed), (2) rejecting content whose length exceeds MAX_CANVAS_SIZE, and (3) implementing a per-conversation sliding-window render counter (timestamps stored e.g. on CanvasState or a small in-memory map) to enforce MAX_RENDER_RATE (raise ValueError with clear messages on violation). Update comments around render_canvas, CanvasState and canvas_event to note these limits and ensure rejected renders return appropriate error responses rather than creating new pending entries.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 179 - 191, The respondToCanvas callback lacks connection checks, optimistic UI and error/retry handling and the canvas_event handler needs idempotent state updates to avoid races; update respondToCanvas to verify wsRef.current && wsRef.current.readyState === WebSocket.OPEN, perform an optimistic setCanvases update setting that canvas' status to "pending", send inside try/catch and on failure either revert the optimistic update or enqueue the interaction for retry; implement a small retry/queue mechanism tied to wsRef (drained on open) and ensure canvas_event handling inside the message useEffect updates canvases idempotently by locating by canvas_id and applying content/version/event-type logic (e.g., only replace if newer or map existing -> updated content, otherwise append new canvas) so status transitions from "pending" → "active" on rendered/updated events without race conditions.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 150 - 156, Update CanvasRenderer.tsx's event-delegation to robustly walk up from the event target to the nearest [data-action] (use target.closest('[data-action]') or manual loop) and centralize logic into handlers like handleDelegateClick, handleFormSubmit and handleSelectChange; for anchor elements always call event.preventDefault() before dispatching the interaction; for forms intercept onSubmit (not button clicks), call preventDefault(), gather named inputs, disable the form's submit controls and set local interaction state to 'pending' to prevent double-submission until a response arrives; for <select> elements intercept onChange in handleSelectChange and optionally debounce rapid changes; ensure after sending the interaction you set/reset the local 'pending' status so further interactions are blocked while pending.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 209 - 220, The data-payload attribute currently allows raw JSON in HTML which risks injection, broken quoting, and oversized payloads; update the design and implementation so render_canvas validates incoming data-payload values (ensure valid JSON, reject control characters/escaped HTML entities, and enforce a max size such as 4KB per attribute) and have CanvasRenderer parse payloads inside a try-catch, reject payloads exceeding the size limit, and never eval() payload contents; additionally require agents/tools to produce payloads with JSON.stringify() and that DOM updates use setAttribute() (not innerHTML) to preserve escaping and avoid XSS when using data-payload and when performing targeted updates via update_canvas.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 122 - 136, The sanitizer currently defines ALLOWED_TAGS but omits an explicit ALLOWED_ATTRS list; update sanitizeCanvasHtml to pass a DOMPurify config that explicitly lists allowed attributes (ALLOWED_ATTRS) including the required data attributes: data-action, data-payload, data-element-id, plus common safe attrs like id, class, name, type, value, href, src, alt, title, role and aria-*patterns; ensure you also forbid or strip any event handler attrs (attributes starting with "on") either via FORBID_ATTR or a DOMPurify hook so onclick/onerror/etc are removed. Use the ALLOWED_TAGS constant and a new ALLOWED_ATTRS constant when calling DOMPurify.sanitize in sanitizeCanvasHtml so the data-* attributes are preserved and dangerous attributes are blocked.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 104 - 114, The _handle_canvas_interaction websocket handler is missing validation and error handling; update_handle_canvas_interaction to (1) verify canvas_registry exists and return/log/send an error if not, (2) validate canvas_id is present and exists in the registry before calling canvas_registry.resolve_interaction, (3) perform authentication/authorization by checking the incoming conversation_id/session against the active user/session for that canvas (reject and notify if mismatched), and (4) validate the structure and allowed values of action, payload, and form_data (reject malformed or disallowed actions with a clear websocket error) instead of silently failing; ensure any validation or resolve_interaction errors are caught, logged, and replied to over the websocket.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/memory.py around lines 485 - 491, Replace the string forward-reference and suppression comments in _get_daemon_client with a real static-only import using typing.TYPE_CHECKING: add "from typing import TYPE_CHECKING" and an "if TYPE_CHECKING: from gobby.utils.daemon_client import DaemonClient" block near the top of the file, keep the runtime local import inside_get_daemon_client for lazy import, change the return type annotation from the quoted "DaemonClient" to the actual DaemonClient type, and remove the "# type: ignore[name-defined]" and "# noqa: F821" comments.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/config/app.py around lines 367 - 370, The new field declaration uses an undefined type MemoryBackupConfig which will raise a NameError; change the type back to MemorySyncConfig (or if you opt to rename, rename MemorySyncConfig -> MemoryBackupConfig across the codebase). Specifically, update the memory_sync Field in app.py to reference MemorySyncConfig (or perform a global rename of the class in gobby.config.persistence and update all references in sync/memories.py, cli/memory.py, tests and the import in app.py) so the type name and imports are consistent.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_session.py around lines 416 - 422, The redundant isinstance(cli_source, str) check should be removed in the cache mapping call inside the session handling logic: directly pass cli_source (which comes from event.source.value set in handle_session_start) to session_manager.cache_session_mapping; update the call in the method that contains cache_session_mapping to use source=cli_source and keep external_id and session_id as-is (refer to cache_session_mapping and handle_session_start to locate the change).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/claude_streaming.py around lines 67 - 68, The docstring for the model parameter in claude_streaming (mentions default "claude-sonnet-4-6") does not match the function/constructor default value which is set to "opus"; update either the docstring or the default argument so they match—specifically edit the model parameter description in the docstring or change the default value from "opus" to "claude-sonnet-4-6" in the function signature where model is defined (search for the model parameter/assignment in claude_streaming.py).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/sdk_compat.py around lines 15 - 17, The module imports private internals claude_agent_sdk._internal.client and claude_agent_sdk._internal.message_parser and only relies on runtime hasattr guards (in the current guards around the internal usage), which is fragile; update the project dependency to a strict pin (e.g., claude-agent-sdk==0.1.18) and add a runtime version check in sdk_compat.py that reads the installed claude_agent_sdk version (via importlib.metadata or pkg_resources) and raises a clear, fast-fail error if the version != "0.1.18" so consumers know to pin the package, keeping the hasattr guards as a fallback only for backward compatibility.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/config.py around lines 150 - 154, The code currently validates by constructing new_config twice (once with the placeholder ref and again after merging the actual value), which is redundant; instead compute actual_nested = unflatten_config({key: value}) before building new_config and merge it into actual_dict (via _current_config().model_dump and deep_merge) so you create DaemonConfigCls(**actual_dict) only once for validation, or add a short comment near new_config explaining why the two-phase construct is required if you intentionally must accept refs first; update the logic around unflatten_config,_current_config, deep_merge and DaemonConfigCls to build the final actual_dict prior to the single new_config instantiation.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/memory.py around lines 575 - 590, The loop that rebuilds the knowledge graph iterates memories sequentially calling kg.add_to_graph, which can block the event loop; modify the loop in the memory processing section (where memories = memory_manager.list_memories and for memory in memories) to periodically yield control (e.g., call await asyncio.sleep(0) or await asyncio.sleep(small_interval) every N iterations or after each iteration) so the event loop stays responsive during long rebuilds while keeping the existing extraction/error accounting (extracted, errors, memories_processed).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/memory.py around lines 533 - 548, The current sequential loop over memories (calling memory_manager.rebuild_crossrefs_for_memory for each item in memories) can block the event loop; update this block to process memories concurrently with a bounded concurrency pattern (e.g., use an asyncio.Semaphore or a simple batching approach) so multiple rebuild_crossrefs_for_memory calls run in parallel but are limited (rather than all at once), collect results and sum created crossrefs, and still catch/log per-memory exceptions; alternatively, if you prefer minimal change, insert an await asyncio.sleep(0) every N iterations inside the for loop to yield control. Ensure you reference the existing variables/methods: memory_manager.list_memories, memories, memory_manager.rebuild_crossrefs_for_memory, total_created, and preserve the final return shape.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/pipelines/__init__.py around lines 395 - 424, The session resolution logic in_execute_pipeline duplicates_resolve_session; replace the inline resolve block in_execute_pipeline with a call to the existing_resolve_session helper (using session_manager and session_id) and use its returned resolved session id and project_id when calling run_pipeline; ensure you preserve the same error responses (e.g., returning {"success": False, "error": ...}) so behavior stays identical and update references to resolved_id and project_id accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/pipelines/_execution.py around lines 127 - 143, The background pipeline task created with asyncio.create_task(...) (task) and_execute_pipeline_background is started but not tracked or awaited, which risks abrupt cancellation on shutdown and makes lifecycle unclear; update the code to register the created task in a central tracker or registry (e.g., a module-level set/dict or an executor-managed collection) and remove it when done (use task.add_done_callback to both call _log_exception and remove the task from the tracker), and add a brief docstring or comment near the create_task call referencing get_pipeline_status so callers know to poll status for completion and that shutdown must await or cancel tracked tasks.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 597 - 617, Replace the hardcoded TMUX_HEALTH_CHECK_DELAY constant with a configurable value: expose it as a configurable parameter or read from an existing config/env var (e.g., AGENT_TMUX_HEALTH_CHECK_DELAY) with a default of 0.5, then use that value where TMUX_HEALTH_CHECK_DELAY is currently referenced in spawn_agent.py (the post-spawn block that checks spawn_result.terminal_type and calls_check_tmux_session_alive). Ensure the new config value is parsed to float and documented/defaulted, and update any callers or tests that rely on the constant if you choose to make it a function parameter rather than a module-level config.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py around lines 486 - 490, The_DANGEROUS_BASH_PATTERNS regex in chat_session.py misses service-management and download-then-execute patterns; update the pattern (variable_DANGEROUS_BASH_PATTERNS) to also match commands like systemctl, service, init and common download-and-pipe-to-shell patterns (e.g., curl|wget\s+.*\|\s*(bash|sh)) so inputs containing "systemctl", "service", "init" or "curl ... | bash" / "wget ... | sh" are flagged as dangerous; ensure the additions fit into the existing alternation and respect the WORD boundary (\b) and MULTILINE flag.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/configuration.py around lines 682 - 689, Validate and safely apply the batch UPDATE that sets is_secret by first validating each entry in request.config_secret_keys (e.g., match allowed key-name regex and reject/normalize invalid entries) and enforce a sane max batch size (e.g., 500–1000) to avoid huge placeholder lists; then inside config_store.db.transaction() for the UPDATE in configuration.py split the validated list into chunks and execute the parameterized UPDATE statement for each chunk (using the existing placeholders technique per chunk) so you never interpolate raw user input into SQL and avoid oversized IN-lists while preserving atomicity.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 114 - 136, The warning in_call_github_mcp logs only the exception message; change the logging to include the full traceback by using logger.exception or passing exc_info=True to the logger call (e.g., replace logger.warning(f"GitHub MCP call failed ({tool_name}): {e}") with logger.exception(...) or logger.warning(..., exc_info=True)); keep raising the HTTPException the same so behavior is unchanged but the full exception/traceback is recorded for debugging.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 618 - 624, Replace the try/except NameError control flow by initializing result before the deletion branches and then checking it explicitly: set result = None (or a default object) before the conditional blocks that call git deletion when server.services.git_manager is truthy, then later update git_deleted = result.success only if result is not None (or has the expected attribute), otherwise keep git_deleted = True; reference the variables result, git_deleted, server.services.git_manager and the result.success check when making the change.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 683 - 689, The code dynamically creates self._pending_modes in the block that queues modes; instead, declare and initialize self._pending_modes: dict[str, str] = {} in the class initializer (__init__) so it's always present and discoverable; update the constructor of the class that contains the chat-mode logic (the class with the method that logs "Chat mode set..." and queues modes) to add the initialization, and remove the hasattr(...) check and any dynamic setattr usage in the method that sets/queues modes (which references _pending_modes and logs "Chat mode '...'' queued for future conversation").

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/config_store.py around lines 174 - 181, The current clear_secret function can leave an orphaned config_store row because it deletes from the secret_store first and then the config_store; change clear_secret to perform both operations inside a single DB transaction (like set_secret does) so either both succeed or both roll back, e.g. begin/commit/rollback around secret_store.delete and self.db.execute, and replace the bare "except Exception" with more specific exception handling for errors you expect from secret_store.delete and DB operations (referencing clear_secret, config_key_to_secret_name, secret_store.delete, and self.db.execute).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/pipeline_executor.py around lines 173 - 174, Add a brief comment above the current_step_execution declaration explaining its lifecycle and purpose: state that current_step_execution (type StepExecution | None) is set to the StepExecution instance immediately before a step begins, used by the exception/cleanup path to attribute and mark that specific step as failed, and cleared/reset after step completion (including on retries) so subsequent errors are not misattributed. Mention it is relied on by the error-handling code that marks step failure and records failure metadata.

- Verify each finding against the current code and only fix it if needed.

In @tests/agents/test_spawn.py around lines 75 - 87, Update the test_agent_run_id_format test to not only check the prefix and length but also validate the suffix is lowercase hex: after calling prepare_terminal_spawn and obtaining result.agent_run_id, add a regex assertion (e.g. matching '^run-[0-9a-f]{12}$') to ensure the 12 characters after the 'run-' prefix are valid hex; reference test_agent_run_id_format, prepare_terminal_spawn, and the agent_run_id field when locating where to add this assertion.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 47 - 85, The useEffect currently lists the entire sessionsHook object in its dependency array which can trigger unnecessary reruns if sessionsHook is a new reference each render; update the dependency array to use the stable properties used inside the effect instead (e.g., sessionsHook.sessions and sessionsHook.refresh) so the effect only re-runs when the sessions list or the refresh function actually change, keeping the rest of the logic (wasStreamingRef, titleSynthesisCountRef, currentSession lookup, fetch to /sessions/:id/synthesize-title) unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConversationPicker.tsx around lines 101 - 103, In ConversationPicker.tsx, avoid rendering the duplicate "Chats" session-group label when there are no agents/sessions to group: conditionally render the <div className="session-group"> (or at least the <div className="session-group-label">Chats</div>) only when the sessions/agents list used by the component is non-empty; update the JSX around the session-group, session-group-label, and sessions-list so the label is omitted unless there is content to justify it.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConversationPicker.tsx around lines 190 - 200, The per-instance 1s setInterval inside the useEffect (the update/interval logic that computes uptime from startTime and calls setUptime) will scale poorly with many agents; refactor so components subscribe to a shared timer instead of creating their own interval. Implement a shared timer provider or singleton (e.g., useSharedTimer or a global EventEmitter that ticks every second) and replace the local setInterval/update/clearInterval logic in the component using startTime/setUptime to listen to that shared tick and compute uptime on each tick; keep the existing uptime computation using startTime to avoid changing formatting logic.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConversationPicker.tsx around lines 183 - 187, AgentUptime currently falls back to Date.now() when startedAt is undefined which misrepresents uptime; update AgentUptime (the startedAt prop handling and any uptime calculation/render path) to detect missing startedAt and render a placeholder like "—" or "unknown" instead of computing from Date.now(), e.g. return the placeholder early or set a sentinel value in the memo and branch in the render; ensure any helpers or functions that compute elapsed time (inside AgentUptime) handle the missing-startedAt case and avoid starting timers when startedAt is absent.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/DashboardPage.css around lines 348 - 355, The .dash-error rule uses a hardcoded color (#ef4444); change its color declaration to use a CSS variable with a fallback (e.g., var(--color-error, #ef4444)) so it matches the pattern used elsewhere (like var(--color-success, #22c55e)); update the .dash-error selector in DashboardPage.css to reference that variable and ensure consistency with other status color usages.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/GitHubPage.tsx around lines 95 - 149, The JSX is invalid because the inline object used to map tabs to content is not wrapped in parentheses; locate the render block in GitHubPage.tsx where the expression uses the object keyed by activeTab (the code that builds overview/branches/prs/worktrees/clones/cicd from sc and then indexes it with [activeTab]) and wrap that object literal in parentheses so the expression becomes a parenthesized object expression (e.g., replace { { overview: ..., branches: ..., ... }[activeTab] ?? null } with { [ { overview: ..., branches: ..., ... } ](activeTab) ?? null }), leaving the component props and fallback logic unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryGraph.tsx around lines 5 - 10, The MemoryGraphProps interface declares a memories: GobbyMemory[] prop that is never used by the MemoryGraph component (the component obtains data via fetchGraphData), so remove the unused property from the interface and from any prop destructuring/usage in the MemoryGraph component (search for MemoryGraphProps and the component function signature/props destructuring), then update all call sites/types that pass memories to MemoryGraph to stop providing that prop or adjust them to use fetchGraphData; ensure TypeScript compiles and run tests to confirm no remaining references to memories.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryPage.tsx around lines 101 - 113, The fetch inside the MemoryPage component's useEffect can update state after unmount; fix it by creating an AbortController, pass its signal to fetch('/api/config/values', { signal }), and in the effect cleanup call controller.abort() so the request is cancelled on unmount; when resolving the promise, only call setMemoryGraphLimit and setKnowledgeGraphLimit if the fetch was not aborted (or ignore an AbortError in the catch) to avoid state updates on an unmounted component.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx at line 680, wrappedOnChange is recreated every render causing potential unnecessary re-renders of CodeMirrorEditor; wrap it in useCallback to memoize it (e.g., replace the inline const wrappedOnChange = (...) => { setIsDirty(true); onChange(content) } with a useCallback hook) and include setIsDirty and onChange in the dependency array so the callback updates when those change; ensure you import useCallback from React and then pass the memoized wrappedOnChange to CodeMirrorEditor.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 154 - 171, In handleYamlSave validate parsed.description before using it: check if parsed.description !== undefined and typeof parsed.description !== 'string' then throw a clear "Invalid YAML: \"description\" must be a string" error, and only pass (parsed.description as string) to updateWorkflow when it has been validated (otherwise set description to undefined); update references to parsed.description in the updateWorkflow payload accordingly (symbols: handleYamlSave, parsed, yamlEditorWf, updateWorkflow).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 235 - 261, The project search dropdown rendered when showProjectSearch is true is missing ARIA attributes; add role="listbox" (and an appropriate aria-label or aria-labelledby) to the options container (the div wrapping filtered.map) and add role="option" plus aria-selected={(p.id === selectedProjectId)} to each mapped item (the button inside filtered.map), and ensure the trigger button that toggles showProjectSearch has aria-expanded={showProjectSearch} and aria-controls referencing the listbox id; update references to projectSearch, setProjectSearch, onProjectChange, selectedProjectId and setShowProjectSearch accordingly so semantics are preserved.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 104 - 123, The FileReader in handleFilesSelected lacks an onerror handler so read failures are silent; add reader.onerror to capture the error, revoke any created previewUrl if needed, and surface/record the failure (e.g., processLogger/console.error and a user-visible message or state update) before skipping adding the file to setQueuedFiles; ensure reader.onload remains unchanged and that any cleanup (URL.revokeObjectURL) is performed on error to avoid leaks.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/CodeBlock.tsx around lines 36 - 39, The language detection regex in CodeBlock.tsx only allows word characters so IDs like language-objective-c and language-c++ fail; update the regex used to compute match (the /language-(...)/ in the match assignment) to accept letters, digits, hyphens and plus signs (e.g. a character class like [A-Za-z0-9+-]+) and make it case-insensitive, then keep the existing language = match ? match[1] : '' extraction and leave codeString and isInline logic unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/CodeBlock.tsx around lines 1 - 52, The copy timeout set in CodeBlockInner's handleCopy can fire after the component unmounts and call setCopied; fix it by storing the timeout id (from setTimeout) in a ref and clearing it on unmount via a useEffect cleanup. Update CodeBlockInner to import/use React.useRef, assign the timer id when calling setTimeout in handleCopy, and clearTimeout(timerRef.current) in a cleanup so setCopied is not called after unmount.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/Markdown.tsx around lines 25 - 27, The current key in the blocks.map render uses the loop index (key={`${id}-${i}-${block.length}`}) which can cause unstable reconciliation when blocks are inserted or reordered; replace the index-based key with a stable content-based identifier by computing a deterministic hash from the block content (or using a unique id field on the block) and use that in the MemoizedBlock key, updating the code that renders MemoizedBlock to use key={`${id}-${contentHash}`} (or key={`${id}-${block.id}`}) so keys remain stable across streaming updates and prevent unnecessary re-renders of MemoizedBlock.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactPanel.tsx around lines 32 - 54, In handleDownload inside ArtifactPanel.tsx, wrap the data-URI parsing and atob decoding in a try/catch and validate the result of content.split(',') yields two parts before using b64 so malformed data URIs don't throw; on error fall back to creating a text/blob download or surface a user-friendly error via console/process UI and ensure URL.revokeObjectURL is still called. Also sanitize the generated filename derived from artifact.title by stripping path traversal characters (/, \), removing or replacing other filesystem-unfriendly characters (e.g., : * ? " < > |), collapsing whitespace, and truncating to a safe length before appending the ext so downloads cannot create weird paths or invalid names. Ensure changes reference handleDownload, artifact.title, content, and URL.revokeObjectURL so the fix is localized.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 7 - 30, The parseCSV function currently returns [['']] for empty or whitespace-only input because it trims and then processes, pushing an empty row; modify parseCSV to check the trimmed text at the start and return an empty array when trimmed === '' to ensure whitespace-only input yields [] (so downstream "Empty data" checks work); locate the parseCSV function and add this early-return guard before the loop that iterates over trimmed.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/MemorySkillsCard.tsx around lines 1 - 4, Export the Props interface so parent components and tests can import it; update the declaration in MemorySkillsCard.tsx from "interface Props { memory: { count: number } skills: { total: number } }" to an exported interface (export interface Props ...) and ensure any consuming modules or tests import Props from this component file (or adjust their imports) to use the exported type.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 42 - 58, handleViewDiff currently swallows fetch errors (only console.error) so add and use a diff error state (e.g., diffError / setDiffError) to surface failures to the user: clear diffError and setDiffLoading(true) at the start of handleViewDiff, in the catch setDiffError(e) (or a friendly message) and ensure setDiffLoading(false) in finally; then update the BranchDetail render to show the diffError to the user (inline message, alert, or toast) when present so users see when the diff fetch fails. Use the existing identifiers handleViewDiff, setDiff, setShowDiff and setDiffLoading when wiring this up.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 93 - 98, Extract the inline IIFE date-formatting logic into a shared utility (e.g., formatDateOrDash or formatDate) and replace the duplicated blocks in ClonesView, CICDView, and PullRequestsView with calls to that helper; the utility should accept the raw date value (like clone.created_at), parse to Date, return '-' for invalid dates and otherwise return toLocaleDateString(), and then update the JSX in ClonesView (the span using the IIFE) to call the new helper instead of the inline function.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 21 - 29, The handleDelete function awaits onDelete(id) but ignores its boolean result; update handleDelete to capture the returned boolean (const success = await onDelete(id)), and if success is false show an error feedback (e.g., call a toast/error state like setDeleteError or invoke a notification) and avoid clearing confirm state so the UI reflects failure; only clear setConfirmDelete(null) when success is true while still ensuring setActionLoading(null) runs in finally. Reference: handleDelete, onDelete, setActionLoading, setConfirmDelete (and add setDeleteError or toast call).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx at line 32, The code uses latestRun = ciRuns[0] in SourceControlOverview which assumes ciRuns is sorted newest-first; make this explicit and robust by either sorting/filtering ciRuns before selecting the latest or selecting the latest by timestamp (e.g., compare run.createdAt or run.timestamp) to derive latestRun; update the logic that computes latestRun (and any usages in the "CI Status" card) to handle empty arrays and to document the assumption in a comment so the component does not display stale data if the backend ordering changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 96 - 103, The numeric input in WorktreesView.tsx for cleanupHours is missing an accessible label; update the input element (the one using value={cleanupHours} and onChange={(e) => setCleanupHours(Math.max(1, Number(e.target.value)))}) to include an aria-label (or aria-labelledby) that clearly describes the field (e.g., "cleanup hours" or "hours until cleanup") so screen readers can announce its purpose.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 20 - 21, The current single-string actionLoading state in WorktreesView can be overwritten by concurrent ops; change actionLoading from string | null to a Set<string> and update setActionLoading usages (e.g., in sync/delete handlers) to add the worktree id with an immutable update and remove it on completion or error, similarly convert actionError to map or clear per-id errors using setActionError where appropriate, and update UI checks (e.g., disabled and has checks) to use actionLoading.has(id) so multiple concurrent operations are tracked correctly; update any references to setActionLoading(prev => ...) to create a new Set(prev) when adding/removing ids and ensure cleanup on finally.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 78 - 90, The status counts are being recomputed for each status on every render inside STATUSES.map by calling worktrees.filter(...).length repeatedly; fix this by computing a single memoized lookup (e.g., countsByStatus) with React.useMemo that iterates worktrees once and produces a Map/object of status -> count, using worktrees as the dependency, then replace worktrees.filter(...).length with countsByStatus[s] (falling back to 0) in the rendering loop (references: STATUSES, worktrees, statusFilter, setStatusFilter).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useArtifacts.ts around lines 6 - 14, The loadPanelWidth function can return NaN if localStorage contains a non-numeric value because parseInt may produce NaN which then poisons Math.max/Math.min; fix it by parsing the stored value into a number, validating it (Number.isFinite or !Number.isNaN) before applying the clamp, and only return the clamped value when the parsed result is a valid number; otherwise fall back to the default 480. Update references in loadPanelWidth and PANEL_WIDTH_KEY handling so the code first does const parsed = parseInt(stored, 10) (or Number(stored)), check validity, then return Math.max(300, Math.min(800, parsed)) only for valid parsed values, with the existing try/catch and development warning preserved.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 119 - 122, The refs localPollRef and githubPollRef are typed as number | null which is browser-specific; update their types to use ReturnType<typeof setInterval> | null for cross-platform safety (e.g., const localPollRef = useRef<ReturnType<typeof setInterval> | null>(null) and same for githubPollRef) to match the window.setInterval usage elsewhere and avoid Node/Browser type mismatches; no change needed for fetchLocalRef/fetchGitHubRef.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 319 - 335, The syncWorktree function calls fetchWorktrees() without awaiting it, so returning true can occur before the UI state updates; update syncWorktree (the async function defined as const syncWorktree = useCallback(...)) to await fetchWorktrees() after a successful response (await fetchWorktrees()) so the function only returns true once the worktrees have been refreshed; ensure any errors from fetchWorktrees are allowed to surface to the catch block or handled consistently.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 356 - 372, The syncClone function calls fetchClones() without awaiting it, which can cause race conditions; update syncClone (the useCallback async function) to await fetchClones() after a successful POST to `${getBaseUrl()}/api/source-control/clones/${id}/sync` so the clone list refresh completes before returning true (ensure you keep fetchClones in the dependency array).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 303 - 317, In cleanupWorktrees, the calls to fetchWorktrees() and fetchStatus() are not awaited which can return before state updates; change those invocations inside the if (!dryRun) branch to await fetchWorktrees() and await fetchStatus() (keeping the existing dependency names) so the function only returns after both refreshes complete.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useTerminal.ts around lines 3 - 4, Change SHOW_MODES from a mutable string array to a readonly tuple by appending "as const" to its declaration (the symbol SHOW_MODES in useTerminal.ts); this will make its elements literal types and readonly so usages like SHOW_MODES.includes(...) and any derived types infer correct union literal types instead of string. After making SHOW_MODES readonly, adjust any variables typed from it (e.g., showMode/state or params derived from SHOW_MODES) to use the inferred literal union (or typeof SHOW_MODES[number]) where necessary so TypeScript accepts comparisons and preserves narrower types.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useTerminal.ts around lines 120 - 121, Update the stale inline comment inside the event handler that checks if (event.event === 'agent_started' && SHOW_MODES.includes(event.mode || '')): the comment currently says "Add new agent (embedded or tmux)" but SHOW_MODES now includes 'terminal' as well, so change the comment to reflect the expanded set (e.g., "Add new agent (embedded, tmux, terminal)" or generalize to "Add new agent for supported modes") so it accurately describes the behavior of SHOW_MODES and event.mode handling.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useTerminal.ts around lines 66 - 84, The fetch('/api/agents/running') flow lacks an HTTP status check before calling r.json(); update the chain in useTerminal.ts to verify the response is ok (e.g. check r.ok or r.status) and throw or handle non-2xx responses before parsing, so setAgents(...) only runs on successful responses; ensure errors are caught and logged in the existing .catch so you don't operate on undefined data (references: fetch('/api/agents/running'), setAgents, SHOW_MODES, RunningAgent).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 131 - 150, Replace the 200ms polling in the useEffect that watches playbackQueueRef with an event-driven listener: add subscribe/unsubscribe or onPlay/onStop callback support to AudioPlaybackQueue (or expose an "onStateChange" handler) so the hook can register handlers instead of polling; inside the hook (the effect that currently uses playbackQueueRef.current.isPlaying, wasPlaying, vadRef, setIsSpeaking and setIsListening) register callbacks that setIsSpeaking(true/false), pause/resume vadRef.current and call setIsListening accordingly, and remove those listeners in the effect cleanup. Ensure you reference the existing playbackQueueRef, vadRef, setIsSpeaking, and setIsListening when wiring callbacks so behavior matches the current pause/start logic.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 209 - 212, The call to vad.start() can throw (e.g., permission revoked) but is unprotected; wrap vad.start() in a try-catch around the block where vadRef.current is set and start is invoked (the code that assigns to vadRef.current, calls vad.start(), and then setVoiceMode/setIsListening). In the catch, log or surface the error (use existing logger or console.error), ensure vadRef.current is cleared if start failed, and set state to not listening (setIsListening(false) and setVoiceMode(false)) so the UI stays consistent; rethrow only if upstream needs it.
