import sys
import random
import asyncio

sys.path.append("../")
from yaclaw.channel import Channel
from yaclaw.log import log

"""
Random talker channel plugin for YaClaw.

This plugin simulates a random talker for testing purposes.

ACP version: Message body is a JSON-RPC 2.0 object, following the ACP specification.
"""


class ChannelRandomTalker(Channel):
    counter = 0
    lock = asyncio.Lock()

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
            "channel_random_talker_dump",
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
            "channel_random_talker_dump",
            f"Channel {self.channel_name}: New session request: {body}",
        )
        await self.handle_request_message(body)

        # random talker loop
        while not self.shutdown:
            interval = random.random() * 3
            await asyncio.sleep(interval)
            async with ChannelRandomTalker.lock:
                ChannelRandomTalker.counter += 1
                self.num_method_calls += 1
                message = (
                    f"{self.channel_name}: Message #{str(ChannelRandomTalker.counter)}"
                )
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
            print(f"{self.channel_name} request ID {self.num_method_calls}: {message}")
            await log(
                "channel_random_talker_dump",
                f"Channel {self.channel_name}: User message request: {body}",
            )
            await self.handle_request_message(body)

    async def handle_response_message(self, response):
        body = response.get("body", None)
        await log(
            "channel_random_talker_dump",
            f"Channel {self.channel_name}: Received response: {body}",
        )
        id_ = body.get("id", None)
        if id_ == 1:
            msg = f"Channel {self.channel_name}: Initialization response received."
            await log("channel_random_talker", msg)
            print(msg)
        elif id_ == 2:
            result = body.get("result", {})
            self.session_id = result.get("sessionId", None)
            msg = f"Channel {self.channel_name}: New session response received. session ID: {self.session_id}"
            await log("channel_random_talker", msg)
            print(msg)
        elif id_ is None:
            params = body.get("params", {})
            update = params.get("update", {})
            content = update.get("content", {})
            text = content.get("text", "")
            msg = f"{self.channel_name} update: {text}"
            await log("channel_random_talker", msg)
            print(msg)
        else:
            result = body.get("result", {})
            stop_reason = result.get("stopReason", "")
            msg = f"Channel {self.channel_name}: response ID {id_}: {stop_reason}"
            await log("channel_random_talker", msg)
            print(msg)

    async def stop(self):
        self.shutdown = True

    async def finalize(self):
        pass
