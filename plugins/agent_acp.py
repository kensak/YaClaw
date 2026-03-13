"""
ACP (Agent Client Protocol) agent plugin for YaClaw.

Connects to any ACP-compatible agent as a subprocess via stdio (JSON-RPC 2.0).
Replaces the pexpect-based copilot/codex plugins with a clean protocol-level
integration.

Supported agents (examples):
  GitHub Copilot CLI : command="copilot"  args=["--acp"]
  OpenAI Codex CLI   : command="npx"     args=["-y", "@zed-industries/codex-acp"]
  OpenCode           : command="opencode" args=[]
  Gemini CLI         : command="gemini"   args=[]

settings.json example:
  {
    "plugin": "agent_acp",
    "command": "copilot",
    "args": ["--acp"],
    "work_dir": "workspace/copilot",
    "auto_approve": true,
    "env": {}
  }
"""

import asyncio
import os
import sys
from typing import Any

import acp
from acp import (
    PROTOCOL_VERSION,
    NewSessionResponse,
    ReadTextFileResponse,
    RequestPermissionResponse,
    WriteTextFileResponse,
    spawn_agent_process,
)
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    DeniedOutcome,
    Implementation,
)

sys.path.append("../")
from yaclaw.agent import Agent
from yaclaw.log import log


class _ACPClient:
    """
    ACP Client callbacks — receives streaming updates and file-system requests
    from the remote ACP agent.
    """

    def __init__(self, auto_approve: bool, work_dir: str, output_thought: bool = False):
        self._auto_approve = auto_approve
        self._work_dir = work_dir
        self._output_thought = output_thought
        self.chunks: list[str] = []
        self.thought_chunks: list[str] = []

    # ------------------------------------------------------------------
    # session/update — streaming content from the agent
    # ------------------------------------------------------------------
    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        if isinstance(update, AgentMessageChunk):
            content = update.content
            if hasattr(content, "text"):
                self.chunks.append(content.text)
        elif isinstance(update, AgentThoughtChunk):
            content = update.content
            if hasattr(content, "text"):
                self.thought_chunks.append(content.text)

    # ------------------------------------------------------------------
    # session/request_permission — tool execution approval
    # ------------------------------------------------------------------
    async def request_permission(
        self, options: list, session_id: str, tool_call: Any, **kwargs: Any
    ) -> RequestPermissionResponse:
        if self._auto_approve and options:
            chosen_id = options[0].option_id
            return RequestPermissionResponse(outcome=AllowedOutcome(optionId=chosen_id))
        return RequestPermissionResponse(outcome=DeniedOutcome())

    # ------------------------------------------------------------------
    # fs/read_text_file
    # ------------------------------------------------------------------
    async def read_text_file(
        self, path: str, session_id: str, **kwargs: Any
    ) -> ReadTextFileResponse:
        full_path = path if os.path.isabs(path) else os.path.join(self._work_dir, path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            content = f"[Error reading file: {e}]"
        return ReadTextFileResponse(content=content)

    # ------------------------------------------------------------------
    # fs/write_text_file
    # ------------------------------------------------------------------
    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        full_path = path if os.path.isabs(path) else os.path.join(self._work_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return None

    # ------------------------------------------------------------------
    # on_connect — called when the connection to the agent is established
    # ------------------------------------------------------------------
    def on_connect(self, conn: Any) -> None:
        pass

    # ------------------------------------------------------------------
    # ext_method / ext_notification — forward unknown extension calls
    # ------------------------------------------------------------------
    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        pass


class HandlerACP(Agent):
    """YaClaw Agent plugin that connects to an ACP-compatible subprocess."""

    # ------------------------------------------------------------------
    # YaClaw lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_name: str, agent_settings: dict) -> bool:
        self._client = _ACPClient(
            auto_approve=agent_settings.get("auto_approve", False),
            work_dir=os.path.abspath(agent_settings.get("work_dir", ".")),
            output_thought=agent_settings.get("output_thought", False),
        )
        self._conn = None
        self._session_id: str | None = None
        self._ready_event = asyncio.Event()
        self._prompt_lock = asyncio.Lock()
        return True

    async def start_handler(self) -> None:
        """Spawn the ACP subprocess, handshake, and keep it alive."""
        command: str = self.settings["command"]
        args: list[str] = self.settings.get("args", [])
        work_dir: str = os.path.abspath(self.settings.get("work_dir", "."))
        extra_env: dict = self.settings.get("env", {})

        env = {**os.environ, **extra_env}

        await log("acp", f"Agent {self.agent_name}: spawning ACP process: {command} {' '.join(args)}")

        try:
            async with spawn_agent_process(
                self._client,
                command,
                *args,
                env=env,
                cwd=work_dir,
                transport_kwargs={"limit": 4 * 1024 * 1024},  # 4MB: avoid LimitOverrunError on large JSON responses
            ) as (conn, process):
                self._conn = conn

                # ACP handshake
                await conn.initialize(
                    protocol_version=PROTOCOL_VERSION,
                    client_info=Implementation(name="YaClaw", version="0.2.0"),
                )
                await log("acp", f"Agent {self.agent_name}: ACP initialize OK.")

                resp: NewSessionResponse = await conn.new_session(cwd=work_dir, mcp_servers=[])
                self._session_id = resp.session_id
                await log("acp", f"Agent {self.agent_name}: session created: {self._session_id}")

                self._ready_event.set()

                msg = f"Agent {self.agent_name}: ACP agent is ready."
                await log("acp", msg)
                print(msg)

                # Wait for the subprocess to exit
                await process.wait()
                await log("acp", f"Agent {self.agent_name}: ACP process exited.")

        except Exception as e:
            msg = f"Agent {self.agent_name}: failed to start ACP process: {e}"
            await log("error", msg)
            print(msg)
            raise
        finally:
            self._ready_event.set()  # unblock any waiting handle_request_message

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def handle_request_message(self, request: dict) -> None:
        await self._ready_event.wait()

        if self._conn is None or self._session_id is None:
            msg = f"Agent {self.agent_name}: ACP connection not available."
            await log("error", msg)
            print(msg)
            return

        body: str = request.get("body", "")

        # Only one prompt at a time per session
        async with self._prompt_lock:
            self._client.chunks.clear()
            self._client.thought_chunks.clear()

            # Send typing indicators while waiting for the agent
            self._prompt_done = False
            typing_task = asyncio.create_task(self._send_typing_indicators(request))

            try:
                await self._conn.prompt(
                    session_id=self._session_id,
                    prompt=[acp.schema.TextContentBlock(type="text", text=body)],
                )
            finally:
                self._prompt_done = True
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

            if self._client._output_thought and self._client.thought_chunks:
                thought_text = "💭 " + "".join(self._client.thought_chunks).strip()
                thought_msg = await self.create_response_skeleton(request)
                thought_msg["body"] = thought_text
                await self.handle_response_message(thought_msg)

            result = "".join(self._client.chunks).strip()
            await log("acp", f"Agent {self.agent_name}: response: {result[:200]}...")

            response = await self.create_response_skeleton(request)
            response["body"] = result
            await self.handle_response_message(response)

    async def _send_typing_indicators(self, request: dict) -> None:
        """Send '[...]' to the channel every 5 seconds while the agent is working."""
        try:
            while not self._prompt_done:
                await asyncio.sleep(5)
                if not self._prompt_done:
                    indicator = await self.create_response_skeleton(request)
                    indicator["body"] = "[...]"
                    await self.handle_response_message(indicator)
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        self._ready_event.set()  # unblock any waiting coroutines

    async def finalize(self) -> None:
        pass
