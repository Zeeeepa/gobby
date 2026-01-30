# Remote Access for Gobby

**Goal**: Work with Gobby from anywhere - full interaction capabilities remotely.

**Priority Order**: Web UI > Tailscale > Telegram > SSH tunneling

**Inspired by**: [moltbot/moltbot](https://github.com/moltbot/moltbot) - multi-channel messaging, WebSocket control plane, Tailscale integration

---

## Phase 1: Authentication & Security Foundation

Before exposing Gobby remotely, we need authentication.

### Files to Create (Auth)

```text
src/gobby/auth/
  __init__.py           # Module exports
  config.py             # AuthConfig, TLSConfig models
  tokens.py             # Token generation/validation (secrets.token_urlsafe)
  middleware.py         # FastAPI auth middleware
  providers/
    __init__.py
    local.py            # Token-based auth
    tailscale.py        # Tailscale identity header auth
```

### Files to Modify (Auth)

| File | Changes |
| ---- | ------- |
| `src/gobby/config/app.py` | Add `RemoteAccessConfig`, `AuthConfig`, `TLSConfig` |
| `src/gobby/servers/http.py` | Add auth middleware, localhost bypass |
| `src/gobby/servers/websocket.py` | Wire up `auth_callback` with token validation |
| `src/gobby/runner.py` | Integrate auth config into server startup |
| `src/gobby/cli/daemon.py` | Add `gobby auth` commands |

### Configuration (Auth)

```yaml
remote_access:
  enabled: true
  auth:
    enabled: true
    mode: "token"  # or "tailscale", "password"
    allow_localhost: true  # Skip auth for local connections
  tls:
    enabled: true
    auto_generate: true  # Self-signed cert in ~/.gobby/certs/
```

### CLI Commands (Auth)

- `gobby auth enable` - Enable auth, generate token
- `gobby auth token` - Show/regenerate token
- `gobby auth disable` - Disable auth

---

## Phase 2: Web UI

Browser-based interface for full session interaction.

### Architecture

- Serve static React/Preact app from FastAPI
- WebSocket connection for real-time updates
- REST API fallbacks for initial data loading

### Files to Create (Web UI)

```text
src/gobby/web/
  __init__.py
  routes.py             # FastAPI routes for UI
  static/               # Built frontend assets (gitignored, built from ui/)

ui/                     # Frontend source (Vite + React/Preact)
  src/
    App.tsx
    components/
      SessionList.tsx
      SessionView.tsx
      MessageStream.tsx
      PromptInput.tsx
    hooks/
      useWebSocket.ts
      useSessions.ts
    api/
      client.ts         # REST + WebSocket client
```

### WebSocket Protocol Enhancements

Add message types to `src/gobby/servers/websocket.py`:

```python
# New message types
"session_list"      # Request: list sessions
"session_connect"   # Request: connect to session
"session_prompt"    # Request: send prompt to session
"session_stream"    # Response: streaming output
"session_complete"  # Response: agent finished
```

### UI Features

1. **Dashboard**: List projects, sessions, running agents
2. **Session View**: Full conversation history with streaming
3. **Prompt Input**: Send messages to sessions
4. **Agent Control**: Stop/interrupt running agents
5. **Task Board**: View/manage Gobby tasks
6. **Status**: Daemon health, connected MCPs, metrics

### Files to Modify (Web UI)

| File | Changes |
| ---- | ------- |
| `src/gobby/servers/http.py` | Mount web routes, add SPA fallback |
| `src/gobby/servers/websocket.py` | Add UI-specific message handlers |
| `src/gobby/runner.py` | Include web routes in startup |

---

## Phase 3: Tailscale Integration

Secure remote access without port exposure.

### Files to Create (Tailscale)

```text
src/gobby/remote/
  __init__.py
  tailscale.py          # TailscaleManager class
  config.py             # TailscaleConfig model
```

### TailscaleManager

```python
class TailscaleManager:
    def is_available(self) -> bool: ...
    def get_status(self) -> dict: ...
    def get_ip(self) -> str | None: ...
    def serve_start(self, port: int) -> bool: ...
    def funnel_start(self, port: int) -> bool: ...
    def serve_stop(self) -> bool: ...
```

### CLI Commands (Tailscale)

Add to `src/gobby/cli/remote.py`:

- `gobby remote serve` - Start Tailscale Serve (tailnet-only)
- `gobby remote funnel` - Start Tailscale Funnel (public HTTPS)
- `gobby remote stop` - Stop remote exposure
- `gobby remote status` - Show Tailscale status and URLs

### Configuration (Tailscale)

```yaml
remote_access:
  tailscale:
    enabled: true
    auto_serve: false   # Auto-start Serve on daemon start
    funnel: false       # Use Funnel instead of Serve
```

### Auth Integration

When Tailscale Serve/Funnel is active:

- Extract user from `Tailscale-User-Login` header
- Skip token auth for verified tailnet users
- Map tailnet identity to Gobby user

---

## Phase 4: Telegram Bot

Mobile access via Telegram.

### Files to Create (Telegram)

```text
src/gobby/channels/
  __init__.py
  base.py               # Abstract ChannelAdapter
  manager.py            # Route messages to sessions
  telegram/
    __init__.py
    adapter.py          # TelegramAdapter
    bot.py              # Bot implementation (python-telegram-bot)
    commands.py         # Command handlers
    config.py           # TelegramConfig
```

### Bot Commands

| Command | Action |
| ------- | ------ |
| `/start` | Initialize, link Telegram account |
| `/status` | Daemon status, active sessions |
| `/sessions` | List sessions (buttons to connect) |
| `/connect <id>` | Connect to session |
| `/disconnect` | Disconnect from session |
| `/stop` | Stop running agent |
| `/prompt <text>` | Send prompt (or just type without command) |

### Configuration (Telegram)

```yaml
channels:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    allowed_user_ids: [12345678]  # Whitelist
    default_project: "gobby"
```

### Files to Modify (Telegram)

| File | Changes |
| ---- | ------- |
| `src/gobby/config/app.py` | Add `ChannelsConfig`, `TelegramConfig` |
| `src/gobby/runner.py` | Start Telegram bot as background task |

---

## Phase 5: SSH Tunneling Support

Documentation and helper scripts for SSH access.

### Files to Create (SSH)

```text
src/gobby/remote/
  ssh.py                # SSH tunnel helpers

docs/remote-access.md   # User documentation
```

### CLI Commands (SSH)

- `gobby remote ssh-command` - Print SSH tunnel command for copy/paste
- `gobby remote ssh-config` - Generate SSH config snippet

### Output Example

```bash
$ gobby remote ssh-command
# Run this on your remote machine:
ssh -N -L 60887:127.0.0.1:60887 -L 60888:127.0.0.1:60888 user@your-machine

# Then access Gobby at:
# HTTP:      http://localhost:60887
# WebSocket: ws://localhost:60888
```

---

## Implementation Order

| Phase | Effort | Dependencies | Priority |
| ----- | ------ | ------------ | -------- |
| 1. Auth Foundation | Medium | None | Required first |
| 2. Web UI | High | Phase 1 | High |
| 3. Tailscale | Low | Phase 1 | High |
| 4. Telegram | Medium | Phase 1 | Medium |
| 5. SSH Docs | Low | Phase 1 | Low |

**Recommended sequence**: Phase 1 → Phase 3 (quick win) → Phase 2 (main feature) → Phase 4 → Phase 5

---

## Verification

### Phase 1 (Auth)

```bash
# Test token auth
curl -H "Authorization: Bearer $(gobby auth token)" http://localhost:60887/admin/status

# Test localhost bypass
curl http://localhost:60887/admin/status  # Should work without token
```

### Phase 2 (Web UI)

1. Open `http://localhost:60887/` in browser
2. List sessions, connect to one
3. Send a prompt, verify streaming response
4. Stop an agent mid-execution

### Phase 3 (Tailscale)

```bash
gobby remote serve
# Access from another tailnet device at https://<machine>.<tailnet>.ts.net/
```

### Phase 4 (Telegram)

1. Start chat with bot
2. `/status` - verify daemon connection
3. `/sessions` - list active sessions
4. Connect and send prompts

---

## Security Checklist

- [ ] Auth tokens stored with 0600 permissions
- [ ] TLS enabled for remote connections
- [ ] Localhost bypass only when explicitly configured
- [ ] Telegram bot restricted to allowed_user_ids
- [ ] Rate limiting on auth endpoints (future)
- [ ] Audit logging for remote access (future)

---

## References

- [moltbot/moltbot](https://github.com/moltbot/moltbot) - Inspiration for multi-channel architecture
- Moltbot gateway docs: WebSocket control plane on port 18789, Tailscale Serve/Funnel integration
- Moltbot channels: Telegram, Slack, Discord, WhatsApp, Signal, iMessage adapters
