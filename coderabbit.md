Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/workflows/gobby-daemon-mcp.md around lines 63 - 84, The examples using mcp_call_tool lack context about its origin and setup; update the documentation around the examples to explicitly state whether mcp_call_tool is pseudocode or show the minimal setup needed (e.g., the import or client initialization) before calling it, referencing the mcp_call_tool usage in the snippets so readers know where the function comes from and any required initialization or authentication steps.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl around lines 346 - 354, The .gobby/memories.jsonl contains corrupted JSONL records (entries containing substrings like "showenectionClosed", "desie hook_dispatcher.py", "gobbon_migrate_add_mem0_id()", and "Rationa.") that must be removed or repaired; locate the affected records by their ids (e.g., 495f0b9e-df23-5eec-8605-ee6341ec8dd6, 6bf7e921-0388-5bb2-82ed-810f65bd54fd, f3c42649-6ed1-5025-bdd2-9677ccd81fe6 and nearby lines), delete or replace those JSON objects with correct content, ensure each line is valid JSON (no truncation or garbled text), run a JSONL validator (or simple JSON parse) over .gobby/memories.jsonl to confirm validity, and commit the cleaned file with a brief message noting removal of corrupted memory entries.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 248 - 252, Phase 2's "Non-blocking canvases" approach (where update_canvas broadcasts partial updates and canvas interactions are injected as synthetic user messages) risks message-injection attacks; update the design and implementation so injected messages are clearly tagged (add metadata like synthetic:true and origin:canvas_id when creating messages in the update_canvas handling path), run the same sanitization/validation pipeline on canvas action payloads as you do for keyboard input, enforce rate limits and throttling for messages created from CanvasPanel.tsx/ChatPage.tsx event handlers to prevent flooding, and add an immutable audit trail/log entry for every synthetic injection (including canvas_id, user_id, timestamp, payload hash); also evaluate and implement reduced permission scopes for synthetic messages versus authentic user input.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 62, The plan currently marks server-side HTML sanitization for render_canvas as optional—make it mandatory: ensure render_canvas(content, ...) always sanitizes HTML on the server before persisting any CanvasState and before broadcasting the canvas_event (event: "rendered"), and remove the "optional" qualifier from the plan; reference the render_canvas function, CanvasState storage flow, and the canvas_event emission so the sanitizer runs in that path and all stored/broadcast payloads are the sanitized version.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 260 - 273, Add a validation rule for data-action values and document it in the Data Attribute Convention: require actions match a safe pattern (alphanumeric, underscores, hyphens, length ≤64) and show the validator API names VALID_ACTION_PATTERN and validate_action as the canonical check to use before emitting or handling an action; update the text after the data-action bullet to state the constraint and include an example regex description and a short note advising callers to run validate_action() and to reject/log invalid actions to avoid injection/metrics/routing issues.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 62, The render_canvas API currently hardcodes a 600s wait for blocking canvases; add a timeout parameter to render_canvas(content: str, canvas_id: str = "", title: str = "", blocking: bool = True, timeout: int = 600), validate and clamp it to a maximum (e.g., 1800 seconds) before use, and replace the hardcoded wait with asyncio.wait_for on the associated asyncio.Event using the provided timeout; update places that create/store CanvasState and broadcast canvas_event to accept/propagate the timeout as needed and ensure the function returns the same `{canvas_id, interaction...}` or `{canvas_id, status: "rendered"}` shape based on blocking vs non-blocking behavior.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 84 - 90, In render_canvas, validate the raw byte size of the incoming content before any sanitization/storage by computing len(content.encode('utf-8')) and reject if it exceeds MAX_CANVAS_SIZE; raise/return a clear error using the exact message "Canvas content exceeds 64KB limit" (or a ValueError that includes the actual byte size and MAX_CANVAS_SIZE) so callers see both sizes; ensure this check is placed at the start of render_canvas (before calling sanitizers or persisting) and references the MAX_CANVAS_SIZE constant.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 115 - 144, The handler _handle_canvas_interaction currently only validates canvas_id but not ownership; after obtaining the canvas state from the registry (use canvas_registry.get_canvas_state(canvas_id) or equivalent) check that canvas_state.conversation_id matches the authenticated connection context (websocket.conversation_id) and if not call self._send_error(websocket, "Not authorized for this canvas") and return; ensure CanvasState exposes conversation_id and the websocket object carries the authenticated conversation_id before calling canvas_registry.resolve_interaction to prevent unauthorized interactions.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 297 - 307, Add structured audit logging for all canvas lifecycle events: when render_canvas is called, when canvas state is updated, when resolve_interaction/unblock is invoked, and when clear_canvas completes. Log entries should include canvas_id, conversation_id, user_id, action_type (render, update, interact, clear), timestamp, success/failure, and for interactions only a sanitized payload summary (truncate and remove sensitive fields). Instrument the WebSocket broadcast/interaction handler used in tests/websocket/test_canvas_interaction.py and the functions referenced in tests/tools/test_canvas.py (render_canvas, resolve_interaction, clear_canvas, and the interaction handler) to emit these structured logs so security/monitoring systems can ingest them.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 84 - 90, Enforce the limits in render_canvas by (1) implementing a per-conversation sliding-window rate limiter that stores the timestamps of the last N renders and rejects with an error if more than MAX_RENDER_RATE renders occur within 60 seconds (use MAX_RENDER_RATE constant), (2) checking and rejecting if the conversation already has >= MAX_CANVASES_PER_CONVERSATION canvases, and (3) rejecting if content length > MAX_CANVAS_SIZE; additionally add a proactive background sweeper task (run e.g., every 5 minutes) that removes expired canvases (where completed == True or datetime.now() > expires_at) and also invoke a lightweight lazy sweep at the start of render_canvas as a fallback, and finally add a cleanup hook triggered when conversations are deleted or archived to remove all associated canvases.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 154 - 174, The sanitizeCanvasHtml implementation currently allows the style attribute and does not validate URI schemes for href/src, which permits CSS and URI injection; update sanitizeCanvasHtml (and the ALLOWED_ATTRS constant) to either remove 'style' from ALLOWED_ATTRS or keep it but strip dangerous properties via a DOMPurify hook, and add a DOMPurify.addHook('uponSanitizeAttribute', ...) in sanitizeCanvasHtml that (1) rejects style values containing position:fixed|absolute, high z-index, or other risky CSS, and (2) parses href/src values and only keeps them when their scheme is in a whitelist like ['http','https','mailto'] or when they are safe relative paths (e.g., start with '/'), otherwise set data.keepAttr = false to drop the attribute.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 219 - 242, The respondToCanvas callback currently does an optimistic update but never reverts on missing server confirmation and may send using a stale conversationId; fix by adding a 5s revert timeout when you call updateCanvasStatus(canvasId, 'completed') and store the timeout ID (e.g., in a local Map or ref keyed by canvasId) so you can clearTimeout(revertTimeout) when a server confirmation for that canvas arrives (ensure your server message handler clears the matching timeout); before sending, validate conversationIdRef.current matches the active conversation (or bail/log if not) and only call ws.send when wsRef.current is open and the conversation matches, and on send failure revert immediately by calling updateCanvasStatus(canvasId, 'active') and clearing the timeout if set.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 179 - 196, Update the CanvasRenderer interaction handling to add client-side throttling and payload-size validation: introduce a MAX_PAYLOAD_SIZE (e.g., 4096) and check the length of element.getAttribute('data-payload') before attempting JSON.parse in the existing handleInteraction flow, warning and returning if too large; additionally add click throttling by implementing a debounce or an "interaction in flight" flag (300ms) around the delegated click/submit/change handler tied to data-action so duplicate/rapid interactions are ignored while an interaction is pending; keep null-checks for e.target, max traversal depth (20), and preserve try/catch around JSON.parse and existing behavior for status === 'completed'.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 297 - 307, Add integration and unit tests to cover security and concurrency edge cases: in tests/websocket/test_canvas_interaction.py add cases that trigger MAX_RENDER_RATE and MAX_CANVASES_PER_CONVERSATION and assert the proper error responses and no leftover state; simulate a blocking canvas to assert timeout after 600s and that the pending entry is removed from_pending_canvases; attempt interactions from a different conversation/user and assert rejection; create concurrent interaction attempts against the same render_canvas instance to surface race conditions and assert deterministic resolution via resolve_interaction; and send malformed data-payloads (invalid JSON, oversized payload, special characters) to assert graceful handling. Also add/extend unit tests in tests/tools/test_canvas.py to verify memory cleanup of expired canvases and that timeouts/limits do not leak entries in _pending_canvases.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/spawn.py around lines 160 - 162, The current check in spawn.py uses a falsy test "if not agent_run_id" which treats empty strings as missing and will silently generate a new ID; change this to an explicit None check by testing "agent_run_id is None" (the logic that assigns agent_run_id = f"run-{uuid.uuid4().hex[:12]}" should only run when agent_run_id is exactly None) so that empty strings passed into the function are preserved and only actual None triggers ID generation.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/install.py around lines 331 - 339, The try/except around importing and calling configure_ide_terminal_title should also catch ImportError (and optionally AttributeError) so missing .installers.ide_config or a missing export doesn't crash the install command; update the exception clause around the import/call of .installers.ide_config and the call to configure_ide_terminal_title (vscode_result) to include ImportError (and AttributeError) and keep the existing warning message path so the optional VS Code terminal title setup fails gracefully.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/memory.py around lines 519 - 534, The query string is constructed via f"?project_id={project_id}" without URL-encoding, so if project_ref resolves to a value containing special characters the request may break; update the code around resolve_project_ref and the params variable construction to URL-encode project_id (e.g., use urllib.parse.quote or urllib.parse.urlencode) before passing it into client.call_http_api(f"/memories/crossrefs/rebuild{params}", ...) so the request is safe; keep the conditional behavior (params empty when project_id is None) and ensure the encoded parameter name remains project_id.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_session.py around lines 96 - 99, The return uses an unnecessary str() wrapper around std_path (which is already a string); remove the redundant conversion so the function returns std_path directly. Update the block around std_path (the tempfile.gettempdir() f-string and the Path(...).exists() check) to return std_path instead of str(std_path) and keep the existing debug log using self.logger.debug.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/hook_manager.py around lines 672 - 676, The code reads self._session_manager.db without guarding against self._session_manager being None, which can raise an uncaught AttributeError; update the try block around the LocalProjectManager creation/ensure_exists to first verify self._session_manager is not None (or explicitly handle the None case) before accessing .db, or include AttributeError in the except tuple; refer to _session_manager, LocalProjectManager, and ensure_exists when making the change so the access is safely guarded or the AttributeError is handled.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/session_coordinator.py around lines 364 - 365, Replace the broad "except Exception as e" in the session stats counting block with a DB-specific handler: import sqlite3 if needed and change the clause to "except sqlite3.Error as e" and keep the same self.logger.warning(f'Failed to count session stats for {session.id}: {e}') so database errors are handled precisely; do not silently catch all Exceptions—let other unexpected exceptions propagate (or add a separate explicit fallback only if you intend to log+rethrow).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/memory.py around lines 518 - 551, The rebuild_crossrefs tool hardcodes limit=500 when calling memory_manager.list_memories; add a new parameter limit: int | None = 500 to the async def rebuild_crossrefs signature and use that variable in the call to memory_manager.list_memories(project_id=project_id, limit=limit), and propagate that parameter to any docstring/registry metadata so the API matches rebuild_knowledge_graph; ensure default behavior remains 500 and update the returned "memories_processed" to reflect the actual list length as before.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/pipelines/__init__.py around lines 60 - 71, The function_resolve_session_ref currently returns the original ref when session_manager is None, which can hide errors; change it to explicitly raise an error (e.g., ValueError or RuntimeError) when session_manager is None so callers get a clear failure instead of an unresolved ref. In practice, update _resolve_session_ref to check if session_manager is None and raise with a message like "cannot resolve session reference '<ref>' without a LocalSessionManager" (include the ref for context); keep the rest of the logic using get_project_context and session_manager.resolve_session_reference unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/pipelines/_execution.py around lines 12 - 13, The module-level _background_tasks set is never cleaned up on daemon shutdown; add a module-level async cleanup function (e.g., cleanup_background_tasks or shutdown_background_tasks) that iterates over _background_tasks, cancels any pending asyncio.Tasks, awaits them with asyncio.gather(..., return_exceptions=True) to drain results, clears the set, and logs failures; then call this cleanup function from the application's shutdown sequence so all tasks tracked by_background_tasks are properly awaited/cancelled.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 602 - 621, Remove the synchronous await sleep in the main spawn path so tmux health checks don't add 0.5s to every spawn; instead make the check optional or run in background: add a config or parameter (e.g., skip_tmux_health_check or enable_tmux_health_check) to guard the behavior and/or use asyncio.create_task to run the sequence that waits TMUX_HEALTH_CHECK_DELAY and calls _check_tmux_session_alive(spawn_result.tmux_session_name) and then performs agent_registry.remove(run_id, status="failed") and runner.run_storage.fail(...) if needed, ensuring any exceptions are caught and logged; keep the existing logic intact but off the hot path so spawn_result is returned immediately when the check is disabled or backgrounded.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 38 - 41, The TMUX_HEALTH_CHECK_DELAY initialization uses float(os.environ.get(...)) which will raise ValueError on non-numeric input; update the code around TMUX_HEALTH_CHECK_DELAY (and the GOBBY_TMUX_HEALTH_CHECK_DELAY env lookup) to parse safely by wrapping the float conversion in a try/except (or use a helper that validates), falling back to the default 0.5 and optionally logging a warning when parsing fails so invalid env values don't crash spawn_agent.py.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py around lines 237 - 243, The_pending_approval field is currently typed as dict[str, Any] | None which loses structure; create a specific type (either a TypedDict or dataclass named PendingApproval with fields tool_name: str and arguments: dict[str, Any]) and change ChatSession._pending_approval to PendingApproval | None; update any usage sites that index into _pending_approval (e.g., reads/writes of "tool_name" or "arguments") to use attribute access if you choose a dataclass or key access if you choose a TypedDict, and adjust imports/annotations accordingly so type checkers and IDEs recognize the new type.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py around lines 491 - 498, Update the_DANGEROUS_BASH_PATTERNS regex in chat_session.py to cover the missed cases: add patterns to detect redirection-to-file followed by execution (e.g., ">\s*[^;&\n]+(?:&&|\|\|)?\s*(?:sh|bash|\.\/)" to catch "curl ... > script.sh && sh script.sh"), make rm variants robust to arbitrary whitespace and flags (e.g., accept sequences like "rm\s+-\s*r\s*-?\s*f\b" or use "rm(?:\s+[^\n;&|]+)*\s+-[^\n;&|]*[rf][^\n;&|]*"), and include detection for command substitution forms using backticks or $(...) around dangerous commands; also add a short comment above_DANGEROUS_BASH_PATTERNS documenting these limitations and why some constructs may still bypass regex-based checks so future maintainers can extend it safely.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/sessions.py around lines 622 - 624, Wrap the provider.generate_text(llm_prompt) call in an async timeout (e.g., asyncio.timeout or asyncio.wait_for) to avoid hanging: call provider.generate_text with a configurable timeout (suggest 10s or use server/llm_service timeout config), catch asyncio.TimeoutError and handle it by logging via server.logger/processLogger and returning a sensible fallback title or HTTP error; update the block around get_default_provider()/generate_text in sessions.py accordingly and ensure the asyncio import is added and the TimeoutError path strips/returns a safe title.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 583 - 627, The delete_worktree handler’s git-deletion branching is too scattered; refactor delete_worktree to determine one git deletion target up front (resolve repo_path via _resolve_project and choose WorktreeGitManager(repo_path) when repo_path is truthy, otherwise use server.services.git_manager), store which path was chosen (e.g., used_manager = "WorktreeGitManager" or "server_git_manager"), call a single delete_worktree(...) once and capture the result, log the chosen path with logger.warning/info and any result.message, and then proceed to delete the DB record via worktree_storage.delete; keep the existing git_deleted/response behavior but remove the nested try/except/fallback branches so deletion logic is consolidated and easier to trace.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/voice.py around lines 128 - 131, Replace the f-string log in the exception handler with structured logging: remove logger.error(f"Error sending TTS audio to client: {e}") and call logger.error("Error sending TTS audio to client", exc_info=True, extra={"error": e}) (or logger.exception("Error sending TTS audio to client") if you want traceback) so the log uses context instead of string interpolation; update the handler around the ConnectionClosed/ConnectionClosedError block where logger.error is called.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/voice.py around lines 58 - 62, The _tts_websockets dict is currently typed as dict[str, Any]; change it to a precise websocket connection type used in your project (for example dict[str, websockets.server.WebSocketServerProtocol] or dict[str, WebSocket] depending on your websocket library) and add the appropriate import at the top of the module, updating the annotation for _tts_websockets; if you intentionally need Any for flexibility, keep the Any but add a clarifying comment on the expected value type (e.g., "# values are WebSocketServerProtocol instances") so callers and type-checkers understand the intended type.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/voice.py around lines 333 - 334, Replace the plain string interpolation logger.error in the TTS exception handler with structured logging that attaches the exception and contextual fields: call logger.error("TTS send error", exc_info=True, extra={"session_id": session_id, "user_id": user_id, "connection_id": connection_id, "voice": voice_name, "text_preview": tts_text[:100]}) or use logger.exception("TTS send error", extra={...}) so the exception stack is captured and searchable; update the except block where logger.error(...) is used to include exc_info/exception and relevant local context variables (session_id, user_id, connection_id, voice_name, tts_text) while avoiding leaking full PII.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sessions/manager.py at line 62, Add a short explanatory comment where self.db is assigned from session_storage.db that states why the raw DB handle is being exposed (e.g., required for transaction coordination, cross-session queries, or performance-sensitive bulk operations), describes any intended safe usage patterns or ownership/transaction responsibilities, and warns that callers should not mutate internal session state directly; reference the assignment to self.db and session_storage.db (or consider replacing the direct exposure with a documented accessor if you want stricter encapsulation).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/config_store.py around lines 174 - 184, The clear_secret method currently performs secret_store.delete inside the self.db.transaction() context, so if delete fails the DB deletion still commits; to make cleanup atomic, remove the try/except from inside the transaction and let exceptions from secret_store.delete propagate (or explicitly raise on failure) so the transaction rolls back; specifically update clear_secret (and its use of config_key_to_secret_name and SecretStore.delete) to call secret_store.delete before committing the transaction or re-raise any caught exceptions within the transaction instead of swallowing them, and keep the logger usage (logger.warning / exc_info) only when you intend to allow orphaned secrets (document that choice if you keep current behavior).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/cron.py around lines 60 - 63, The function currently suppresses a return-type error with a type: ignore because mypy doesn't see that job.interval_seconds is narrowed to int; after the existing falsy check (if not job.interval_seconds: return None) extract job.interval_seconds into a local variable (e.g., interval = job.interval_seconds) and use that local variable in both timedelta(...) calls so both branches clearly produce datetime and you can safely remove the "type: ignore[return-value]" on the astimezone(...) return; reference the CronJob dataclass field interval_seconds and the function that computes next_dt.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/migrations.py around lines 924 - 927, The current call to db.fetchall("SELECT id, content FROM memories WHERE id LIKE 'mm-%'") can OOM on large tables; change the logic in migrations.py to iterate the query via a cursor or batched fetches instead of loading all rows into memory (e.g., use db.execute(...) and loop over cursor or use fetchmany(batch_size) to process and migrate each batch), keeping the same early-exit behavior (replace the initial rows truthiness check with a check that the cursor yields no rows before logging via logger.info("No mm-prefix memory IDs to migrate") and returning).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sync/memories.py around lines 185 - 226, import_sync currently opens the export JSONL twice (once to count lines, then again in_import_memories_sync), doubling IO; change import_sync to read the file once and either (a) count and buffer the non-empty lines into a list and pass that list to_import_memories_sync (add a parameter to accept lines), or (b) change _import_memories_sync to accept an iterable/file-like object and pass the already-open file iterator from import_sync after counting; use _get_export_path to locate the file and memory_manager.count_memories() to decide whether to import, and ensure the new call signatures and any buffering handle large files safely (e.g., stream vs. buffer) while preserving the existing return value.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/utils/project_context.py around lines 59 - 73, The code silently swallows all exceptions when reading root / ".gobby" / "project.json" for override_id; change the bare except to catch specific exceptions (FileNotFoundError, PermissionError, json.JSONDecodeError, and OSError) and log the error with context (include override_id and project root) using the module logger (or the existing logger) before falling back to returning {"id": override_id}; keep the existing behavior of returning the minimal context when the file is missing or invalid.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/voice/tts.py around lines 73 - 92, The BOS message currently includes a redundant API key field; remove the "xi_api_key" entry from the bos_message dict created in the TTS connection sequence (the code that builds bos_message used after establishing self._ws via websockets.connect). Keep authentication only in the WebSocket handshake header (additional_headers={"xi-api-key": api_key}) and ensure any references to self._config.elevenlabs_api_key in the bos_message are deleted so the API key is not sent in the message body.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/engine.py around lines 163 - 169, When template rendering for a handler fails and you assign the unrendered value into state.variables, update the warning to include the preserved raw value so debugging shows what "{{...}}" was kept; modify the logger.warning call near where state.variables[variable] = value is set to include state.session_id, handler_type, variable and the raw value (value) along with the exception (e) so logs contain both the error and the unrendered template text.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_config.py around lines 384 - 404, The test test_set_config_secret_encrypts relies on a patched get_machine_id but constructs a new SecretStore(temp_db) inside the test, coupling the test to SecretStore's internal call to get_machine_id; either extract SecretStore(temp_db) creation into the test fixture (so the patched get_machine_id is applied consistently) or explicitly patch/mocking get_machine_id where SecretStore is instantiated (or document the dependency) to ensure the mocked machine id is used reliably; update the test to use the fixture-provided SecretStore or add a local patch around the SecretStore(...) construction so get_machine_id is controlled.

- Verify each finding against the current code and only fix it if needed.

In @tests/servers/test_chat_session.py around lines 224 - 256, The assertion comparing captured_options["cwd"] to str(Path.cwd()) is flaky because Path.cwd() is evaluated at assertion time; before calling await session.start() capture the current working directory into a variable (e.g., expected_cwd = str(Path.cwd()) ) or patch Path.cwd for determinism, then call await session.start() and assert captured_options["cwd"] == expected_cwd; update the test_start_falls_back_without_project_path test to reference that captured expected_cwd (and keep symbols: session.start(), captured_options, Path.cwd()) so the comparison is stable.

- Verify each finding against the current code and only fix it if needed.

In @web/scripts/copy-vad-assets.cjs around lines 13 - 22, The loop copying FILES using fs.copyFileSync can throw (e.g., missing destination dir or write errors); update the block around fs.copyFileSync(src, dest) in copy-vad-assets.cjs to create the destination directory if needed (use path.dirname(dest) and mkdirSync with recursive: true) and wrap the copy in a try/catch that logs a clear error including src, dest and the caught error (and continues to the next file) so the postinstall hook doesn't crash the whole run.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 51 - 85, Extract stable references from sessionsHook at the top of the effect (e.g., const { sessions, refresh } = sessionsHook) and use those in the effect body and dependency array instead of sessionsHook to avoid stale-closure issues; also create an AbortController, pass its signal into fetch, and in the effect's cleanup call controller.abort() (and/or check controller.signal.aborted before calling refresh) so the in-flight POST to /sessions/{id}/synthesize-title is cancelled if the component unmounts or deps change. Ensure the effect's dependencies are [isStreaming, conversationId, sessions, refresh] and still update wasStreamingRef.current at the end.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConfigurationPage.tsx at line 132, BACKEND_SECRET_MASK is being reconstructed on every render inside the ConfigurationPage component; hoist it to module scope alongside SECRET_PATTERNS to avoid repeated allocation and for consistency. Move the declaration of BACKEND_SECRET_MASK = '********' out of the function and place it near the top-level where SECRET_PATTERNS is defined, then remove the in-function declaration so only the module-scoped constant is used.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConfigurationPage.tsx around lines 130 - 147, The placeholder never appears because when isMasked (value === BACKEND_SECRET_MASK) the input value is the mask string; change the component to use a derived displayedValue (e.g., const displayedValue = isMasked ? '' : String(value ?? '')) and pass displayedValue to the input's value prop instead of String(value ?? ''), keeping the existing onChange handler (onChange(fullPath, e.target.value)) so that typing replaces the masked secret; keep BACKEND_SECRET_MASK and isMasked logic intact so the underlying value remains unchanged until the user enters a new value.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConversationPicker.tsx around lines 145 - 175, The agent list items currently always render as interactive (role="button", tabIndex={0}, onClick, onKeyDown) even when onNavigateToAgent is undefined; update the JSX that maps agents in ConversationPicker to only add role="button", tabIndex, onClick and onKeyDown handlers when onNavigateToAgent is provided (e.g., conditionally spread interactiveProps or wrap attributes in a ternary), and update styling so .session-item uses cursor: pointer only when interactive (or add a CSS class like .interactive when onNavigateToAgent exists) to prevent non-functional items from appearing clickable; keep the rest of the markup (AgentUptime, session-source-dot, PROVIDER_COLORS, etc.) unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConversationPicker.tsx around lines 182 - 205, AgentUptime currently falls back to Date.now() in the useMemo (startTime) when startedAt is missing/invalid, causing uptime to show from component mount; change the logic so that when startedAt is undefined or invalid startTime is undefined/null and the component displays a placeholder like "—" or "unknown" instead of calculating elapsed time. Update the useMemo for startTime (inside AgentUptime) to return undefined for invalid/missing startedAt, modify the useEffect/update function to no-op or set uptime to the placeholder when startTime is falsy, and ensure the JSX returns that placeholder (using the uptime state or a direct conditional) so the UI no longer shows misleading durations.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryGraph.tsx around lines 108 - 116, The useEffect that sets a setTimeout to call fgRef.current?.zoomToFit can leak if the component unmounts before 500ms; update the effect in MemoryGraph.tsx to store the timeout ID (from setTimeout) and return a cleanup function that clears it (clearTimeout) to prevent the callback from running after unmount; keep existing logic around hasZoomedRef and only schedule/clear the timeout when forceData.nodes.length > 0 and hasZoomedRef.current is false, referencing hasZoomedRef, fgRef, and zoomToFit so the timeout is reliably canceled on unmount or dependency changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryGraph.tsx around lines 83 - 92, The effect that calls fetchGraphData (inside the useEffect in MemoryGraph.tsx) lacks error handling so setLoading(true) can remain true if the promise rejects; wrap the fetchGraphData(memoryLimit) call with a try/catch/finally (or use .catch/.finally) so that errors are caught (log or handle them) and setLoading(false) is always called in the finally path, and only call setGraphData(data) when not cancelled and data is present; keep the cancelled guard around state updates and ensure any error does not leave loading stuck.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryPage.tsx around lines 277 - 294, The max attribute and clamping logic in the Limit input are using hardcoded values (1000/5000) which can drift from defaults; update the component to derive those max values from shared constants (e.g., DEFAULT_KNOWLEDGE_LIMIT, DEFAULT_MEMORY_LIMIT or MAX_KNOWLEDGE_LIMIT / MAX_MEMORY_LIMIT) and use the same constants for the input max and the sliderMax clamp used in the onChange handler for viewMode, then replace the inline literals in the value/onChange branch that reference viewMode, knowledgeGraphLimit, memoryGraphLimit with these constants to ensure a single source of truth.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MobileSessionDrawer.tsx around lines 81 - 85, The current badge logic in MobileSessionDrawer using session.model.split('-').slice[-1](0) is fragile for names without hyphens or with different patterns; create a small helper (e.g., getModelBadge(model: string)) and replace the inline expression with it: have the helper first handle falsy input, then attempt a robust extraction (prefer a regex to capture a trailing version/token like /([A-Za-z0-9]+)$/ or fall back to the full model string truncated to a safe length), and return a sensible default (e.g., the original model or 'unknown') so the UI never shows undefined or an unexpected token while keeping the className session-detail-model-badge unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MobileTerminalDrawer.tsx around lines 25 - 30, attachedKey lookup currently matches sessions by s.name only which can collide across sockets; update the lookup in MobileTerminalDrawer to compare the full session identifier (e.g. `${s.socket}:${s.name}`) against attachedSession (or change attachedSession to store that composite id) so you find the exact session. Locate the attachedKey expression and replace the name-only compare with a composite key comparison, and ensure activeTitle still uses terminalNames[`${attachedKey.socket}:${attachedKey.name}`] (or the same composite id) to remain consistent.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MobileTerminalDrawer.tsx at line 124, The isAttached boolean currently couples attachment state with streaming by computing isAttached as attachedSession === session.name && streamingId !== null; change it to only reflect attachment (isAttached should be true when attachedSession === session.name) by removing the streamingId !== null check so the UI highlights an attached but idle session; keep streamingId logic separate (e.g., use streamingId !== null where you render streaming indicators) and update any dependent UI branches that assumed streaming implied attachment.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/TerminalsPage.tsx around lines 190 - 197, Extract the inline IIFE that computes displayName into a memoized value or helper function for readability: create a useMemo hook (e.g., const displayName = useMemo(() => { ... }, [attachedSession, attachedSocketRef.current, terminalNames, sessions])) or a named function (e.g., getDisplayName(attachedSession, attachedSocketRef.current, terminalNames, sessions)) that implements the same logic (return null if !attachedSession; lookup key `${attachedSocketRef.current}:${attachedSession}` in terminalNames; fall back to sessions.find(...) and return s?.pane_title || s?.window_name || null), then pass that memoized/helper value to the displayName prop instead of the IIFE.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 512 - 543, The three icon-only buttons lack accessible names; update the buttons that call handleDuplicate, handleExport, and handleDelete to include aria-label attributes (e.g., aria-label="Duplicate workflow", aria-label="Download YAML", aria-label="Delete workflow") so screen readers announce them; ensure the aria-label text matches the existing title for each button and add the attribute to the elements with className "workflows-action-icon" (and "workflows-action-icon--danger") that wrap the SVGs.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 154 - 172, The code currently treats an explicit empty name in YAML as absent due to `(parsed.name as string) || yamlEditorWf.name`; to make intent explicit, update handleYamlSave: add a validation that rejects empty-string names (e.g., if (parsed.name !== undefined && (typeof parsed.name !== 'string' || parsed.name.trim() === '')) throw new Error('Invalid YAML: "name" must be a non-empty string')), leaving the existing fallback to yamlEditorWf.name unchanged when name is omitted; reference symbols: handleYamlSave, parsed.name, yamlEditorWf, updateWorkflow.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 683 - 694, The handleSave function clears the dirty flag unconditionally after onSave finishes, which can lose edits made while the save was in-flight; modify handleSave to track the saved snapshot or version and only clear isDirty when the current content matches that saved snapshot (e.g., store lastSavedContent or a saveCounter before calling onSave, then after await onSave compare current content/state to lastSavedContent (or ensure saveCounter hasn't been incremented) before calling setIsDirty(false)); update references in handleSave, onSave callers, and any state setters (setIsDirty, setSaving, setError) so the dirty flag is only cleared when it truly reflects that no new edits occurred during the save.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 140 - 152, handleYamlEdit currently logs exportYaml failures to console and leaves the editor empty; update it to surface the error to the user by showing a UI notification or toast and/or setting an error state before clearing YAML. Specifically, inside the catch block for exportYaml in handleYamlEdit, call your app's notification/toast API (or set an error flag/state and setYamlContent to an explanatory message) so users see a clear error message; keep the existing setYamlLoading(false) in finally and preserve setYamlEditorWf(wf).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 104 - 127, The file-size check in handleFilesSelected silently skips oversized files (MAX_FILE_SIZE_BYTES) with only console.warn; update handleFilesSelected to show user-facing feedback when a file is skipped by invoking the app's notification/toast mechanism (or set an inline error state) with a clear message including file.name and the size limit, and ensure any UI state used (e.g., a toast dispatcher or a local skippedFiles/queuedFiles error state tied to setQueuedFiles) is updated so users see why their file wasn't attached; keep the existing preview/reader logic and still revoke previewUrl on reader.onerror.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/Markdown.tsx around lines 25 - 38, The key currently uses the index which causes re-keying when blocks are inserted at the front; in the Markdown component change the MemoizedBlock key to rely primarily on stable content identity (use stableHash(block) combined with id, e.g. `${id}-${stableHash(block)}`) instead of `${id}-${i}-${stableHash(block)}` so identical blocks keep the same key across shifts; if your app can legitimately have identical blocks and you need to disambiguate duplicates, keep a deterministic disambiguator (not the raw map index on every render) such as a per-block unique id assigned when parsing tokens, or append an occurrence counter derived from content rather than the iteration index.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageItem.tsx at line 15, The variable isCommandResult in MessageItem (const isCommandResult = message.role === 'system' && message.toolCalls?.length && !message.content) is computed but unused; either delete this declaration or wire it into the component's render logic where system/tool call messages are handled (e.g., use isCommandResult to choose the JSX branch, add a conditional render for command result UI, or add a CSS class/prop to the existing message rendering). Update MessageItem to remove the unused const if it's unnecessary, or replace existing conditional checks with isCommandResult so the system/tool-call-only path is actually used.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageList.tsx around lines 26 - 35, The scroll handler in useEffect (handleScroll) updates userScrolledUpRef on every scroll event; wrap that logic in a debounce or throttle to reduce event frequency (e.g., use a small throttle like 100ms or a debounce with a short delay) and attach the throttled/debounced function to scrollRef.current instead of the raw handleScroll. Ensure you store the timer or throttled function in a ref (or import lodash.throttle) so you can clear any pending timeout or cancel the throttle in the cleanup function before removing the event listener, and keep the distanceFromBottom calculation and userScrolledUpRef update inside the debounced/throttled callback.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MobileChatDrawer.tsx around lines 49 - 52, Extract the inline style block used for the "No conversations" message in MobileChatDrawer into a dedicated CSS class (e.g., .mobile-chat-drawer-empty) and replace the inline style on the div with that class; ensure the new class mirrors the inline rules (padding: 0.75rem 1rem; color: var(--text-muted); font-size: calc(var(--font-size-base) *0.85)) and add it alongside the existing mobile-chat-drawer-* and session-* styles so the empty state styling is consistent and maintainable.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MobileChatDrawer.tsx around lines 27 - 35, The header div with className "mobile-chat-drawer-header" currently toggles via onClick but lacks keyboard accessibility; update the element that uses setIsOpen, isOpen and activeTitle to be keyboard-focusable by adding role="button", tabIndex={0}, an onKeyDown handler that listens for Enter and Space and calls setIsOpen(!isOpen), and include an appropriate aria-expanded attribute (true/false based on isOpen); ensure the visual span "mobile-chat-drawer-title" remains unchanged and that the onClick handler still toggles so both mouse and keyboard work.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ModeSelector.tsx around lines 46 - 65, Add ARIA roles and keyboard navigation to the dropdown rendered by CHAT_MODES: give the container div role="listbox" and each item role="option" with aria-selected={m.id === mode} and tabIndex={m.id === mode ? 0 : -1}; implement an onKeyDown handler (attached to the listbox) to handle ArrowDown/ArrowUp to move focus between options, Enter/Space to call onModeChange(m.id) and close (setOpen(false)), and Escape to close and return focus to the trigger; ensure focus is moved to the selected/first option when open and update focus/aria-selected when selection changes; use existing symbols ModeIcon, onModeChange, setOpen, mode, and CHAT_MODES to locate and update the code.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ModeSelector.tsx around lines 70 - 101, The switch in ModeIcon (function ModeIcon({ mode }: { mode: ChatMode })) lacks a default branch so adding new ChatMode values in CHAT_MODES will make it return undefined; add a default case that returns a sensible fallback SVG icon (and optionally a console.warn mentioning the unexpected mode) so the component always renders an icon for unknown modes and remains forward-compatible.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 149 - 154, The console.error in ToolCallCard.tsx inside the try/catch that serializes call.result should not be left unguarded for production; replace that direct console call with a development-only guard or use the app's logging utility. Update the catch for the serialization in the block that sets resultStr (referencing call.result and resultStr) to either remove the console.error, wrap it with a check like NODE_ENV !== 'production' before logging, or call the centralized logger (e.g., logger.error) so production consoles aren't polluted.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactCodeView.tsx around lines 16 - 27, The header div that contains the Edit/View Button is rendered even when onChange is undefined, creating empty space; wrap or conditionally render the entire header block (the div with className "flex items-center justify-end px-2 py-1 border-b border-border") only when onChange is present so the Button (and its handlers using isEditing and setIsEditing) and border are omitted entirely if no onChange prop is provided.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactContext.tsx around lines 3 - 5, The interface ArtifactContextValue is currently unexported which prevents consumers from typing values for ArtifactContext.Provider; export the ArtifactContextValue interface so external modules can import it for type-safe provider implementations and ensure the signature (openCodeAsArtifact: (language: string, content: string, title?: string) => void) remains unchanged so existing uses of ArtifactContext and ArtifactContext.Provider continue to type-check correctly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactImageView.tsx around lines 20 - 29, The current inline regex used to validate image sources in the ArtifactImageView render conditional (the ternary that checks /^(https?:|data:image\/|\/|\.\/)/.test(content)) misses protocol-relative URLs and parent-relative paths; replace the inline test with a clearer validator (e.g., extract to an isValidImageSrc function) and update the pattern to accept protocol-relative URLs ("//") and parent-relative paths ("../") — for example expand the regex to include // and ../ (or use a pattern like /^(https?:|\/\/|data:image\/|\.{1,2}\/|\/)/) and then use isValidImageSrc(content) in the conditional that renders the <img> to ensure those valid sources pass.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactPanel.tsx around lines 32 - 61, The base64 decoding in handleDownload uses atob(binary) which can throw for malformed data; wrap the decoding/parsing branch (inside the artifact.type === 'image' && content.startsWith('data:') block) in a try/catch, catch DOMException or general errors from atob(), and on error create a safe fallback Blob (e.g., Blob([content], { type: 'application/octet-stream' })) and optionally log the error via console.error or a supplied logger before continuing to generate the download URL and revoke it as before; ensure the error handling still sets blob and proceeds to createObjectURL, a.click(), and URL.revokeObjectURL to avoid leaving resources allocated.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 74 - 82, The current rendering in ArtifactSheetView uses the map indices (ri, ci) as React keys for sorted.map and row.map which causes remounts when sorting changes; update the row key to a stable identifier instead: if your CSV rows include a unique id column, use that (e.g., row.id or row[uniqueIndex]); otherwise preserve and use the original pre-sort index or compute a stable hash from the row content (e.g., join values) and use that as the key for the outer <tr> (keep a separate stable key for the inner <td> as well, e.g., column name or index). Ensure you locate the map calls using sorted.map((row, ri) => ...) and row.map((cell, ci) => ...) in ArtifactSheetView and replace ri/ci keys with the stable keys described.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactVersionBar.tsx around lines 42 - 56, Extract the inline SVG icon components ChevronLeftIcon and ChevronRightIcon into a shared icons module and import them into ArtifactVersionBar (or, if these icons already exist in the codebase, replace the local definitions with imports); ensure the exported icon components use the same props/signature as other icons in the library (e.g., width/height/className) so they are reusable and consistent across the app, update ArtifactVersionBar to import and use the shared ChevronLeftIcon and ChevronRightIcon, and remove the local function definitions.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ResizeHandle.tsx around lines 65 - 76, The ResizeHandle component lacks keyboard accessibility — add keyboard focus and arrow-key resizing: make the outer div focusable by adding tabIndex={0}, implement an onKeyDown handler (e.g., handleKeyDown) on the same element that listens for ArrowLeft/ArrowRight (and optionally ArrowUp/ArrowDown) to adjust the pane width, reuse or call the existing resize logic used by handleMouseDown/handleTouchStart (or factor shared resizing into a helper like performResize) and ensure preventDefault/stopPropagation as needed and that the component (ResizeHandle) updates state/props the same way as mouse/touch events.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Dialog.tsx around lines 32 - 37, The dialog's class list currently includes "focus:outline-none" which removes the keyboard focus indicator; update the className string in Dialog.tsx (the element using cn(...) with props className) to preserve keyboard focus by replacing "focus:outline-none" with a keyboard-friendly alternative such as "focus-visible:outline-none" or by applying a visible focus style (e.g. a focus-visible ring class) so that the Dialog component still shows a clear focus indicator for keyboard users while suppressing it for mouse interactions.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/ScrollArea.tsx around lines 9 - 21, The ScrollArea component's scrollable div isn't keyboard-focusable; add tabIndex={0} to the element rendered in ScrollArea (the div using ref and className via cn) so keyboard users can focus and scroll the region, ensuring the prop is applied alongside existing ref, className, and {...props} without altering other attributes or behavior.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/ScrollArea.tsx around lines 11 - 17, The WebKit-only scrollbar CSS in ScrollArea.tsx should include Firefox properties for consistency: update the className passed into cn (in the ScrollArea component) to add Firefox-compatible arbitrary properties such as '[scrollbar-width:thin]' and a scrollbar-color value (e.g. '[scrollbar-color:var(--border)_transparent]' or a concrete color) alongside the existing WebKit rules; alternatively mention using the tailwind-scrollbar plugin and replace/augment the WebKit rules with its cross-browser utility classes. Ensure you modify the className expression where cn(...) is used to include these new bracketed CSS utilities so Firefox users get a thin/colored thumb too.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Select.tsx around lines 5 - 7, Add and export a SelectLabel to improve accessibility for grouped options: implement a SelectLabel component that forwards ref to SelectPrimitive.Label (use the same prop types as SelectPrimitive.Label) and apply any necessary styling, give it a displayName of "SelectLabel", and export it alongside Select, SelectGroup, and SelectValue so consumers can associate labels with SelectGroup for screen readers.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Textarea.tsx around lines 19 - 24, The resize callback (resize) currently clamps the textarea height using internalRef.current and maxHeight but doesn't set overflow, preventing scrolling when content exceeds maxHeight; update resize to detect when internalRef.current.scrollHeight > maxHeight and then set internalRef.current.style.overflowY = 'auto' (otherwise set it to 'hidden' or '') so the textarea becomes scrollable when clamped, while keeping existing autoResize and height logic.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/SessionsCard.tsx around lines 31 - 54, The segmented progress bar in SessionsCard renders color-only segments (SEGMENTS map and the "other" segment) without accessible labels; update the rendering for segments in SessionsCard to include an aria-label (and optionally a title) on each .dash-bar-segment that contains the segment key/name, raw value, and percentage (e.g., `${key}: ${value} (${pct.toFixed(1)}%)`), and apply a similar aria-label/title to the "other" segment so screen readers can convey the meaning of each colored segment.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/SystemHealthCard.tsx around lines 3 - 11, formatUptime currently returns "0m" when seconds is less than 60; update the function (formatUptime) to detect sub-minute uptimes and return a seconds string instead (e.g. `${seconds}s`) or a clear "<1m" indicator rather than "0m"; keep existing behavior for minutes/hours/days and ensure seconds is handled when seconds is a number and less than 60.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/TasksCard.tsx around lines 1 - 7, Export the locally defined types so other modules can reuse them: change the declarations of SegmentKey and TaskCounts to be exported (export type SegmentKey = ... and export type TaskCounts = ...), and if Props is part of the component public surface consider exporting it too (export interface Props { tasks: TaskCounts }). Update any internal references to use the exported names and ensure the component still imports/exports appropriately.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/TasksCard.tsx around lines 52 - 66, The ring elements in rings.map use ring.color as the React key which is fragile; update the key to a stable identifier (e.g., use a unique segment id property or the map index) to avoid re-render bugs — locate the rings.map callback in TasksCard.tsx and replace key={ring.color} with a stable key such as key={ring.key} (if rings items include a unique id) or key={index} passed from rings.map((ring, index) => ...) so each <circle> has a deterministic unique key.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 77 - 79, The error message rendering in BranchDetail currently uses an inline style for color on the diffError paragraph; change it to use a semantic CSS class (e.g., replace the inline style with a class like "sc-text-error" alongside "sc-text-muted" or replace "sc-text-muted" entirely) so the color is controlled by stylesheet variables and is more maintainable; update the JSX that renders diffError in the BranchDetail component (the <p> that references diffError) and ensure any padding remains via classes (add a utility class if needed) rather than inline style.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchesView.tsx around lines 84 - 99, The remote branch rows in BranchesView (the remoteBranches.map rendering that creates <tr> with key={b.name} and onClick calling setSelectedBranch) lack keyboard accessibility; update the <tr> for remote branches to be focusable and operable via keyboard by adding tabIndex={0}, role="button" (or role="row" with appropriate selection semantics) and an onKeyDown handler that mirrors the onClick behavior (toggle selection when Enter or Space is pressed) and include an ARIA attribute such as aria-pressed or aria-selected tied to selectedBranch === b.name for screen readers; keep the existing onClick and visual selected class (sc-table__row--selected) intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchesView.tsx around lines 33 - 59, The table rows rendered in BranchesView.tsx are only clickable with mouse; update the row element (the <tr> created in localBranches.map) to be keyboard-focusable and operable: add tabIndex={0}, role="button" (or role="row" with aria-selected), and an onKeyDown handler that calls setSelectedBranch(selectedBranch === b.name ? null : b.name) when Enter or Space is pressed; also set an appropriate aria-selected attribute based on selectedBranch and preserve the existing onClick behavior so keyboard and screen-reader users can select branches.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/CICDView.tsx around lines 50 - 55, Extract the inline IIFE date formatting into a small helper (e.g., formatDate) and use optional chaining on run.created_at; replace the IIFE in CICDView.tsx with a call like formatDate(run?.created_at) so formatDate parses the input, checks isNaN(d.getTime()), and returns either d.toLocaleDateString() or '-'—this keeps the rendering concise and relocates the parsing/validation logic to a reusable function.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 40 - 47, handleSync currently sets loading, awaits onSync(id) and always clears loading but doesn't handle errors; wrap the await in a try/catch similar to handleDelete: catch the error from onSync(id), call the same user-visible error reporting used elsewhere (e.g., showToast / processLogger / notify) with a clear message including the error, and then rethrow or return as appropriate; keep setActionLoading(id) before the try and setActionLoading(null) in finally so loading is cleared regardless. Ensure you reference handleSync, setActionLoading, and onSync when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/GitHubUnavailable.tsx around lines 4 - 8, The SVG inside the GitHubUnavailable component (the element wrapped by the div with className "sc-unavailable__icon") is decorative and should be hidden from assistive tech; add aria-hidden="true" to the <svg> element so screen readers skip the icon and avoid redundant announcements.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 37 - 40, Create a proper typed interface (e.g. PRDetail) describing the expected PR response fields (body?: string, html_url?: string, requested_reviewers?: { login: string }[], labels?: { name: string; color: string }[]) and use it for the component state (replace current Record<string, unknown> with PRDetail | null for the detail state), then remove the ad-hoc `as` casts around detail usages (variables like body, htmlUrl, reviewers, labels) so they read directly from detail with optional chaining and defaults.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestsView.tsx around lines 25 - 32, handleFilterChange triggers an async fetch without updating a loading flag, so add and use a loading state (e.g., loading with setLoading) inside handleFilterChange: setLoading(true) before calling fetchPrs(f === 'all' ? 'all' : f), clear previous errors/selection as you already do, then in the fetch promise chain or try/catch/finally ensure setLoading(false) runs after success or failure (and keep the existing setFetchError logic in the catch). Also update the component render to show a loading indicator whenever loading is true so users see feedback while fetchPrs is in-flight.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx around lines 32 - 34, The current reduce that computes latestRun by comparing run.created_at strings (ciRuns.reduce) is fragile; convert the created_at values to numeric timestamps (e.g., new Date(run.created_at).getTime()) for comparison inside the reducer so you compare numbers not strings, and handle invalid dates by falling back to 0 or the original string comparison to avoid NaN. Replace the string comparison in the reducer with timestamp-based comparison using new Date(...).getTime().

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 174 - 180, The Sync button currently disables via actionLoading.has(wt.id) but doesn't change its label; update the button in WorktreesView.tsx to mirror Delete's UX by rendering conditional text based on actionLoading (e.g., show "Syncing..." when actionLoading.has(wt.id) and "Sync" otherwise) and ensure the onClick still calls handleSync(wt.id) and disabled remains actionLoading.has(wt.id).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/tasks/TaskOverview.tsx around lines 21 - 57, The card definitions in TaskOverview.tsx use className values that no longer match their labels (the cards array with entries keyed 'open','in_progress','review','escalated','closed' currently uses classes like task-overview-card--now/--review/--stuck), causing confusion; update the className for each card in the cards array to semantic names (e.g., task-overview-card--open, task-overview-card--in-progress, task-overview-card--needs-review, task-overview-card--escalated, task-overview-card--closed) or consolidate shared styles intentionally and document that choice—change the className values in the cards array where defined to reflect the label/filterStatus for clearer maintenance.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 138 - 217, The other fetch helpers (fetchBranches, fetchPrs, fetchWorktrees, fetchClones, fetchCiRuns) only log errors but don’t update the shared error state; update each to follow fetchStatus’s pattern: on r.ok set the corresponding state (setBranches/setPrs/setWorktrees/setClones/setCiRuns) and call setError(null), on non-ok call setError(`HTTP ${r.status}: ${r.statusText}`), and in the catch block capture the Error message (e instanceof Error ? e.message : String(e)), call setError(message) and still console.error with the original error; keep the existing buildParams usage and parameter default for fetchPrs.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 401 - 417, The two useEffect blocks that call fetchLocalRef.current() and fetchGitHubRef.current() immediately when projectId changes can produce out-of-order state updates if projectId changes rapidly; wrap each effect call with a per-effect "stale" guard or an AbortController tied to the effect lifecycle (for example: create a local let isStale = false or an AbortController before calling fetchLocalRef.current()/fetchGitHubRef.current(), pass the signal or check isStale in the fetch handlers, and in the effect cleanup set isStale = true or controller.abort()) and ensure the fetch handlers (the functions referenced by fetchLocalRef.current and fetchGitHubRef.current) check the flag/abort signal before committing any state (setIsLoading or other state updates) so results from previous projectId values are ignored.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useTerminal.ts around lines 120 - 121, Update the stale inline comment in useTerminal.ts: where the code checks if event.event === 'agent_started' and (SHOW_MODES as readonly string[]).includes(event.mode || ''), change the comment "Add new agent (embedded or tmux)" to mention the current modes (e.g., "Add new agent (embedded, tmux, or terminal)") or a generic "Add new agent (supported show modes)" so it correctly reflects that SHOW_MODES now includes 'terminal'; keep the rest of the logic untouched.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts at line 176, The hardcoded onnxWASMBasePath value in the useVoice hook (onnxWASMBasePath: '<https://cdn.jsdelivr.net/npm/onnxruntime-web@1.24.1/dist/>') creates an external runtime dependency; change the initialization to first prefer bundled/local WASM assets (bundle the onnxruntime-web dist files into the app and point onnxWASMBasePath to that local path) and add robust error handling around the ONNX runtime initialization within useVoice (catch load/init failures, attempt a fallback to a bundled path if the CDN fails, and surface a clear degraded-state flag or user-facing error) so voice features degrade gracefully when the CDN is unreachable.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/index.css around lines 2459 - 2475, Add a keyboard focus affordance for the mobile drawer button by defining a :focus-visible rule for .mobile-drawer-action (e.g., visible outline or box-shadow and ensure background/text colors remain accessible); update the .mobile-drawer-action CSS to include a .mobile-drawer-action:focus-visible selector that applies a clear focus indicator consistent with other controls and preserves existing hover/active styles and border radius.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/source-control.css around lines 832 - 835, Replace the hardcoded hex colors in the diff status rules by introducing semantic CSS variables and using them in the classes; define variables like --status-added, --status-modified, --status-deleted, --status-renamed (e.g., in :root or a theme selector) and update .sc-diff__file-status--A, .sc-diff__file-status--M, .sc-diff__file-status--D, .sc-diff__file-status--R to use var(--status-...) so themes can override those values later.
