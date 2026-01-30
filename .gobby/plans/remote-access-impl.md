# Remote Access for Gobby - Implementation Plan

## Overview

Implement full remote access capabilities for Gobby following the 5-phase approach from `docs/plans/remote-access.md`:

1. **Phase 1: Auth Foundation** - Token auth, TLS, localhost bypass
2. **Phase 2: Web UI** - Browser-based session interface
3. **Phase 3: Tailscale** - Secure remote access via Tailscale Serve/Funnel
4. **Phase 4: Telegram Bot** - Mobile access via Telegram
5. **Phase 5: SSH Docs** - Helper scripts and documentation

**Implementation order**: Phase 1 → Phase 3 (quick win) → Phase 2 (main feature) → Phase 4 → Phase 5

---

## Phase 1: Auth Foundation

### Tasks

- [ ] Create `src/gobby/config/auth.py` with AuthConfig, TLSConfig, RemoteAccessConfig models (category: code)
- [ ] Create `src/gobby/auth/tokens.py` with TokenManager class (category: code)
- [ ] Create `src/gobby/auth/tls.py` with certificate generation (category: code)
- [ ] Create `src/gobby/auth/middleware.py` with AuthMiddleware and create_auth_callback (category: code)
- [ ] Create `src/gobby/auth/__init__.py` module exports (category: code)
- [ ] Create `src/gobby/cli/auth.py` with enable, token, disable, status commands (category: code)
- [ ] Modify `src/gobby/config/app.py` to add RemoteAccessConfig (category: code)
- [ ] Modify `src/gobby/servers/http.py` to add AuthMiddleware (category: code)
- [ ] Modify `src/gobby/runner.py` to wire up auth callback and TLS (category: code)
- [ ] Modify `src/gobby/cli/__init__.py` to register auth command group (category: code)
- [ ] Create `tests/auth/test_tokens.py` (category: test)
- [ ] Create `tests/auth/test_middleware.py` (category: test)

### Key Design

- Token storage: `~/.gobby/auth_token` (0o600 permissions)
- Token validation: `secrets.compare_digest()` for timing-safe comparison
- Localhost bypass: Default enabled for backward compatibility
- TLS certs: Auto-generate via OpenSSL to `~/.gobby/certs/`

---

## Phase 3: Tailscale Integration

**Depends on**: Phase 1

### Tasks

- [ ] Create `src/gobby/remote/config.py` with TailscaleConfig model (category: code)
- [ ] Create `src/gobby/remote/tailscale.py` with TailscaleManager class (category: code)
- [ ] Create `src/gobby/remote/__init__.py` module exports (category: code)
- [ ] Create `src/gobby/cli/remote.py` with serve, funnel, stop, status commands (category: code)
- [ ] Create `src/gobby/auth/providers/tailscale.py` for Tailscale identity header auth (category: code)
- [ ] Modify `src/gobby/config/app.py` to add TailscaleConfig (category: code)
- [ ] Modify `src/gobby/cli/__init__.py` to register remote command group (category: code)
- [ ] Modify `src/gobby/runner.py` to add auto-serve on startup (category: code)
- [ ] Create `tests/remote/test_tailscale.py` (category: test)

### TailscaleManager Methods

```python
class TailscaleManager:
    def is_available(self) -> bool          # Check CLI installed
    def get_status(self) -> TailscaleStatus # Parse `tailscale status --json`
    def get_ip(self) -> str | None          # Get Tailscale IPv4
    def get_dns_name(self) -> str | None    # Get DNS name
    def serve_start(port, https_port) -> bool
    def funnel_start(port, https_port) -> bool
    def serve_stop() -> bool
```

---

## Phase 2: Web UI

**Depends on**: Phase 1

### Tasks

- [ ] Create `src/gobby/config/web.py` with WebUIConfig model (category: code)
- [ ] Create `src/gobby/web/__init__.py` module exports (category: code)
- [ ] Create `src/gobby/web/routes.py` with FastAPI routes for static files + SPA fallback (category: code)
- [ ] Modify `src/gobby/servers/http.py` to mount web routes (category: code)
- [ ] Modify `src/gobby/servers/websocket.py` to add session_list, session_connect, session_stream handlers (category: code)
- [ ] Modify `src/gobby/config/app.py` to add WebUIConfig (category: code)
- [ ] Initialize `ui/` directory with Vite + Preact scaffold (category: config)
- [ ] Create `ui/src/api/client.ts` REST + WebSocket client (category: code)
- [ ] Create `ui/src/hooks/useWebSocket.ts` connection hook (category: code)
- [ ] Create `ui/src/components/dashboard/Dashboard.tsx` (category: code)
- [ ] Create `ui/src/components/sessions/SessionList.tsx` (category: code)
- [ ] Create `ui/src/components/sessions/SessionView.tsx` with streaming (category: code)
- [ ] Create `ui/src/components/sessions/PromptInput.tsx` (category: code)
- [ ] Create `ui/src/components/tasks/TaskBoard.tsx` (category: code)
- [ ] Create `ui/src/components/status/StatusPanel.tsx` (category: code)
- [ ] Update `.gitignore` for frontend build artifacts (category: config)

### Tech Stack

- **Frontend**: Preact (3KB), Vite, Tailwind CSS
- **State**: Zustand or Preact Signals
- **Routing**: wouter
- **Build output**: `src/gobby/web/static/`

---

## Phase 4: Telegram Bot

**Depends on**: Phase 1

### Tasks

- [ ] Create `src/gobby/channels/base.py` with ChannelAdapter ABC (category: code)
- [ ] Create `src/gobby/channels/manager.py` with ChannelManager (category: code)
- [ ] Create `src/gobby/channels/__init__.py` module exports (category: code)
- [ ] Create `src/gobby/channels/telegram/config.py` with TelegramConfig (category: code)
- [ ] Create `src/gobby/channels/telegram/adapter.py` with TelegramAdapter (category: code)
- [ ] Create `src/gobby/channels/telegram/commands.py` with bot commands (category: code)
- [ ] Create `src/gobby/channels/telegram/bot.py` bot service (category: code)
- [ ] Create `src/gobby/channels/telegram/__init__.py` (category: code)
- [ ] Modify `src/gobby/config/app.py` to add ChannelsConfig (category: code)
- [ ] Modify `src/gobby/runner.py` to start/stop Telegram bot (category: code)
- [ ] Add `python-telegram-bot>=21.0` to pyproject.toml optional deps (category: config)
- [ ] Create `tests/channels/test_manager.py` (category: test)
- [ ] Create `tests/channels/test_telegram.py` (category: test)

### Bot Commands

| Command | Action |
|---------|--------|
| `/start` | Initialize, show user ID |
| `/status` | Daemon status |
| `/sessions` | List sessions with buttons |
| `/connect <id>` | Connect to session |
| `/disconnect` | Disconnect |
| `/stop` | Stop running agent |

---

## Phase 5: SSH Documentation

**Depends on**: Phase 1

### Tasks

- [ ] Create `src/gobby/remote/ssh.py` with tunnel helper functions (category: code)
- [ ] Add ssh-command and ssh-config commands to `src/gobby/cli/remote.py` (category: code)
- [ ] Create `docs/remote-access.md` user documentation (category: docs)

---

## Configuration Example

```yaml
# ~/.gobby/config.yaml
remote_access:
  enabled: true
  auth:
    enabled: true
    mode: "token"
    allow_localhost: true
    token_file: "~/.gobby/auth_token"
  tls:
    enabled: true
    auto_generate: true

tailscale:
  enabled: true
  auto_serve: false
  funnel: false

web_ui:
  enabled: true

channels:
  telegram:
    enabled: false
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    allowed_user_ids: []
```

---

## Verification

### Phase 1 (Auth)
```bash
gobby auth enable
curl -H "Authorization: Bearer $(gobby auth token)" http://localhost:60887/admin/status
```

### Phase 2 (Web UI)
Open `http://localhost:60887/` in browser

### Phase 3 (Tailscale)
```bash
gobby remote serve
# Access from tailnet at https://<machine>.<tailnet>.ts.net/
```

### Phase 4 (Telegram)
Start chat with bot, use `/status` command

---

## Security Checklist

- [ ] Auth tokens stored with 0600 permissions
- [ ] TLS enabled for remote connections
- [ ] Localhost bypass only when explicitly configured
- [ ] Telegram bot restricted to allowed_user_ids
- [ ] Tailscale Funnel requires explicit confirmation
- [ ] Token comparison uses timing-safe secrets.compare_digest()
