# Communications Implementation Code Review

**Date**: 2026-03-28
**Epic**: #10940
**Scope**: All communication adapters (Slack, Telegram, Discord, Teams, Email, SMS) and shared infrastructure

---

## Executive Summary

Reviewed the communications module against platform API best practices and audited the shared infrastructure for architectural issues. Found **4 P0 bugs**, **3 P0 security issues**, and numerous resilience/feature gaps across all adapters.

| Priority | Count | Category |
|----------|-------|----------|
| P0 | 7 | Bugs (4), Security (3) |
| P1 | 8 | Bugs (2), Resilience (4), Security (1), Features (1) |
| P2 | 10 | Resilience (4), Features (4), Performance (1), Quality (1) |
| P3 | 6 | Quality (2), Features (4) |

---

## 1. Cross-Cutting Infrastructure Audit (#10932)

### Architecture

**Manager monolith** — `manager.py` (686 lines) handles adapter lifecycle, message routing, identity resolution, thread mapping, and session bridging. Identity resolution (`_resolve_identity`, `_find_cross_channel_identity`, `_bridge_identity`) and thread tracking (`_thread_map`) should be extracted into dedicated classes.

**Inconsistent platform destination resolution** — Each adapter resolves the platform-specific destination differently:
- Slack (`slack.py:108`): Uses `message.channel_id` directly — but the manager sets this to the Gobby internal UUID
- Telegram (`telegram.py:104`): Uses `message.metadata_json.get('chat_id')`
- Teams (`teams.py:99`): Uses `message.channel_id` as conversation_id + `metadata_json.get('service_url')`
- Discord (`discord.py:152`): Uses `message.platform_thread_id or message.channel_id`

No consistent contract exists. Should be standardized via a `resolve_destination()` method or always passing platform-specific config.

### Bugs

**Webhook JSON re-serialization breaks verification** (`manager.py:498`) — When the payload arrives as a parsed dict, we re-serialize to bytes for signature verification via `json.dumps()`. This may not produce byte-identical output (key ordering, whitespace), breaking HMAC verification for Slack and Twilio. Fix: always pass the raw request body to `verify_webhook`.

**update_channel API endpoint broken** (`routes/communications.py:128-130`) — Calls `store.update_channel(channel_id=..., config_json=..., enabled=...)` with keyword args, but `LocalCommunicationsStore.update_channel` accepts a `ChannelConfig` object.

### Security

**Webhook verification optional by default** (`manager.py:497`) — Verification only runs when `channel.webhook_secret` is set. Unverified webhooks should at minimum produce a warning log.

**Channel deletion: no cascade cleanup** (`storage/communications.py:106-109`) — `delete_channel` only removes the channel row. Identities, messages, routing rules, and attachments become orphaned.

### Concurrency

**Thread map eviction is FIFO, not LRU** (`manager.py:451-452`) — Active conversations can be evicted while stale ones persist. An `OrderedDict` with move-to-end on access would fix this.

**Shared dict mutation without synchronization** — `_adapters`, `_channel_by_name`, and `_thread_map` are plain dicts mutated from multiple async paths with no locking.

### Resilience

**No retry logic anywhere** — None of the adapters implement retry-with-backoff for transient failures. Messages fail immediately on first error.

**Rate limiter is client-side only** (`rate_limiter.py`) — Doesn't read or respect platform rate-limit response headers.

**Routing rules: DB hit on every event** (`router.py:45`) — `list_routing_rules()` queries the database on every `match_channels()` call. Should cache with a short TTL.

### Encapsulation

**Private store access** — `routes/communications.py:124` and `mcp_proxy/tools/communications.py:52,81,146` access `comms_manager._store` directly. Should expose public methods.

---

## 2. Slack Adapter (#10926)

**File**: `src/gobby/communications/adapters/slack.py` (281 lines)

### What We Got Right
- HMAC-SHA256 verification follows the exact Slack signing secret spec
- Replay attack prevention (5-minute timestamp window)
- auth.test validation on initialization
- Bot message filtering (ignores own messages)
- Reaction event parsing
- Thread support via `thread_ts`
- Word-boundary message chunking

### Issues Found

| Priority | Issue | Location |
|----------|-------|----------|
| P0 | url_verification broken — raises exception not caught by route handler | `slack.py:191`, `routes/communications.py:57-71` |
| P0 | Deprecated `files.upload` API (deprecated March 2025) | `slack.py:141-157` |
| P0 | `channel_id` mismatch — sends Gobby UUID to Slack API | `slack.py:108` |
| P1 | No rate limit header handling (`Retry-After`, `X-Slack-Retry-Num`) | All send methods |
| P1 | No retry on transient errors (429, 5xx) | All send methods |
| P2 | No Block Kit support — only plain text | `slack.py:105-106` |
| P2 | No Socket Mode option (requires public URL) | Architecture |
| P2 | No event deduplication (Slack retries events) | `slack.py:175-246` |
| P3 | No message edit/delete (`chat.update`/`chat.delete`) | Missing |
| P3 | No unfurl control parameters | `slack.py:105` |

### Recommendations
1. Fix url_verification: return `CommsMessage` with `content_type='url_verification'` instead of raising exception
2. Migrate to `files.getUploadURLExternal` + `files.completeUploadExternal` flow
3. Read Slack channel ID from config_json, not `message.channel_id`
4. Add `Retry-After` handling with backoff
5. Consider Socket Mode as alternative for local deployments

---

## 3. Telegram Bot API (#10927)

**File**: `src/gobby/communications/adapters/telegram.py` (271 lines)

### What We Got Right
- Webhook secret_token verification with `hmac.compare_digest()`
- `setWebhook` with `secret_token` parameter
- Webhook/polling mutual exclusion (deletes webhook when polling)
- `getUpdates` offset tracking (`offset = update_id + 1`)
- Long polling timeout (30s)
- Message length limit (4096) and caption limit (1024) match API spec

### Issues Found

| Priority | Issue | Location |
|----------|-------|----------|
| P1 | No 429/retry_after handling | `telegram.py:126-127` |
| P1 | Naive character-boundary chunking instead of `chunk_message()` | `telegram.py:110-113` |
| P2 | No `parse_mode` support (HTML/MarkdownV2) | `telegram.py:118-125` |
| P2 | No `allowed_updates` filtering on setWebhook | `telegram.py:84-91` |
| P2 | No `max_connections` configuration | `telegram.py:84-91` |
| P2 | Always multipart upload — no `file_id` reuse | `telegram.py:146-154` |
| P2 | Deprecated `reply_to_message_id` — should use `reply_parameters` | `telegram.py:124-125` |
| P3 | Ignores non-text messages (photos, documents, callbacks) | `telegram.py:192-194` |
| P3 | No callback query support | Missing |
| P3 | Webhook port not validated (API only supports 443, 80, 88, 8443) | `telegram.py:82` |

### Recommendations
1. Add 429/retry_after handling: extract `parameters.retry_after` from response
2. Use `self.chunk_message(content)` instead of naive slicing
3. Add `allowed_updates: ["message"]` to setWebhook and getUpdates
4. Support `parse_mode` parameter (default to HTML)

---

## 4. Discord Gateway & Bot API (#10928)

**File**: `src/gobby/communications/adapters/discord.py` (322 lines)

### What We Got Right
- Ed25519 signature verification matches Discord's spec exactly
- API v10 for both REST and Gateway
- Correct IDENTIFY payload with proper intents (37376 = GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT)
- PING handling (interaction type 1)
- Message chunking at 2000 chars
- Multipart attachment upload with `payload_json` field
- Graceful shutdown (cancels gateway task, closes client)

### Issues Found

| Priority | Issue | Location |
|----------|-------|----------|
| P0 | **No heartbeat implementation** — connection dies in ~45 seconds | `discord.py:122-135` |
| P1 | No session resume (opcode 6) — wastes session starts on reconnect | `discord.py:96-140` |
| P1 | No sequence number tracking (required for heartbeat and resume) | `discord.py:122-135` |
| P1 | No REST rate limit handling (429, `X-RateLimit-*` headers) | `discord.py:158` |
| P2 | No embed support — only plain text | `discord.py:153-157` |
| P2 | Hardcoded Gateway URL — should use `GET /gateway/bot` | `discord.py:104-105` |
| P2 | Fixed 5s reconnect delay — should be exponential backoff | `discord.py:138` |
| P2 | No Gateway event rate limit tracking (120/60s limit) | Architecture |
| P3 | MESSAGE_CONTENT privileged intent not validated | `discord.py:112` |
| P3 | No interaction response support | Missing |

### Recommendations
1. **Critical**: Implement heartbeat loop — parse opcode 10 (Hello) for `heartbeat_interval`, send opcode 1 periodically
2. Track sequence numbers from every dispatch event
3. Implement session resume (opcode 6) with stored session_id + last sequence
4. Add REST rate limit handling: read `X-RateLimit-*` headers, retry on 429
5. Use `GET /gateway/bot` to fetch WSS URL and check session start limits

---

## 5. Microsoft Teams Bot Framework (#10929)

**File**: `src/gobby/communications/adapters/teams.py` (237 lines)

### What We Got Right
- OAuth2 client_credentials grant with correct scope and early refresh (5 min before expiry)
- JWT verification against Bot Framework JWKS with RS256, audience, and issuer checks
- serviceUrl claim validation (https:// required)
- Correct Activity model construction
- Adaptive Card support with proper content type
- Reply threading via `replyToId`

### Issues Found

| Priority | Issue | Location |
|----------|-------|----------|
| P0 | **No tenant validation** — any Teams tenant can message the bot | `teams.py:201-235` |
| P0 | **No service URL allowlist** — outbound messages could be redirected | `teams.py:96-101` |
| P1 | Token refresh race condition under concurrent sends | `teams.py:92-93` |
| P1 | No retry logic (429/5xx) | `teams.py:132` |
| P1 | JWKS key rotation not handled (no lifespan on JWK client) | `teams.py:216` |
| P2 | No proactive messaging (no ConversationReference storage) | Missing |
| P2 | No conversationUpdate/invoke/messageReaction handling | `teams.py:167` |
| P2 | No adaptive card action handling | Missing |
| P3 | No @mention stripping (`<at>...</at>` markup) | `teams.py:175` |
| P3 | No file attachment support | Missing |
| P3 | Hardcoded JWKS URL (commercial cloud only) | `teams.py:23` |

### Recommendations
1. Add `allowed_tenants` config, check JWT `tid` claim
2. Validate outbound URLs against known Bot Framework domains
3. Add `asyncio.Lock` for token refresh
4. Set JWK client lifespan for key rotation
5. Store ConversationReference for proactive messaging

---

## 6. Email SMTP/IMAP (#10930)

**File**: `src/gobby/communications/adapters/email.py` (278 lines)

### What We Got Right
- TLS/STARTTLS handling (port 465 = direct TLS, port 587 = STARTTLS)
- RFC 2822 compliant Message-ID generation via `make_msgid()`
- Threading headers (`In-Reply-To` and `References`)
- IMAP UNSEEN search for polling
- Multipart parsing with text/plain preference over text/html
- Graceful shutdown with error handling
- Proper MIME attachments via `add_attachment()`

### Issues Found

| Priority | Issue | Location |
|----------|-------|----------|
| P0 | **IMAP messages never marked as seen** — duplicates on every poll | `email.py:177` |
| P1 | No connection pooling or reconnection logic | `email.py:96-109` |
| P1 | No IMAP IDLE support (polling only) | `email.py:171-237` |
| P1 | No multipart/alternative for outbound HTML (text+html) | `email.py:129-132` |
| P2 | No OAuth2 support (required by Gmail/Outlook since 2022) | `email.py:86-89` |
| P2 | No rate limiting awareness (Gmail: 500/day free) | All send methods |
| P2 | No bounce/DSN detection | `email.py:171-237` |
| P2 | Incomplete References header (only single-depth) | `email.py:127` |
| P3 | SMTP context manager not used (half-open on login failure) | `email.py:97-104` |
| P3 | IMAP SELECT called on every poll (unnecessary) | `email.py:176` |
| P3 | Blocking `file_path.read_bytes()` in async context | `email.py:163` |

### Recommendations
1. Mark messages as `\Seen` after successful processing
2. Add reconnection with exponential backoff (`_ensure_connected()` helper)
3. Implement IMAP IDLE via `idle_start()` / `wait_server_push()` with polling fallback
4. Send multipart/alternative: `set_content(plain)` then `add_alternative(html, subtype='html')`
5. Add OAuth2 XOAUTH2 SASL support

---

## 7. Twilio SMS API (#10931)

**File**: `src/gobby/communications/adapters/sms.py` (222 lines)

### What We Got Right
- Correct REST API endpoint and basic auth pattern
- Twilio signature validation (HMAC-SHA1, base64, timing-safe compare)
- Correct `application/x-www-form-urlencoded` webhook parsing
- MMS support via `MediaUrl` parameter
- Word-boundary message chunking at 1600 chars
- Async HTTP client with connection reuse

### Issues Found

| Priority | Issue | Location |
|----------|-------|----------|
| P1 | **No Messaging Service SID support** (required for A2P 10DLC) | `sms.py:93-97` |
| P1 | No status callback support (no delivery tracking) | `sms.py:93-97` |
| P1 | No error code handling (30003, 30005, 30007, etc.) | `sms.py:99-104` |
| P1 | No opt-out handling (STOP/HELP/UNSTOP keywords) | `sms.py:154-186` |
| P2 | Webhook URL verification fragile (requires custom headers) | `sms.py:199-213` |
| P2 | No rate limiting awareness (per-number sending rates) | `sms.py:92-108` |
| P2 | No retry logic (429/5xx) | `sms.py:99-100` |
| P3 | No A2P 10DLC compliance surface | Config/docs |
| P3 | No MMS media type validation | `sms.py:110-136` |
| P3 | No segment count tracking (billing impact) | `sms.py:99-104` |

### Recommendations
1. Add `messaging_service_sid` as alternative to `from_number` — use `MessagingServiceSid` parameter when present
2. Add `StatusCallback` URL support in config and send payload
3. Inspect `error_code` and `error_message` in send responses
4. Detect opt-out keywords in `parse_webhook()` and set metadata flags
5. Document webhook URL requirement for signature verification

---

## Consolidated Priority Table

| # | Priority | Category | Issue | File:Line |
|---|----------|----------|-------|-----------|
| 1 | P0 | Bug | Webhook JSON re-serialization breaks HMAC verification | `manager.py:498` |
| 2 | P0 | Bug | Slack url_verification exception not caught | `slack.py:191` |
| 3 | P0 | Bug | update_channel API endpoint wrong signature | `routes/communications.py:128` |
| 4 | P0 | Bug | Discord gateway has no heartbeat (dies in ~45s) | `discord.py:122` |
| 5 | P0 | Security | Teams: no tenant validation | `teams.py:201` |
| 6 | P0 | Security | Teams: no service URL allowlist | `teams.py:96` |
| 7 | P0 | Bug | Email IMAP messages never marked as seen (duplicates) | `email.py:177` |
| 8 | P1 | Bug | Slack channel_id mismatch (Gobby UUID vs Slack ID) | `slack.py:108` |
| 9 | P1 | Bug | Inconsistent destination resolution across adapters | Multiple |
| 10 | P1 | Security | No cascade on channel deletion (orphaned records) | `storage/communications.py:106` |
| 11 | P1 | Resilience | No retry logic in any adapter | All adapters |
| 12 | P1 | Resilience | Email SMTP connection never reconnects | `email.py:103` |
| 13 | P1 | Resilience | Email no IMAP IDLE | `email.py:171` |
| 14 | P1 | Resilience | Teams token refresh race condition | `teams.py:92` |
| 15 | P1 | Feature | SMS: no Messaging Service SID (A2P 10DLC required) | `sms.py:93` |
| 16 | P1 | Feature | SMS: no status callbacks / opt-out handling | `sms.py:93,154` |
| 17 | P1 | Resilience | Discord: no session resume | `discord.py:96` |
| 18 | P1 | Resilience | Discord: no REST rate limit handling | `discord.py:158` |
| 19 | P1 | Bug | Telegram: naive chunking (breaks words) | `telegram.py:110` |
| 20 | P2 | Resilience | Rate limiter is client-side only | `rate_limiter.py` |
| 21 | P2 | Performance | Routing rules DB query on every event | `router.py:45` |
| 22 | P2 | Feature | Slack: no Block Kit support | `slack.py:105` |
| 23 | P2 | Feature | Discord: no embed support | `discord.py:153` |
| 24 | P2 | Feature | Email: no OAuth2 support | `email.py:86` |
| 25 | P2 | Feature | Email: no multipart/alternative for HTML | `email.py:129` |
| 26 | P2 | Resilience | Discord: hardcoded gateway URL | `discord.py:104` |
| 27 | P2 | Resilience | Discord: fixed 5s reconnect (should be exponential) | `discord.py:138` |
| 28 | P2 | Feature | Teams: no proactive messaging | Missing |
| 29 | P2 | Resilience | SMS: webhook URL verification fragile | `sms.py:199` |
| 30 | P3 | Quality | Manager monolith — extract identity + threading | `manager.py` |
| 31 | P3 | Quality | Private store access from routes/MCP tools | Multiple |
