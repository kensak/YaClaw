import sys
import asyncio
import importlib.machinery
import importlib.util
from abc import ABC, abstractmethod
from typing import final
from yaclaw.log import log
from yaclaw.message import Message, is_message


class Channel(ABC):
    def __init__(self):
        """__init__ canot be async, so do not put any async code here. Use async initialize() instead."""

    @abstractmethod
    async def initialize(self, channel_name, channel_settings):
        pass

    @final
    async def __initialize(self, channel_name, channel_settings):
        await log("trace", f"Channel {channel_name}: Initializing...")
        self.channel_name = channel_name
        self.channel_settings = channel_settings
        # self.forward_to = self.channel_settings.get("forward_to", [])
        self.response_message_queue = asyncio.Queue()
        return await self.initialize(channel_name, channel_settings)

    @abstractmethod
    async def start_listener(self):
        pass

    @final
    async def __start_listener(self):
        await log("trace", f"Channel {self.channel_name}: Starting listener...")
        await self.start_listener()

    @final
    async def __start_queue_handler(self):
        await log("trace", f"Channel {self.channel_name}: Starting queue handler...")
        while True:
            response = await self.response_message_queue.get()
            await log(
                "trace",
                f"Channel {self.channel_name}: Got message from queue: {response}",
            )
            await self.handle_response_message(response)

    @final
    async def __start(self):
        await log(
            "trace", f"Channel {self.channel_name}: Starting queue and listener..."
        )
        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(self.__start_listener())
            task2 = tg.create_task(self.__start_queue_handler())

    @final
    async def create_request_skeleton(self):
        request = {
            "from_": self.channel_name,
            "to_": self.channel_settings["agent"],
            "body": "",
        }
        if "reply_to" in self.channel_settings:
            request["reply_to"] = self.channel_settings["reply_to"]
        return request

    @final
    async def handle_request_message(self, request):
        """
        Put the request message in the queue of the destination agent.
        This is called by the channel plugin when it receives a message from the outside world.

        If `request` is string, constructs a request message from it.
        """
        from yaclaw.agent import AgentManager

        if is_message(request):
            request_message = request
        else:
            request_message = await self.create_request_skeleton()
            request_message["body"] = request
        await log(
            "trace", f"Channel {self.channel_name}: Received message: {request_message}"
        )
        await log(
            "trace",
            f"Channel {self.channel_name}: Putting message in queue for agent {request_message['to_']}...",
        )

        to_ = request_message["to_"]
        if isinstance(to_, list):
            to_ = to_[0]
        agent = AgentManager.get_agent(to_)
        if agent is None:
            await log(
                "error",
                f"Channel {self.channel_name}: No agent found with name '{to_}'. Skipping...",
            )
            return

        await agent.request_message_queue.put(request_message)
        await log(
            "trace",
            f"Channel {self.channel_name}: Message put in queue for agent {request_message['to_']}.",
        )

    @abstractmethod
    async def handle_response_message(self, response):
        """
        Receives a message from the agent connected to this channel and sends it to the outside world.
        This is called by the agent when it sends a message to this channel.
        """
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def finalize(self):
        pass

    @final
    async def __finalize(self):
        await log("trace", f"Finalizing channel: {self.channel_name}...")
        await self.stop()
        await self.finalize()
        self.response_message_queue.shutdown(immediate=True)
        await log("trace", f"Channel {self.channel_name} finalized.")


class ChannelManager:
    __channel_settings = {}
    __channel_dict = {}  # channel_name -> Channel instance

    @classmethod
    async def initialize(cls, channel_settings):
        await log("trace", "ChannelManager: Initializing channels...")
        cls.__channel_settings = channel_settings

        for channel_name, settings in channel_settings.items():
            await log(
                "trace", f"ChannelManager: Initializing channel {channel_name}..."
            )

            plugin_name = settings.get("plugin", None)
            if plugin_name is None:
                await log(
                    "error",
                    f"ChannelManager: No plugin specified for channel {channel_name}. Aborting...",
                )
                return False
            plugin_path = f"plugins/{plugin_name}.py"

            # Load plugin if not already loaded
            if plugin_name not in sys.modules:
                # Load plugin
                loader = importlib.machinery.SourceFileLoader(plugin_name, plugin_path)
                spec = importlib.util.spec_from_loader(loader.name, loader)
                await log("trace", f"ChannelManager: Loading {plugin_name} plugin...")
                module = importlib.util.module_from_spec(spec)
                sys.modules[plugin_name] = module
                loader.exec_module(module)
            else:
                await log(
                    "trace",
                    f"ChannelManager: {plugin_name} plugin already loaded. Reusing...",
                )
                module = sys.modules[plugin_name]

            # register Channel-derived class
            class_ = None
            for attr in dir(module):
                class_ = getattr(module, attr)
                if (
                    isinstance(class_, type)
                    and issubclass(class_, Channel)
                    and class_ != Channel
                ):
                    break
            if class_ is None:
                await log(
                    "error",
                    f"ChannelManager.initialize: No Channel derived class found in plugin {plugin_name} for channel {channel_name}. Aborting...",
                )
                return False

            # Instantiate channel object and register.
            channel_instance = class_()
            if not await channel_instance._Channel__initialize(channel_name, settings):
                await log(
                    "error",
                    f"ChannelManager.initialize: Failed to initialize channel {channel_name} with plugin {plugin_name}. Aborting...",
                )
                return False
            cls.__channel_dict[channel_name] = channel_instance
            await log("trace", f"ChannelManager: {channel_name} channel initialized.")

        return True

    @classmethod
    def get_channel(cls, channel_name):
        return cls.__channel_dict.get(channel_name, None)

    @classmethod
    async def start_all(cls):
        await log("trace", "ChannelManager: Starting all channels...")
        async with asyncio.TaskGroup() as tg:
            for channel_name, channel_instance in cls.__channel_dict.items():
                tg.create_task(channel_instance._Channel__start())
        await log("trace", "ChannelManager: All channels started.")

    @classmethod
    async def finalize(cls):
        await log("trace", "ChannelManager: Finalizing all channels...")
        for channel_name, channel_instance in cls.__channel_dict.items():
            await channel_instance._Channel__finalize()
        await log("trace", "ChannelManager: All channels finalized.")
