import sys
import asyncio
import base64
import datetime
import io
import json
import time
import random
import re
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
  When the agent sends session/request_permission, a PermissionView with
  discord.ui.Button options is posted to Discord.  Button style is determined
  by the ACP PermissionOptionKind: allow_once/allow_always → Danger (red),
  reject_once/reject_always → Secondary (grey).  The view times out after
  180 seconds.

Typing indicator:
  While the agent is processing a session/prompt request, _typing_loop() sends
  a typing indicator every 5 seconds.  It is cancelled when stopReason arrives,
  or after 120 seconds as a safety timeout.  New messages are ignored while
  _is_processing is True.

/modes, /ai_models, /reasoning_efforts commands:
  Each command posts a Discord Select menu (ConfigSelectView) for the
  corresponding ACP configId ("mode", "model", "reasoning_effort").  The
  current value is pre-selected.  Commands are visually distinguished by the
  Select placeholder emoji (🎯 / 🤖 / 🧠).  Choosing an option sends
  session/set_config_option to the agent.  The menu times out after 60 seconds.
  All three commands are available even while _is_processing is True.

/sessions command:
  Posts a Discord Select menu (SessionSelectView) listing available sessions.
  All pages are fetched via session/list (pagination via nextCursor) before the
  menu is shown.  After the user picks a session, session/load is sent.
  Up to 25 sessions are shown (Discord's Select menu limit).
  Available only when the agent advertises session_list / session_load
  capabilities in its initialize response.
"""

_CHUNK_MAX = 1990  # leave headroom below Discord's 2000-char hard limit
_EDIT_INTERVAL = 1.5  # minimum seconds between message edits
_AUTO_FLUSH_DELAY = 5.0  # seconds after last chunk before auto-flushing

# ACP PermissionOptionKind values that represent an allow action.
_ALLOW_KINDS = {"allow_once", "allow_always"}

# Mapping from MIME type to a sensible default filename for Discord uploads.
_MIME_TO_EXT: dict[str, str] = {
    "image/png": "image.png",
    "image/jpeg": "image.jpg",
    "image/gif": "image.gif",
    "image/webp": "image.webp",
    "image/svg+xml": "image.svg",
    "audio/mpeg": "audio.mp3",
    "audio/mp4": "audio.mp4",
    "audio/ogg": "audio.ogg",
    "audio/wav": "audio.wav",
    "audio/webm": "audio.webm",
    "video/mp4": "video.mp4",
    "video/webm": "video.webm",
    "application/pdf": "document.pdf",
    "application/zip": "archive.zip",
    "application/json": "data.json",
    "text/plain": "text.txt",
    "text/markdown": "document.md",
    "text/html": "document.html",
    "text/csv": "data.csv",
}


def _mime_to_filename(mime_type: str) -> str:
    """Return a default filename for the given MIME type."""
    return _MIME_TO_EXT.get(mime_type, "attachment.bin")


def _filename_from_uri_and_mime(uri: str, mime_type: str) -> str:
    """Derive a filename from *uri* if it has an extension, else fall back to MIME type."""
    if uri:
        path = uri.split("?")[0].rstrip("/")
        basename = path.split("/")[-1]
        if basename and "." in basename:
            return basename
    return _mime_to_filename(mime_type)


def _extract_mcp_file_blocks(text: str) -> list[dict]:
    """Try to parse *text* as an MCP tool result and return non-text content blocks.

    MCP tools return results serialised as a JSON string with the shape:
      {"content": [{"type": "image", "data": "...", "mimeType": "..."}, ...]}

    If *text* is not valid JSON, it might be a message from a tool indicating
    that the output was too large and saved to a file. In that case, we try to
    read the file and return its content as a block.

    If *text* is not valid JSON or does not match that shape, returns [].
    """
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # Check for "Output too large... Saved to: <path>"
        # Tool output often looks like:
        # Output too large to read at once (57.5 KB). Saved to: C:\Users\tmvbb\AppData\Local\Temp\1774257056272-copilot-tool-output-khk6n9.txt
        match = re.search(r"Saved to:\s*(.+?\.txt)", text)
        if match:
            path = match.group(1).strip()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                # Recursive call to parse the content of the file
                return _extract_mcp_file_blocks(file_content)
            except Exception as e:
                print(f"Failed to read large output file {path}: {e}")
                return []
        return []

    if not isinstance(parsed, dict):
        return []

    blocks = parsed.get("content", [])
    if not isinstance(blocks, list):
        return []

    return [b for b in blocks if isinstance(b, dict) and b.get("type") != "text"]


class PermissionView(discord.ui.View):
    """A discord.ui.View that presents ACP permission options as buttons.

    Button style is determined by the ACP ``kind`` field:
      allow_once / allow_always  → ButtonStyle.danger  (red)
      reject_once / reject_always → ButtonStyle.secondary (grey)

    After any button is pressed all buttons are disabled and the message
    is edited in-place.  The same happens on timeout (180 s).
    """

    def __init__(self, options: list, on_select):
        super().__init__(timeout=180)
        self.message: discord.Message | None = None
        self._on_select = on_select
        for opt in options:
            kind = opt.get("kind", "")
            style = (
                discord.ButtonStyle.danger
                if kind in _ALLOW_KINDS
                else discord.ButtonStyle.secondary
            )
            button = discord.ui.Button(
                label=opt["name"],
                style=style,
                custom_id=opt["optionId"],
            )
            button.callback = self._make_callback(opt["optionId"])
            self.add_item(button)

    def _make_callback(self, option_id: str):
        async def callback(interaction: discord.Interaction):
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            await self._on_select(option_id)

        return callback

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class ConfigSelectView(discord.ui.View):
    """A generic discord.ui.View with a Select menu for choosing an ACP config option.

    The current value is pre-selected.  After a selection the menu is disabled
    and the message edited in-place.  Times out after 60 seconds.

    Differentiate commands visually via the *placeholder* emoji:
      /modes             → "🎯 Select a mode..."
      /ai_models         → "🤖 Select a model..."
      /reasoning_efforts → "🧠 Select a reasoning effort..."
    """

    def __init__(self, config_info: dict, on_select, placeholder: str = "Select..."):
        super().__init__(timeout=60)
        self.message: discord.Message | None = None
        self._on_select = on_select
        current_value = config_info.get("currentValue", "")
        select_options = [
            discord.SelectOption(
                label=opt["name"],
                value=opt["value"],
                default=(opt["value"] == current_value),
            )
            for opt in config_info.get("options", [])
        ]
        select = discord.ui.Select(
            placeholder=placeholder,
            options=select_options,
        )
        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        selected_value = interaction.data["values"][0]
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self._on_select(selected_value)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


def _format_session_label(session: dict) -> str:
    """Format a session dict into a ≤100-char Discord SelectOption label."""
    str_utc = session.get("updatedAt", "")
    if str_utc:
        try:
            dt_utc = datetime.datetime.strptime(str_utc, "%Y-%m-%dT%H:%M:%S.%f%z")
            dt_local = dt_utc.astimezone()
            time_str = dt_local.strftime("%m/%d %H:%M")
        except Exception:
            time_str = str_utc[:10]
    else:
        time_str = "??/?? ??:??"
    title = session.get("title", "") or session.get("sessionId", "")[:8]
    label = f"{time_str} {title}"
    return label[:100]


class SessionSelectView(discord.ui.View):
    """A discord.ui.View with a Select menu for picking a session to load.

    Shows up to 25 sessions (Discord's Select max).  The current session is
    pre-selected.  After selection the menu is disabled.  Times out after 60 s.
    """

    def __init__(self, sessions: list, on_select, current_session_id: str = ""):
        super().__init__(timeout=60)
        self.message: discord.Message | None = None
        self._on_select = on_select
        select_options = [
            discord.SelectOption(
                label=_format_session_label(s),
                value=s["sessionId"],
                default=(s["sessionId"] == current_session_id),
            )
            for s in sessions
        ]
        select = discord.ui.Select(
            placeholder="📂 Select a session...",
            options=select_options,
        )
        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        selected_value = interaction.data["values"][0]
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self._on_select(selected_value)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class ChannelDiscord(Channel):

    async def initialize(self, channel_name, channel_settings):
        await self.log("trace", "Initializing...")

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.output_thought = channel_settings.get("output_thought", False)
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

        # Auto-flush timer task (cancelled and recreated on each chunk)
        self._flush_task: asyncio.Task | None = None

        # Typing indicator task
        self._typing_task: asyncio.Task | None = None
        self._is_processing: bool = False

        # ACP config options (populated from session/new response and config_option_update)
        self.config_options: list = []

        # Last `sessionUpdate` value, for detecting change of chunk type
        self.last_session_update = None

        # Session list state (populated by session/list responses)
        self.sessions: list = []
        self.cursor: str | None = None
        self.capabilities: list = []
        self._collecting_sessions: bool = False

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

            # --- sessions command (/sessions) ---
            cmd = text.strip()
            if cmd == "/sessions":
                await self._session_ready.wait()
                if "session_list" not in self.capabilities:
                    await message.channel.send(
                        "Session listing not supported by the agent."
                    )
                    return
                self.sessions = []
                self.cursor = None
                self._collecting_sessions = True
                self.num_method_calls += 1
                acp_body = {
                    "jsonrpc": "2.0",
                    "id": self.num_method_calls,
                    "method": "session/list",
                    "params": {"cwd": "/dummy/dir"},
                }
                await self.log("dump", f"Session list request: {acp_body}")
                await self.handle_request_message(acp_body)
                return

            # --- config commands (/modes, /ai_models, /reasoning_efforts) ---
            if cmd in ("/modes", "/ai_models", "/reasoning_efforts"):
                await self._session_ready.wait()
                config_map = {
                    "/modes": ("mode", "🎯 Select a mode...", "mode"),
                    "/ai_models": ("model", "🤖 Select a model...", "model"),
                    "/reasoning_efforts": (
                        "reasoning_effort",
                        "🧠 Select a reasoning effort...",
                        "reasoning effort",
                    ),
                }
                config_id, placeholder, label = config_map[cmd]
                config_info = next(
                    (s for s in self.config_options if s["id"] == config_id), None
                )
                if config_info is None or not config_info.get("options"):
                    await message.channel.send(f"No {label}s available.")
                    return

                async def on_config_select(value: str, _config_id: str = config_id):
                    self.num_method_calls += 1
                    acp_body = {
                        "jsonrpc": "2.0",
                        "id": self.num_method_calls,
                        "method": "session/set_config_option",
                        "params": {
                            "sessionId": self.session_id,
                            "configId": _config_id,
                            "value": value,
                        },
                    }
                    await self.log("dump", f"Config set request: {acp_body}")
                    await self.handle_request_message(acp_body)

                current_value = config_info.get("currentValue", "")
                current_name = next(
                    (
                        o["name"]
                        for o in config_info["options"]
                        if o["value"] == current_value
                    ),
                    current_value,
                )
                view = ConfigSelectView(config_info, on_config_select, placeholder)
                view.message = await message.channel.send(
                    f"Current {label}: **{current_name}**", view=view
                )
                return

            # --- regular prompt ---
            if self._is_processing:
                return

            await self._session_ready.wait()

            self._is_processing = True
            self._typing_task = asyncio.get_event_loop().create_task(
                self._typing_loop(message.channel)
            )

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
                try:
                    agent_capabilities = body["result"]["agentCapabilities"]
                    if "list" in agent_capabilities.get("sessionCapabilities", {}):
                        self.capabilities.append("session_list")
                    if agent_capabilities.get("loadSession", False):
                        self.capabilities.append("session_load")
                except Exception:
                    pass
            self._initialized.set()
            msg = "ACP initialization response received."
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return

        elif self._init_state == "before_session_new":
            self._init_state = "ready"
            result = body.get("result", {})
            self.session_id = result.get("sessionId", None)
            if "configOptions" in result:
                self.config_options = result["configOptions"]
                await self.log("info", "Received initial config options.")
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
            if session_update == "agent_message_chunk":
                raw_content = update.get("content", [])
                if isinstance(raw_content, dict):
                    raw_content = [raw_content]
                is_new_sequence = self.last_session_update != "agent_message_chunk"
                first_text = is_new_sequence
                ch = await self._get_discord_channel()
                for block in raw_content:
                    block_type = block.get("type", "")
                    if block_type == "text":
                        text = block.get("text", "")
                        if text:
                            if first_text:
                                await self._flush_chunk()
                                text = "🗨️ " + text
                                first_text = False
                            await self._append_chunk(text)
                    else:
                        await self._flush_chunk()
                        if ch is not None:
                            await self._send_file_block(block, ch)
            elif session_update == "agent_thought_chunk":
                raw_content = update.get("content", {})
                if isinstance(raw_content, list):
                    raw_content = raw_content[0] if raw_content else {}
                text = raw_content.get("text", None)
                if self.output_thought and text:
                    if self.last_session_update != "agent_thought_chunk":
                        await self._flush_chunk()
                        text = "💭 " + text
                    await self._append_chunk(text)
            elif session_update == "tool_call_update":
                if update.get("status") == "completed":
                    ch = await self._get_discord_channel()
                    if ch is not None:
                        for item in update.get("content", []):
                            if item.get("type") == "content":
                                inner = item.get("content", {})
                                if inner.get("type") == "text":
                                    for block in _extract_mcp_file_blocks(
                                        inner.get("text", "")
                                    ):
                                        await self._send_file_block(block, ch)
            elif session_update == "config_option_update":
                if "configOptions" in update:
                    self.config_options = update["configOptions"]
                    await self.log("info", "config_options updated via notification.")
            elif session_update == "session_info_update":
                session_id = params.get("sessionId", "")
                title = update.get("title", None)
                if title and session_id:
                    session = next(
                        (s for s in self.sessions if s.get("sessionId") == session_id),
                        None,
                    )
                    if session is not None:
                        session["title"] = title
                        await self.log(
                            "info", f"Session {session_id} title updated: {title}"
                        )
            # Other notification types (plan, …) are intentionally ignored.
            self.last_session_update = session_update
            return

        # ---- Agent-initiated request (has id + method) -------------------

        method = body.get("method", "")
        if method == "session/request_permission":
            if self._typing_task is not None:
                self._typing_task.cancel()
                self._typing_task = None
            params = body.get("params", {})
            tool_call = params.get("toolCall", {})
            tool_call_id = tool_call.get("toolCallId", "")
            title = tool_call.get("title", "")
            options = params.get("options", [])

            async def on_select(option_id: str):
                acp_response = {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": {
                        "outcome": {"outcome": "selected", "optionId": option_id}
                    },
                }
                await self.log("dump", f"Permission response: {acp_response}")
                await self.handle_request_message(acp_response)

            view = PermissionView(options, on_select)
            ch = self.client.get_channel(self.channel_id)
            if ch is None:
                ch = await self.client.fetch_channel(self.channel_id)
            if ch:
                view.message = await ch.send(
                    f"Agent requests permission for tool call `{tool_call_id}`: {title}",
                    view=view,
                )
            return

        # ---- Method response (session/prompt complete, etc.) -------------

        error = body.get("error", None)
        if error:
            code = error.get("code", 0)
            message = error.get("message", "")
            if code == -32602 and re.match(r"Session .* not found", message):
                # Agent don't recognize the session ID anymore, likely due to an internal reset. Re-run the init sequence to get a new session ID.
                self._init_state = "before_init"
                self._initialized.clear()
                self._session_ready.clear()
                self.session_id = None
                asyncio.get_event_loop().create_task(self._acp_init_task())
            return

        result = body.get("result", {})
        if "configOptions" in result:
            self.config_options = result["configOptions"]
            await self.log("info", "config_options updated via method response.")

        if "sessions" in result:
            sessions = result["sessions"]
            self.sessions.extend(sessions)
            self.cursor = result.get("nextCursor", None)
            await self.log(
                "info",
                f"Received {len(sessions)} sessions. cursor={self.cursor}",
            )
            if self.cursor is not None and self._collecting_sessions:
                # Fetch next page
                self.num_method_calls += 1
                acp_body = {
                    "jsonrpc": "2.0",
                    "id": self.num_method_calls,
                    "method": "session/list",
                    "params": {"cwd": "/dummy/dir", "cursor": self.cursor},
                }
                await self.log("dump", f"Session list next page request: {acp_body}")
                await self.handle_request_message(acp_body)
            elif self._collecting_sessions:
                # All pages collected — post Select menu
                self._collecting_sessions = False
                ch = await self._get_discord_channel()
                if ch is not None:
                    if not self.sessions:
                        await ch.send("No sessions available.")
                    else:

                        async def on_session_select(session_id: str):
                            if "session_load" not in self.capabilities:
                                return
                            self.num_method_calls += 1
                            acp_body = {
                                "jsonrpc": "2.0",
                                "id": self.num_method_calls,
                                "method": "session/load",
                                "params": {
                                    "sessionId": session_id,
                                    "cwd": "/dummy/dir",
                                    "mcpServers": [],
                                },
                            }
                            await self.log("dump", f"Session load request: {acp_body}")
                            await self.handle_request_message(acp_body)

                        total = len(self.sessions)
                        header = f"Total sessions: {total}"
                        if total > 25:
                            header += " (showing first 25)"
                        view = SessionSelectView(
                            self.sessions[:25], on_session_select, self.session_id or ""
                        )
                        view.message = await ch.send(header, view=view)
            return

        if "sessionId" in result and not result.get("stopReason"):
            self.session_id = result["sessionId"]
            await self.log("info", f"Session changed. session_id={self.session_id}")

        stop_reason = result.get("stopReason", "")
        if stop_reason:
            if self._typing_task is not None:
                self._typing_task.cancel()
                self._typing_task = None
            self._is_processing = False
            await self._flush_chunk()
            msg = f"Response complete (stopReason: {stop_reason})"
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)

    # ------------------------------------------------------------------
    # Incremental chunk helpers
    # ------------------------------------------------------------------

    async def _typing_loop(self, ch) -> None:
        """Send typing indicator to *ch* every 5 s until cancelled or 30 s timeout."""
        deadline = asyncio.get_event_loop().time() + 30
        try:
            while asyncio.get_event_loop().time() < deadline:
                if ch is not None:
                    try:
                        await ch.typing()
                    except Exception:
                        pass
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        finally:
            self._is_processing = False

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
    # File / attachment helpers
    # ------------------------------------------------------------------

    async def _send_file_block(self, block: dict, ch) -> None:
        """Send a non-text ACP content block to Discord as a file upload or Embed.

        Supported block types:
          image / audio  — base64-encoded data → discord.File
          resource       — blob (base64) or text → discord.File
          resource_link  — URI reference → discord.Embed
        """
        block_type = block.get("type", "")
        try:
            if block_type in ("image", "audio"):
                data_b64 = block.get("data", "")
                mime_type = block.get("mimeType", "")
                filename = _filename_from_uri_and_mime(block.get("uri", ""), mime_type)
                raw = base64.b64decode(data_b64)
                await ch.send(file=discord.File(io.BytesIO(raw), filename=filename))

            elif block_type == "resource":
                resource = block.get("resource", {})
                uri = resource.get("uri", "")
                mime_type = resource.get("mimeType", "")
                filename = _filename_from_uri_and_mime(uri, mime_type)
                blob = resource.get("blob")
                if blob is not None:
                    raw = base64.b64decode(blob)
                    await ch.send(file=discord.File(io.BytesIO(raw), filename=filename))
                else:
                    text = resource.get("text", "")
                    await ch.send(
                        file=discord.File(
                            io.BytesIO(text.encode("utf-8")), filename=filename
                        )
                    )

            elif block_type == "resource_link":
                uri = block.get("uri", "")
                name = block.get("name") or uri
                description = block.get("description", "")
                mime_type = block.get("mimeType", "")
                embed = discord.Embed(title=name)
                if uri.startswith(("http://", "https://")):
                    embed.url = uri
                else:
                    uri_line = f"`{uri}`"
                    description = (
                        f"{uri_line}\n{description}".strip()
                        if description
                        else uri_line
                    )
                if description:
                    embed.description = description
                if mime_type:
                    embed.set_footer(text=mime_type)
                await ch.send(embed=embed)

            else:
                await self.log(
                    "warning",
                    f"Unknown ACP content block type: {block_type!r}, skipping.",
                )

        except Exception as e:
            await self.log(
                "error", f"Failed to send file block (type={block_type!r}): {e}"
            )

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
