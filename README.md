# YaClaw

```
    ██╗   ██╗ █████╗ 
    ╚██╗ ██╔╝██╔══██╗
     ╚████╔╝ ███████║
      ╚██╔╝  ██╔══██║
       ██║   ██║  ██║
       ╚═╝   ╚═╝  ╚═╝
          ██████╗██╗      █████╗ ██╗    ██╗
         ██╔════╝██║     ██╔══██╗██║    ██║
         ██║     ██║     ███████║██║ █╗ ██║
         ██║     ██║     ██╔══██║██║███╗██║
         ╚██████╗███████╗██║  ██║╚███╔███╔╝
          ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
```

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL-lightgrey.svg)](https://learn.microsoft.com/windows/wsl/)
[![Status](https://img.shields.io/badge/status-experimental-orange.svg)]()

[日本語](README_ja.md)

> **Yet Another 'Claw'-like Tool — Use Your Favorite AI Coding CLI, Through Your Favorite Channel**

**A simple bridge that lets you remotely control an AI coding CLI from Discord.**

---

## What does it do?

YaClaw forwards messages you type in Discord directly to Codex CLI or Copilot CLI, then posts the AI's reply back to your channel. Because the agent runs on your own machine, **your full local environment is available — MCP config, file access, shell commands, everything.**

```
You ──[Discord message]──▶ YaClaw ──▶ Codex CLI / Copilot CLI
                                        (running on your machine)
   ◀──[Discord reply]──────────────────────────────────────────
```

---

## Features

- **Persistent sessions** — the same session stays alive until you restart; no lost context
- **Your environment, intact** — MCP settings, skills, and your filesystem work exactly as they do locally
- **Scheduler support** — send prompts to AI on a schedule to automate recurring tasks
- **Plugin architecture** — add new channels and agents by dropping in a Python file
- **Lightweight** — one command to launch: `uv run main.py`

---

## Supported Channels & Agents

| Type | Name | Plugin |
|------|------|--------|
| Channel | Discord | `channel_discord` |
| Channel | Scheduler | `channel_schedule` |
| Agent | GitHub Copilot CLI | `agent_copilot_cli` |
| Agent | OpenAI Codex CLI | `agent_codex_cli` |
| Agent | Echo (for testing) | `agent_echo` |

---

## Quick Start

### Prerequisites

- Linux or WSL (Windows native is unsupported — the Python `pty` library doesn't work on Windows)
- [uv](https://github.com/astral-sh/uv) installed
- Codex CLI or Copilot CLI installed
- A Discord bot already created

### Step 1: Clone

```bash
git clone https://github.com/kensak/YaClaw.git
cd YaClaw
```

### Step 2: Create a `.env` file

```bash
# .env
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here
```

### Step 3: Configure `settings.json`

```json
{
    "channel": {
        "discord": {
            "plugin": "channel_discord",
            "channel_id": "${DISCORD_CHANNEL_ID}",
            "bot_token": "${DISCORD_BOT_TOKEN}",
            "agent": "codex"
        }
    },
    "agent": {
        "codex": {
            "plugin": "agent_codex_cli",
            "work_dir": "workspace/codex"
        }
    }
}
```

> `agent.[name].plugin` is the filename (without extension) of a Python plugin in the `plugins/` folder.

### Step 4: Launch

```bash
uv run main.py
```

### Step 5: Test it

Send a message in your configured Discord channel. If the AI replies, you're good to go!

---

## Configuration Examples

The `examples/` folder contains ready-to-use configurations.

| File | Description |
|------|-------------|
| `settings_minimal_codex.json` | Minimal setup for Codex CLI |
| `settings_minimal_copilot.json` | Minimal setup for Copilot CLI |
| `settings_schedule.json` | Automated tasks via scheduler |
| `settings_forward_test.json` | Agent-to-agent forwarding test |

---

## Logging

Logs are written to `log/log-YYYYMMDD.json`. Pipe to `jq` for flexible filtering.

```bash
# Show only trace-level logs
cat log/log-20260301.json | jq -c -r 'select(.type == "trace") | [.time, .message] | join(" ")'
```

---

<details>
<summary>Writing Plugins</summary>

Drop a Python file in the `plugins/` folder and define **exactly one** class that subclasses `Channel` or `Agent`. The class name is arbitrary; the filename (without extension) is what you put in the `plugin` field of `settings.json`.

```json
{
    "channel": { "my_ch": { "plugin": "my_channel_plugin", "agent": "my_agent", ... } },
    "agent":   { "my_agent": { "plugin": "my_agent_plugin", ... } }
}
```

---

### Channel Plugin (basic)

See `plugins/channel_random_talker.py` for a minimal channel implementation.

```python
from yaclaw.channel import Channel

class MyChannel(Channel):

    async def initialize(self, channel_name, channel_settings):
        # One-time setup. self.channel_name and self.channel_settings
        # are already set by the framework at this point.
        # Return False to abort startup on failure.
        return True

    async def start_listener(self):
        # Put your incoming-message loop here.
        # Simplest form — pass a plain string to the agent:
        await self.handle_request_message("Hello!")

        # To control reply_to or other fields explicitly:
        # request = await self.create_request_skeleton()
        # request["body"] = "Hello!"
        # request["reply_to"] = "other_channel"
        # await self.handle_request_message(request)

    async def handle_response_message(self, response):
        # Called when the agent sends a reply.
        # response["body"] contains the response text.
        print(response["body"])

    async def stop(self):
        # Signal your loop to stop (e.g. set a shutdown flag).
        pass

    async def finalize(self):
        # Release any resources.
        pass
```

**Notes**

- `handle_request_message(msg)` accepts either a **plain string** or a **dict** (request message).
- `create_request_skeleton()` returns a dict with `from`, `to`, and `reply_to` pre-filled.
- `handle_response_message` is called serially via an internal queue — no need to worry about concurrent calls.

---

### SNS / Bot Channel Plugin

See `plugins/channel_discord.py` for an example that integrates with an external service.

```python
from yaclaw.channel import Channel

class MySnsBotChannel(Channel):

    async def initialize(self, channel_name, channel_settings):
        # Read credentials from settings.json
        self.token = channel_settings.get("bot_token", None)
        if self.token is None:
            return False   # Missing required setting — abort
        self.client = MyBotClient()
        return True

    async def start_listener(self):
        # Start the external library's async event loop here.
        # This method should block until the loop ends.
        @self.client.on_message
        async def on_message(msg):
            await self.handle_request_message(msg.text)

        await self.client.start(self.token)

    async def handle_response_message(self, response):
        body = response.get("body", "")
        if not body:          # Skip empty responses
            return
        await self.client.send(body)

    async def stop(self):
        await self.client.close()   # Always close the client cleanly

    async def finalize(self):
        pass
```

**Notes**

- `await` the external library's event loop inside `start_listener`.
- Guard against empty `response["body"]` to avoid sending blank messages.
- Close your client in `stop` so the `asyncio.TaskGroup` can shut down cleanly.

---

### Agent Plugin

See `plugins/agent_echo.py` for a minimal agent implementation.

```python
from yaclaw.agent import Agent

class MyAgent(Agent):

    async def initialize(self, agent_name, agent_settings):
        # One-time setup. Return False to abort startup.
        return True

    async def start_handler(self):
        # Runs concurrently with the request queue (e.g. to launch
        # an external process). For simple agents, just return.
        pass

    async def handle_request_message(self, request):
        # request["body"] contains the incoming text.
        body = request["body"]

        # Build a response skeleton (from/to/via are set automatically)
        response = await self.create_response_skeleton(request)
        response["body"] = f"Got it: {body}"

        # Send the response back to the channel (or next agent)
        await self.handle_response_message(response)

    async def stop(self):
        pass

    async def finalize(self):
        pass
```

**Notes**

- `start_handler` and `handle_request_message` run **concurrently** inside an `asyncio.TaskGroup`.
- Always use `create_response_skeleton(request)` — it handles forwarding chains (when `to` is a list) correctly.
- Calling `handle_response_message(response)` automatically routes the reply to the correct destination (channel or next agent) based on `response["to"]`.

</details>

---

<details>
<summary>Design Details (click to expand)</summary>

### Actors

There are two actor types — channels and agents — that communicate via message passing.

- **Channel**: Sends requests to an agent and receives responses. Responses are serialized via a queue.
- **Agent**: Handles requests from channels or other agents and returns responses. Requests are serialized via a queue.

### Message Routing

Notation like `{from: A, to: X}` represents a message (content omitted).

#### Basic Operation

```
Channel A ---{from: A, to: X}-----------> Agent X
          <--{from: X, to: A, via: X}---
```

#### Changing the Reply Destination with `reply_to`

Useful for a `schedule` channel that sends periodic prompts to an AI.

```
Channel A ---{from: A, to: X, reply_to: B}---> Agent X
Channel B <--{from: X, to: B, via: X}--------
```

#### Forwarding

Pre-specify a forwarding chain when sending a message.

```
Channel A  ---{from: A, to: [X, Y, Z]}---------> Agent X
Agent X    ---{from: X, to: [Y, Z], reply_to: A, via: X}---> Agent Y
Agent Y    ---{from: Y, to: Z, reply_to: A, via: [X, Y]}---> Agent Z
Agent Z    ---{from: Z, to: A, via: [X,Y,Z]}------------> Channel A
```

</details>

---

## Contributing

Bug reports, feature requests, and pull requests are all welcome!
If you build a plugin for a new channel or agent, feel free to share it.

---

## Disclaimer

This project is experimental and has minimal security considerations. You are responsible for protecting against information leaks via external services and communication channels. AI tools may behave unexpectedly, including hallucinations. Take appropriate precautions for your data. The author is not liable for any damages resulting from use of this software.

---

## License

[MIT License](LICENSE)
