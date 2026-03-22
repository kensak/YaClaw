"""
ACP (Agent Client Protocol) agent plugin for YaClaw.

Connects to any ACP-compatible agent as a subprocess via stdio (JSON-RPC 2.0).
Raw pass-through proxy: the channel sends ACP JSON-RPC dicts as the message
`body`, and this plugin writes them directly to the subprocess stdin.
Responses and notifications received from stdout are forwarded back to the
channel as-is.

Supported agents (examples):
  GitHub Copilot CLI : command="copilot"  args=["--acp"]
  OpenAI Codex CLI   : command="npx"     args=["-y", "@zed-industries/codex-acp"]
  OpenCode           : command="opencode" args=["acp"]
  Gemini CLI         : command="gemini"   args=["--acp"]

settings.json example:
  {
    "plugin": "agent_acp",
    "command": "opencode",
    "args": ["acp"],
    "work_dir": "workspace/opencode",
    "env": {}
  }
"""

import asyncio
import json
import os
import shutil
import sys

sys.path.append("../")
from yaclaw.agent import Agent


class HandlerACP(Agent):
    """
    YaClaw Agent plugin that proxies ACP JSON-RPC messages to/from a
    subprocess via stdin/stdout.

    Message flow:
      Channel → handle_request_message(request)
              → write request["body"] (JSON-RPC dict) to process stdin

      Process stdout → _stdout_reader()
              → route JSON-RPC response/notification back to the channel(s)

    State maps
    ----------
    _id_map : dict[int|str, dict]
        JSON-RPC id → original YaClaw request dict.
        Populated when a request is sent; removed when the response arrives.
        Used to route responses back to the correct channel.

    _session_map : dict[str, list[dict]]
        sessionId → list of original YaClaw request dicts.
        Used to route id-less notifications to every channel that shares
        the session (multiple channels may hold the same session).

    _session_load_old_sid : dict[int|str, str | None]
        JSON-RPC id of a session/load request → the old sessionId that the
        requesting channel was previously registered under.
        Used to clean up the stale _session_map entry once session/load
        succeeds.
    """

    # ------------------------------------------------------------------
    # YaClaw lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, agent_name: str, agent_settings: dict) -> bool:
        # _ready_event blocks handle_request_message() until the subprocess
        # has started.  Cleared on process exit so the next restart cycle
        # also blocks correctly.
        self._ready_event = asyncio.Event()

        # The running subprocess (not yet started at this point).
        self._process: asyncio.subprocess.Process | None = None

        # When True, the restart loop exits instead of restarting.
        self._shutdown = False

        # JSON-RPC id → original YaClaw request.
        # Registered each time the channel sends a request; removed when the response arrives.
        self._id_map: dict[int | str, dict] = {}

        # sessionId → list of original YaClaw requests from channels that hold this session.
        # Used to resolve the routing destination for id-less notifications.
        # A list because multiple channels may share the same session.
        self._session_map: dict[str, list[dict]] = {}

        # JSON-RPC id of a session/load request → the old sessionId before the load.
        # Retained so the stale _session_map entry can be cleaned up once session/load succeeds.
        self._session_load_old_sid: dict[int | str, str | None] = {}

        # channel_name → the name of the channel to forward ACP chunks to.
        self._forward_acp_chunks_to: dict[str, str] = {}

        # Absolute path to the working directory for the subprocess (defaults to current dir).
        self.work_dir: str = os.path.abspath(self.settings.get("work_dir", "."))

        return True

    # ------------------------------------------------------------------
    # start_handler — spawn the subprocess and auto-restart on exit
    # ------------------------------------------------------------------

    async def start_handler(self) -> None:
        """Spawn the ACP subprocess and keep it alive with auto-restart."""
        command: str = self.settings["command"]
        # On Windows, resolve e.g. "opencode" → "opencode.cmd" automatically.
        command = shutil.which(command) or command
        args: list[str] = self.settings.get("args", [])
        extra_env: dict = self.settings.get("env", {})
        env = {**os.environ, **extra_env}

        while not self._shutdown:
            await self.log(
                "trace",
                f"Spawning ACP process: {command} {' '.join(args)}",
            )
            try:
                self._process = await asyncio.create_subprocess_exec(
                    command,
                    *args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.work_dir,
                    env=env,
                )
            except FileNotFoundError:
                msg = f"Command not found: {command}"
                await self.log("error", msg)
                print(msg)
                return  # Cannot start — do not retry.

            msg = f"ACP process started (PID={self._process.pid})."
            await self.log("trace", msg)
            print(msg)

            # Process is up — allow handle_request_message() to proceed.
            self._ready_event.set()

            try:
                # Run stdout reader, stderr logger, and process-exit watcher concurrently.
                # When any task finishes the TaskGroup cancels the rest.
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._stdout_reader())
                    tg.create_task(self._stderr_logger())
                    tg.create_task(self._process.wait())
            except* Exception as eg:
                for exc in eg.exceptions:
                    await self.log(
                        "error",
                        f"Exception in subprocess task: {exc}",
                    )

            # Process has exited — reset state before the next restart cycle.
            exit_code = self._process.returncode
            await self.log(
                "trace",
                "trace",
                f"ACP process exited (code={exit_code}).",
            )
            self._id_map.clear()
            self._session_map.clear()
            self._session_load_old_sid.clear()
            self._ready_event.clear()  # Block incoming requests until the next start.
            self._process = None

            if self._shutdown:
                break

            # Brief delay before restarting to prevent a tight crash-restart loop.
            await self.log("trace", f"Restarting in 3 seconds...")
            await asyncio.sleep(3)

    # ------------------------------------------------------------------
    # _stdout_reader — read JSON-RPC objects from stdout and route to channels
    # ------------------------------------------------------------------

    async def _stdout_reader(self) -> None:
        """Read JSON-RPC objects from process stdout and route to channels."""
        while True:
            line = await self._process.stdout.readline()
            if not line:
                # EOF — process closed stdout.
                break

            try:
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue  # Skip blank lines.
                obj = json.loads(text)
            except json.JSONDecodeError as e:
                await self.log(
                    "warning",
                    f"stdout JSON parse error: {e} | raw: {text[:200]}",
                )
                continue

            await self.log("dump", f"stdout: {obj}")

            id_ = obj.get("id")

            if id_ is not None and "method" not in obj:
                # ---- Response to our request (has an id, no method field) --------
                original_request = self._id_map.pop(id_, None)
                if original_request is None:
                    await self.log(
                        "warning",
                        f"Received response for unknown id={id_}. Ignoring.",
                    )
                    continue

                # Retrieve the method from the original request body.
                # (No need for a separate _id_method dict — the full request is stored in _id_map.)
                method = original_request.get("body", {}).get("method", "")

                if "result" in obj:

                    # Update _session_map only on successful responses.
                    if method == "session/new":
                        # A new session was created — register its sessionId.
                        new_sid = obj["result"].get("sessionId")
                        if new_sid:
                            self._session_map.setdefault(new_sid, []).append(
                                original_request
                            )
                            await self.log(
                                "trace",
                                f"session/new → registered sessionId={new_sid}",
                            )

                    elif method == "session/load":
                        # Session loaded successfully.
                        # The new sessionId was pre-registered in handle_request_message(),
                        # so here we only need to remove the stale old sessionId entry.
                        old_sid = self._session_load_old_sid.pop(id_, None)
                        if old_sid is not None:
                            old_list = self._session_map.get(old_sid)
                            if old_list is not None:
                                # Remove this channel's request from the old sessionId list.
                                from_ch = original_request.get("from_")
                                self._session_map[old_sid] = [
                                    r for r in old_list if r.get("from_") != from_ch
                                ]
                                if not self._session_map[old_sid]:
                                    # Delete the key when the list becomes empty.
                                    del self._session_map[old_sid]
                                await self.log(
                                    "trace",
                                    f"session/load → removed old sessionId={old_sid}",
                                )

                # Forward the response back to the channel.
                response = await self.create_response_skeleton(original_request)
                response["body"] = obj
                await self.handle_response_message(response)

            elif id_ is not None:
                # ---- Agent-initiated request (has both id and method) ------------
                # e.g. session/request_permission — the agent asks the channel for
                # approval before executing a tool call.  Route to all channels that
                # hold the session so they can send a response back.
                params = obj.get("params", {})
                session_id = params.get("sessionId")
                requests_list = (
                    self._session_map.get(session_id, []) if session_id else []
                )

                if not requests_list:
                    await self.log(
                        "warning",
                        f"Agent-initiated request '{obj.get('method')}' "
                        f"for unknown sessionId={session_id!r}. Ignoring.",
                    )
                    continue

                # Broadcast to all channels that share this session.
                for req in requests_list:
                    response = await self.create_response_skeleton(req)
                    response["body"] = obj
                    await self.handle_response_message(response)

            else:
                # ---- Notification (no id) ----------------------------------------
                # Look up the destination channel(s) via sessionId in _session_map.
                params = obj.get("params", {})
                session_id = params.get("sessionId")
                requests_list = (
                    self._session_map.get(session_id, []) if session_id else []
                )

                if not requests_list:
                    await self.log(
                        "warning",
                        f"Notification for unknown sessionId={session_id!r}. Ignoring.",
                    )
                    continue

                # Broadcast to all channels that share this session.
                for req in requests_list:
                    response = await self.create_response_skeleton(req)
                    response["body"] = obj

                    # If the channel has a `forward_acp_chunks_to` setting and the message is update chunk,
                    # override the destination.
                    forward_to = self._forward_acp_chunks_to.get(response.get("to_"))
                    if forward_to:
                        try:
                            sessionUpdate = obj["params"]["update"]["sessionUpdate"]
                        except KeyError:
                            sessionUpdate = ""
                        if sessionUpdate[-6:] == "_chunk":
                            response["to_"] = forward_to

                    await self.handle_response_message(response)

    # ------------------------------------------------------------------
    # _stderr_logger — log stderr output from the subprocess
    # ------------------------------------------------------------------

    async def _stderr_logger(self) -> None:
        """Log stderr output from the subprocess."""
        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                await self.log("stderr", f"stderr: {text}")

    # ------------------------------------------------------------------
    # handle_request_message — write incoming JSON-RPC from the channel to stdin
    # ------------------------------------------------------------------

    async def handle_request_message(self, request: dict) -> None:
        """Write the JSON-RPC body from the channel to the subprocess stdin."""
        # Wait until the subprocess is ready (also blocks during a restart).
        await self._ready_event.wait()

        if self._process is None or self._process.stdin is None:
            await self.log("error", "Process not available.")
            return

        body: dict = request.get("body", {})
        id_ = body.get("id")
        method = body.get("method", "")
        params = body.get("params", {})

        if id_ is not None:
            if "cwd" in params:
                # Override the cwd in the request with our `work_dir` setting.
                # This is to prevent malicious channel plugin from setting an arbitrary cwd.
                body["params"]["cwd"] = self.work_dir

            if method:
                # Our request to the agent — save id → request for response routing.
                self._id_map[id_] = request

            # If body has an id but no method, it is the channel's response to an
            # agent-initiated request (e.g. session/request_permission).
            # Just pass it through to stdin — no _id_map entry needed.

        if method == "initialize":
            # Set the forward_acp_chunks_to for the source channel if specified in the request's _meta.
            try:
                self._forward_acp_chunks_to[request["from_"]] = body["params"]["_meta"][
                    "yaclaw"
                ]["forward_acp_chunks_to"]
            except KeyError:
                pass

        elif method == "session/load":
            # Pre-register the new sessionId immediately so that any session/update
            # notification that arrives before the success response is not dropped.
            # Also save the old sessionId so it can be cleaned up when session/load succeeds.
            new_sid = (body.get("params") or {}).get("sessionId")
            from_ch = request.get("from_")
            if new_sid:
                # Find which sessionId this channel is currently registered under.
                old_sid = next(
                    (
                        sid
                        for sid, reqs in self._session_map.items()
                        if any(r.get("from_") == from_ch for r in reqs)
                    ),
                    None,
                )
                # Pre-register the new sessionId so incoming notifications are received.
                self._session_map.setdefault(new_sid, []).append(request)
                # Remember the old sessionId for cleanup after a successful response.
                self._session_load_old_sid[id_] = old_sid
                await self.log(
                    "trace",
                    f"session/load → pre-registered sessionId={new_sid} (old={old_sid})",
                )

        await self.log("dump", f"stdin: {body}")

        # Write the JSON-RPC object as a single line to stdin.
        line = json.dumps(body, ensure_ascii=False) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

    # ------------------------------------------------------------------
    # stop / finalize
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """Signal the restart loop to exit and terminate the subprocess."""
        self._shutdown = True
        self._ready_event.set()  # Unblock any handle_request_message() waiting on the event.
        if self._process is not None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass  # Process already exited — nothing to do.

    async def finalize(self) -> None:
        pass
