import sys
import asyncio
import json

sys.path.append("../")
from yaclaw.channel import Channel
from yaclaw.log import log

"""
Terminal channel plugin for YaClaw.

This plugin is for testing.
It sends terminal inputs to the agent and displays the agent's responses, updates and notifications in the terminal.

ACP version: Message body is a JSON-RPC 2.0 object, following the ACP specification.
"""


class ChannelTerminal(Channel):

    @classmethod
    async def async_input(cls, prompt: str) -> str:
        print(prompt, end="", flush=True)
        return (await asyncio.to_thread(sys.stdin.readline)).rstrip("\n")

    async def initialize(self, channel_name, channel_settings):
        self.num_method_calls = 0
        self.session_id = None
        self.shutdown = False
        return True

    async def start_listener(self):
        # initialize ACP connection
        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientInfo": {
                    "name": self.channel_name,
                    "title": self.channel_name,
                    "version": "1.0.0",
                },
            },
        }
        await log(
            "channel_terminal_dump",
            f"Channel {self.channel_name}: ACP initialize request: {body}",
        )
        await self.handle_request_message(body)

        # new session
        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "session/new",
            "params": {"cwd": "/", "mcpServers": []},
        }
        await log(
            "channel_terminal_dump",
            f"Channel {self.channel_name}: New session request: {body}",
        )
        await self.handle_request_message(body)

        print("-------------------")
        print("🖥 Terminal channel")
        print("-------------------")

        await asyncio.sleep(2)

        # terminal loop
        while not self.shutdown:
            message = await ChannelTerminal.async_input("\n> ")
            if message.strip() == "":
                continue
            self.num_method_calls += 1
            body = {
                "jsonrpc": "2.0",
                "id": self.num_method_calls,
                "method": "session/prompt",
                "params": {
                    "sessionId": self.session_id,
                    "prompt": [
                        {
                            "type": "text",
                            "text": message,
                        }
                    ],
                },
            }
            await log(
                "channel_terminal_dump",
                f"Channel {self.channel_name}: User message request: {body}",
            )
            await self.handle_request_message(body)
            await asyncio.sleep(2)

    async def handle_response_message(self, response):
        body = response.get("body", None)
        await log(
            "channel_terminal_dump",
            f"Channel {self.channel_name}: Received response: {body}",
        )
        print(json.dumps(body, indent=2))
        id_ = body.get("id", None)
        if id_ == 1:
            msg = f"Channel {self.channel_name}: Initialization response received."
            await log("channel_terminal", msg)
            print(msg)
        elif id_ == 2:
            result = body.get("result", {})
            self.session_id = result.get("sessionId", None)
            msg = f"Channel {self.channel_name}: New session response received. session ID: {self.session_id}"
            await log("channel_terminal", msg)
            print(msg)
        elif id_ is None:
            params = body.get("params", {})
            update = params.get("update", {})
            content = update.get("content", {})
            text = content.get("text", "")
            msg = f"{self.channel_name} update: {text}"
            await log("channel_terminal", msg)
            print(text)
        else:
            result = body.get("result", {})
            stop_reason = result.get("stopReason", "")
            msg = f"Channel {self.channel_name}: response ID {id_}: {stop_reason}"
            await log("channel_terminal", msg)
            print(msg)

    async def stop(self):
        self.shutdown = True

    async def finalize(self):
        pass
