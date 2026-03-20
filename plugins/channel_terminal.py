import os
import sys
import asyncio
import json
import datetime
from zoneinfo import ZoneInfo

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
    num_instance = 0

    @classmethod
    async def async_input(cls, prompt: str) -> str:
        print(prompt, end="", flush=True)
        return (await asyncio.to_thread(sys.stdin.readline)).rstrip("\n")

    async def initialize(self, channel_name, channel_settings):
        if ChannelTerminal.num_instance > 0:
            msg = f"Channel {self.channel_name}: ChannelTerminal can have only one instance. Aborting..."
            await log("error", msg)
            print(msg)
            return False
        ChannelTerminal.num_instance = 1
        self.init_state = "before_init"
        self._initialized = asyncio.Event()
        self._wait_response = asyncio.Event()
        self.num_method_calls = 0
        self.session_id = None
        self.shutdown = False
        self.work_dir = None
        self.capabilities = []
        self.sessions = []
        self.config_options = []
        self.cursor = None
        self.wait_answer_mode = False
        self.wait_answer_mode_id = 0
        self.wait_answer_mode_options = []
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
        await self._initialized.wait()
        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "session/new",
            "params": {"cwd": self.work_dir, "mcpServers": []},
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
            if self.wait_answer_mode:
                self.wait_answer_mode = False
                body = {
                    "jsonrpc": "2.0",
                    "id": self.wait_answer_mode_id,
                    "result": {
                        "outcome": {
                            "outcome": "selected",
                            "optionId": self.wait_answer_mode_options[
                                int(message.strip()) - 1
                            ]["optionId"],
                        }
                    },
                }
                await log(
                    "channel_terminal_dump",
                    f"Channel {self.channel_name}: Permission request handled: {body}",
                )
                await self.handle_request_message(body)
                continue
            if message[0] == "/":  # command
                args = message.split(" ")
                command = args[0][1:].strip()
                if command == "sessions":
                    if "session_list" not in self.capabilities:
                        print("Session listing not supported by the agent.")
                        continue
                    self.sessions = []
                    self.cursor = None
                    while True:
                        self.num_method_calls += 1
                        body = {
                            "jsonrpc": "2.0",
                            "id": self.num_method_calls,
                            "method": "session/list",
                            "params": {"cwd": self.work_dir},
                        }
                        if self.cursor is not None:
                            body["params"]["cursor"] = self.cursor
                        await log(
                            "channel_terminal_dump",
                            f"Channel {self.channel_name}: Session list request: {body}",
                        )
                        await self.handle_request_message(body)
                        await self._wait_response.wait()
                        self._wait_response.clear()
                        if self.cursor is None:
                            break
                    print(f"Total sessions: {len(self.sessions)}")
                    for i, session in enumerate(self.sessions):
                        sid = session.get("sessionId", "")
                        str_utc = session.get("updatedAt", "")
                        # example: "2025-10-29T14:22:15.421Z"
                        if str_utc == "":
                            time_str = "unknown time     "
                        else:
                            # str_utc2 = str_utc.replace("Z", "+00:00")
                            datetime_utc = datetime.datetime.strptime(
                                str_utc, "%Y-%m-%dT%H:%M:%S.%f%z"
                            )
                            datetime_jst = datetime_utc.astimezone(
                                datetime.timezone(datetime.timedelta(hours=+9))
                            )
                            time_str = datetime_jst.strftime("%Y-%m-%d %H:%M:%S")
                        print(
                            f"{"*" if sid == self.session_id else " "}{(i+1):2d}: {time_str} {session.get('title', '')}"
                        )
                    continue
                elif command == "session":  # load session
                    if "session_load" not in self.capabilities:
                        print("Session loading not supported by the agent.")
                        continue
                    if len(self.sessions) == 0:
                        print("No sessions available.")
                        continue
                    if len(args) < 2:
                        print("No session number provided.")
                        continue
                    try:
                        index = int(args[1])
                        if index < 1 or index > len(self.sessions):
                            print("Invalid session number.")
                            continue
                        session = self.sessions[index - 1]
                        self.session_id = session["sessionId"]

                        self.num_method_calls += 1
                        body = {
                            "jsonrpc": "2.0",
                            "id": self.num_method_calls,
                            "method": "session/load",
                            "params": {
                                "sessionId": self.session_id,
                                "cwd": self.work_dir,
                                "mcpServers": [],
                            },
                        }
                        await log(
                            "channel_terminal_dump",
                            f"Channel {self.channel_name}: Session load request: {body}",
                        )
                        await self.handle_request_message(body)
                    except ValueError:
                        print("Invalid input.")
                    continue
                elif command == "modes":
                    mode_info = next(
                        (s for s in self.config_options if s["id"] == "mode"), None
                    )
                    if mode_info is not None:
                        print("Available modes:")
                        current_value = mode_info.get("currentValue", "")
                        for i, option in enumerate(mode_info["options"]):
                            print(
                                f"{"*" if option["value"] == current_value else " "}{(i+1):2d}: {option["name"]}"
                            )
                    continue
                elif command == "mode":
                    mode_info = next(
                        (s for s in self.config_options if s["id"] == "mode"), None
                    )
                    if mode_info is None:
                        print("No modes available.")
                        continue
                    if len(args) < 2:
                        print("No mode number provided.")
                        continue
                    try:
                        index = int(args[1])
                        if index < 1 or index > len(mode_info["options"]):
                            print("Invalid mode number.")
                            continue
                        mode = mode_info["options"][index - 1]

                        self.num_method_calls += 1
                        body = {
                            "jsonrpc": "2.0",
                            "id": self.num_method_calls,
                            "method": "session/set_config_option",
                            "params": {
                                "sessionId": self.session_id,
                                "configId": "mode",
                                "value": mode["value"],
                            },
                        }
                        await log(
                            "channel_terminal_dump",
                            f"Channel {self.channel_name}: Mode set request: {body}",
                        )
                        await self.handle_request_message(body)
                    except ValueError:
                        print("Invalid input.")
                    continue
                elif command == "models":
                    mode_info = next(
                        (s for s in self.config_options if s["id"] == "model"), None
                    )
                    if mode_info is not None:
                        print("Available models:")
                        current_value = mode_info.get("currentValue", "")
                        for i, option in enumerate(mode_info["options"]):
                            print(
                                f"{"*" if option["value"] == current_value else " "}{(i+1):2d}: {option["name"]}"
                            )
                    continue
                elif command == "model":
                    model_info = next(
                        (s for s in self.config_options if s["id"] == "model"), None
                    )
                    if model_info is None:
                        print("No models available.")
                        continue
                    if len(args) < 2:
                        print("No model number provided.")
                        continue
                    try:
                        index = int(args[1])
                        if index < 1 or index > len(model_info["options"]):
                            print("Invalid model number.")
                            continue
                        model = model_info["options"][index - 1]

                        self.num_method_calls += 1
                        body = {
                            "jsonrpc": "2.0",
                            "id": self.num_method_calls,
                            "method": "session/set_config_option",
                            "params": {
                                "sessionId": self.session_id,
                                "configId": "model",
                                "value": model["value"],
                            },
                        }
                        await log(
                            "channel_terminal_dump",
                            f"Channel {self.channel_name}: Model set request: {body}",
                        )
                        await self.handle_request_message(body)
                    except ValueError:
                        print("Invalid input.")
                    continue
                elif command == "reasoning_efforts":
                    mode_info = next(
                        (
                            s
                            for s in self.config_options
                            if s["id"] == "reasoning_effort"
                        ),
                        None,
                    )
                    if mode_info is not None:
                        print("Available reasoning efforts:")
                        current_value = mode_info.get("currentValue", "")
                        for i, option in enumerate(mode_info["options"]):
                            print(
                                f"{"*" if option["value"] == current_value else " "}{(i+1):2d}: {option["name"]}"
                            )
                    continue
                elif command == "reasoning_effort":
                    reasoning_effort_info = next(
                        (
                            s
                            for s in self.config_options
                            if s["id"] == "reasoning_effort"
                        ),
                        None,
                    )
                    if reasoning_effort_info is None:
                        print("No reasoning efforts available.")
                        continue
                    if len(args) < 2:
                        print("No reasoning effort number provided.")
                        continue
                    try:
                        index = int(args[1])
                        if index < 1 or index > len(reasoning_effort_info["options"]):
                            print("Invalid reasoning effort number.")
                            continue
                        reasoning_effort = reasoning_effort_info["options"][index - 1]

                        self.num_method_calls += 1
                        body = {
                            "jsonrpc": "2.0",
                            "id": self.num_method_calls,
                            "method": "session/set_config_option",
                            "params": {
                                "sessionId": self.session_id,
                                "configId": "reasoning_effort",
                                "value": reasoning_effort["value"],
                            },
                        }
                        await log(
                            "channel_terminal_dump",
                            f"Channel {self.channel_name}: Reasoning effort set request: {body}",
                        )
                        await self.handle_request_message(body)
                    except ValueError:
                        print("Invalid input.")
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
        id_ = body.get("id", None)
        if id_ is not None:
            print(json.dumps(body, indent=2))

        if self.init_state == "before_init":  # initialize
            self.init_state = "before_session_new"
            try:
                self.work_dir = os.path.abspath(
                    body["result"]["_meta"]["yaclaw"]["cwd"]
                )
            except Exception:
                self.work_dir = os.path.abspath(".")

            try:
                agentCapabilities = body["result"]["agentCapabilities"]
                if "list" in agentCapabilities.get("sessionCapabilities", {}):
                    self.capabilities.append("session_list")
                if agentCapabilities.get("loadSession", False):
                    self.capabilities.append("session_load")
            except Exception:
                pass

            self._initialized.set()
            msg = f"Channel {self.channel_name}: Initialization response received."
            await log("channel_terminal", msg)
            print(msg)

        elif self.init_state == "before_session_new":  # session/new
            self.init_state = "after_session_new"
            result = body.get("result", {})
            self.session_id = result.get("sessionId", None)
            msg = f"Channel {self.channel_name}: New session response received. session ID: {self.session_id}"
            await log("channel_terminal", msg)
            print(msg)
            self.config_options = result.get("configOptions", [])

        elif id_ is None:  # notification or update
            params = body.get("params", {})
            update = params.get("update", {})
            sessionUpdate = update.get("sessionUpdate", "")
            if sessionUpdate[-6:] == "_chunk":
                content = update.get("content", {})
                if isinstance(content, list):
                    content = content[0]
                text = content.get("text", "")
                msg = f"{self.channel_name} update: {text}"
                await log("channel_terminal", msg)
                print(text, end="")
            elif sessionUpdate == "session_info_update":
                sessionId = params.get("sessionId", "")
                title = update.get("title", None)
                if title:
                    session = next(
                        (s for s in self.sessions if s["id"] == sessionId), None
                    )
                    if session is not None:
                        session["title"] = title
                        msg = f"Channel {self.channel_name}: Session {sessionId} title updated: {title}"
                        await log("channel_terminal", msg)
                        print(msg)
            elif sessionUpdate == "plan":
                entries = update.get("entries", [])
                print("Plan:")
                for i, entry in enumerate(entries):
                    print(
                        f"{(i+1):2d}: {entry['priority']:6s} {entry['status']:7s} {entry['content']}"
                    )
            else:
                print(json.dumps(body, indent=2))

        else:
            method = body.get("method", "")
            if method == "session/request_permission":  # permission request from agent
                id_ = body.get("id", None)
                params = body.get("params", {})
                toolCall = params.get("toolCall", {})
                toolCallId = toolCall.get("toolCallId", "")
                options = params.get("options", [])
                print(f"\nAgent requests permission for tool call {toolCallId}:")
                for i, option in enumerate(options):
                    print(f"{(i+1):2d}: {option['name']}")
                self.wait_answer_mode_id = id_
                self.wait_answer_mode_options = options
                self.wait_answer_mode = True
                print("Enter option number: ", end="", flush=True)
            else:  # method response
                result = body.get("result", {})
                if "sessions" in result:
                    sessions = result["sessions"]
                    self.sessions.extend(sessions)
                    self.cursor = result.get("nextCursor", None)
                    msg = f"Channel {self.channel_name}: Received {len(sessions)} sessions. Cursor: {self.cursor}"
                    await log("channel_terminal", msg)
                    print(msg)
                    self._wait_response.set()
                elif "configOptions" in result:
                    self.config_options = result["configOptions"]
                    msg = f"Channel {self.channel_name}: Received config options."
                    await log("channel_terminal", msg)
                    print(msg)
                else:
                    stop_reason = result.get("stopReason", "")
                    msg = (
                        f"Channel {self.channel_name}: response ID {id_}: {stop_reason}"
                    )
                    await log("channel_terminal", msg)
                    print("\n" + msg)

    async def stop(self):
        self.shutdown = True

    async def finalize(self):
        pass
