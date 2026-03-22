import sys
import random
import asyncio

sys.path.append("../")
from yaclaw.channel import Channel

"""
Random talker channel plugin for YaClaw.

This plugin simulates a random talker for testing purposes.

ACP version: Message body is a JSON-RPC 2.0 object, following the ACP specification.
"""


class ChannelRandomTalker(Channel):
    counter = 0
    lock = asyncio.Lock()

    async def initialize(self, channel_name, channel_settings):
        # ACP protocol state
        self._init_state = "before_init"
        self._initialized = asyncio.Event()  # set after initialize response
        self._session_ready = asyncio.Event()  # set after session/new response
        self.num_method_calls = 0
        self.session_id = None
        self.shutdown = False
        return True

    async def start_listener(self):
        # initialize ACP connection
        while True:
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
            await self.log("dump", f"ACP initialize request: {body}")
            await self.handle_request_message(body)

            # Block until handle_response_message() processes the initialize response.
            await self._initialized.wait()

            if self._init_state == "before_session_new":
                break
            self._initialized.clear()
            self.num_method_calls = random.randint(700, 799)

        # new session
        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "session/new",
            "params": {"cwd": "/", "mcpServers": []},
        }
        await self.log("dump", f"New session request: {body}")
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
            await self.log("dump", f"User message request: {body}")
            await self.handle_request_message(body)

    async def handle_response_message(self, response):
        body = response.get("body", None)
        if body is None:
            return

        await self.log("dump", f"Received response: {body}")

        id_ = body.get("id", None)

        # ---- ACP handshake states ----------------------------------------

        if self._init_state == "before_init":
            if "error" in body:
                error = body["error"]
                code = error.get("code", "")
                message = error.get("message", "")

                if code != 7001:  #  7001: ID used.
                    msg = f"Initialization error ({code}): {message}, details: {error.get('data', {}).get('details', '')}"
                    print(f"Channel {self.channel_name}: " + msg)
                    raise Exception(msg)
            else:
                self._init_state = "before_session_new"
            self._initialized.set()
            msg = "ACP initialization response received."
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return

        elif self._init_state == "before_session_new":
            self._init_state = "ready"
            result = body.get("result", {})
            self.session_id = result.get("sessionId", None)
            self._session_ready.set()
            msg = f"Session ready. session_id={self.session_id}"
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return

        # ---- Notification (no id) ----------------------------------------

        if id_ is None:
            params = body.get("params", {})
            update = params.get("update", {})
            content = update.get("content", {})
            text = content.get("text", "")
            msg = f"Update: {text}"
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return

        # ---- Agent-initiated request (has id + method) -------------------
        # ---- Method response (session/prompt complete, etc.) -------------

        result = body.get("result", {})
        stop_reason = result.get("stopReason", "")
        msg = f"response ID {id_}: {stop_reason}"
        await self.log("info", msg)
        print(f"Channel {self.channel_name}: " + msg)

    async def stop(self):
        self.shutdown = True

    async def finalize(self):
        pass
