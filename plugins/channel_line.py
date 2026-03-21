import os
import sys
import asyncio
from aiohttp import web
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    Configuration,
    AsyncApiClient,
    AsyncMessagingApi,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    UserSource,
    GroupSource,
    RoomSource,
)
from linebot.v3.exceptions import InvalidSignatureError

sys.path.append("../")
from yaclaw.channel import Channel
from yaclaw.log import log

"""
LINE Messaging API channel plugin for YaClaw.

ACP version: Message body is a JSON-RPC 2.0 object, following the ACP specification.
Receives messages from LINE via Webhook and replies using the Reply API.
cf. https://github.com/line/line-bot-sdk-python

ACP flow:
  start_listener() runs two concurrent tasks:
    _acp_init_task : sends ACP initialize → waits for _initialized event
                     → sends session/new (with cwd from initialize response)
                     → _session_ready is set, unblocking webhook_handler
    _webhook_task  : starts the aiohttp webhook server immediately;
                     incoming messages wait for _session_ready before
                     being forwarded as session/prompt requests

Chunk accumulation:
  ACP notifications with *_chunk updates are accumulated in _current_body.
  When stopReason is received the full accumulated text is sent in one
  Reply API call (LINE messages have a single-use 30-second reply token).

Permission requests:
  session/request_permission is handled automatically by the plugin:
  it selects "allow_always" if available, otherwise "allow_once".
  If neither option is available a JSON-RPC error is returned.

Required settings:
  channel_access_token : LINE channel access token
  channel_secret       : LINE channel secret
  agent                : name of the agent to forward messages to

Optional settings:
  target_id     : accept messages only from this LINE user ID or group ID
  host          : webhook server bind address (default: "0.0.0.0")
  port          : webhook server port (default: 8000)
  webhook_path  : URL path for the webhook endpoint (default: "/webhook")

Notes:
  - The Reply API reply_token expires 30 seconds after the original message.
    If the agent takes longer than 30 seconds to respond, the reply will fail.
  - The reply_token is single-use; it is consumed when _send_accumulated() fires.
  - The Loading Animation is shown immediately after session/prompt is sent
    and is supported only for 1:1 chats (UserSource).
  - LINE requires the webhook endpoint to be reachable over HTTPS.
    Use a reverse proxy or a tunnelling tool (e.g. ngrok) for local development.
"""

# Reply API limits
_MAX_MSG_LEN = 5000  # max characters per TextMessage
_MAX_MESSAGES = 5  # max messages per reply


class ChannelLine(Channel):

    async def initialize(self, channel_name, channel_settings):
        await self.log("trace", "Initializing...")

        self.channel_access_token = channel_settings.get("channel_access_token", None)
        if self.channel_access_token is None:
            msg = "LINE channel access token not specified in settings. Aborting..."
            await self.log("error", msg)
            print(msg)
            return False

        self.channel_secret = channel_settings.get("channel_secret", None)
        if self.channel_secret is None:
            msg = "LINE channel secret not specified in settings. Aborting..."
            await self.log("error", msg)
            print(msg)
            return False

        self.target_id = channel_settings.get("target_id", None)
        if self.target_id == "null" or self.target_id == "":
            self.target_id = None
        self.host = channel_settings.get("host", "0.0.0.0")
        self.port = channel_settings.get("port", 8000)
        self.webhook_path = channel_settings.get("webhook_path", "/webhook")

        # LINE SDK objects (kept alive for the duration of the channel)
        self.parser = WebhookParser(self.channel_secret)
        configuration = Configuration(access_token=self.channel_access_token)
        self.api_client = AsyncApiClient(configuration)
        self.messaging_api = AsyncMessagingApi(self.api_client)

        # Reply token received from the latest inbound message.
        # Single-use and valid for only 30 seconds.
        self.current_reply_token = None
        # user_id of the latest sender; used for loading animation (1:1 only).
        self.current_user_id = None

        # ACP protocol state
        self._init_state = "before_init"
        self._initialized = asyncio.Event()  # set after initialize response
        self._session_ready = asyncio.Event()  # set after session/new response
        self.num_method_calls = 0
        self.session_id = None
        self.work_dir = None

        # Chunk accumulation buffer
        self._current_body: str = ""

        self._stop_event = asyncio.Event()
        self._runner = None

        await self.log("trace", "Initialized.")
        return True

    # ------------------------------------------------------------------
    # start_listener — run ACP init and webhook server concurrently
    # ------------------------------------------------------------------

    async def start_listener(self):
        await self.log("trace", "Starting listener...")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._acp_init_task())
            tg.create_task(self._webhook_task())

    async def _acp_init_task(self):
        """Send ACP initialize, then session/new once the cwd is known."""
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

        # Block until handle_response_message() processes the initialize response
        # and populates self.work_dir.
        await self._initialized.wait()

        self.num_method_calls += 1
        body = {
            "jsonrpc": "2.0",
            "id": self.num_method_calls,
            "method": "session/new",
            "params": {"cwd": self.work_dir, "mcpServers": []},
        }
        await self.log("dump", f"New session request: {body}")
        await self.handle_request_message(body)
        # _session_ready is set by handle_response_message() after session/new succeeds.

    async def _webhook_task(self):
        """Start the aiohttp webhook server and block until stop() is called."""

        async def webhook_handler(request: web.Request) -> web.Response:
            signature = request.headers.get("X-Line-Signature", "")
            body = await request.text()

            await self.log("trace", f"Webhook received.")

            try:
                events = self.parser.parse(body, signature)
            except InvalidSignatureError:
                await self.log("warning", "Invalid signature. Rejecting request.")
                return web.Response(status=400, text="Invalid signature")
            except Exception as e:
                await self.log("error", f"Failed to parse webhook body: {e}")
                return web.Response(status=400, text="Bad request")

            for event in events:
                if not isinstance(event, MessageEvent):
                    continue
                if not isinstance(event.message, TextMessageContent):
                    continue

                # Filter by target_id when configured
                if self.target_id is not None:
                    source = event.source
                    if isinstance(source, UserSource):
                        source_id = source.user_id
                    elif isinstance(source, GroupSource):
                        source_id = source.group_id
                    elif isinstance(source, RoomSource):
                        source_id = source.room_id
                    else:
                        source_id = None

                    if source_id != self.target_id:
                        await self.log(
                            "trace",
                            f"Message from '{source_id}' filtered out (target_id={self.target_id}).",
                        )
                        continue

                # Store reply_token and sender id for use in _send_accumulated()
                self.current_reply_token = event.reply_token
                self.current_user_id = (
                    event.source.user_id
                    if isinstance(event.source, UserSource)
                    else None
                )

                await self.log("info", f"Received message: {event.message.text}")

                # Gate: wait until ACP session is ready before forwarding
                await self._session_ready.wait()

                self.num_method_calls += 1
                acp_body = {
                    "jsonrpc": "2.0",
                    "id": self.num_method_calls,
                    "method": "session/prompt",
                    "params": {
                        "sessionId": self.session_id,
                        "prompt": [{"type": "text", "text": event.message.text}],
                    },
                }
                await self.log("dump", f"User message request: {acp_body}")
                await self.handle_request_message(acp_body)

                # Show loading animation immediately after forwarding the prompt
                if self.current_user_id is not None:
                    try:
                        await self.messaging_api.show_loading_animation(
                            ShowLoadingAnimationRequest(chat_id=self.current_user_id)
                        )
                    except Exception as e:
                        await self.log(
                            "trace",
                            f"Loading animation not sent (may be unsupported in this context): {e}",
                        )

            return web.Response(status=200, text="OK")

        app = web.Application()
        app.router.add_post(self.webhook_path, webhook_handler)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        msg = (
            f"Channel {self.channel_name}: "
            f"LINE webhook server listening on {self.host}:{self.port}{self.webhook_path}"
        )
        await self.log("info", msg)
        print(msg)

        # Block here until stop() is called
        await self._stop_event.wait()

    # ------------------------------------------------------------------
    # handle_response_message — ACP response / notification dispatcher
    # ------------------------------------------------------------------

    async def handle_response_message(self, response):
        body = response.get("body", None)
        if body is None:
            return

        await self.log("channel_line_dump", f"Received response: {body}")

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
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)
            return

        if self._init_state == "before_session_new":
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
            if session_update.endswith("_chunk"):
                content = update.get("content", {})
                if isinstance(content, list):
                    content = content[0] if content else {}
                text = content.get("text", "")
                if text:
                    self._current_body += text
                    await self.log(
                        "dump",
                        f"Chunk accumulated ({len(self._current_body)} chars total)",
                    )
            # Other notification types (session_info_update, plan, …) are
            # intentionally ignored in this basic implementation.
            return

        # ---- Agent-initiated request (has id + method) -------------------

        method = body.get("method", "")
        if method == "session/request_permission":
            params = body.get("params", {})
            options = params.get("options", [])
            # Prefer allow_always, fall back to allow_once, error otherwise
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
                await self.log(
                    "dump",
                    f"Auto-approved permission request with '{chosen['optionId']}'",
                )
            else:
                reply_body = {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "error": {"code": -32000, "message": "No allow option available"},
                }
                await self.log(
                    "warning",
                    "No allow option in session/request_permission. Returning error.",
                )
            await self.handle_request_message(reply_body)
            return

        # ---- Method response (session/prompt complete, etc.) -------------

        result = body.get("result", {})
        stop_reason = result.get("stopReason", "")
        if stop_reason:
            await self._send_accumulated()
            msg = f"Response complete (stopReason: {stop_reason})"
            await self.log("info", msg)
            print(f"Channel {self.channel_name}: " + msg)

    # ------------------------------------------------------------------
    # _send_accumulated — send buffered chunks via LINE Reply API
    # ------------------------------------------------------------------

    async def _send_accumulated(self):
        """Send the accumulated chunk body as a LINE reply, then reset state."""
        text = self._current_body
        self._current_body = ""

        if not text:
            await self.log("trace", "No accumulated text to send.")
            return

        reply_token = self.current_reply_token
        if reply_token is None:
            await self.log(
                "warning",
                "No reply token available. The token may have already been used or expired (>30 s). "
                "Response will be discarded.",
            )
            return
        self.current_reply_token = None  # clear immediately to prevent accidental reuse

        # Split long responses into at most _MAX_MESSAGES chunks of _MAX_MSG_LEN chars
        messages = []
        remaining = text
        while remaining and len(messages) < _MAX_MESSAGES:
            messages.append(TextMessage(text=remaining[:_MAX_MSG_LEN]))
            remaining = remaining[_MAX_MSG_LEN:]

        if remaining:
            await self.log(
                "warning",
                f"Response exceeded {_MAX_MESSAGES * _MAX_MSG_LEN} chars and was truncated.",
            )

        try:
            await self.messaging_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=messages)
            )
        except Exception as e:
            await self.log("error", f"Failed to send reply: {e}")

    # ------------------------------------------------------------------
    # stop / finalize
    # ------------------------------------------------------------------

    async def stop(self):
        await self.log("trace", "Stopping...")
        self._stop_event.set()

    async def finalize(self):
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        await self.api_client.close()
        await self.log("trace", "LINE channel has been finalized.")
