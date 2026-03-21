import os
import sys
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor

sys.path.append("../")
from yaclaw.channel import Channel
from yaclaw.log import log

"""
Schedule channel plugin for YaClaw.

ACP version: Message body is a JSON-RPC 2.0 object, following the ACP specification.
Sends scheduled prompts to the connected ACP agent at predefined intervals.
Uses apscheduler library: https://github.com/agronholm/apscheduler

ACP flow:
  start_listener() runs ACP initialize → waits for _initialized →
  sends session/new → waits for _session_ready →
  registers scheduler jobs → starts scheduler (non-blocking) → returns.

Chunk / stopReason handling:
  All ACP notifications (chunks, stopReason, etc.) are logged and discarded.
  Set `forward_acp_chunks_to` in settings to have the agent route chunks
  directly to another channel (e.g. Discord) instead of returning them here.

Permission requests:
  session/request_permission is handled automatically:
  "allow_always" is preferred; "allow_once" is the fallback.
  If neither is available, a JSON-RPC error is returned.

settings.json example:
  {
    "plugin": "channel_schedule",
    "agent": "opencode",
    "forward_acp_chunks_to": "discord",
    "entry": {
      "morning_routine": {
        "everyday_at": "08:00",
        "message": "Good morning! Please summarise overnight activity."
      },
      "heartbeat": {
        "every_n_minutes": 30,
        "message": "Is everything okay?"
      }
    }
  }

Note: the per-entry `agent` and `reply_to` fields from the legacy (non-ACP)
format are no longer used.  The agent is taken from `channel_settings["agent"]`
and responses are received by this channel and discarded.
"""


class ChannelSchedule(Channel):

    async def initialize(self, channel_name, channel_settings):
        self.entry_list = channel_settings.get("entry", {})
        self.scheduler = AsyncIOScheduler(executors={"default": AsyncIOExecutor()})

        # ACP protocol state
        self._init_state = "before_init"
        self._initialized = asyncio.Event()  # set after initialize response
        self._session_ready = asyncio.Event()  # set after session/new response
        self.num_method_calls = 0
        self.session_id = None
        self.work_dir = None

        # Optional: direct chunk forwarding hint for the agent
        self.forward_acp_chunks_to = channel_settings.get("forward_acp_chunks_to", None)

        return True

    # ------------------------------------------------------------------
    # start_listener — ACP handshake then scheduler start (non-blocking)
    # ------------------------------------------------------------------

    async def start_listener(self):
        await log(self.channel_name, "info", "Starting listener...")
        print(f"Schedule Channel {self.channel_name}: Starting listener...")

        # ---- Step 1: ACP initialize ----
        self.num_method_calls += 1
        init_params = {
            "protocolVersion": 1,
            "clientInfo": {
                "name": self.channel_name,
                "title": self.channel_name,
                "version": "1.0.0",
            },
        }
        if self.forward_acp_chunks_to is not None:
            init_params["_meta"] = {
                "yaclaw": {"forward_acp_chunks_to": self.forward_acp_chunks_to}
            }
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "initialize",
            "params": init_params,
        }
        await log(self.channel_name, "dump", f"ACP initialize request: {body}")
        await self.handle_request_message(body)

        # ---- Step 2: wait for initialize response (cwd resolved) ----
        await self._initialized.wait()

        # ---- Step 3: session/new ----
        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "session/new",
            "params": {"cwd": self.work_dir, "mcpServers": []},
        }
        await log(self.channel_name, "dump", f"New session request: {body}")
        await self.handle_request_message(body)

        # ---- Step 4: wait for session/new response (session_id resolved) ----
        await self._session_ready.wait()

        # ---- Step 5: register jobs and start scheduler ----
        dest_agent = self.channel_settings.get("agent", None)
        if dest_agent is None:
            msg = "No agent specified in channel settings. No jobs will be scheduled."
            await log(self.channel_name, "error", msg)
            print(f"Channel {self.channel_name}: " + msg)
        else:
            for entry_name, entry in self.entry_list.items():
                message_text = entry.get("message", "")

                everyday_at = entry.get("everyday_at", None)
                if everyday_at is not None:
                    spl = everyday_at.split(":")
                    hour = int(spl[0])
                    minute = int(spl[1])
                    self.scheduler.add_job(
                        self._fire_prompt,
                        trigger="cron",
                        args=[dest_agent, message_text],
                        hour=hour,
                        minute=minute,
                        id=f"{entry_name}_cron",
                    )
                    await log(
                        self.channel_name,
                        "info",
                        f"Scheduled '{entry_name}' every day at {everyday_at}.",
                    )

                every_n_minutes = entry.get("every_n_minutes", None)
                if every_n_minutes is not None:
                    self.scheduler.add_job(
                        self._fire_prompt,
                        trigger="interval",
                        args=[dest_agent, message_text],
                        minutes=every_n_minutes,
                        id=f"{entry_name}_interval",
                    )
                    await log(
                        self.channel_name,
                        "info",
                        f"Scheduled '{entry_name}' every {every_n_minutes} min.",
                    )

        self.scheduler.start()
        msg = f"Scheduler started. session_id={self.session_id}"
        await log(self.channel_name, "info", msg)
        print(f"Channel {self.channel_name}: " + msg)

    async def _fire_prompt(self, dest_agent: str, message_text: str):
        """Build and dispatch a session/prompt ACP request."""
        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "session/prompt",
            "params": {
                "sessionId": self.session_id,
                "prompt": [{"type": "text", "text": message_text}],
            },
        }
        request = {
            "from_": self.channel_name,
            "to_": dest_agent,
            "body": body,
        }
        await log(self.channel_name, "dump", f"Scheduled prompt: {body}")
        await self.handle_request_message(request)

    # ------------------------------------------------------------------
    # handle_response_message — ACP response / notification dispatcher
    # ------------------------------------------------------------------

    async def handle_response_message(self, response):
        body = response.get("body", None)
        if body is None:
            return

        await log(self.channel_name, "dump", f"Received response: {body}")

        id_ = body.get("id", None)

        # ---- ACP handshake states ----------------------------------------

        if self._init_state == "before_init":
            self._init_state = "before_session_new"
            try:
                self.work_dir = os.path.abspath(
                    body["result"]["_meta"]["yaclaw"]["cwd"]
                )
            except Exception:
                self.work_dir = os.path.abspath(".")
            self._initialized.set()
            msg = f"ACP initialization response received. cwd={self.work_dir}"
            await log(self.channel_name, "info", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return

        if self._init_state == "before_session_new":
            self._init_state = "ready"
            result = body.get("result", {})
            self.session_id = result.get("sessionId", None)
            self._session_ready.set()
            msg = f"Session ready. session_id={self.session_id}"
            await log(self.channel_name, "info", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return

        # ---- Notification (no id) ----------------------------------------

        if id_ is None:
            params = body.get("params", {})
            update = params.get("update", {})
            session_update = update.get("sessionUpdate", "")
            if session_update.endswith("_chunk"):
                content = update.get("content", {})
                if isinstance(content, list):
                    content = content[0] if content else {}
                text = content.get("text", "")
                await log(self.channel_name, "dump", f"Chunk discarded: {text!r}")
            else:
                await log(
                    self.channel_name,
                    "dump",
                    f"Notification discarded: {session_update!r}",
                )
            return

        # ---- Agent-initiated request (has id + method) -------------------

        method = body.get("method", "")
        if method == "session/request_permission":
            params = body.get("params", {})
            options = params.get("options", [])
            chosen = next(
                (o for o in options if o.get("optionId") == "allow_always"), None
            )
            if chosen is None:
                chosen = next(
                    (o for o in options if o.get("optionId") == "allow_once"), None
                )
            if chosen is not None:
                reply_body = {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": {
                        "outcome": {
                            "outcome": "selected",
                            "optionId": chosen["optionId"],
                        }
                    },
                }
                await log(
                    self.channel_name,
                    "info",
                    f"Auto-approved permission with '{chosen['optionId']}'",
                )
            else:
                reply_body = {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "error": {"code": -32000, "message": "No allow option available"},
                }
                await log(
                    self.channel_name,
                    "warning",
                    "No allow option in session/request_permission. Returning error.",
                )
            await self.handle_request_message(reply_body)
            return

        # ---- Method response (session/prompt complete, etc.) -------------

        result = body.get("result", {})
        stop_reason = result.get("stopReason", "")
        if stop_reason:
            await log(
                self.channel_name,
                "info",
                f"Response complete (stopReason: {stop_reason}). Discarded.",
            )

    # ------------------------------------------------------------------
    # stop / finalize
    # ------------------------------------------------------------------

    async def stop(self):
        self.scheduler.remove_all_jobs()

    async def finalize(self):
        self.scheduler.shutdown()
