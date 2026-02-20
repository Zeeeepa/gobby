Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl at line 201, The exported memories contain user-specific absolute paths and usernames; update and use the existing _sanitize_content() function (in src/gobby/sync/memories.py) to normalize/scrub filesystem paths before committing/serializing memories by replacing home-directory patterns (/Users/<user>, /home/<user>, ~/..., /private/...) with a neutral token like '~' or '<redacted>' and ensure every code path that writes memory exports or the JSONL (where entries like the one shown are produced) calls _sanitize_content() for the record's content and any path-like fields; add tests or a small normalization regex set to catch common variants (~/, /Users/, /home/, /private/tmp/, Windows C:\ paths) and apply it to the memory export flow.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl at line 378, The memory JSONL contains garbled/truncated records (e.g., id "495f0b9e-df23-5eec-8605-ee6341ec8dd6") that must be removed or re-ingested with correct content; locate those entries by their ids and either delete them from the JSONL or replace them with a validated, clean record. Add a validation step in the code path that appends to the JSONL (the function responsible for writing/flush operations) to detect and reject partial/corrupted writes—validate JSON parseability, required fields (id, content, type, created_at) and content length, and only append after successful validation and fsync/atomic write. Also add a small repair script or CLI command that scans the file, reports malformed lines, and offers safe removal/re-ingest.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 305 - 306, The data-payload parsing in CanvasRenderer currently uses JSON.parse in a try/catch but lacks protection against JSON bombs; add a depth-check before accepting parsed payloads by implementing a validatePayloadDepth(obj, maxDepth=10) helper and calling it immediately after JSON.parse(payloadStr) (or better, wrap parse+validate together), rejecting and logging a warning if validation fails; reference the data-payload handling in CanvasRenderer and the new validatePayloadDepth function so reviewers can locate and test the change.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 144 - 145, The resolve_interaction call lacks synchronization and can race; update canvas_registry.resolve_interaction to use a per-canvas asyncio.Lock (e.g., add a_canvas_locks dict) and wrap the lookup-and-update in an async with lock block so the sequence is atomic: fetch canvas from_pending_canvases, check canvas.completed (or canvas_state.completed), raise if already completed, otherwise set completed=True and store interaction_result, and then set any pending_event; reference resolve_interaction, canvas_registry, _canvas_locks, _pending_canvases, and canvas.completed in your change.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 13, Update the "How does it work across CLIs?" section to explicitly document multi-tab behavior: state that render_canvas broadcasts the canvas to all open tabs, that locking ensures the first interaction wins (mention the locking mechanism by name if applicable), and that other tabs must listen for the canvas_event with event: "completed" to reconcile/refresh their UI; also note how race conditions are handled (lock acquisition and rejection path) and that secondary interactions should be ignored or result in a UI update via the canvas_event so all tabs remain consistent.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 90, Clarify and implement sweeper lifecycle: start the background canvas sweeper when the WebSocket server lifespan begins, store the asyncio.Task reference in the server state so only one task exists, and cancel/await that task on server shutdown; implement the sweeper loop as _canvas_sweeper(registry, shutdown_event) that checks shutdown_event.is_set(), wraps registry.sweep_expired() in try/except (logging errors) and awaits asyncio.sleep(60) between runs, and ensure render_canvas still performs a lazy sweep fallback and enforces the early size check (len(content.encode('utf-8')) vs MAX_CANVAS_SIZE) and conversation/count/rate limits (MAX_CANVASES_PER_CONVERSATION) before sanitization.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 268 - 269, Add a concrete canvas_event handler in the WebSocket message handling section (e.g., in useChat.ts) that listens for msg.type === 'canvas_event' and, when msg.event === 'interaction_confirmed', invokes the existing clearCanvasRevertTimeout(msg.canvas_id) to cancel any pending revert and calls updateCanvasStatus(msg.canvas_id, 'completed') to persistently mark the canvas done; ensure the case branch is added to the switch/if that processes incoming WS messages and that both functions are imported/accessible in that scope.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 256 - 261, The optimistic-revert pattern using updateCanvasStatus(canvasId, 'completed') and the revertTimeout setTimeout(..., 5000) creates a confusing UX—change to a three-state flow: call updateCanvasStatus(canvasId, 'pending') when interaction is sent, show a loading indicator for the pending state, then on server success call updateCanvasStatus(canvasId, 'completed') and clear the pending timeout (clearTimeout(revertTimeout)); on server failure or when the timeout expires call updateCanvasStatus(canvasId, 'active') and surface an explicit error message instead of silently reverting. Ensure the timeout logic is tied to the 'pending' state and that transitions only move to 'completed' on real confirmation.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 184 - 192, The sanitizeCanvasHtml function is incomplete; implement post-processing by parsing the DOMPurify result into a DOM (e.g., DOMParser), then remove any inline CSS properties listed in FORBIDDEN_CSS_PROPERTIES from elements with a style attribute (parse style declarations, drop forbidden keys, and reserialize), and validate href/src attributes on elements by testing their values against the existing ALLOWED_URI_REGEXP (or ALLOWED_URI_SCHEMES) and removing or blanking attributes that don't match; finally serialize the sanitized DOM back to string and return it. Reference sanitizeCanvasHtml, FORBIDDEN_CSS_PROPERTIES, ALLOWED_TAGS/ALLOWED_ATTRS, and ALLOWED_URI_REGEXP when locating where to add the DOM parsing, style-cleaning, and URL validation logic (or alternatively use DOMPurify hooks to strip forbidden styles and validate URIs).

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 15, Add explicit WebSocket disconnection handling so blocking canvas interactions don't hang: detect disconnect in the WebSocket lifecycle handler (e.g., on_disconnect) and call into the canvas registry (e.g.,_canvas_registry.cancel_conversation_canvases) to cancel any pending canvases for that conversation; for each pending canvas object (look for fields like pending_event, completed, interaction_result, conversation_id) mark it completed, set an error interaction_result (e.g., {"error":"websocket_disconnected"}) and set/trigger its pending_event to wake the awaiting asyncio.Event used by the AskUserQuestion/blocking canvas code path so the agent receives an immediate error instead of waiting for timeout.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 212, The doc incorrectly states a 16KB limit for data-payload validation while the spec defines MAX_CANVAS_SIZE = 64KB; update the text to either standardize the limit or clarify the relationship (e.g., state that data-payload is a subset of the canvas and thus must be <= MAX_CANVAS_SIZE) so the values are consistent—refer to the `data-payload` validation sentence and the `MAX_CANVAS_SIZE` constant in the document and change the 16KB value to match or add a short explanatory note linking the two limits.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 62, The render_canvas implementation must explicitly validate and clamp the timeout parameter; inside the render_canvas function clamp timeout to the 1–3600 range (e.g., timeout = max(1, min(3600, timeout))) before any blocking wait logic, ensure that this clamped timeout is used when waiting on the asyncio.Event and when returning or logging timeouts, and document the behavior alongside other validations (HTML sanitization, raw byte size vs MAX_CANVAS_SIZE, CanvasState storage and broadcasting via canvas_event with event:"rendered") so callers and tests rely on the enforced limit.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 128 - 130, Add recursive depth validation for nested structures: implement a helper like validate_payload_depth(obj, max_depth=10, current_depth=0) that returns False if current_depth exceeds max_depth and recursively checks dict values and list elements, then call it in the same handler after the existing isinstance checks (where payload and form_data are validated) to reject too-deep nesting; if validation fails, call self._send_error(websocket, "payload or form_data too deeply nested") and return. Ensure the helper is referenced from the handler so functions/methods named validate_payload_depth and _send_error are used consistently.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 87, Specify and implement a sliding-window rate limiter for MAX_RENDER_RATE: add a per-conversation timestamp store (e.g., CanvasState._render_timestamps mapping conversation_id -> list[datetime]) and implement a check_rate_limit(conversation_id: str) that prunes timestamps older than now - 1 minute, rejects if len >= MAX_RENDER_RATE, otherwise appends now and returns allowed; ensure the check is used where renders are scheduled/invoked (e.g., render/dispatch methods) and make the timestamp update atomic/thread-safe if concurrency is possible.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 209, The delegated click handler that walks up from e.target to find the closest `[data-action]` with a hard limit of 20 levels is insufficient for DoS protection; update the handler (the delegated click logic that references `e.target` and `[data-action]`) to enforce a maximum number of nodes inspected per traversal (e.g., cap total nodes checked across all ancestor/sibling checks), wrap the entire handler in a short execution timeout (abort further work if exceeded), and add a per-canvas rate limiter (token bucket or sliding window keyed by canvas id) to limit rapid repeated invocations; ensure these checks short-circuit before executing action handlers and log/ignore events when limits are hit.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 139, The registry spec is missing the get_canvas API used by the handler; add a public method signature and description for get_canvas to the registry specification so canvas_registry.get_canvas(canvas_id) is documented and returns CanvasState | None; update the registry docs/spec to include get_canvas(self, canvas_id: str) -> CanvasState | None with a brief docstring "Retrieve canvas state by ID, or None if not found" and note it returns self._pending_canvases.get(canvas_id) as the expected behavior so callers like the handler at canvas_registry.get_canvas(canvas_id) are covered.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 85 - 86, Add server-wide resource limits by introducing constants like MAX_TOTAL_CANVASES (e.g., 1000) and MAX_CANVASES_PER_USER alongside the existing MAX_CANVASES_PER_CONVERSATION and MAX_CANVAS_SIZE, then enforce them at canvas creation and conversation-creation points (e.g., in functions that create or add canvases such as create_canvas/add_canvas_to_conversation) by checking current global canvas count and per-user canvas count before allowing a new canvas and returning an appropriate error; additionally, implement a simple memory budget check (compute current canvases × MAX_CANVAS_SIZE per conversation and refuse new canvases when it would exceed a configured per-conversation or global memory cap) and add metrics/atomic counters to track total and per-user canvas counts for accurate enforcement.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 286, Add concrete implementation guidance: inject synthetic canvas messages at the interaction handling entrypoint (implement an injectSyntheticMessage call inside the existing canvas interaction handler function, e.g., handleCanvasInteraction or CanvasController.handleEvent) so they enter the same pipeline as user input; persist them via the same storage API but with a clear discriminator in the message record (store { source: 'canvas', canvas_id, metadata: { action, timestamp } } on the Message object saved by MessageStore.save or MessageRepository.create and include a boolean flag like isSynthetic) and ensure logging uses that discriminator (e.g., Logger.info(..., { source, canvas_id, isSynthetic })) so they are distinguishable from real users; finally, append synthetic messages to the agent conversation history when calling ConversationService.appendMessage or ConversationContext.addMessage but treat them differently in agent logic (e.g., mark as non-authoritative or lower-priority) and ensure sanitization and rate-limiting happen in injectSyntheticMessage before persistence.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 332 - 346, The audit logging currently emits structured events via logger.info ("canvas_rendered", "canvas_interaction", "canvas_expired") but lacks operational metrics; add metric emissions alongside those log calls: emit a gauge named canvas_active_count when canvases are created/removed, increment a counter canvas_render_total in the same place as the "canvas_rendered" log, record interaction latency with a histogram/summary canvas_interaction_latency_seconds around the code that handles actions (paired with the "canvas_interaction" log), increment a counter canvas_expiration_total with the "canvas_expired" log, and increment a labeled counter canvas_error_total by error_type where errors are logged—ensure metrics include labels for canvas_id, conversation_id, action/error_type to aid filtering and use the existing metrics client or provider used by the service.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 181, The FORBIDDEN_CSS_PROPERTIES constant currently lists only five properties and should be expanded to a comprehensive set to prevent UI redressing/clickjacking and performance exploits; update the FORBIDDEN_CSS_PROPERTIES array (the const named FORBIDDEN_CSS_PROPERTIES) to include additional properties such as transform, filter, backdrop-filter, mix-blend-mode, clip-path, mask, animation, transition, height, width, overflow, position-related aliases, zIndex variants, pointer-events, cursor, isolation, contain, will-change, backface-visibility, perspective, and any other presentation/compositing properties your security policy requires, ensuring you use the same identifier (FORBIDDEN_CSS_PROPERTIES) and export/consume it where needed so the new list is applied consistently throughout the codebase.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 137 - 142, The ownership check is using an untrusted client-provided value (data.get("conversation_id")) to compare against canvas_state.conversation_id; change it to derive the conversation id from the authenticated WebSocket/session state (e.g., use self._conversation_id or the session store) instead of data.get("conversation_id"), then perform the check on canvas_registry.get_canvas(canvas_id) => canvas_state.conversation_id and call self._send_error(websocket, ...) if they differ; remove or ignore the client-supplied conversation_id to prevent spoofing.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 62, Update the plan for render_canvas to specify the Python HTML sanitization library: recommend using nh3 (Rust-backed ammonia) for server-side allowlist sanitization in new 2026 projects; replace any mention of Bleach with nh3 and explicitly state that render_canvas(content: str, ...) must use nh3 to strip <script> tags, remove on* event handlers, and neutralize javascript: URIs before storing CanvasState and broadcasting canvas_event; keep the existing notes about validating raw byte size against MAX_CANVAS_SIZE, clamping timeout, blocking behavior, and the return payload shape ({canvas_id, interaction: ...} or {canvas_id, status: "rendered"}).

- Verify each finding against the current code and only fix it if needed.

In @pyproject.toml at line 35, The pyproject.toml currently pulls croniter (croniter>=6.0.0) which is marked unmaintained and may be unpublished after 2025-03-15 and its 6.x changes (timezone handling in timestamp_to_datetime and epoch behavior on non-UTC/32-bit systems) can change runtime behavior; update dependency management by either pinning to a vetted safe version or replacing croniter with a maintained alternative or vendoring a fork, add targeted unit/integration tests exercising timestamp_to_datetime and epoch calculations across timezones and 32-bit/64-bit environments, and add a CI check and a repository note/issue tracking the migration plan (also keep claude-agent-sdk>=0.1.39 as-is if no changes needed).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/lifecycle_monitor.py at line 60, Replace the f-string logging in AgentLifecycleMonitor with structured logging that passes the interval as context; locate the logger.info call in the AgentLifecycleMonitor (the line using f"AgentLifecycleMonitor started (interval={self._check_interval}s)") and change it to log a static message (e.g. "AgentLifecycleMonitor started") while supplying self._check_interval (and optionally the unit "s") as structured data/keyword argument so downstream log processors can parse the interval field.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/lifecycle_monitor.py around lines 107 - 108, Replace the runtime assert on tmux_name with an explicit check: after reading tmux_name = agent.tmux_session_name, test "if tmux_name is None" and raise a clear exception (e.g., ValueError or RuntimeError) or handle the error path (log and continue) instead of using assert; update the code in lifecycle_monitor.py where tmux_name and agent.tmux_session_name are used to ensure deterministic runtime validation and clear error messaging.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/lifecycle_monitor.py around lines 82 - 88, Replace the broad "except Exception as e" block in lifecycle_monitor.py (the try/except around the agent lifecycle check that currently calls logger.error) with a more specific and informative handler: either catch specific expected error types (e.g., RuntimeError, OSError) or, if you must catch all exceptions for this background loop, use logger.exception(...) to log the full traceback and exception type; keep the existing asyncio.CancelledError handling for the await asyncio.sleep(self._check_interval) loop intact so cancellation continues to be handled separately.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/spawn.py around lines 411 - 419, The code generates agent_run_id and writes it to session metadata (agent_run_id, session_manager.update_terminal_pickup_metadata) but never creates the corresponding agent_runs DB record; add a call after generating agent_run_id to create the agent_runs record (e.g., via the existing agent_runs/agent_run manager or DB client) with fields session_id=child_session.id, agent_run_id, workflow_name, initial status (e.g., "created"/"pending") and any owner/creator info, and handle/log errors similar to other spawn functions (mirror what prepare_gemini_spawn_with_preflight does) so the metadata and DB are in sync.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/spawn.py around lines 164 - 170, Replace the ad-hoc _logging.getLogger call and_pts_logger usage with the module-level logger variable named logger (defined as logger = logging.getLogger(__name__)), and change the f-string log to use structured logging with context parameters—for example, call logger.info("Creating agent_run %s for child_session %s", agent_run_id, child_session.id) or use logger.info(..., extra={"agent_run_id": agent_run_id, "child_session_id": child_session.id}) in the prepare_terminal_spawn code where_pts_logger and the f-string are currently used.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/app_context.py around lines 194 - 196, Replace the broad "except Exception as e" in the lazy PipelineExecutor creation with specific exception types to follow guidelines: catch (ImportError, ValueError, TypeError, OSError) as e instead, keeping the same_logger.warning call and return None behavior; locate the except block that logs "Failed to lazily create PipelineExecutor" in the lazy creation routine (the code that imports/constructs PipelineExecutor) and update the exception clause to the specific tuple of exceptions.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/installers/git_hooks.py around lines 87 - 93, The grep invocations that check git diff output are using regular-expression matching for the patterns ".gobby/tasks.jsonl" and ".gobby/tasks_meta.json", so change those grep calls to use fixed-string matching (add the -F flag) to avoid treating the dot as a regex metacharacter; update both occurrences of grep -q "\.gobby/tasks.jsonl" and grep -q "\.gobby/tasks_meta.json" to grep -F -q with the same string literals so the script reliably matches the exact paths before running git add.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/session_coordinator.py around lines 416 - 419, Replace the bare "except Exception as e:" in the tmux capture-pane fallback with specific subprocess-related exceptions (e.g., subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) so you only catch expected failures; update the except clause to "except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:" (ensure subprocess is imported) and keep the existing self.logger.debug message that references tmux_session_name and e.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/session_coordinator.py around lines 389 - 392, Replace the broad "except Exception as e" in the inter_session_messages fallback with a specific database exception (e.g., "except sqlite3.Error as e") to match the pattern used elsewhere (line ~366) and avoid catching unrelated errors; ensure "sqlite3" is imported at the module top if not already, and keep the existing self.logger.debug(...) call to log the error details.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/agents/researcher.yaml around lines 64 - 69, The on_mcp_error handler currently unconditionally sets the variable parent_notified to true via the send_to_parent tool (server: gobby-agents, tool: send_to_parent, action: set_variable, variable: parent_notified), which masks failures; change the flow so send_to_parent is attempted with retry logic (e.g., 3 attempts with backoff) and only set parent_notified to true on a confirmed success response, and on final failure emit/log an explicit error action or set a separate variable (e.g., parent_notification_error) or call an alternate notify_partial_failure action so the system can surface the communication failure instead of transitioning to shutdown silently.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/prompts/expansion/system.md at line 122, The Markdown example currently escapes the shell pipe in the string "No test files removed: `git diff --name-only HEAD~1 \| grep -v test`", which prevents the command from running; remove the backslash before the pipe so the command reads with a normal pipe operator (i.e., use `git diff --name-only HEAD~1 | grep -v test`) in the file and update the string in src/gobby/install/shared/prompts/expansion/system.md accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/workflows/session-lifecycle.yaml around lines 259 - 272, The Pre-Existing Error/Warning/Failure policy text is duplicated between the inject_context action in on_session_start and on_before_agent; remove the duplicate and extract the policy into a single reusable template or variable (e.g., define a top-level template name like "pre_existing_policy" or a workflow variable) and reference it from both inject_context actions (those using action: inject_context and the when condition variables.get('_session_initialized')). Update both occurrences to include or reference that single template by name so the policy text is maintained in one place.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/workflows/session-lifecycle.yaml around lines 147 - 154, Duplicate session context template used in the inject_context actions under on_session_start and on_before_agent should be consolidated: create a YAML anchor or reusable named template (e.g.,_session_context_template or session_context_template) containing the current template body (referencing session.seq_num, session.id, session.external_id, session.source) and replace the inline template values in the inject_context entries (the actions named inject_context in on_session_start and on_before_agent) with a reference to that anchor/template so both places use template: *session_context_template (or the named template reference) to remove duplication.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/claude_streaming.py at line 90, The default model value uses the invalid alias "opus"; update the default for the model parameter (the `model` argument in src/gobby/llm/claude_streaming.py) to a valid Claude SDK model identifier such as "claude-opus-4-6" or "claude-opus-4-20250514" (or read the value from config/ENV) so API calls use a supported model name instead of the shorthand "opus".

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/litellm_executor.py around lines 35 - 56, Update the MODEL_ALIASES mapping to use the canonical, timestamped Anthropic model IDs and keep resolve_model_alias as-is; specifically replace the "sonnet" and "haiku" values in MODEL_ALIASES with the full snapshot IDs (e.g., the current API shows claude-sonnet-4-5-20250929 and claude-haiku-4-5-20251001) so resolve_model_alias("sonnet") and resolve_model_alias("haiku") return the verified full model strings while leaving "opus" unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/registries.py around lines 278 - 279, The catch-all "except Exception as e" used when creating the CloneGitManager should be narrowed to the same specific exceptions used earlier to follow the project's guideline; replace the broad except in the CloneGitManager creation block with the specific tuple (TypeError, OSError, RuntimeError) (the same pattern used in the prior block around lines 196-201) and keep the existing logger.warning(f"Failed to create CloneGitManager: {e}") behaviour so only those expected exceptions are caught and logged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/server.py around lines 103 - 142, The_resolve_and_set_project_context function currently uses bare excepts, shadows the json import, and has an overly generic return type; update it to catch specific exceptions (e.g., catch ImportError/LookupError around LocalProjectManager creation/get calls, and catch OSError and json.JSONDecodeError when reading/parsing project_file), remove the local alias import and use the module-level json, and tighten the signature/return annotation from Any to Optional[object] (or a more specific ContextToken type if available) while still returning the result of set_project_context(ctx) or set_project_context({"id": session.project_id}) as before. Ensure references: _resolve_and_set_project_context, set_project_context, LocalProjectManager, project_file, and json.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/agents.py around lines 293 - 307, The code uses blocking subprocess.run inside an async context (the tmux cleanup that references tmux_session_name, tmux_cfg/TmuxConfig, result["tmux_session_killed"], and logger), which can block the event loop; replace it with an async implementation—either spawn the command with asyncio.create_subprocess_exec and await its completion (collect stdout/stderr and set result["tmux_session_killed"] on success) and wrap with asyncio.wait_for for timeout, or run subprocess.run in a separate thread via loop.run_in_executor to avoid blocking; ensure exceptions are caught and logged using the existing logger and preserve the current behavior of setting result["tmux_session_killed"] only on success.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/memory.py around lines 536 - 553, The logger.warning call inside the inner except should use %-style formatting to avoid eager f-string evaluation: change logger.warning(f"Crossref failed for {memory.id}: {e}") to logger.warning("Crossref failed for %s: %s", memory.id, e) (optionally include exc_info=True if stacktrace is desired) in the block that handles exceptions from memory_manager.rebuild_crossrefs_for_memory so the message is lazily formatted.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/memory.py around lines 573 - 599, The logger call inside the memory extraction loop uses an f-string; change it to %-style formatting and include exception info: replace the f-string in the except block that references logger.warning for KG extraction failures (while handling memory_manager.kg_service and calling kg.add_to_graph) with a call like logger.warning("KG extraction failed for %s: %s", memory.id, e, exc_info=True) so the message uses % placeholders and the traceback is logged; keep the same increment of errors and existing control flow (including the asyncio.sleep throttle).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/pipelines/__init__.py around lines 176 - 201, Extract the repeated session/project resolution into a helper named_resolve_session_and_project(session_id) that returns a tuple (resolved_id, project_id) and raises ValueError for invalid session_id or KeyError (or a distinct exception) when the session is not found; then replace the duplicated blocks in_run_pipeline and_execute_pipeline to call this helper and convert those exceptions into the existing error return shapes (e.g., {"success": False, "error": ...}) so behavior remains identical while centralizing logic.

-

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/worktrees.py around lines 124 - 143, The ValueError raised by WorktreeGitManager(resolved_path) is caught but the returned error string drops the exception message; update the except block to capture the exception (e.g., except ValueError as e) and include its message in the returned error text so callers get the original context (referencing WorktreeGitManager, _git_manager_cache and get_project_context in the same block).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/memory/vectorstore.py around lines 69 - 77, Replace the direct client access and assert with a call to the class helper to preserve consistent error handling: call self._ensure_client() to obtain the client (instead of using client = self._client; assert client is not None), then use that client to call collection_exists and create_collection with self._collection_name and VectorParams(size=self._embedding_dim, distance=Distance.COSINE); this keeps behavior identical but returns the clearer RuntimeError from_ensure_client() when the client is missing.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py around lines 797 - 807, The code lazily imports gobby.conductor.pricing.litellm and calls_llm.get_model_info inside the hot streaming path (context_window derivation), causing unnecessary overhead; refactor by moving the import of litellm to module scope (or otherwise cache the imported module) and cache model info per model (e.g., a dict keyed by self._last_model) so context_window is looked up from the cache instead of calling get_model_info on every ResultMessage; update the logic around context_window, self._last_model, and get_model_info to consult the cache first and only call get_model_info once per new model, retaining the existing exception handling for compatibility.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/memory.py around lines 190 - 196, The current code builds memory_ids then calls server.memory_manager.storage.get_all_crossrefs(...) and filters in Python (variables: memory_ids, get_all_crossrefs, crossrefs), which can be slow for large datasets; modify the storage layer to add a method like get_crossrefs_for_memories(project_id, memory_ids, limit, ...) and call that from this route so the filtering (source_id/target_id in memory_ids) happens at the database level in server.memory_manager.storage instead of in-memory in the route.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/projects.py at line 18, The delete protection gap is that HIDDEN_PROJECT_NAMES includes "_global" but SYSTEM_PROJECT_NAMES does not, so delete_project still allows removing it; update the SYSTEM_PROJECT_NAMES constant in src/gobby/storage/projects.py to include "_global" (same token used in HIDDEN_PROJECT_NAMES) so that functions relying on SYSTEM_PROJECT_NAMES (e.g., delete_project) will correctly block deletion of the _global project.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/sessions.py around lines 671 - 677, Remove the redundant initial lookup: delete the call to server.session_manager.get(session_id) and the associated if-check that raises 404; instead call server.session_manager.update_title(session_id, title) directly and keep the existing result None check that raises HTTPException(status_code=404, detail="Session not found"). Ensure you remove the unused local variable session so the route only relies on update_title's return value to determine existence.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/sessions.py around lines 660 - 679, The rename_session endpoint is missing the timing metric in its JSON response; match synthesize_session_title by capturing a start timestamp (e.g., time.perf_counter()) at the top of rename_session (before metrics.inc_counter or the work), compute elapsed_ms after update_title completes, and include "response_time_ms": <elapsed_ms> in the returned dict along with "status" and "title"; ensure time is imported and use the same units/rounding as synthesize_session_title for consistency and any existing metrics usage (refer to rename_session, synthesize_session_title, metrics.inc_counter, and server.session_manager.update_title).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 102 - 104, Replace f-string log calls that embed variables (e.g., logger.debug(f"Failed to resolve project {project_id}: {e}")) with structured, lazy logging: call logger.debug("Failed to resolve project %s", project_id, exc_info=e or True, extra={"project_id": project_id}) or use extra fields like extra={"project_id": project_id, "error": str(e)} so the message and context remain structured and evaluated lazily; do this for all occurrences of logger.debug using f-strings (including the handlers that catch exceptions and reference variables like project_id or e) and ensure exceptions are captured with exc_info=True or exc_info=e for full stack context.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 133 - 135, The current except Exception blocks (e.g., around the GitHub MCP call that logs with logger.warning and raises HTTPException(502, ...), and the similar blocks at the other noted locations) are too broad; replace them with narrow catches for the expected failures (for example catch requests.exceptions.RequestException for HTTP/MCP calls, subprocess.CalledProcessError (or the specific git library exception you use) for git command failures, and OSError/shutil.Error for worktree deletion/filesystem errors), log the error and raise HTTPException(502, ...) from the caught exception, and let any other unexpected exceptions propagate (re-raise) instead of being swallowed; apply the same change to the other occurrences at the referenced spots (lines ~295-296 and ~612-613) keeping the existing logger.warning/HTTPException behavior for only these specific exception types.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/tmux.py around lines 103 - 114, The except block around session enumeration currently swallows all errors; change it to "except Exception as e:" and emit a debug-level log with context (e.g. using self.logger.debug or the module logger) including the exception info before continuing so the fallback remains but failures are visible for troubleshooting; update the block referencing session_mgr/session_manager, the list() call, and gs.terminal_context to log a message like "failed to enumerate active Gobby sessions" with exc_info=True.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/voice.py around lines 91 - 99, The code in _get_or_connect_tts reads the private attribute tts._connected from ElevenLabsTTS, creating tight coupling; add a public property (e.g., is_connected) to ElevenLabsTTS that returns the connection state, update ElevenLabsTTS to expose that property instead of relying on _connected, and then change_get_or_connect_tts to call tts.is_connected (or the new public method) when checking connection before returning or popping entries from self._tts_sessions keyed by conversation_id.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sessions/manager.py around lines 397 - 410, The method update_terminal_pickup_metadata should mirror the class's error-handling pattern: wrap the call to self._storage.update_terminal_pickup_metadata in a try/except Exception as e block, log the exception with contextual fields (session_id, agent_run_id, workflow_name) using the class logger (e.g., self._logger.error(..., exc_info=True) similar to update_session_status), and then re-raise the exception so callers still see the error; keep the same return value on success.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/voice/stt.py at line 115, The call sets initial_prompt=self._config.whisper_prompt or None which is redundant if whisper_prompt already defaults to None; replace it with initial_prompt=self._config.whisper_prompt (i.e., remove the "or None") where the parameter is passed so the value is used directly; look for the code passing initial_prompt and update that invocation (referencing initial_prompt and self._config.whisper_prompt) to simplify the expression.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/engine.py around lines 164 - 176, The info log is outside the template-rendering failure branch and can incorrectly report that a variable was set even when rendering failed; update the code in engine.py around the exception handling for template rendering (the block that references state.variables, handler_type, variable, value, server_name, tool_name, and logger) so that the logger.info call that logs "handler set {variable}={value} (triggered by {server_name}/{tool_name})" is moved inside the else branch where state.variables[variable] = value happens, ensuring the log only runs when the assignment actually succeeds.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/observers.py around lines 100 - 175, The new observer log lines use f-strings (e.g., logger.info(f"Session {state.session_id}: ..."), logger.warning(...), logger.debug(...)) which breaks structured logging; replace them with structured logging calls that pass context as fields (use logger.info("Session event: task_claimed=false (detected close_task success)", extra={"session_id": state.session_id, "inner_tool": inner_tool_name}) or the logger's supported keyword-field form) and do the same for all other messages in this block (the warnings about unresolved raw_task_id, the debug skip message, the info setting task_claimed/claming, and the auto-link success/failure) so that session_id, inner_tool_name, task_id/claimed_task_id and any error info are provided as separate structured fields instead of interpolated into f-strings; update logger calls in the same block and the other referenced blocks (around the later log instances) accordingly.

-

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_pipeline_background_cleanup.py around lines 17 - 22, The fixture _clear_background_tasks uses yield but declares a None return type; change its signature to a generator type (e.g., def_clear_background_tasks() -> Generator[None, None, None] or -> Iterator[None]) and add the corresponding import from typing (Generator or Iterator) at the top of the test file so pytest understands the fixture is a generator fixture while keeping the body (_background_tasks.clear(), yield, _background_tasks.clear()) unchanged.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_pipeline_background_cleanup.py around lines 64 - 79, The test test_cleanup_handles_errored_tasks is using a timing-dependent await asyncio.sleep(0.01) to let the _fail task error; replace that with a deterministic yield or explicit await: either await asyncio.sleep(0) to yield control before calling cleanup_background_tasks(), or explicitly await the created task (task) inside a try/except to consume its exception prior to calling cleanup_background_tasks(); update references to_background_tasks and cleanup_background_tasks accordingly so the task is removed deterministically.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_worktrees_coverage.py around lines 513 - 522, Remove the redundant "from unittest.mock import patch" duplicate imports in the test file: locate the two extra import statements that re-import patch near the tests that call patch("gobby.mcp_proxy.tools.worktrees.get_project_context", ...) (used around the _resolve_project_context assertions) and delete them so only the top-of-file import remains; ensure the tests still reference patch as before and run.

- Verify each finding against the current code and only fix it if needed.

In @tests/servers/test_http_pipelines.py around lines 281 - 298, The duplicated mock setup in the mock_execution_manager fixture used by TestPipelinesApproveEndpoint and TestPipelinesRejectEndpoint should be extracted into a shared factory or module-level fixture: create a single helper (e.g., make_mock_execution_manager or a module-scoped pytest fixture) that builds and returns the configured MagicMock (set get_step_by_approval_token to return mock_step and get_execution to return a PipelineExecution with ExecutionStatus.RUNNING), then replace the duplicate mock_execution_manager definitions in both test classes to call or depend on that shared helper; ensure references to PipelineExecution and ExecutionStatus remain the same so behavior is unchanged.

- Verify each finding against the current code and only fix it if needed.

In @tests/test_app_context.py around lines 12 - 21, Add an explicit return type hint to the helper function _make_container: annotate it to return ServiceContainer (e.g. def _make_container(...) -> ServiceContainer) and ensure ServiceContainer is imported or referenced with its correct name so the test module type checks; keep the existing body unchanged.

- Verify each finding against the current code and only fix it if needed.

In @tests/workflows/test_observers_detection.py around lines 78 - 92, Remove the dead fixture make_before_agent_event: delete the entire fixture function (the def make_before_agent_event() factory and its nested _make) since it is never used; references to HookEvent, HookEventType.BEFORE_AGENT and SessionSource.CLAUDE inside that fixture can be removed along with it to clean up unused test code.

- Verify each finding against the current code and only fix it if needed.

In @web/scripts/copy-vad-assets.cjs around lines 13 - 26, The loop that copies files (iterating FILES and using SRC_DIR/DEST_DIR and fs.copyFileSync) doesn't ensure the destination directory exists, causing ENOENT failures; before calling fs.copyFileSync for each file, ensure the target directory (parent of dest) is created (e.g., check path.dirname(dest) and create it with fs.mkdirSync(dir, { recursive: true }) or equivalent) so copyFileSync succeeds even on a fresh clone; keep error handling and logging as-is.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConfigurationPage.tsx around lines 13 - 25, isSecretField currently does case-sensitive comparisons and will miss variants like "API_Key" or "Password"; modify isSecretField so it normalizes inputs to lowercase before checking: convert the incoming path to lowercase, map secretKeys to lowercase (or compare against a lowercased set), and ensure SECRET_PATTERNS are treated/literalized in lowercase when running the .includes/.some checks; update the comparisons in isSecretField (and any callers relying on it) to use the lowercased values so secret detection becomes case-insensitive.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConversationPicker.tsx around lines 48 - 52, The useState initializer in ConversationPicker reads localStorage directly (isPinned and isOpen) which breaks SSR; change initialization to safe defaults (e.g., const [isPinned, setIsPinned] = useState(true) and const [isOpen, setIsOpen] = useState(true)) and then on client mount (useEffect with no deps) read localStorage if typeof window !== 'undefined' and call setIsPinned(saved === 'true') and setIsOpen(...) as needed; also persist changes to localStorage in effects or event handlers that call setIsPinned so all reads happen only on the client and SSR no longer accesses localStorage.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConversationPicker.tsx around lines 293 - 304, The current useEffect in ConversationPicker updates uptime every second even when minutes/hours precision would suffice; change the implementation (startTime, setUptime, update) to use a dynamic scheduling strategy: replace the fixed setInterval with a recursive setTimeout (or adjust interval length) that computes elapsed inside update and chooses the next delay (e.g., 1s while showing seconds, 30s–60s when showing minutes, 60s+ when showing hours), reschedules itself after each run, and ensures cleanup by clearing the timeout in the effect's return; this reduces unnecessary updates while retaining correct rollovers between seconds/minutes/hours.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/GitHubPage.tsx around lines 73 - 93, The tab buttons rendered from TABS do not expose selection state to assistive tech; in the button inside the TABS.map (the element using activeTab, setActiveTab, sc and className "sc-page__tab") add an aria-selected attribute set to {activeTab === tab.key} (i.e. aria-selected={activeTab === tab.key}) so the currently active tab is communicated to screen readers; ensure the value updates when setActiveTab is called and leave the existing disabled behavior intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/GitHubPage.tsx around lines 95 - 149, Extract the large object-literal used for tab switching into a helper function (e.g., renderTabContent) to improve readability and avoid embedding a complex object directly inside JSX; the helper should accept no args (or activeTab) and return the correct component for keys "overview", "branches", "prs", "worktrees", "clones", and "cicd" using a switch or lookup, returning null by default, and the JSX should then render {sc.isLoading && !sc.status ? <div className="sc-page__loading">Loading...</div> : renderTabContent()} while keeping references to sc, activeTab, SourceControlOverview, BranchesView, PullRequestsView, WorktreesView, ClonesView, and CICDView intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryPage.tsx around lines 12 - 17, DEFAULT_KNOWLEDGE_GRAPH_LIMIT is currently equal to KNOWLEDGE_LIMIT_MAX (5000), preventing users from increasing the value in the UI; update the constant DEFAULT_KNOWLEDGE_GRAPH_LIMIT to a value below KNOWLEDGE_LIMIT_MAX (e.g., 2500 or another sensible default) in MemoryPage.tsx so the UI control can increase it, or if the default intentionally should be the max, add an inline comment next to DEFAULT_KNOWLEDGE_GRAPH_LIMIT explaining that behavior; reference the symbols DEFAULT_KNOWLEDGE_GRAPH_LIMIT and KNOWLEDGE_LIMIT_MAX when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryPage.tsx around lines 105 - 119, The fetch in the useEffect (the AbortController + fetch('/api/config/values') block) can throw when calling res.json() on a malformed OK response; change the response handling to safely attempt parsing JSON (e.g., await res.text() then try JSON.parse or wrap res.json() in try/catch) and fall back to logging the parse error and returning null instead of letting the exception bubble; ensure you still respect res.ok, preserve the AbortError check in the .catch block, and only call setMemoryGraphLimit/setKnowledgeGraphLimit when parsed JSON yields numeric values.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MobileSessionDrawer.tsx around lines 31 - 55, The header div in MobileSessionDrawer acts as a toggle but lacks the aria-expanded attribute; update the header element (the div with className "mobile-chat-drawer-header" and onClick toggling isOpen) to include aria-expanded={isOpen} so screen readers are informed of the drawer state, ensure the attribute value uses the isOpen boolean and preserve the existing onClick, role (if added) and other props.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SessionDetail.tsx around lines 274 - 286, The dropdown menu in SessionDetail lacks keyboard navigation; add an onKeyDown handler on the dropdown container (the element that renders the buttons like the Resume Session button) to handle ArrowDown/ArrowUp to move focus between menu items, Enter/Space to activate the focused item (invoke the same callbacks like onContinueInChat(session)), and Escape to close the menu (call setDropdownOpen(false)). Implement focus management using refs (e.g., an array of refs for each menu item or a focusIndex state) and useEffect to focus the first item when the dropdown opens; ensure each button has tabIndex={-1} when managing focus programmatically and still supports click activation and the existing disabled/hasMessages logic.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/Settings.tsx around lines 73 - 86, The theme buttons in the Settings component need an aria-pressed attribute to indicate their toggle state; update the button elements rendered in the map (the ones with className "theme-option" and onClick handler onThemeChange) to include aria-pressed={settings.theme === t} so the active state is exposed to assistive tech and stays in sync when onThemeChange updates settings.theme.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/TerminalsPage.tsx around lines 568 - 571, The PID display currently uses a truthy check (`{panePid && (...)}`) which will hide legitimate PID 0; update the conditional to explicitly check for null/undefined (e.g., `panePid != null`) so PID 0 renders correctly. Locate the JSX around `displayName`, `sessionName`, and `panePid` (the span with className "session-pid") and replace the truthy guard with an explicit null/undefined check to ensure only absent PIDs are hidden.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/TerminalsPage.tsx around lines 98 - 112, The memoized values attachedDisplayName and attachedPid currently read attachedSocketRef.current but don't include it in their dependency arrays, causing stale results when the socket changes; fix this by deriving the current socket into a stable value (e.g., const attachedSocket = attachedSocketRef.current or track it in state when the attached socket changes) and then replace attachedSocketRef.current references with that derived attachedSocket and include attachedSocket in the dependency arrays for useMemo, ensuring the lookups against terminalNames and sessions recompute when the socket or attachedSession changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/TerminalsPage.tsx around lines 197 - 205, The onCreate prop is being passed an inline arrow (() => createSession()) which creates a new function on every render and can break memoization in MobileTerminalDrawer; fix this by passing the stable createSession reference directly (onCreate={createSession}) or wrap createSession in a useCallback and pass that (e.g., memoizedCreateSession) so the prop identity is stable; update the MobileTerminalDrawer prop usage to use the memoized function and ensure the useCallback dependency list includes only the dependencies required by createSession.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.css around lines 344 - 368, Add an explicit keyboard focus style for the icon buttons by defining a :focus and/or :focus-visible rule for .workflows-action-icon (and a matching variant for .workflows-action-icon--danger) so the focus state mirrors the hover styles (visible background, text color and border-color) and is consistently visible for keyboard users; ensure to preserve existing transitions and use the same color tokens/hex values used in the hover rules.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 730 - 735, Add a visible keyboard shortcut hint to the modal UI to indicate that Cmd/Ctrl+S will trigger the editor save: update the modal header or footer where CodeMirrorEditor is used to render a small hint (e.g., "Save (Cmd/Ctrl+S)") next to the Save button or inline with the title; ensure the hint is tied to the same save action passed as onSave to CodeMirrorEditor (handleSave) so the text matches behavior and consider using a simple platform-detection helper to show "Cmd+S" on macOS and "Ctrl+S" elsewhere for clarity.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 157 - 176, handleYamlSave currently only type-checks optional fields and allows missing essential fields like name and steps; update it so parsed must include a non-empty string name and a non-empty array steps before calling updateWorkflow. Specifically, in handleYamlSave validate that parsed.name exists and is a trimmed non-empty string (don’t fall back to yamlEditorWf.name) and that parsed.steps exists and is an array with at least one element; return/throw clear validation errors if those checks fail, and only then call updateWorkflow with name, description (optional) and definition_json from parsed. Ensure you use the existing variables/functions (yamlEditorWf, yamlContent, parsed, updateWorkflow) and keep the JSON.stringify(parsed) behavior for definition_json.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 140 - 155, handleYamlEdit can apply stale YAML when switching workflows quickly; modify it to track the in-flight request (e.g., using a ref like currentExportIdRef or an AbortController) so responses are ignored if they don't match the latest requested workflow ID. Specifically, when handleYamlEdit starts, generate/assign a unique fetch id and setYamlEditorWf(wf); after awaiting exportYaml(wf.id) check that the stored fetch id still matches before calling setYamlContent, setYamlEditorWf(null) or window.alert; also only clear/set yamlLoading for the matching fetch to avoid hiding loading state for a newer request. Update references in handleYamlEdit to use the ref/id check around sets for setYamlContent, setYamlEditorWf and setYamlLoading, and cancel/ignore stale results.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 107 - 130, handleFilesSelected currently assumes reader.result is a valid data URL and may extract an invalid base64 string; update the reader.onload handler in handleFilesSelected to first verify reader.result is a string and matches a data-URL-with-base64 pattern (e.g. /^data:[^;]+;base64,/) before splitting; only set base64 when that check passes (const base64 = matched ? result.split[','](1) : null), otherwise log a warning including file.name and keep base64 as null (and revoke preview if you decide to skip queuing); reference handleFilesSelected, reader.result, setQueuedFiles and the base64 extraction logic when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatPage.tsx around lines 32 - 34, The provider value object for ArtifactContext is being re-created each render causing extra re-renders; wrap { openCodeAsArtifact } in a stable memoized object (e.g., create artifactContextValue with useMemo depending on openCodeAsArtifact) and pass that memoized object to ArtifactContext.Provider instead of an inline object to avoid recreating the value on every render.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ContextUsageIndicator.tsx around lines 56 - 59, The current ContextUsageIndicator uses the DOM title attribute (title={tooltipLines.join('\n')}) which is not keyboard-accessible; replace it with an accessible tooltip component (or the app's UI library Tooltip) and move tooltipLines into that component's content, ensure the wrapper (ContextUsageIndicator) exposes proper ARIA attributes (e.g., aria-describedby or role="tooltip") and keyboard focusability (tabIndex or wrap with a focusable element) so screen readers and keyboard users can open/read the tooltip; update the JSX around the div with className="flex items-center gap-1.5 text-xs text-muted-foreground" to use the Tooltip component and reference tooltipLines, keeping visual styling but removing the title prop.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ContextUsageIndicator.tsx around lines 60 - 81, The SVG progress indicator is missing ARIA semantics; update the <svg> in ContextUsageIndicator (the element that uses size, radius, strokeWidth, color, circumference, dashOffset) to include accessible attributes: set role="progressbar" and add aria-valuemin="0" aria-valuemax="100" and aria-valuenow computed from the current progress (derive percent from circumference and dashOffset, e.g., percent = 100 * (1 - dashOffset / circumference) and round it), and include either aria-label="Context usage" or aria-labelledby pointing to a visible/visually-hidden label so screen readers understand the indicator. Ensure decorative fallback (aria-hidden="true") is not used if you expose the progress values.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageItem.tsx around lines 37 - 39, Replace the direct DOM manipulation in the image onError handler with React state: add a boolean state (e.g., showLogo) in the MessageItem component initialized true, set showLogo to false in the onError callback for the img, and conditionally render the <img ... /> only when showLogo is true and message.role === 'assistant'; update the img element reference in the JSX and remove the inline style mutation to keep the logic idiomatic and testable.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MobileChatDrawer.tsx around lines 99 - 106, The TrashIcon SVG is decorative and should be hidden from assistive tech; update the TrashIcon component so the <svg> element includes aria-hidden="true" (and optionally focusable="false" for older browsers) to ensure the parent button (title="Delete chat") remains the accessible label; modify the SVG attributes in the TrashIcon function accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MobileChatDrawer.tsx around lines 27 - 38, Add an aria-expanded attribute to the header toggle to expose the drawer state to assistive tech: in the MobileChatDrawer component's interactive div (className "mobile-chat-drawer-header") that uses onClick and onKeyDown and toggles state via setIsOpen, add aria-expanded={isOpen} so screen readers know whether the drawer is open or closed while keeping the existing role="button" and tabIndex={0}.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ModeSelector.tsx around lines 15 - 32, In ModeSelector.tsx, update the radio-like <button> used when mapping CHAT_MODES (the button that checks m.id === mode and calls onModeChange) to include an explicit type attribute and ARIA disabled state: add type="button" to prevent implicit form submissions and add aria-disabled={disabled} alongside the existing disabled prop so screen readers receive the disabled state; keep the existing role="radio", aria-checked, onClick, title, and className logic intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ThinkingBlock.tsx around lines 16 - 38, Add an aria-controls attribute to the interactive div that toggles the thinking panel so screen readers associate the button with the content region: for the div with role="button" (the clickable block using expanded and setExpanded) add aria-controls pointing to the content id used by the Markdown wrapper (the id built from messageId, e.g. `${messageId}-thinking`), ensuring the content container/Markdown keeps that matching id.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 289 - 296, AskUserQuestionCard currently returns null silently when args.questions is missing or not an array; change this to log a helpful debug warning in development builds and still return null for production. In the AskUserQuestionCard function, detect the invalid state of args/questions and call console.warn or a dev-only logger with context (include call.id or call.toolName and the problematic args variable) so developers can see why the component rendered nothing, then continue to return null; keep the runtime behavior unchanged for production by gating the log with process.env.NODE_ENV === 'development' (or the app's dev flag).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 39 - 60, Add a JSDoc block for the parseReadOutput function that documents its expected input format ("<line_number>→<content>" per line), the parameter type (string), the return shape ({ content: string; startLine: number } | null), behavior on malformed lines, and an example input/output; include notes that line numbers are parsed from the first matching line and that empty lines are preserved as blank content. This comment should be placed immediately above the parseReadOutput function declaration to make its contract clear to future readers and callers.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactImageView.tsx around lines 19 - 29, The ArtifactImageView currently only validates the src regex for content and does not handle image load failures; add an onError handler on the <img> in ArtifactImageView that sets a local state flag (e.g., imageError) when the image fails to load, and render a user-friendly fallback (e.g., a <span> with "Failed to load image" or a placeholder) instead of the broken image; use the existing content and zoom props/variables to keep sizing consistent and ensure the fallback is shown when imageError is true.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 61 - 70, Header th elements currently only handle onClick, making header sorting inaccessible via keyboard; update the header rendering (the headers.map block) to make each header interactive by adding tabIndex={0}, role="button" (or using a <button>), and an onKeyDown handler that calls handleSort(i) when Enter or Space is pressed, while preserving the existing onClick and aria-sort state derived from sortCol/sortAsc for screen readers; reference the headers.map, handleSort, sortCol and sortAsc identifiers when making the changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 7 - 31, The parseCSV function currently leaves inQuotes true if a quote is never closed, causing the rest of the input to be consumed into a single cell; update parseCSV to detect this after the main loop (check the inQuotes flag) and handle it defensively: either throw a clear, descriptive error (e.g., "Unclosed quote in CSV input") or implement a fallback that treats the trailing quote as literal (append a closing quote to current or unescape and continue) before pushing current into cells and rows; make the behavior consistent and documented, and ensure any thrown error includes context so callers can handle malformed CSVs (references: function parseCSV, local vars inQuotes, current, cells, rows).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactVersionBar.tsx around lines 42 - 56, The two inline icon components ChevronLeftIcon and ChevronRightIcon should be moved to a shared icons module so they can be reused across the app; create/export these components from a central file (e.g., Icons.tsx or components/icons) and replace the local definitions in ArtifactVersionBar.tsx with imports of ChevronLeftIcon and ChevronRightIcon to ensure consistency and avoid duplication.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/styles.css at line 78, The hover rule .message-content tbody tr:hover uses a near-transparent white overlay that will be invisible in light themes; update styles.css to make the hover theme-aware by replacing the hardcoded rgba(255,255,255,0.02) with a theme variable (e.g. --hover-bg) and/or add a light-theme override for the selector (use [data-theme="light"] .message-content tbody tr:hover to set a subtle dark overlay such as rgba(0,0,0,0.02)); adjust the theme variable definitions accordingly so both light and dark themes show a visible hover.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Button.tsx around lines 37 - 48, The Button component can render an actual <button> which defaults to type="submit"; update the render so when Comp is the native 'button' you ensure a default type of "button" is applied (e.g. pass type={props.type ?? 'button'} only when Comp === 'button') so using Button inside forms won't accidentally submit them; locate the Button functional component (forwardRef, Comp, asChild, Slot) and add the conditional default type when spreading props to the rendered element.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Select.tsx around lines 5 - 8, SelectLabel is currently re-exported directly from SelectPrimitive.Label while SelectTrigger/SelectContent/SelectItem are wrapped with custom styling; create a styled wrapper for SelectPrimitive.Label (e.g., a new SelectLabel component) applying the same design system classes/props used by SelectTrigger/SelectItem and export that instead of the raw re-export. Ensure the new SelectLabel accepts and forwards props/children and retains the original element identity (uses SelectPrimitive.Label under the hood) so existing consumers keep the same API but get consistent visuals.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/Select.tsx around lines 85 - 99, The ChevronDownIcon and CheckIcon are static and should be extracted as constant JSX elements instead of function components to avoid recreating elements on each render; replace the function declarations for ChevronDownIcon and CheckIcon with const ChevronDownIcon = (<svg ...>...</svg>) and const CheckIcon = (<svg ...>...</svg>) (keeping the same attributes and children) and update any usages that call them as components to use the constants directly where they were previously rendered.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/MemorySkillsCard.tsx at line 6, The MemorySkillsCard component currently lacks an explicit return type; update the function signature for MemorySkillsCard to include an explicit JSX.Element return type (e.g., MemorySkillsCard({ memory, skills }: Props): JSX.Element) to improve type safety and clarity, ensuring Props stays as the parameter type and no other implementation changes are made.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/PluginsCard.tsx around lines 1 - 3, Rename the generic interface Props to a more descriptive PluginsCardProps to improve clarity and avoid conflicts; update the interface declaration (interface Props) to interface PluginsCardProps and replace all references/usages of Props within the PluginsCard component (and any exported types or prop annotations) to PluginsCardProps so the component’s prop typing stays consistent.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/SystemHealthCard.tsx around lines 47 - 50, The UI accesses background_tasks.active directly in SystemHealthCard and can render "undefined" or throw if background_tasks is null/undefined; update the render to safely read this value (e.g., use optional chaining or a fallback) by replacing direct uses of background_tasks.active in SystemHealthCard with a null-safe expression such as background_tasks?.active ?? 0 (or an appropriate fallback/placeholder) so the component behaves consistently with the existing null-checked process fields.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/SystemHealthCard.tsx around lines 3 - 12, The formatUptime function can return a fractional seconds value when seconds < 60; to fix, after the null check in formatUptime(seconds: number | null) immediately floor the seconds (e.g., const secs = Math.floor(seconds)) and use that integer variable for the final return and any other comparisons that expect integers so the returned low-second string is like `${secs}s` and display is consistent with other units.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/TasksCard.tsx around lines 9 - 14, SEGMENTS currently uses hardcoded hex strings; replace those hex values with CSS variable references (e.g., '--color-segment-open', '--color-segment-in-progress', '--color-segment-closed', '--color-segment-blocked') so the component uses var(...) for colors. Update the SEGMENTS constant (and any code that reads its color property) to store the CSS variable string like "var(--color-segment-open, #3b82f6)" to preserve a hex fallback, and ensure corresponding CSS variables are defined in the theme (light/dark) so SegmentKey usage continues to work without changing its type.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/TasksCard.tsx around lines 41 - 80, The SVG in TasksCard.tsx (the element using SIZE, rings, total, RADIUS, CIRCUMFERENCE) is missing accessibility metadata; update the <svg> element to include role="img" and an accessible name by adding a <title id={titleId}> describing the chart (e.g., "Tasks distribution") and set aria-labelledby={titleId} (or aria-label if you prefer a short label), and optionally add a <desc> with summary of total and segment meaning; ensure titleId is unique (e.g., derived from component instance) and reference it from the svg so screen readers can announce the chart and its total.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 43 - 60, The handleViewDiff function can start fetches that aren't canceled when branchName changes; modify handleViewDiff to create an AbortController, pass its signal into fetchDiff, and store that controller in a ref (or return it) so the existing useEffect that clears diff/showDiff on branch change can call controller.abort() in its cleanup; also update the catch in handleViewDiff to ignore abort errors (or check error.name === 'AbortError') and avoid setting state after an aborted fetch, and ensure the controller is cleaned up after success/failure.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchesView.tsx at line 40, Extract the duplicated inline onKeyDown handler into a reusable function in the BranchesView component: create a handler factory (e.g., handleRowKeyDown) that accepts a branch name and returns a React.KeyboardEvent handler which checks for 'Enter' or ' ' keys, calls e.preventDefault(), and toggles selection via setSelectedBranch(branchName === selectedBranch ? null : branchName); then replace the two inline handlers on the local and remote branch rows with onKeyDown={handleRowKeyDown(b.name)} to remove duplication and improve readability.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 27 - 50, handleDelete and handleSync only catch thrown exceptions, so when onDelete/onSync resolve to false no error is shown; update both handlers to check the awaited result (const ok = await onDelete(id) / await onSync(id)) and if ok === false setActionError with an appropriate message (e.g., 'Failed to delete clone' / 'Failed to sync clone') before proceeding to finally; keep existing try/catch for thrown errors and ensure setActionLoading and setConfirmDelete behavior (in handleDelete) remain unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 37 - 40, The current code in PullRequestDetail.tsx uses unsafe type assertions for body, htmlUrl, reviewers, and labels which can break if the API shape changes; update each to perform runtime checks instead (e.g., for body and htmlUrl use typeof x === 'string' ? x : '' and for reviewers/labels use Array.isArray(detail?.requested_reviewers) ? detail.requested_reviewers.filter(item => item && typeof item.login === 'string') : [] and similarly for labels filter by objects with name/color strings), or extract small helpers like getStringOrEmpty and getArrayOrEmpty to encapsulate these guards so the component never assumes the API types.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestsView.tsx around lines 72 - 97, The table rows in PullRequestsView are not keyboard-accessible because the clickable <tr> with onClick (using setSelectedPr and selectedPr) can't receive keyboard events; make each row focusable and operable by keyboard by adding tabindex="0", a keyboard handler (onKeyDown) that triggers the same toggle logic as the onClick when Enter or Space are pressed, and include an appropriate ARIA role (e.g., role="button") and aria-selected state tied to selectedPr to communicate selection to assistive tech; ensure the handlers call setSelectedPr(selectedPr === pr.number ? null : pr.number) just like the onClick.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestsView.tsx around lines 26 - 36, handleFilterChange may call setFetchError and setFilterLoading after the component unmounts if fetchPrs is still pending; wrap the async flow to avoid state updates on unmounted components by tracking mounted state or using an AbortController. Modify the component to create a mounted flag (or controller) in the component scope or a useEffect cleanup, pass cancellation into fetchPrs or check the flag before calling setFetchError/setFilterLoading/setSelectedPr, and ensure the cleanup toggles the flag or aborts the request so handleFilterChange only updates state when the component is still mounted. Use the symbols handleFilterChange, fetchPrs, setFetchError, setFilterLoading, setSelectedPr (and the component's useEffect cleanup) to locate where to add the guard.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx around lines 24 - 25, The catch currently only logs errors in SourceControlOverview (the promise chain that calls setRecentCommits), so add an error state (e.g., recentCommitsError via useState) and update it inside the .catch((e) => { if (!cancelled) { setRecentCommitsError(e); console.error(...)} }) so the component can render a subtle UI indicator; update the JSX to show a non-blocking message/icon when recentCommitsError is set and clear the error when a successful fetch updates recent commits (e.g., in the .then branch call setRecentCommitsError(null) or reset it within the fetch function).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useChat.ts around lines 664 - 715, The continueSessionInChat function can apply fetched messages after the user has switched to another conversation, causing a race overwrite; capture the newConversationId (or snapshot conversationIdRef.current) before the fetch and after receiving mapped messages, verify that conversationIdRef.current === newConversationId (or the snapshot) before calling setMessages and saveMessagesForConversation, and optionally use an AbortController for the fetch to cancel it when switching conversations (check/wsRef.current send remains unchanged).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useDashboard.ts around lines 59 - 63, The effect currently calls refresh() then sets an interval that invokes fetchStatus, causing a potential double-fetch on mount because refresh simply wraps fetchStatus; change the effect to call fetchStatus() directly on mount and set the interval to fetchStatus, and use [fetchStatus] as the dependency array (remove refresh) so the initial load and subsequent polling use the same stable function and avoid duplicate or overlapping requests; alternatively, if you must keep refresh in other places, protect against duplicate runs by guarding with a ref that tracks whether the initial load completed before starting the interval (referencing useEffect, refresh, fetchStatus).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSessions.ts around lines 152 - 169, The optimistic update in renameSession updates sessions via setSessions before the network call but only refreshes via fetchSessions on error, leaving the UI showing the new title until fetch completes; change renameSession to capture the previous session title (by reading prevSessions or finding the session by id), perform the optimistic setSessions update, and on any fetch error or non-ok response immediately revert by calling setSessions with the preserved previous title (and still call fetchSessions if you want to re-sync); reference renameSession, setSessions, and fetchSessions when locating where to add the rollback logic.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSettings.ts around lines 13 - 17, The MODEL_OPTIONS array defines a fixed set of valid model values but updateModel currently accepts any string; change this by deriving a union type from MODEL_OPTIONS (e.g. type ModelValue = typeof MODEL_OPTIONS[number]['value']) and narrow updateModel to accept ModelValue (and/or validate at runtime). In updateModel (and the other setters referenced around the same area), check the incoming value against MODEL_OPTIONS.map(o => o.value) and only persist it if it exists (otherwise reject or fallback to a default), and update any related state/usage sites to use the new ModelValue type to prevent invalid values from being stored or propagated.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 138 - 152, fetchStatus clears the global error on success but other fetchers (fetchBranches, fetchWorktrees, etc.) do not, leaving stale errors visible after a later successful fetch; update each fetch function (fetchBranches, fetchWorktrees, and any similar functions) so that when r.ok is true and you set the successful response state you also call setError(null) to clear previous errors (or alternatively introduce per-resource error state if you prefer finer granularity), ensuring consistency with fetchStatus.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 196 - 199, The MicVAD initialization currently points onnxWASMBasePath at a CDN; to harden production, copy the required onnxruntime-web/dist WASM assets into your app's static output (e.g., via vite-plugin-static-copy into /ort-assets/) and change the MicVAD.new configuration's onnxWASMBasePath to the local path (e.g., '/ort-assets/'); additionally wrap the MicVAD.new(...) call in a try-catch around the call in useVoice.ts so you can log the error, surface user-friendly feedback, and provide a fallback path or disable VAD gracefully if loading fails.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 247 - 255, When initializing MicVAD (MicVAD.new) ensure you own and cleanup the MediaStream: call navigator.mediaDevices.getUserMedia yourself before invoking MicVAD.new, pass the acquired stream via the getStream option, implement pauseStream to stop tracks and resumeStream to re-acquire if needed, assign the returned vad to vadRef.current only after successful initialization, and in the catch block stop any acquired stream tracks (stream?.getTracks().forEach(t=>t.stop())) and null out the stream so no microphone tracks leak while still setting setVoiceError and logging the original error.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/index.css around lines 1692 - 1721, Add keyboard focus-visible styles for the interactive theme controls by updating the .theme-option and .theme-option.active rules to include :focus-visible (and :focus where appropriate) so keyboard users get a visible focus ring and contrast analogous to hover/active states; ensure the focus style uses a clear outline or box-shadow with outline-offset and sufficient color contrast against var(--bg-tertiary)/var(--bg-secondary), and apply the same :focus-visible pattern to the session-detail dropdown item selectors referenced elsewhere to match hover/active appearance and maintain accessibility.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/source-control.css around lines 57 - 60, The focus state for .sc-page__project-select:focus currently removes the outline and only changes border color, which is insufficient for keyboard users; update the rule for .sc-page__project-select:focus to replace outline: none with a clear, high-contrast focus indicator (for example add an outline or visible box-shadow and an outline-offset) so the focused element is easily discernible—ensure the new indicator uses accessible color contrast (referencing var(--accent) if desired) and apply it alongside the existing border-color change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/source-control.css around lines 32 - 39, The .sc-page__branch-badge rule is using hardcoded colors (#1e1b4b and #a78bfa) that are repeated elsewhere; define semantic CSS variables (e.g. --color-purple-bg and --color-purple-text) in :root or the shared variables file and replace the literal values in .sc-page__branch-badge and other occurrences (the repeated badge color uses) with those variables to ensure consistency and easier maintenance; update any other selectors referencing the same hex values to use the new variables so colors remain consistent across the stylesheet.

- Verify each finding against the current code and only fix it if needed.

In @web/src/types/chat.ts around lines 12 - 16, CHAT_MODES is currently a mutable array losing literal types; make it readonly and preserve literal id types by declaring the array with "as const" (i.e., convert the export const CHAT_MODES: ChatModeInfo[] = [...] to a const literal with "as const"), then update any dependent types to derive narrowed unions from it (for example use typeof CHAT_MODES[number]["id"] or a ReadonlyArray-based type) so ChatModeInfo and consumers get the stronger, readonly literal types. Ensure references to CHAT_MODES, ChatModeInfo, and any code using mode ids are adjusted to the new readonly/literal types.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/agent_messaging.py around lines 106 - 124, The code instantiates LocalAgentRunManager (agent_run_mgr) but never uses it and directly touches session_manager._db with raw SQL; replace the direct DB access by adding/using a manager API: implement/find a method on LocalAgentRunManager such as find_by_child_session(child_session_id) to locate the latest agent_run row and then call the manager's complete() or a new set_result(agent_run_id, result) method to update the result and timestamp, removing direct use of session_manager._db and deleting the unused agent_run_mgr instantiation if not needed after wiring through the manager.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/workflows/_query.py around lines 266 - 285, The lifecycle_state added to workflows may have variables == None, so update the append logic in the block that calls state_manager.get_state(resolved_session_id) to defensively set variables to an empty dict when None; i.e., when creating the dict to append to workflows (the entry with keys "workflow_name", "enabled", "priority", "current_step", "variables", "source"), replace direct use of lifecycle_state.variables with a safe fallback (lifecycle_state.variables or {}) so downstream code expecting a dict always gets one.
