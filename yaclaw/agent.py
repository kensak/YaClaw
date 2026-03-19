import sys
import asyncio
import importlib.machinery
import importlib.util
from abc import ABC, abstractmethod
from typing import final
from yaclaw.log import log


class Agent(ABC):
    def __init__(self):
        """__init__ canot be async, so do not put any async code here. Use async initialize() instead."""

    @abstractmethod
    async def initialize(self, agent_name, agent_settings):
        pass

    @final
    async def __initialize(self, agent_name, agent_settings):
        await log("trace", f"Agent {agent_name}: Initializing...")
        self.agent_name = agent_name
        self.settings = agent_settings
        self.request_message_queue = asyncio.Queue()
        return await self.initialize(agent_name, agent_settings)

    @abstractmethod
    async def start_handler(self):
        """
        Start the handler.
        This blocks until the handler terminates.
        """
        pass

    @final
    async def __start_handler(self):
        await log("trace", f"Agent {self.agent_name}: Starting handler...")
        await self.start_handler()

    @final
    async def __start_queue_handler(self):
        await log("trace", f"Agent {self.agent_name}: Starting queue handler...")
        while True:
            request = await self.request_message_queue.get()
            await log(
                "trace", f"Agent {self.agent_name} got message from queue: {request}"
            )
            await self.__handle_request_message(request)

    @final
    async def __start(self):
        await log("trace", f"Agent {self.agent_name}: Starting queue and handler...")
        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(self.__start_handler())
            task2 = tg.create_task(self.__start_queue_handler())

    @abstractmethod
    async def handle_request_message(self, request):
        pass

    @final
    async def __handle_request_message(self, request):
        await log(
            "trace", f"Agent {self.agent_name} is handling request message : {request}"
        )
        await self.handle_request_message(request)
        await log(
            "trace", f"Finished handling request message for agent {self.agent_name}."
        )

    @final
    async def create_response_skeleton(self, request):
        response = {"via": [], "body": ""}
        if "reply_to" not in request:
            response["reply_to"] = request["from_"]
        else:
            response["reply_to"] = request["reply_to"]
        to_ = request["to_"]
        if type(to_) == str:
            to_ = [to_]
        if to_[0] != self.agent_name:
            await log(
                "warning",
                f"Handler for agent {self.agent_name}: Message is not destined for this agent. Message: {request}",
            )
        response["from_"] = to_[0]
        response["to_"] = to_[1:]
        if response["to_"] == []:
            response["to_"] = response["reply_to"]
            del response["reply_to"]
        elif len(response["to_"]) == 1:
            response["to_"] = response["to_"][0]
        response["via"].append(self.agent_name)
        return response

    @final
    async def handle_response_message(self, response):
        from yaclaw.channel import ChannelManager

        await log("trace", f"Agent {self.agent_name} is responding: {response}")
        if "reply_to" in response:
            dest_agent_name = (
                response["to_"]
                if isinstance(response["to_"], str)
                else response["to_"][0]
            )
            dest_agent = AgentManager.get_agent(dest_agent_name)
            await log(
                "trace",
                f"Agent {self.agent_name}: Putting response message in queue for agent {dest_agent.agent_name}...",
            )
            await dest_agent.request_message_queue.put(response)
            await log(
                "trace",
                f"Agent {self.agent_name}: Response message put in queue for agent {dest_agent.agent_name}.",
            )
        else:
            channel = ChannelManager.get_channel(response["to_"])
            await log(
                "trace",
                f"Agent {self.agent_name}: Putting response message in queue for channel {channel.channel_name}...",
            )
            await channel.response_message_queue.put(response)
            await log(
                "trace",
                f"Agent {self.agent_name}: Response message put in queue for channel {channel.channel_name}.",
            )

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def finalize(self):
        pass

    @final
    async def __finalize(self):
        await log("trace", f"Finalizing agent: {self.agent_name}...")
        await self.stop()
        await self.finalize()
        self.request_message_queue.shutdown(immediate=True)
        await log("trace", f"Agent {self.agent_name} finalized.")


class AgentManager:
    __agent_settings = {}
    __agent_dict = {}  # agent_name -> Agent instance
    # is_ready_event = asyncio.Event()

    @classmethod
    async def initialize(cls, agent_settings):
        await log("trace", "AgentManager: Initializing agents...")
        cls.__agent_settings = agent_settings

        # Create and register agents.
        for agent_name, settings in agent_settings.items():
            await log("trace", f"AgentManager: Creating agent: {agent_name}...")

            plugin_name = settings.get("plugin", None)
            if plugin_name is None:
                await log(
                    "error",
                    f"AgentManager: No plugin specified for agent {agent_name}. Aborting...",
                )
                return False
            plugin_path = f"plugins/{plugin_name}.py"

            if plugin_name not in sys.modules:
                await log("trace", f"AgentManager: Loading {plugin_name} plugin...")
                loader = importlib.machinery.SourceFileLoader(plugin_name, plugin_path)
                spec = importlib.util.spec_from_loader(loader.name, loader)
                module = importlib.util.module_from_spec(spec)
                sys.modules[plugin_name] = module
                loader.exec_module(module)
            else:
                await log(
                    "trace",
                    f"AgentManager: {plugin_name} plugin already loaded. Reusing...",
                )
                module = sys.modules[plugin_name]

            # register Agent derived class
            for attr in dir(module):
                class_ = getattr(module, attr)
                if (
                    isinstance(class_, type)
                    and issubclass(class_, Agent)
                    and class_ != Agent
                ):
                    break

            if class_ is None:
                await log(
                    "error",
                    f"AgentManager.initialize: No Agent derived class found in plugin {plugin_name} for agent {agent_name}. Aborting...",
                )
                return False
            # Instantiate agent object and register.
            agent_instance = class_()
            if not await agent_instance._Agent__initialize(agent_name, settings):
                await log(
                    "error",
                    f"AgentManager.initialize: Failed to initialize agent {agent_name} with plugin {plugin_name}. Aborting...",
                )
                return False
            cls.__agent_dict[agent_name] = agent_instance
            await log("trace", f"AgentManager: {agent_name} agent initialized.")

        return True

    @classmethod
    def get_agent(cls, agent_name):
        return cls.__agent_dict.get(agent_name, None)

    @classmethod
    async def start_all(cls):
        await log("trace", "AgentManager: Starting all agents...")
        async with asyncio.TaskGroup() as tg:
            for agent_name, settings in cls.__agent_settings.items():
                agent_instance = cls.__agent_dict.get(agent_name)
                tg.create_task(agent_instance._Agent__start())
        await log("trace", "AgentManager: All agents started.")

    @classmethod
    async def finalize(cls):
        await log("trace", "AgentManager: Finalizing all agents...")
        for agent_name, agent_instance in cls.__agent_dict.items():
            await agent_instance._Agent__finalize()
        await log("trace", "AgentManager: All agents finalized.")
