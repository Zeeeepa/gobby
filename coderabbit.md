 Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 292 - 312, Add a CHECK constraint on the party_approval_gates table to enforce that
  approved_by/approved_at and rejected_by/rejected_at are mutually exclusive and consistent with the status column: reference the
  party_approval_gates table and the columns status, approved_by, approved_at, rejected_by, rejected_at and add a CHECK that allows
  only (status='approved' with approved_*set and rejected_* NULL), (status='rejected' with rejected_*set and approved_* NULL), or
  (status IN ('pending','waiting') with both approved_*and rejected_* NULL); apply this constraint in the CREATE TABLE definition
  (or ALTER TABLE if modifying an existing table) so the database enforces the invariant.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 166 - 198, The schema lacks enforcement of visibility timeouts so stale claims in
  party_work_queue won't auto-release; update the model and queries to enforce party_queue_config.visibility_timeout_seconds by (1)
  adding a computed column or stored value on party_work_queue (e.g., timeout_at derived from claimed_at +
  visibility_timeout_seconds when an item is claimed) or persist visibility expiry on claim, (2) adding a background cleanup/cron
  query that sets status='available' and clears claimed_by_member_id where status='claimed' AND timeout_at < current time, and/or
  (3) changing the claim query logic used by your claim function(s) to exclude records where status='claimed' AND claimed_at +
  visibility_timeout_seconds > now so only non-expired claims are considered available; locate changes around the party_work_queue
  table definition and the claim/reclaim code paths that reference claimed_at, status, claimed_by_member_id and
  party_queue_config.visibility_timeout_seconds to implement the chosen approach.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 264 - 278, The approval_gates mapping uses edge-style string keys like
  "developer->qa" (approval_gates) which is ambiguous if a role name contains "->"; update the schema to a structured representation
   (e.g., convert approval_gates to a sequence of objects with from_role and to_role fields, including message and auto_approve_by)
  and migrate existing keys (e.g., "developer->qa") into objects, or alternatively add and enforce a validation rule that role names
   cannot contain the substring "->" and document this constraint; adjust any parsing/serialization logic that reads approval_gates
  to accept the new nested format (from_role/to_role) or the validated string-key format accordingly.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 333 - 336, Update the gate_rejected documentation to explicitly describe the
  rejection cascade algorithm: specify using a graph traversal (BFS or DFS) starting at the rejected node (to_role) to collect
  transitive dependents, detail how to mark those nodes blocked, and define "no path to completion" as a reachability check from any
   non-blocked start nodes to all terminal/goal nodes (describe checking for at least one path to each terminal node); include
  time/space complexity (O(V+E) for traversal and reachability checks), note performance implications for large DAGs and recommend
  async/background execution if necessary, and add concise pseudocode or references to standard graph algorithms to make the
  behavior unambiguous (refer to gate_rejected, to_role, transitive dependents, and party viability checks).

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 516 - 517, Update the section describing "Original leader resurrects" to specify a
  safe deactivation protocol for the old leader: when detecting a leader_session_id mismatch the leader must first mark its
  session/state as "deposed" (preventing any new leader operations), then either wait for in-flight operations (e.g., spawn_member,
  approve_gate) to complete or explicitly roll them back/abort, and only after that fully deactivate the leader workflow;
  alternatively document that all leader operations (spawn_member, approve_gate, etc.) are idempotent and safe to abandon
  mid-execution or that transaction isolation will be used to prevent partial writes; also add a note about using
  trigger_leader_recovery or human intervention if leader_recovery is not configured and how in-flight operations are expected to be
   handled in that scenario.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 401 - 405, The leader transition has a race between updating
  parties.leader_session_id and sending the leader_changed P2P message which can let tool calls (e.g., gobby-party tool invocations)
   validate against stale cached values; fix by ensuring leader validation is done against the authoritative DB at call time (read
  parties.leader_session_id inside the tool call path instead of using cached session IDs), or implement a two‑phase handover in the
   recovery flow: call a method to mark the old leader as "deposed", then atomically update parties.leader_session_id to the new
  leader, then emit the leader_changed broadcast; alternatively document/ensure tool operations are idempotent and tolerant of
  eventual consistency if you choose not to change validation.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 235 - 238, Clarify the semantics in the "Composition with On-Demand" section: state
  explicitly whether spawn_mode: on_demand provides a spawn context to newly spawned agents in addition to queue items (i.e., agents
   receive both a one-time spawn_context and continuous work_queue items), whether upstream outputs are auto-published to work_queue
   (explicitly yes/no), and how agents should prioritize/handle both sources (e.g., process spawn_context first then poll/claim
  work_queue items or handle both concurrently). Update the paragraph around "A role can use BOTH: `spawn_mode: on_demand` +
  `work_queue`" to describe the chosen behavior and add a short concrete example or pseudocode showing an agent handler that reads
  spawn_context (from on_demand) and then loops claiming messages from `work_queue` (or alternately interleaves), referencing the
  terms spawn_mode: on_demand, spawn_context, work_queue, and role so readers can locate the change.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 389 - 398, The current leader recovery design passes a potentially large context
  snapshot as step_variables (including parties, party_members, party_approval_gates, computed DAG state); to avoid huge JSON
  payloads, change the workflow to NOT pass the full snapshot: either (A) remove the heavy step_variables and have the recovery
  workflow’s on_enter call get_party_status(party_id) immediately to load live state, or (B) reduce step_variables to a minimal
  payload (party_id, recovery_reason, leader_session_id, recovery_count/timestamp) and fetch everything else via queries
  (party_members, party_approval_gates, computed DAG) when needed; if you must keep any snapshot, document the size/party-size
  limits and restrict snapshot fields to only critical values (e.g., leader_session_id, crash counts) referenced by the recovery
  logic.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 30 - 36, The design saves upstream outputs into the unstructured
  party_members.outputs_json and then spawns on_demand roles expecting keys like variables.upstream_branch, which risks
  missing-field runtime failures; add a per-role expected-outputs schema registry and validate outputs against that schema when
  harvesting/storing (the code path that reads/stores outputs into party_members.outputs_json) and again before spawning on_demand
  instances (the logic that checks spawn_mode: on_demand and activates workflows), persist validation results or errors alongside
  outputs, and surface clear error messages if required fields are absent so downstream workflows or the spawn flow can fail fast
  with actionable diagnostics.

- Verify each finding against the current code and only fix it if needed.

  In @docs/plans/party-time-p2.md around lines 72 - 81, The UNIQUE(party_id, triggered_by_member_id, target_role) constraint
  prevents multiple queue entries from the same upstream member and conflicts with the intended queueing model; decide whether
  repeated completions should dedupe (overwrite) or queue independently, then update the party_pending_spawns schema accordingly: if
   dedupe is intended, remove triggered_by_member_id from the UNIQUE clause (make UNIQUE(party_id, target_role)); if queuing each
  completion is intended, add a sequence/timestamp/nonce column (e.g., spawn_seq INTEGER or occurrence_id TEXT) and include it in
  the UNIQUE key (or omit UNIQUE altogether) so multiple rows per (party_id, triggered_by_member_id, target_role) are allowed;
  update any insertion/upsert logic in code that relies on the previous UNIQUE behavior (functions interacting with
  party_pending_spawns) to match the chosen approach.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/cli/utils.py around lines 390 - 393, The import from gobby.runner_maintenance (write_shutdown_source) is inside the
  loop that signals each daemon (where proc.send_signal is called); move the line "from gobby.runner_maintenance import
  write_shutdown_source" out of the loop (e.g., to the top of the function or module) so the function is imported once, then keep
  calling write_shutdown_source("cli_kill_all") and proc.send_signal(signal.SIGTERM) inside the loop.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/hooks/event_handlers/_session.py around lines 459 - 460, The reassignment loop currently requires
  task_handoff.get("task_claimed") to be truthy which prevents re-linking when only claimed_tasks exist; change the condition in the
   handoff logic (the block referencing task_handoff and claimed_tasks in the session event handler) to check claimed_tasks directly
   (e.g., if claimed_tasks:) and run the for claimed_id in claimed_tasks: loop unconditionally when claimed_tasks is non-empty so
  claimed tasks are always re-assigned/re-linked during handoff; ensure claimed_tasks is treated safely if None (use truthy check or
   explicit list/default) and remove or stop relying on task_handoff.get("task_claimed") for this reassignment.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/hooks/event_handlers/_session.py around lines 405 - 434, The SESSION_START path currently blocks up to 90s by
  calling summary_event.wait(timeout=max_wait_s) after invoking _dispatch_session_summaries_fn (summary_event, max_wait_s,
  dispatched) which delays activation; instead, make summary dispatch non-blocking: invoke_dispatch_session_summaries_fn as you do
  but do not call summary_event.wait on the main thread — either (A) start a short-lived daemon/background thread or schedule a
  background task that waits on summary_event and logs timeout/debug info, or (B) remove the wait entirely and make max_wait_s
  configurable (reduce default) if you must poll; ensure the parent re-read (parent = self._session_storage.get(parent_session_id))
  happens immediately so SESSION_START proceeds, and keep existing try/except around _dispatch_session_summaries_fn to log
  exceptions.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/hooks/hook_manager.py around lines 764 - 827, The scheduling path in_dispatch_session_summaries can create a task
  via loop.create_task(coro) without guaranteeing done_event is set if the task fails to start or is dropped; update
  _dispatch_session_summaries so that after creating the task (the result of loop.create_task(coro)) you attach a completion
  callback that sets done_event (e.g., task.add_done_callback(lambda_: done_event.set()) if done_event is not None) to ensure
  done_event is always signaled when the task finishes or errors; also keep the existing exception handlers for
  asyncio.run_coroutine_threadsafe and asyncio.run paths unchanged.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/llm/claude_executor.py around lines 276 - 303, The current check skips assigning total_cost when
  result_msg.total_cost_usd is 0.0 because it uses a truthiness test; update the cost-extraction logic in the api_key branch (the
  block creating CostInfo) to use safe attribute access (e.g., getattr(result_msg, "total_cost_usd", None)) and explicitly check for
   None so zero costs are captured, and likewise use getattr(result_msg, "usage", None) or .get on usage only after confirming usage
   is not None; then populate CostInfo (used below in AgentResult) with those values so zero-cost responses are recorded.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/llm/gemini_executor.py around lines 44 - 68, In GeminiExecutor.__init__, validate that when auth_mode == "api_key"
  an api_key is provided and non-empty; if not, raise a clear ValueError (or TypeError) describing the missing api_key so callers
  fail fast instead of letting_get_client receive None; update any docstring/comments accordingly and ensure the validation
  references the auth_mode and api_key attributes so it's obvious where the check occurs.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/llm/openai_executor.py around lines 45 - 63, The __init__ method in OpenAIExecutor lacks an explicit return type;
  add the annotation "-> None" to the OpenAIExecutor.__init__ signature so it reads as a constructor returning None, keeping the
  existing parameters (default_model, api_key, api_base) and preserving the body that sets self.default_model, self.api_key,
  self.api_base, self.logger, and self._client.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/llm/openai_executor.py around lines 116 - 118, Replace the mutable list turns_counter = [0] with an integer variable
   (e.g., turns_used = 0) in the outer scope and, inside the timeout handler closure that currently mutates turns_counter, declare
  nonlocal turns_used and update that integer instead of modifying a list element; adjust any references to turns_counter[0] to
  turns_used and ensure increments and reads use the new nonlocal variable so the closure updates propagate correctly.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/llm/openai_executor.py around lines 152 - 161, Replace the eager f-string logging with lazy/structured logging: in
  the exception handler inside the OpenAI executor (where self.logger.error currently uses f"OpenAI API error: {e}"), change it to
  self.logger.error("OpenAI API error: %s", e, exc_info=True) and include any relevant context via the logger's structured fields if
   available; do the same for the other occurrence referenced (the second self.logger.error), and leave the AgentResult.error value
  as a simple str(e) or formatted string computed separately (not inside the logger call) so logging formatting is deferred and
  exception info is captured.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/llm/openai_executor.py around lines 84 - 102, In_convert_tools, avoid mutating ToolSchema.input_schema by replacing
   the shallow copy with a deep copy (e.g., use copy.deepcopy) when creating params so nested structures like properties aren't
  shared; import copy and set params = copy.deepcopy(tool.input_schema) before adding the default "type" key and building the OpenAI
   function dict in the_convert_tools method.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/mcp_proxy/tools/sessions/_handoff.py around lines 166 - 175, The code only sets summary_result["send_result"] when
  send_content is non-empty, leaving callers without an explicit status when to_session is requested but no content exists; update
  the block around session_manager.get(...) so that summary_result["send_result"] is always set: if send_content is present call
  summary_result["send_result"] = _send_to_peer(session.id, to_session, send_content), else set summary_result["send_result"] to an
  explicit failure/empty indicator (e.g., False or a descriptive dict/message) so callers can unambiguously detect the no-content
  case; reference session_manager.get, send_content, summary_result["send_result"], and_send_to_peer when making the change.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/runner_maintenance.py around lines 172 - 175, The_get_gobby_home() helper in runner_maintenance.py duplicates the
  logic of get_gobby_home() in cli/utils.py; create a single shared function (e.g., get_gobby_home in a new or existing gobby.paths
  module) that reads GOBBY_HOME and falls back to Path.home() / ".gobby", then replace the local _get_gobby_home() with an import
  from gobby.paths and update any callers (e.g.,_get_gobby_home and cli/utils.py:get_gobby_home) to use the shared get_gobby_home
  to avoid drift.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/runner_maintenance.py around lines 210 - 226, Change the stack-trace log inside_make_handler->handle_shutdown from
  INFO to DEBUG so normal shutdowns keep a concise INFO-level notification while the full traceback is available when debugging;
  leave the initial logger.info call that records the received signal and the logger.info("Shutdown source: %s",
  read_shutdown_source()) and the shutdown_callback() unchanged, but replace the logger.info("Stack at signal receipt:\n%s",
  "".join(traceback.format_stack())) call with a logger.debug call that includes the same traceback content.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/servers/routes/admin/_lifecycle.py around lines 101 - 107, The inline write of shutdown_source.json duplicates the
  centralized marker logic; replace it by calling the shared utility write_shutdown_source from gobby.runner_maintenance (or, if
  import overhead is unacceptable, keep the inline write but add a clear comment explaining the intentional divergence), i.e.,
  locate the inline block that writes shutdown_source.json and either (a) import and invoke
  write_shutdown_source(source="http_restart", sender_pid=os.getpid(), timestamp=time.time()) from gobby.runner_maintenance, or (b)
  add a top-line comment above the block stating why the inline implementation is used and note that the format must remain
  consistent with write_shutdown_source to avoid maintenance drift.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/servers/routes/admin/_lifecycle.py around lines 96 - 107, Remove the redundant second import of the json module from
   the restarter script's imports: keep a single import json in the top-level import statement (import os, sys, time, signal,
  subprocess, json) and delete the duplicate import json later in the file so the module is only imported once.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/sessions/analyzer.py around lines 103 - 104, The assignment relevant_turns = turns in the "Analyze Recent Activity"
  step currently processes every turn which can be expensive for very long sessions; update the comment around that line (in the
  function/method handling analysis, referencing relevant_turns and turns) to document the performance implications and rationale:
  state that full-turn analysis is intentional for accurate handoff context and warn that for extremely long sessions this may need
  optimisation or a configurable window; include a TODO or config note suggesting adding a max-history/window parameter if
  performance becomes an issue.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/sessions/lifecycle.py at line 286, The hardcoded output_path="~/.gobby/session_summaries" should be replaced with a
  configurable value; update the call that sets output_path (the parameter named output_path in this module/function in
  src/gobby/sessions/lifecycle.py) to read from a shared config constant or helper (e.g., Config.SESSION_SUMMARY_DIR or a
  get_summary_dir() function) and ensure you expand the user home (~) with os.path.expanduser before using it; if no existing config
   key exists, add a constant like SESSION_SUMMARY_DIR in the project's config module and use that instead so all summary output
  paths are consistent.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/sessions/summarize.py around lines 26 - 39, The Protocol methods currently use broad Any return types which weakens
  type safety; update SessionManagerProtocol.get, update_compact_markdown, update_summary, and update_status to use the concrete
  return types (e.g., Session, UpdateResult, or None/str as appropriate) and change LLMServiceProtocol.get_default_provider to
  return the concrete Provider type by importing those concrete classes under TYPE_CHECKING and referencing them in the annotations
  (from typing import TYPE_CHECKING; if TYPE_CHECKING: from ... import Session, Provider, UpdateResult) so runtime imports are
  avoided while IDEs and mypy get precise types.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/sessions/summarize.py around lines 278 - 282, The two functions _generate_full_summary and_generate_compact_summary
   handle a missing prompt template differently; update _generate_full_summary to mirror_generate_compact_summary by returning an
  error tuple instead of raising FileNotFoundError: catch the missing-template case where prompt_template is falsy and return (None,
   "Missing prompt template: handoff/session_end") (or similar error object used across the module) so both functions consistently
  return (result, error) tuples; ensure any callers that expect the tuple are preserved.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/sessions/summarize.py around lines 195 - 202, The _read_transcript function currently calls json.loads on every
  non-empty line and will raise json.JSONDecodeError for any malformed JSON; wrap the json.loads call inside a try/except that
  catches json.JSONDecodeError, log or warn (including the path and the offending line or line index) and skip that line instead of
  letting the exception bubble up, then continue appending valid parsed objects to turns; ensure the function still returns the list
   turns unchanged and reference the async function name _read_transcript, the local variable turns, and the use of aiofiles.open
  when adding the error handling.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/sync/memories.py around lines 401 - 449, The merge currently keys on mutable "content" which lets edited memories
  create orphaned file entries and uses synchronous open()/JSON I/O; change this method to async and perform file I/O with an async
  library (e.g., aiofiles), build existing_by_id and db_by_id maps keyed by memory id (use data.get("id") when reading JSONL and
  fallback safely if missing), then merge by id (db entries override file entries for the same id) and write back asynchronously;
  also update calls inside this function to await self.memory_manager.list_memories (and any other awaited helpers like
  self._deduplicate_memories/_sanitize_content if made async) so the whole flow is async and authoritative by id rather than
  content.

- Verify each finding against the current code and only fix it if needed.

  In @src/gobby/workflows/observers.py around lines 164 - 169, The try/except around resolving the display ref for a task (the call
  to task_manager.get_task and access to task_obj.seq_num that sets ref) currently swallows all exceptions; replace the bare
  except/pass with structured logging that records the exception and the task_id context (e.g., except Exception as e:
  logger.exception or logger.debug with exc_info and include {"task_id": task_id} in the log) while keeping the fallback behavior
  (leave ref as task_id if seq_num unavailable).

- Verify each finding against the current code and only fix it if needed.

  In @tests/llm/test_gemini_executor.py around lines 164 - 170, The fixture function executor currently uses a forward-ref string
  annotation "GeminiExecutor" while importing GeminiExecutor inside the function; change the annotation to avoid the
  forward-reference by either (1) importing GeminiExecutor under TYPE_CHECKING at module level and using a real type hint, or (2)
  replace the return/type annotation with typing.Any (e.g., Annotate executor as -> Any) since the client is mocked; update the
  import/annotation references to GeminiExecutor and executor to keep intent clear.

- Verify each finding against the current code and only fix it if needed.

  In @tests/mcp_proxy/tools/test_claim_task.py around lines 440 - 441, Add an assertion that verifies the mapped ref value for the
  claimed task in merged_vars: after the existing checks on merged_vars["task_claimed"] and presence of sample_task.id, assert that
  merged_vars["claimed_tasks"].get(sample_task.id) == sample_task.ref (or the expected ref literal if the test uses a fixed string
  like "#99") so the test validates both key presence and correct ref mapping.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/components/canvas/CanvasPanelHeader.tsx around lines 20 - 30, The SVG inside the Button in CanvasPanelHeader.tsx is
  missing a <title>, so add a concise title element inside that SVG (e.g., "Close Canvas") to improve accessibility; update the SVG
  element rendered by the Button (the JSX block with onClick={onClose} and aria-label="Close Canvas") to include the <title> as the
  first child so assistive tech that parses the SVG directly will get a human-readable label.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/components/rules/ExpressionBuilder.tsx around lines 212 - 213, The ExpressionBuilder input currently reuses CSS
  classes from RuleEditForm (the .rule-edit-input and .rule-edit-mono classes referenced in
  web/src/components/rules/ExpressionBuilder.tsx), creating an implicit coupling; either add equivalent class definitions to
  ExpressionBuilder.css and update ExpressionBuilder.tsx to import that CSS, or explicitly document the dependency in the component
  comment/readme so consumers know RuleEditForm.css must be present—update the component to import the new ExpressionBuilder.css or
  add a short note in the component header pointing to RuleEditForm.css.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/components/rules/ExpressionBuilder.tsx at line 88, The numeric literal check in the conditional that also references
  trimmed and SPECIAL_LITERALS uses /^\d+(\.\d+)*$/ which matches version-like strings (e.g., "1.2.3") instead of standard decimals;
   update that part of the expression in ExpressionBuilder (the conditional using trimmed and SPECIAL_LITERALS) to use
  /^\d+(\.\d+)?$/ to allow an optional single fractional part for decimals (or explicitly keep the original only if version-style
  numbers are intended), ensuring the regex replacement occurs where /^\d+(\.\d+)*$/ is currently used.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/components/rules/RuleEditForm.css around lines 343 - 346, Replace the hardcoded color in the .rule-edit-required rule
  with a CSS variable to support theming; update the declaration to use var(--color-error, #ef4444) (keeping #ef4444 as the
  fallback) so the required indicator follows the design system while preserving the current color when the variable is not set.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/components/rules/RuleEditForm.tsx at line 824, The onBlur handler in RuleEditForm currently uses setTimeout(() =>
  setAddingArg(false), 150) which can race and isn't cleared on unmount; replace this pattern by using the blur event's
  relatedTarget (or event.nativeEvent.relatedTarget) to detect if focus moved into the dropdown/option and only close when focus
  left to an external element, or if you must use a timer, store the timer id in a ref (e.g., addingArgTimeoutRef) and clear it on
  subsequent focus/blur and in a useEffect cleanup to avoid leaks; update the onBlur/onFocus handlers and ensure setAddingArg(false)
   is only called after verifying focus did not move to a valid option and clear the ref on unmount.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/components/rules/RuleEditForm.tsx around lines 598 - 615, The fetchToolSchema call inside the useEffect lacks error
  handling, so failures are swallowed and the UI can hang; update the effect (referencing useEffect, selectedServer, selectedTool,
  fetchToolSchema, setSchema, setLoadingSchema, cancelled) to handle errors by adding a .catch handler (or using async/await with
  try/catch) that, when not cancelled, sets an error-visible state (or clears schema via setSchema(null)) and ensures
  setLoadingSchema(false) runs; also log or surface the error (e.g., via console.error or a user-facing toast) so failures are
  visible to the user.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/components/rules/RuleEditForm.tsx around lines 103 - 110, In RuleEditForm.tsx inside the useEffect hook, refactor the
  long single-line fetch chain (fetch("/api/rules/tags", { signal: controller.signal })...catch(...)) into clearer steps: either
  create an inner async function (e.g., async function loadTags()) or split .then handlers onto separate lines so the
  response.json(), setKnownTags/setTagsError, and the .catch block are each on their own lines; preserve the AbortController usage
  and the aborted-signal check in the catch block and keep the state updates (setKnownTags, setTagsError) and console.error logic
  intact for error cases.

- Verify each finding against the current code and only fix it if needed.

  In @web/src/hooks/useChat.ts around lines 755 - 767, The merge currently preserves local-only messages (messagesRef.current) that
  are missing from the server-mapped list, so server-side deletions remain locally visible; update the logic in the re-attach block
  (referencing viewingSessionIdRef.current, messagesRef.current, mapped, mappedById, merged, newMsgs, and setMessages) to treat the
  server response as authoritative by filtering out any local messages whose ids are not present in mapped (i.e., build existingIds
  from mapped, merge updates from mappedById into any overlapping local messages, then append truly new mapped messages), and
  simplify the condition that decides to call setMessages by using newMsgs.length > 0 || merged differs from mapped (or simply
  always call setMessages with the filtered/merged result when viewingSessionIdRef.current === sid) so deletions on the server are
  reflected locally.

- Verify each finding against the current code and only fix it if needed.

  In @tests/cli/test_cli_utils.py around lines 521 - 530, The test block around kill_all_gobby_daemons is deeply nested; replace the
   six-level nested with statements (patch.dict, patch("psutil.process_iter"), patch("gobby.cli.utils.load_config"),
  patch("os.getpid"), patch("os.getppid")) with a single parenthesized multi-line with statement to compose context managers for
  readability, keeping the same patched targets and return values (mock_proc, mock_config.return_value.daemon_port/websocket.port,
  os.getpid/os.getppid) and leaving the assertions for result == 1 and mock_proc.send_signal.assert_called_with(signal.SIGTERM)
  unchanged.
