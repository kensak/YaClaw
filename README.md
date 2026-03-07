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

[日本語](README_ja.md)

> **Yet Another 'Claw'-like Tool — Use Your Favorite AI Coding CLI, Through Your Favorite Channel**
>
> Control your favorite AI CLI tool running in your favorite working folder, remotely through your Discord channel.

YaClaw is a small variant of OpenClaw. It routes messages you send from a Discord channel to an AI coding CLI tool (Codex CLI, Copilot CLI) running in interactive mode, and sends the AI's responses back to the channel.

The AI coding CLI tool is launched in interactive mode in a specified folder. The same session persists until a restart. Because the tool runs in your usual environment, features like MCP and skills work exactly the same way as they normally would.

Support for new channels (such as Discord) and agents (such as AI coding CLI tools) is enabled through plugins.

## Installation

```bash
git clone https://github.com/kensak/YaClaw.git
```

Windows OS is not supported directly because the Python `pty` library does not work on Windows. Please use it through WSL.

## Usage

```bash
cd YaClaw
uv run main.py
```

## Configuration

Configuration is done in `settings.json`.

Minimal configuration:
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

Put your Discord bot token and channel ID (created in advance) in a `.env` file at the project root folder.

.env
```
DISCORD_BOT_TOKEN=xyz...
DISCORD_CHANNEL_ID=12345...
```

Set `agent.[agent_name].plugin` to the filename (without extension) of the plugin (Python file) in the `plugins/` folder.

* Codex CLI: `agent_codex_cli`
* Copilot CLI: `agent_copilot_cli`
* Echo agent for testing: `agent_echo`

## Logging

Logs are written to `log/log-YYYYMMDD.json`.

You can filter logs flexibly by piping to `jq`.

Example: Show only logs with type `trace`
```bash
cat log/log-20260301.json | jq -c -r 'select(.type == "trace") | [.time, .message] | join(" ")'
```

## Design

### Actors

There are two types of actors — channels and agents — and the model is based on message passing between them.

* **Channel**: Sends requests to an agent and receives responses. Responses are serialized via a queue.

* **Agent**: Returns responses to requests from channels or other agents. Requests are serialized via a queue.

### Message Routing

Notation like `{from: A, to: X}` represents a message. (Message content is omitted.)

#### Basic Operation

Channel A ---{from: A, to: X}--> Agent X  
Agent X ---{from: X, to: A, via: X}--> Channel A

#### Changing the Reply Destination with `reply_to`

This is useful for implementing, for example, a `schedule` channel that periodically sends prompts to an AI (like a heartbeat).

Channel A ---{from: A, to: X, reply_to: B}--> Agent X  
Agent X ---{from: X, to: B, via: X}--> Channel B

#### Forwarding

You can pre-specify forwarding destinations when sending a message.

Channel A ---{from: A, to: [X, Y, Z]}--> Agent X  
Agent X ---{from: X, to: [Y, Z], reply_to: A, via: X}--> Agent Y  
Agent Y ---{from: Y, to: Z, reply_to: A, via: [X, Y]}--> Agent Z  
Agent Z ---{from: Z, to: A, via: [X, Y, Z]}--> Channel A

## Disclaimer

This project is experimental and has had little consideration given to security. Users are responsible for taking their own measures to protect against information leaks from SNS services and communication channels. AI coding CLI tools may behave unexpectedly, including hallucinations. Users are responsible for taking necessary precautions such as protecting data from the tools. The author assumes no liability for any damages arising from the use of this program.
