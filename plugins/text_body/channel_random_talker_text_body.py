import os
import sys
import random
import asyncio

sys.path.append("../")
from yaclaw.channel import Channel
from yaclaw.log import log

"""
Random talker channel plugin for YaClaw.

This plugin simulates a random talker for testing purposes.
"""


class ChannelRandomTalker(Channel):

    counter = 0
    lock = asyncio.Lock()

    async def initialize(self, channel_name, channel_settings):
        self.shutdown = False
        return True

    async def start_listener(self):
        while not self.shutdown:
            interval = random.random() * 3
            await asyncio.sleep(interval)
            async with self.lock:
                ChannelRandomTalker.counter += 1
                body = (
                    f"{self.channel_name}: Message #{str(ChannelRandomTalker.counter)}"
                )
            print(f'{self.channel_name} request: "{body}"')

            # Use `create_request_skeleton` if you want to control the structure of the
            # request message, e.g. to specify "reply_to" or other fields.
            # request = await self.create_request_skeleton()
            # request["body"] = body
            # await self.handle_request_message(request)

            await self.handle_request_message(body)

    async def handle_response_message(self, response):
        print(f"{self.channel_name} response: \"{response['body']}\"")

    async def stop(self):
        self.shutdown = True

    async def finalize(self):
        pass
