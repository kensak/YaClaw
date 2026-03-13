# LINE Channel Plugin (`channel_line`)

This plugin connects YaClaw to [LINE Messaging API](https://developers.line.biz/en/docs/messaging-api/), allowing you to send messages to an AI agent from LINE and receive the replies back in LINE.

---

## LINE Bot Registration

Before configuring this plugin, you need a LINE Messaging API channel.
See [LINE_bot_registration.md](LINE_bot_registration.md) for step-by-step instructions.

---

## settings.json

Add a `line` entry under `channel`:

```json
{
    "channel": {
        "line": {
            "plugin": "channel_line",
            "channel_access_token": "${LINE_CHANNEL_ACCESS_TOKEN}",
            "channel_secret": "${LINE_CHANNEL_SECRET}",
            "target_id": "${LINE_TARGET_ID}",
            "host": "0.0.0.0",
            "port": 8000,
            "webhook_path": "/webhook",
            "agent": "opencode"
        }
    },
    ...
}
```

See `examples/settings_line.json` for a ready-to-use copy.

### Setting reference

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `plugin` | ✅ | — | Must be `"channel_line"` |
| `channel_access_token` | ✅ | — | Long-lived channel access token issued in LINE Developers Console |
| `channel_secret` | ✅ | — | Channel secret (used for webhook signature verification) |
| `agent` | ✅ | — | Name of the agent to forward messages to |
| `target_id` | — | `null` (accept all) | Accept messages only from this LINE user ID (`U…`) or group ID (`C…`) |
| `host` | — | `"0.0.0.0"` | Bind address for the webhook HTTP server |
| `port` | — | `8000` | Port for the webhook HTTP server |
| `webhook_path` | — | `"/webhook"` | URL path for the webhook endpoint |

### .env

```bash
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token_here
LINE_CHANNEL_SECRET=your_channel_secret_here
LINE_TARGET_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # optional: your LINE user ID
```

To find your own LINE user ID, send any message to your bot — the `source.userId` in the Webhook event log (LINE Developers Console) is your user ID.

---

## HTTPS Setup

LINE requires the Webhook URL to be reachable over **HTTPS with a trusted certificate**. A self-signed certificate is rejected.

### Option A — Tailscale Funnel (recommended for always-on home servers)

[Tailscale Funnel](https://tailscale.com/kb/1223/tailscale-funnel) exposes a local port to the public internet with HTTPS managed by Tailscale (trusted CA, fixed URL tied to your machine name).

```bash
# Install Tailscale, log in, then:
tailscale funnel 8000
```

Your webhook URL will be something like:

```
https://your-machine.taile12345.ts.net/webhook
```

This URL is **stable** — it does not change between restarts.

### Option B — ngrok (quick local development)

```bash
ngrok http 8000
```

Use the `https://…ngrok-free.app` URL as the Webhook URL. Note that the free tier generates a **new URL on every run**, so you need to update the LINE Developers Console each time.

### Option C — Let's Encrypt on a public server

If you run YaClaw on a VPS with a domain name, use [Certbot](https://certbot.eff.org/) to obtain a free certificate and place a reverse proxy (e.g. nginx) in front of YaClaw.

---

## How It Works

```
LINE user ──[message]──▶ LINE Platform ──[HTTPS Webhook POST]──▶ YaClaw (channel_line)
                                                                        │
                                                          handle_request_message()
                                                                        │
                                                                   Agent queue
                                                                        │
                                                          handle_response_message()
                                                                        │
LINE user ◀──[reply]──── LINE Platform ◀──[Reply API]────────────────
```

1. LINE Platform sends an HTTPS POST to your webhook endpoint when a user sends a message
2. `channel_line` verifies the HMAC-SHA256 signature and parses the event
3. If `target_id` is set, messages from other users/groups are filtered out
4. The message text is forwarded to the configured agent via `handle_request_message()`
5. When the agent replies, `handle_response_message()` sends it back to LINE via the **Reply API**

---

## Known Limitations

### Reply API — 30-second timeout

The Reply API `reply_token` expires **30 seconds** after the original user message. If the agent takes longer than 30 seconds to respond (common with heavy AI workloads), the reply will fail with a warning logged and the response is discarded.

**Workaround**: Switch to the Push API. This requires `target_id` to be set and a small code change in `handle_response_message()`:

```python
# Replace reply_message() with push_message():
from linebot.v3.messaging import PushMessageRequest
await self.messaging_api.push_message(
    PushMessageRequest(to=self.target_id, messages=messages)
)
```

### Reply API — single-use token

Each `reply_token` can be used **exactly once**. Only the first non-`[...]` response from the agent is sent. Subsequent responses are silently discarded.

### Loading animation — 1:1 chats only

The `[...]` thinking indicator triggers LINE's [Loading Animation API](https://developers.line.biz/en/docs/messaging-api/use-loading-indicator/), which is supported **only in 1:1 direct messages** (UserSource). It is silently skipped for group chats and rooms.

### Message length

LINE's Reply API accepts up to **5 messages per reply**, each up to **5000 characters**. Responses longer than 25,000 characters are truncated; a warning is logged.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Webhook verification fails (400) | `channel_secret` mismatch | Double-check the secret in `.env` and LINE Developers Console |
| No inbound events | Webhook not enabled or URL mismatch | Turn **Use webhook** ON; verify the URL and path |
| `InvalidSignatureError` in logs | Wrong secret | Confirm `channel_secret` is correct |
| Reply fails with API error | `reply_token` expired (>30 s) | Consider switching to Push API (see above) |
| Webhook URL rejected by LINE | HTTP or self-signed cert | Use HTTPS with a trusted CA (Tailscale Funnel, ngrok, or Let's Encrypt) |
| Messages from unexpected users | `target_id` not set | Set `target_id` in `settings.json` to restrict to your user ID |
