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
sys.path.append('../')
from yaclaw.channel import Channel
from yaclaw.log import log

"""
LINE Messaging API channel plugin for YaClaw.

Receives messages from LINE via Webhook and replies using the Reply API.
cf. https://github.com/line/line-bot-sdk-python

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
  - The reply_token is single-use. Only the first substantive response is sent
    via Reply API; any additional responses are logged and discarded.
  - The Loading Animation (shown when "[...]" is received) is supported only
    for 1:1 chats (UserSource). It is silently skipped for groups and rooms.
  - LINE requires the webhook endpoint to be reachable over HTTPS.
    Use a reverse proxy or a tunnelling tool (e.g. ngrok) for local development.
"""

# Reply API limits
_MAX_MSG_LEN  = 5000   # max characters per TextMessage
_MAX_MESSAGES = 5      # max messages per reply


class ChannelLine(Channel):

    async def initialize(self, channel_name, channel_settings):
        await log("trace", f"LINE channel {self.channel_name}: Initializing...")

        self.channel_access_token = channel_settings.get("channel_access_token", None)
        if self.channel_access_token is None:
            msg = f"Channel {self.channel_name}: LINE channel access token not specified in settings. Aborting..."
            await log("error", msg)
            print(msg)
            return False

        self.channel_secret = channel_settings.get("channel_secret", None)
        if self.channel_secret is None:
            msg = f"Channel {self.channel_name}: LINE channel secret not specified in settings. Aborting..."
            await log("error", msg)
            print(msg)
            return False

        self.target_id    = channel_settings.get("target_id",    None)
        if self.target_id == "null" or self.target_id == "":
            self.target_id = None
        self.host         = channel_settings.get("host",         "0.0.0.0")
        self.port         = channel_settings.get("port",         8000)
        self.webhook_path = channel_settings.get("webhook_path", "/webhook")

        # LINE SDK objects (kept alive for the duration of the channel)
        self.parser      = WebhookParser(self.channel_secret)
        configuration    = Configuration(access_token=self.channel_access_token)
        self.api_client  = AsyncApiClient(configuration)
        self.messaging_api = AsyncMessagingApi(self.api_client)

        # Reply token received from the latest inbound message.
        # Single-use and valid for only 30 seconds.
        self.current_reply_token = None
        # user_id of the latest sender; used for loading animation (1:1 only).
        self.current_user_id = None

        self._stop_event = asyncio.Event()
        self._runner     = None

        await log("trace", f"LINE channel {self.channel_name}: Initialized.")
        return True

    async def start_listener(self):
        await log("trace", f"LINE channel {self.channel_name}: Starting listener...")

        async def webhook_handler(request: web.Request) -> web.Response:
            signature = request.headers.get("X-Line-Signature", "")
            body = await request.text()

            await log("trace", f"LINE channel {self.channel_name}: Webhook received.")

            try:
                events = self.parser.parse(body, signature)
            except InvalidSignatureError:
                await log("warning", f"LINE channel {self.channel_name}: Invalid signature. Rejecting request.")
                return web.Response(status=400, text="Invalid signature")
            except Exception as e:
                await log("error", f"LINE channel {self.channel_name}: Failed to parse webhook body: {e}")
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
                        await log("trace",
                            f"LINE channel {self.channel_name}: "
                            f"Message from '{source_id}' filtered out (target_id={self.target_id}).")
                        continue

                # Store reply_token and sender id for use in handle_response_message
                self.current_reply_token = event.reply_token
                self.current_user_id = (
                    event.source.user_id if isinstance(event.source, UserSource) else None
                )

                await log("info",
                    f"LINE channel {self.channel_name}: Received message: {event.message.text}")
                await self.handle_request_message(event.message.text)

            return web.Response(status=200, text="OK")

        app = web.Application()
        app.router.add_post(self.webhook_path, webhook_handler)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        msg = (f"Channel {self.channel_name}: "
               f"LINE webhook server listening on {self.host}:{self.port}{self.webhook_path}")
        await log("info", msg)
        print(msg)

        # Block here until stop() is called
        await self._stop_event.wait()

    async def handle_response_message(self, response):
        response_body = response.get("body", "")
        await log("trace", f"LINE channel {self.channel_name}: Sending response: {response_body}")

        if not response_body:
            await log("trace", f"LINE channel {self.channel_name}: Response body is empty. Skipping...")
            return

        # "[...]" is the thinking indicator → show loading animation for 1:1 chats
        if response_body == "[...]":
            if self.current_user_id is not None and self.response_message_queue.empty():
                try:
                    await self.messaging_api.show_loading_animation(
                        ShowLoadingAnimationRequest(chat_id=self.current_user_id)
                    )
                except Exception as e:
                    await log("trace",
                        f"LINE channel {self.channel_name}: "
                        f"Loading animation not sent (may be unsupported in this context): {e}")
            return

        # Consume the reply_token (single-use, 30-second TTL)
        reply_token = self.current_reply_token
        if reply_token is None:
            await log("warning",
                f"LINE channel {self.channel_name}: "
                "No reply token available. The token may have already been used or expired (>30 s). "
                "Response will be discarded.")
            return
        self.current_reply_token = None  # clear immediately to prevent accidental reuse

        # Split long responses into at most _MAX_MESSAGES chunks of _MAX_MSG_LEN chars
        messages = []
        remaining = response_body
        while remaining and len(messages) < _MAX_MESSAGES:
            messages.append(TextMessage(text=remaining[:_MAX_MSG_LEN]))
            remaining = remaining[_MAX_MSG_LEN:]

        if remaining:
            await log("warning",
                f"LINE channel {self.channel_name}: "
                f"Response exceeded {_MAX_MESSAGES * _MAX_MSG_LEN} chars and was truncated.")

        try:
            await self.messaging_api.reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=messages)
            )
        except Exception as e:
            await log("error", f"LINE channel {self.channel_name}: Failed to send reply: {e}")

    async def stop(self):
        await log("trace", f"LINE channel {self.channel_name}: Stopping...")
        self._stop_event.set()

    async def finalize(self):
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        await self.api_client.close()
        await log("trace", f"LINE channel {self.channel_name} has been finalized.")
