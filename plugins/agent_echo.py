import sys

sys.path.append("../")
from yaclaw.agent import Agent

"""
Echo agent plugin for YaClaw.

This plugin simulates an echo agent for testing purposes.

ACP version: Message body is a JSON-RPC 2.0 object, following the ACP specification.
"""


class HandlerEcho(Agent):
    async def initialize(self, agent_name, agent_settings):
        self.registered_channels = []
        return True

    async def start_handler(self):
        await self.log("trace", f"Agent {self.agent_name}: Starting Echo...")

    async def handle_request_message(self, request):
        body = request["body"]
        await self.log(
            "agent_echo_dump",
            f"Agent {self.agent_name}: Received request: {body}",
        )

        if request.get("via", None) is not None:
            # This message is sent from another agent (forwarding).
            forwarding_body = body.copy()
            method = forwarding_body.get("method", "")
            if method == "session/update":
                try:
                    forwarding_body["params"]["update"]["content"][
                        "text"
                    ] += f" -> {self.agent_name}"
                except KeyError:
                    pass
            forwarding = await self.create_response_skeleton(request)
            forwarding["body"] = forwarding_body
            await self.log(
                "agent_echo_dump",
                f"Agent {self.agent_name}: Forwarding message: {forwarding_body}",
            )
            await self.handle_response_message(forwarding)
            return

        response = await self.create_response_skeleton(request)
        method = body.get("method", None)
        if method is None:
            return
        elif method == "initialize":
            id_ = body.get("id", 0)
            params = body.get("params", {})
            client_info = params.get("clientInfo", {})
            client_name = client_info.get("name", None)
            if client_name is not None:
                if client_name not in self.registered_channels:
                    self.registered_channels.append(client_name)
            resp_body = {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "protocolVersion": 1,
                    "agentInfo": {
                        "name": self.agent_name,
                        "title": self.agent_name,
                        "version": "1.0.0",
                    },
                    "authMethods": [],
                },
            }
        elif method == "session/new":
            id_ = body.get("id", 0)
            params = body.get("params", {})
            resp_body = {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {"sessionId": f"{self.agent_name}_session_1"},
            }
        elif method == "session/prompt":
            id_ = body.get("id", 0)
            params = body.get("params", {})
            session_id = params.get("sessionId", None)
            prompt = params.get("prompt", [{}])
            text = prompt[0].get("text", "")
            resp_body = {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {
                            "type": "text",
                            "text": text + f" -> {self.agent_name}",
                        },
                    },
                },
            }
            response["body"] = resp_body
            await self.log(
                "agent_echo_dump",
                f"Agent {self.agent_name}: Sending update: {resp_body}",
            )
            await self.handle_response_message(response)

            # Don't reuse the response. That will change the value of the previous message already in the queue.
            response = await self.create_response_skeleton(request)
            resp_body = {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {"stopReason": "end_turn"},
            }
        else:
            resp_body = {
                "jsonrpc": "2.0",
                "id": body.get("id", 0),
                "error": {
                    "code": -32601,
                    "message": f"Method {method} not found",
                },
            }
        response["body"] = resp_body
        await self.log(
            "agent_echo_dump",
            f"Agent {self.agent_name}: Sending response: {resp_body}",
        )
        await self.handle_response_message(response)

    async def stop(self):
        pass

    async def finalize(self):
        pass
