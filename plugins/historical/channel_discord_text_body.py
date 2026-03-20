import os
import sys
import asyncio
import discord
from aiohttp.client_exceptions import ClientConnectorDNSError
sys.path.append('../')
from yaclaw.channel import Channel
from yaclaw.log import log
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

    # prepare discord channel ID
    self.channel_id = self.channel_settings.get("channel_id", None)
    if self.channel_id is None:
      msg = f"Channel {self.channel_name}: Discord channel ID not specified in settings. Aborting..."
      await log("error", msg)
      print(msg)
      return False

    # prepare discord bot token
    self.bot_token = self.channel_settings.get("bot_token", None)
    if self.bot_token is None:
      msg = f"Channel {self.channel_name}: Discord bot token not specified in settings. Aborting..."
      await log("error", msg)
      print(msg)
      return False
    
    await log("trace", f"Discord channel {self.channel_name}: Initialized.")
    return True

  async def start_listener(self):
    await log("trace", f"Discord channel {self.channel_name}: Starting listener...")

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

      if len(message.mentions) == 0:
        if self.require_mention:
          return
      else:
        if self.client.user not in message.mentions:
          return

      await self.handle_request_message(message.content)

    await log("trace", "Starting Discord client...")
    try:
      # Start the Discord client and connect to Discord servers. This will block until the client is closed.
      await self.client.start(self.bot_token)
    except ClientConnectorDNSError as e:
      print(f"Failed to connect to Discord. DNS lookup failed: {e}")
      raise Exception('Cannot look up `discord.com` or `gateway.discord.gg` in DNS. Check your network settings.') from e

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
    while response_body:
      head = response_body[:2000]
      await discord_channel.send(head)
      response_body = response_body[2000:]

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
