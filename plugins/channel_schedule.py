import sys
import time
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor
sys.path.append('../')
from yaclaw.channel import Channel
from yaclaw.log import log
"""
Schedule channel plugin for YaClaw.
This plugin generates a request message at predefined intervals (e.g. every minute) and sends it to the connected agent(s).
Uses apscheduler library: https://github.com/agronholm/apscheduler
"""

class ChannelSchedule(Channel):

  shutdown = False

  async def initialize(self, channel_name, channel_settings):
    entry_list = channel_settings.get("entry", [])
    self.scheduler = AsyncIOScheduler(executors={'default': AsyncIOExecutor()})
    for entry_name, entry in entry_list.items():
      dest_agent = entry.get("agent", None)
      if dest_agent is None:
        await log("error", f"ChannelSchedule: No agent specified for entry {entry}. Skipping...")
        continue
      reply_to = entry.get("reply_to", None)
      if reply_to is None:
        await log("error", f"ChannelSchedule: No reply_to specified for entry {entry}. Skipping...")
        continue
      body = entry.get("message", "")
      message = {"from": self.channel_name, "to": dest_agent, "reply_to": reply_to, "body": body}
      everyday_at = entry.get("everyday_at", None)
      if everyday_at is not None:
        spl = everyday_at.split(":")
        hour = int(spl[0])
        minute = int(spl[1])
        self.scheduler.add_job(self.handle_request_message, trigger='cron', args=[message], hour=hour, minute=minute)
      every_n_minutes = entry.get("every_n_minutes", None)
      if every_n_minutes is not None:
        self.scheduler.add_job(self.handle_request_message, trigger='interval', args=[message], minutes=every_n_minutes)
    return True

  async def start_listener(self):
    msg = f"Schedule Channel {self.channel_name}: Starting listener..."
    await log("info", msg)
    print(msg)

    self.scheduler.start()

  async def handle_response_message(self, response):
    await log("warning", f"{self.channel_name} response: \"{response['body']}\"")

  async def stop(self):
    self.scheduler.remove_all_jobs()

  async def finalize(self):
    self.scheduler.shutdown()   
