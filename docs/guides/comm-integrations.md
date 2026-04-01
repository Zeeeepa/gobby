# Communications Integrations Guide

Connect external messaging platforms to Gobby so that inbound messages create sessions and outbound notifications reach your team wherever they are.

## Overview

Gobby's communications framework supports 7 channel types:

| Platform | Type | Inbound | Outbound | Protocol |
|----------|------|---------|----------|----------|
| Slack | `slack` | Webhooks | Bot API | HTTP |
| Telegram | `telegram` | Webhooks / Polling | Bot API | HTTP |
| Discord | `discord` | Gateway (WebSocket) | Bot API | WebSocket + HTTP |
| Microsoft Teams | `teams` | Webhooks | Bot Framework | HTTP |
| Email | `email` | IMAP polling | SMTP | IMAP / SMTP |
| SMS (Twilio) | `sms` | Webhooks | REST API | HTTP |
| Gobby Chat | `gobby_chat` | WebSocket | WebSocket | Internal |

**Gobby Chat** is the built-in native channel that bridges the web UI's WebSocket chat to the communications framework. It's auto-created on startup and requires no configuration.

## Quick Start

### Via Web UI

1. Navigate to **Integrations** in the sidebar
2. Click a platform card in the empty state (or **+ Add Integration**)
3. Fill in credentials and click **Add Channel**
4. Copy the webhook URL from the channel detail panel

### Via CLI

```bash
gobby comms channels add slack my-team
# Follow interactive prompts for Bot Token, Signing Secret, Channel ID
```

## Platform Setup Guides

### Slack

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
2. Under **OAuth & Permissions**, add Bot Token Scopes: `chat:write`, `channels:read`, `channels:history`
3. Install the app to your workspace and copy the **Bot User OAuth Token** (`xoxb-...`)
4. Under **Basic Information**, copy the **Signing Secret**
5. Under **Event Subscriptions**, enable events and set the Request URL to your webhook URL
6. Subscribe to bot events: `message.channels`, `message.groups`, `message.im`

**Gobby config:**
- Bot Token: `xoxb-...` (stored securely in SecretStore)
- Signing Secret: from Basic Information (stored securely)
- Channel ID: optional, limits bot to one channel

### Telegram

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`, follow prompts, copy the **Bot Token**
3. Optionally set the webhook: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WEBHOOK_URL>`

**Gobby config:**
- Bot Token: from BotFather (stored securely)
- Chat ID: optional, target a specific chat

### Discord

1. Create an application at [discord.com/developers](https://discord.com/developers/applications)
2. Go to **Bot**, click **Add Bot**, copy the **Token**
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Go to **OAuth2 > URL Generator**, select `bot` scope + `Send Messages`, `Read Message History` permissions
5. Use the generated URL to add the bot to your server

**Gobby config:**
- Bot Token: from Bot settings (stored securely)
- Channel ID: optional, right-click channel > Copy Channel ID

### Microsoft Teams

1. Register an Azure Bot at [portal.azure.com](https://portal.azure.com)
2. Create an **App Registration** and note the Application (client) ID
3. Generate a client secret under **Certificates & secrets**
4. Configure the messaging endpoint to your webhook URL

**Gobby config:**
- App ID: Application (client) ID (stored securely)
- App Password: client secret (stored securely)

### Email

1. Generate an App Password for your email provider (Gmail: Security > App Passwords)
2. Note your SMTP and IMAP server addresses and ports

**Gobby config:**
- Password: app password (stored securely)
- SMTP Host: e.g., `smtp.gmail.com`
- SMTP Port: e.g., `587` (TLS) or `465` (SSL)
- IMAP Host: e.g., `imap.gmail.com`
- IMAP Port: e.g., `993`
- From Address: your email address

### SMS (Twilio)

1. Create an account at [twilio.com](https://www.twilio.com)
2. From the Console Dashboard, copy your **Account SID** and **Auth Token**
3. Purchase a phone number under **Phone Numbers > Manage > Buy a Number**
4. Under the phone number settings, set the Messaging webhook URL

**Gobby config:**
- Auth Token: from Twilio Console (stored securely)
- Account SID: `AC...` from Console
- From Number: your Twilio number (e.g., `+15551234567`)

## Web UI Walkthrough

The **Integrations** page in the Gobby web dashboard provides:

- **Channel grid**: All configured channels shown as cards with platform-colored borders, status indicators, and quick actions (edit, toggle, remove)
- **Add/Edit modal**: Type-specific forms with secret field handling (password inputs, show/hide toggles)
- **Channel detail panel**: Slide-out panel with live status, webhook URL (copyable), configuration overview, and management actions
- **Messages tab**: Browsable message history with channel/direction filters, expandable message detail, and pagination

### Channel Filters

Use the filter chips above the channel grid to filter by platform type. The search bar filters by channel name.

## Webhook Configuration

Channels that support webhooks (Slack, Telegram, Discord, Teams, SMS) receive inbound messages via HTTP POST to:

```
https://<your-gobby-host>:60887/api/comms/webhooks/<channel-name>
```

The webhook URL is displayed in the channel detail panel with a Copy button.

### Important Notes

- **HTTPS required**: Most platforms require HTTPS for webhooks. Use a reverse proxy (nginx, Caddy) or tunnel (ngrok, Cloudflare Tunnel) for local development.
- **Firewall**: Ensure port 60887 is accessible from the platform's webhook IPs.
- **Verification**: Gobby verifies webhook signatures automatically using the channel's signing secret / auth token.

## Message Routing

Routing rules determine how inbound messages are processed. Rules can match by channel, event pattern, and project. Management is currently available via CLI and API:

```bash
# List routing rules
gobby comms routes list

# Rules are configured via the REST API or MCP tools
```

## MCP Tools Reference

The `gobby-comms` MCP server exposes these tools:

| Tool | Description |
|------|-------------|
| `send_message` | Send a message to a communication channel |
| `list_channels` | List configured channels and their status |
| `get_messages` | Get message history for a channel |
| `add_channel` | Add a new communication channel (accepts `secrets` param) |
| `remove_channel` | Remove a communication channel |
| `link_identity` | Link an external user to a Gobby session |
| `list_identities` | List identity mappings with optional filters |
| `unlink_identity` | Remove session link from an identity |

### Example: Send a message

```python
call_tool("gobby-comms", "send_message", {
    "channel_name": "my-slack",
    "content": "Build completed successfully!",
    "session_id": "#1234"
})
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Webhook verification fails | Check that the signing secret / auth token matches what the platform expects. For Slack, ensure you're using the Signing Secret (not the Bot Token). |
| Messages not appearing | Verify the channel is enabled (`gobby comms channels list`). Check the webhook URL is reachable from the platform. |
| Adapter initialization error | Check daemon logs (`tail -f ~/.gobby/logs/gobby.log`). Common causes: invalid credentials, network issues, missing bot permissions. |
| Polling vs webhook mode | If `webhook_base_url` is not set in config, adapters that support both will fall back to polling mode. Set the base URL for webhook mode. |
| Discord bot not receiving messages | Ensure **Message Content Intent** is enabled in the Developer Portal. The bot needs this privileged intent to read message content. |
| Email connection timeout | Verify SMTP/IMAP hosts and ports are correct. Gmail requires an App Password, not your regular password. |
| Rate limiting | Gobby includes built-in rate limiting per channel. Adjust `rate_limit_per_minute` in channel config if needed. |
