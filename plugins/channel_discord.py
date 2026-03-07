import os
import sys
import asyncio
import discord
from aiohttp.client_exceptions import ClientConnectorDNSError
sys.path.append('../')
from yaclaw.channel import Channel
from yaclaw.log import log
from yaclaw.util import eval_env_var
"""
Discord channel plugin for YaClaw.

This plugin integrates with a specific Discord channel using the discord.py library.
cf. https://discordpy.readthedocs.io/en/stable/
"""

class ChannelDiscord(Channel):

  async def initialize(self, channel_name, channel_settings):
    await log("trace", f"Discord channel {self.channel_name}: Initializing...")
    # Create an Intents object that responds to all events
    intents = discord.Intents.default()
    intents.message_content = True # Grant permission to receive message content
    # Create the Discord client
    self.client = discord.Client(intents=intents)
    self.require_mention = channel_settings.get("require_mention", False)
    await log("trace", f"Discord channel {self.channel_name}: Initialized.")
    return True

  async def start_listener(self):
    await log("trace", f"Discord channel {self.channel_name}: Starting listener...")

    # prepare discord channel ID
    self.channel_id = eval_env_var(self.channel_settings.get("channel_id", "${DISCORD_CHANNEL_ID}"))
    if self.channel_id is None:
      raise Exception(f"Discord channel {self.channel_name}: Discord channel ID not specified in settings. Aborting...")

    @self.client.event
    async def on_ready():
      msg = f'Channel {self.channel_name}: Discord user {self.client.user} has logged in'
      await log("info", msg)
      print(msg)

    @self.client.event
    async def on_message(message):
      # Ignore messages from the bot itself
      if message.author == self.client.user:
          return

      # Ignore messages from bots?
      #if message.author.bot:
      #  return

      # If mention is required and the message does not mention the bot itself, ignore the message.
      if self.require_mention and self.client.user not in message.mentions:
        return

      await self.handle_request_message(message.content)

    await log("trace", "Starting Discord client...")
    try:
      # Start the Discord client and connect to Discord servers. This will block until the client is closed.
      BOT_TOKEN = eval_env_var(self.channel_settings.get("bot_token", "${DISCORD_BOT_TOKEN}"))
      await self.client.start(BOT_TOKEN)
    except ClientConnectorDNSError as e:
      raise Exception('Cannot look up `discord.com` or `gateway.discord.gg` in DNS. Add entry in /etc/hosts or check your network settings.') from e

  async def handle_response_message(self, response):
    response_body = response.get("body", "")
    await log("trace", f"Discord channel {self.channel_name}: Sending response message: {response_body}")
    if response_body is None or response_body == "":
      await log("trace", f"Discord channel {self.channel_name}: Response message body is empty. Skipping...")
      return

    # Get the Discord channel object. Try cache first, then API if not found in cache.
    discord_channel = self.client.get_channel(self.channel_id)
    if discord_channel is None:
      discord_channel = await self.client.fetch_channel(self.channel_id)
    if discord_channel is None:
      await log("warning", f"Discord channel {self.channel_name}: Could not find Discord channel with ID {self.channel_id}. Skipping...")
      return

    # If the response body is "[...]" and the queue is empty, send a typing indicator.
    # If the queue is not empty, just skip.
    if response_body == "[...]":
      if self.response_message_queue.empty():
        async with discord_channel.typing():
          await asyncio.sleep(3)
      return

    # Sends the message to the Discord channel.
    # Discord messages have a maximum length of 2000 characters
    await discord_channel.send(response_body[:2000])

  async def stop(self):
    await log("trace", f"Discord channel {self.channel_name}: Stopping...")
    if self.client.is_closed():
      await log("trace", f"Discord channel {self.channel_name} is already closed.")
    else:
      await self.client.close()
      await log("trace", f"Discord channel {self.channel_name} has been closed.")
    await log("trace", f"Discord channel {self.channel_name} is stopped.")

  async def finalize(self):
    await log("trace", f"Discord channel {self.channel_name} has been finalized.")
