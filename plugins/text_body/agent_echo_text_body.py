import os
import sys
import re
import asyncio
import signal
sys.path.append('../')
from yaclaw.agent import Agent
from yaclaw.util import strip_ansi_escape_codes, first_non_escape_part
from yaclaw.log import log

class HandlerEcho(Agent):

  async def initialize(self, agent_name, agent_settings):
    return True

  async def start_handler(self):
    await log("trace", f"Agent {self.agent_name}: Starting Echo...")

  async def handle_request_message(self, request):
    response = await self.create_response_skeleton(request)
    response["body"] = request["body"] + f" -> {self.agent_name}"
    await self.handle_response_message(response)

  async def stop(self):
    pass

  async def finalize(self):
    pass

