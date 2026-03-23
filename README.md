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
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

[日本語](README_ja.md)

> **Yet Another 'Claw'-like Tool — Use Your Favorite AI Coding CLI, Through Your Favorite Channel**

**A simple bridge that lets you remotely control an AI coding CLI from Discord.**

> **ACP-native messages!** YaClaw now uses [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) JSON-RPC messages instead of plain text. Channels can leverage the full capabilities ACP offers — permission buttons, configuration menus, and much more to come.

---

## What does it do?

YaClaw forwards messages from Discord or LINE to your AI coding CLI and posts the replies back to your channel. Since the agent runs on your own machine with your configured working directory, your full local environment is available as-is — **AGENTS.md, SOUL.md, MCP config, skills, file access, shell commands, everything.**

```
You ──[Discord / LINE message]──▶ YaClaw ──▶ agent (Copilot / Codex / Gemini / OpenCode / …)
   ◀──[Discord / LINE reply]────────────────────────────────
```

---

## Features

- **ACP-based integration** — connects to any ACP-compatible CLI agent (Copilot, Codex, Gemini, OpenCode, …) via clean stdio JSON-RPC 2.0; channels can leverage ACP's full feature set — permission buttons, configuration menus, and more
- **Persistent sessions** — the same session stays alive until you restart; no lost context
- **Session selection** — view available sessions and pick one to resume
- **Thought output control** — enable/disable streaming of agent thought chunks per channel (`output_thought`)
- **Your environment, intact** — MCP settings, skills, and your instructions (SOUL.md, etc.) work exactly as they do locally
- **Scheduler support** — send prompts to an AI on a schedule to automate recurring tasks
- **Plugin architecture** — add new channels and agents by dropping in a Python file
- **Lightweight** — one command to launch: `uv run main.py`

---

## Available Channels & Agents

| Type | Name | Plugin |
|------|------|--------|
| Channel | Discord | `channel_discord` |
| Channel | LINE | `channel_line` — [setup guide](docs/channel_line_doc.md) |
| Channel | Scheduler | `channel_schedule` |
| Channel | Terminal (for testing) | `channel_terminal` |
| Channel | Random Talker (for testing) | `channel_random_talker` |
| Agent | Any ACP-compatible CLI (Copilot, Codex, Gemini, OpenCode, …) | `agent_acp` |
| Agent | Echo (for testing) | `agent_echo` |

---

## Quick Start

### Prerequisites

- Windows, Linux, or macOS
- [uv](https://github.com/astral-sh/uv) installed
- At least one ACP-compatible CLI installed (e.g. `copilot`, `opencode`, `gemini`, `codex`)
- A Discord / LINE bot already created

### Step 1: Clone

```bash
git clone https://github.com/kensak/YaClaw.git
cd YaClaw
```

### Step 2: Create a `.env` file

For Discord:
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
            "agent": "opencode",
            "output_thought": false,
            "require_mention": false
        }
    },
    "agent": {
        "opencode": {
            "plugin": "agent_acp",
            "command": "opencode",
            "args": ["acp"],
            "work_dir": "workspace/opencode"
        }
    }
}
```

> `agent.[name].plugin` is the filename (without extension) of a Python plugin in the `plugins/` folder.
>
> **Key `agent_acp` settings:**
> | Key | Description |
> |-----|-------------|
> | `command` | The CLI executable to launch |
> | `args` | Arguments passed to the CLI (include the ACP flag here) |
> | `work_dir` | Working directory for the agent process and for all the sessions |

### Step 4: Launch

```bash
uv run main.py
```

### Step 5: Test it

Send a message in your configured Discord / LINE channel. If the AI replies, you're good to go!

---

## Commands

Only available when both the CLI agent and the channel support it.
Each command displays a list of options and prompts the user to choose one.

- /sessions — switch to a different session
- /ai_models — change the AI model
- /modes — change the agent mode
- /reasoning_efforts — change the reasoning effort level

---

## Configuration Examples

The `examples/` folder contains ready-to-use configurations.

| File | Description |
|------|-------------|
| `settings_copilot_acp.json` | GitHub Copilot CLI via ACP |
| `settings_codex_acp.json` | OpenAI Codex CLI via ACP (using `@zed-industries/codex-acp`) |
| `settings_gemini_acp.json` | Google Gemini CLI via ACP |
| `settings_opencode_acp.json` | OpenCode via ACP |
| `settings_line.json` | LINE Messaging API channel |
| `settings_schedule.json` | Automated tasks via scheduler |
| `settings_forward_test.json` | Agent-to-agent forwarding test |
| `settings_terminal_conversation_test.json` | Terminal-to-agent test |

---

## Logging

Logs are written to `log/log-YYYYMMDD.json`. Pipe to `jq` for flexible filtering.

```bash
# Show only trace-level logs
cat log/log-20260101.json | jq -c -r 'select(.type == "trace" and .name == "main") | [.time, .message] | join(" ")'
```

---

<details>
<summary>Writing Plugins (click to expand)</summary>

Drop a Python file in the `plugins/` folder and define **exactly one** class that subclasses `Channel` or `Agent`. The class name is arbitrary; the filename (without extension) is what you put in the `plugin` field of `settings.json`.

```json
{
    "channel": { "my_ch": { "plugin": "my_channel_plugin", "agent": "my_agent", ... } },
    "agent":   { "my_agent": { "plugin": "my_agent_plugin", ... } }
}
```

---

### Channel Plugin

See `plugins/text_body/channel_random_talker_text_body.py` for a minimal text-body channel implementation.

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
- `create_request_skeleton()` returns a dict with `from_`, `to_`, and `reply_to` pre-filled.
- `handle_response_message` is called serially via an internal queue — no need to worry about concurrent calls.

For an ACP-body channel implementation, see `plugins/channel_random_talker.py` — it demonstrates the ACP handshake and method/notification handlers. See `plugins/channel_discord.py` for a real-world example with an external service.

---

### Agent Plugin

See `plugins/text_body/agent_echo_text_body.py` for a minimal text-body agent implementation.

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
- Always use `create_response_skeleton(request)` — it handles forwarding chains (when `to_` is a list) correctly.
- Calling `handle_response_message(response)` automatically routes the reply to the correct destination (channel or next agent) based on `response["to_"]`.

For ACP-body agent implementations, see:
- `plugins/agent_echo.py` for a minimal example.
- `plugins/agent_acp.py` for a full-spec example that integrates with AI coding CLIs.

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

You are responsible for protecting against information leaks via external services and communication channels. AI tools may behave unexpectedly, including hallucinations. Take appropriate precautions to protect your data. The author is not liable for any damages resulting from use of this software.

---

## License

[MIT License](LICENSE)
