import sys
import asyncio
import time
import random
import discord
from aiohttp.client_exceptions import ClientConnectorDNSError

sys.path.append("../")
from yaclaw.channel import Channel

"""
Discord channel plugin for YaClaw.

ACP version: Message body is a JSON-RPC 2.0 object, following the ACP specification.
Integrates with a specific Discord channel using the discord.py library.
cf. https://discordpy.readthedocs.io/en/stable/

ACP flow:
  start_listener() runs two concurrent tasks:
    _acp_init_task : sends ACP initialize → waits for _initialized event
                     → sends session/new → session_id is set by handle_response_message
                     → _session_ready is set, unblocking on_message
    _discord_task  : starts the Discord client immediately; on_message waits
                     for _session_ready before forwarding prompts

Incremental chunk display:
  Chunks arriving via ACP notifications are appended to _current_body and
  progressively reflected to Discord by editing _current_discord_msg.
  Edits are throttled to ≥1.5 s to stay within Discord rate limits.
  When _current_body would exceed 1990 chars the current message is finalised
  and a new one is started.

Permission requests:
  When the agent sends session/request_permission, the options are posted to
  Discord and _wait_permission_mode is set.  The user's next integer reply is
  forwarded as the ACP outcome.
"""

_CHUNK_MAX = 1990  # leave headroom below Discord's 2000-char hard limit
_EDIT_INTERVAL = 1.5  # minimum seconds between message edits
_AUTO_FLUSH_DELAY = 5.0  # seconds after last chunk before auto-flushing


class ChannelDiscord(Channel):

    async def initialize(self, channel_name, channel_settings):
        await self.log("trace", "Initializing...")

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.require_mention = channel_settings.get("require_mention", False)

        self.channel_id = self.channel_settings.get("channel_id", None)
        if self.channel_id is None:
            msg = "Discord channel ID not specified in settings. Aborting..."
            await self.log("error", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return False

        self.bot_token = self.channel_settings.get("bot_token", None)
        if self.bot_token is None:
            msg = "Discord bot token not specified in settings. Aborting..."
            await self.log("error", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return False

        # ACP protocol state
        self._init_state = "before_init"
        self._initialized = asyncio.Event()  # set after initialize response
        self._session_ready = asyncio.Event()  # set after session/new response
        self.num_method_calls = 0
        self.session_id = None

        # Incremental chunk state
        self._current_body: str = ""
        self._current_discord_msg: discord.Message | None = None
        self._last_edit_time: float = 0.0

        # Permission request state
        self._wait_permission_mode: bool = False
        self._wait_permission_id = None
        self._wait_permission_options: list = []

        # Auto-flush timer task (cancelled and recreated on each chunk)
        self._flush_task: asyncio.Task | None = None

        # Last `sessionUpdate` value, for detecting change of chunk type
        self.last_session_update = None

        await self.log("trace", "Initialized.")
        return True

    # ------------------------------------------------------------------
    # start_listener — run ACP init and Discord client concurrently
    # ------------------------------------------------------------------

    async def start_listener(self):
        await self.log("trace", "Starting listener...")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._acp_init_task())
            tg.create_task(self._discord_task())

    async def _acp_init_task(self):
        # ACP initialize
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
            self.num_method_calls = random.randint(500, 599)

        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "session/new",
            "params": {"cwd": "/dummy/dir", "mcpServers": []},
        }
        await self.log("dump", f"New session request: {body}")
        await self.handle_request_message(body)
        # _session_ready is set by handle_response_message() after session/new succeeds.

    async def _discord_task(self):
        """Start the Discord client and register event handlers."""

        @self.client.event
        async def on_ready():
            msg = f"Discord user {self.client.user} has logged in"
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)

        @self.client.event
        async def on_message(message):
            if message.author == self.client.user:
                return

            if len(message.mentions) == 0:
                if self.require_mention:
                    return
            else:
                if self.client.user not in message.mentions:
                    return

            text = message.content.strip()
            if not text:
                return

            # --- permission-response mode ---
            if self._wait_permission_mode:
                try:
                    index = int(text) - 1
                    if 0 <= index < len(self._wait_permission_options):
                        self._wait_permission_mode = False
                        body = {
                            "jsonrpc": "2.0",
                            "id": self._wait_permission_id,
                            "result": {
                                "outcome": {
                                    "outcome": "selected",
                                    "optionId": self._wait_permission_options[index][
                                        "optionId"
                                    ],
                                }
                            },
                        }
                        await self.log("dump", f"Permission response: {body}")
                        await self.handle_request_message(body)
                    else:
                        ch = self.client.get_channel(self.channel_id)
                        if ch:
                            await ch.send(
                                f"Invalid option. Please enter 1–{len(self._wait_permission_options)}."
                            )
                except ValueError:
                    pass
                return

            # --- regular prompt ---
            await self._session_ready.wait()

            self.num_method_calls += 1
            body = {
                "jsonrpc": "2.0",
                "id": self.num_method_calls,
                "method": "session/prompt",
                "params": {
                    "sessionId": self.session_id,
                    "prompt": [{"type": "text", "text": text}],
                },
            }
            await self.log("dump", f"User message request: {body}")
            await self.handle_request_message(body)

        await self.log("trace", "Starting Discord client...")
        try:
            await self.client.start(self.bot_token)
        except ClientConnectorDNSError as e:
            print(f"Failed to connect to Discord. DNS lookup failed: {e}")
            raise Exception(
                "Cannot look up `discord.com` or `gateway.discord.gg` in DNS. Check your network settings."
            ) from e

    # ------------------------------------------------------------------
    # handle_response_message — ACP response / notification dispatcher
    # ------------------------------------------------------------------

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
            session_update = update.get("sessionUpdate", "")
            # self.last_session_update is used to detect when the type of chunk changes, so we can add separators or icons in the Discord message for better readability.
            content = update.get("content", {})
            if isinstance(content, list):
                content = content[0] if content else {}
            text = content.get("text", None)
            if session_update == "agent_message_chunk":
                if text:
                    if self.last_session_update != "agent_message_chunk":
                        await self._flush_chunk()
                        text = "🗨️ " + text
                    await self._append_chunk(text)
            elif session_update == "agent_thought_chunk":
                if text:
                    if self.last_session_update != "agent_thought_chunk":
                        await self._flush_chunk()
                        text = "💭 " + text
                    await self._append_chunk(text)
            # Other notification types (session_info_update, plan, …) are
            # intentionally ignored in this basic implementation.
            self.last_session_update = session_update
            return

        # ---- Agent-initiated request (has id + method) -------------------

        method = body.get("method", "")
        if method == "session/request_permission":
            params = body.get("params", {})
            tool_call = params.get("toolCall", {})
            tool_call_id = tool_call.get("toolCallId", "")
            options = params.get("options", [])
            lines = [f"Agent requests permission for tool call `{tool_call_id}`:"]
            for i, opt in enumerate(options):
                lines.append(f"{i + 1}: {opt['name']}")
            lines.append("Enter option number:")
            ch = self.client.get_channel(self.channel_id)
            if ch is None:
                ch = await self.client.fetch_channel(self.channel_id)
            if ch:
                await ch.send("\n".join(lines))
            self._wait_permission_id = id_
            self._wait_permission_options = options
            self._wait_permission_mode = True
            return

        # ---- Method response (session/prompt complete, etc.) -------------

        result = body.get("result", {})
        stop_reason = result.get("stopReason", "")
        if stop_reason:
            await self._flush_chunk()
            msg = f"Response complete (stopReason: {stop_reason})"
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)

    # ------------------------------------------------------------------
    # Incremental chunk helpers
    # ------------------------------------------------------------------

    async def _get_discord_channel(self):
        ch = self.client.get_channel(self.channel_id)
        if ch is None:
            ch = await self.client.fetch_channel(self.channel_id)
        return ch

    async def _append_chunk(self, text: str):
        """Append *text* to the current in-progress Discord message."""
        ch = await self._get_discord_channel()
        if ch is None:
            await self.log(
                "warning", f"Could not find Discord channel {self.channel_id}."
            )
            return

        # If appending would exceed the limit, finalise the current message
        # and start a fresh one.
        if (
            self._current_discord_msg is not None
            and len(self._current_body) + len(text) > _CHUNK_MAX
        ):
            try:
                await self._current_discord_msg.edit(content=self._current_body)
            except Exception:
                pass
            self._current_body = ""
            self._current_discord_msg = None
            self._last_edit_time = 0.0

        self._current_body += text

        if self._current_discord_msg is None:
            # First chunk in this turn — create a new message.
            self._current_discord_msg = await ch.send(self._current_body)
            self._last_edit_time = time.monotonic()
        else:
            # Subsequent chunks — edit the existing message, throttled.
            now = time.monotonic()
            if now - self._last_edit_time >= _EDIT_INTERVAL:
                try:
                    await self._current_discord_msg.edit(content=self._current_body)
                    self._last_edit_time = now
                except Exception:
                    pass

        # (Re)start the auto-flush timer so the final edit fires even when
        # no stopReason arrives (e.g. chunks forwarded from schedule channel).
        if self._flush_task is not None:
            self._flush_task.cancel()
        self._flush_task = asyncio.get_event_loop().create_task(self._delayed_flush())

    async def _delayed_flush(self):
        """Wait _AUTO_FLUSH_DELAY seconds, then flush. Cancelled if another chunk arrives."""
        try:
            await asyncio.sleep(_AUTO_FLUSH_DELAY)
            await self.log("trace", "Auto-flush triggered after inactivity.")
            await self._flush_chunk()
        except asyncio.CancelledError:
            pass

    async def _flush_chunk(self):
        """Perform a final edit so the complete text is visible, then reset state."""
        # Cancel any pending auto-flush timer since we are flushing now.
        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None
        if self._current_discord_msg is not None and self._current_body:
            try:
                await self._current_discord_msg.edit(content=self._current_body)
            except Exception:
                pass
        self._current_body = ""
        self._current_discord_msg = None
        self._last_edit_time = 0.0
        self.last_session_update = None

    # ------------------------------------------------------------------
    # stop / finalize
    # ------------------------------------------------------------------

    async def stop(self):
        await self.log("trace", "Stopping...")
        if self.client.is_closed():
            await self.log("warning", "Already closed.")
        else:
            await self.client.close()
            await self.log("trace", "Closed.")
        await self.log("trace", "Stopped.")

    async def finalize(self):
        await self.log("trace", "Channel has been finalized.")
