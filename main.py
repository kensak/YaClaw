import sys
import json
import asyncio
from dotenv import load_dotenv
import importlib.machinery
import importlib.util
import traceback
from yaclaw.channel import ChannelManager
from yaclaw.agent import AgentManager
from yaclaw.log import log, close_log, initialize_log
from yaclaw.util import eval_env_var


async def main():
    return_code = 0

    try:
        await log("info", "----------------------------------------")
        await log("info", "YaClaw starting...")

        # .envファイルから環境変数を読み込む
        load_dotenv()

        banner_lines = [
            "    ██╗   ██╗ █████╗ ",
            "    ╚██╗ ██╔╝██╔══██╗",
            "     ╚████╔╝ ███████║",
            "      ╚██╔╝  ██╔══██║",
            "       ██║   ██║  ██║",
            "       ╚═╝   ╚═╝  ╚═╝",
            "            ██████╗██╗      █████╗ ██╗    ██╗",
            "           ██╔════╝██║     ██╔══██╗██║    ██║",
            "           ██║     ██║     ███████║██║ █╗ ██║",
            "           ██║     ██║     ██╔══██║██║███╗██║",
            "           ╚██████╗███████╗██║  ██║╚███╔███╔╝",
            "            ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ",
        ]
        # https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797
        gradient = [
            "\x1b[38;5;25m",
            "\x1b[38;5;31m",
            "\x1b[38;5;39m",
            "\x1b[38;5;118m",
            "\x1b[38;5;154m",
            "\x1b[38;5;226m",
            "\x1b[38;5;220m",
            "\x1b[38;5;214m",
            "\x1b[38;5;202m",
            "\x1b[38;5;196m",
            "\x1b[38;5;129m",
            "\x1b[38;5;93m",
        ]
        RESET = "\x1b[0m"
        print("\n")
        for i, line in enumerate(banner_lines):
            color = gradient[i % len(gradient)]
            print(f"{color}{line}{RESET}")
        print("\n")

        with open("settings.json", "r", encoding="utf-8") as f:
            settings_str = f.read()
        try:
            settings_str = eval_env_var(settings_str)
        except Exception as e:
            msg = f"Error evaluating environment variables in settings.json: {e}"
            await log("error", msg)
            print(msg)
            return 1
        settings = json.loads(settings_str)
        await log("trace", "Settings loaded.")

        initialize_log(settings.get("logging", {}).get("suppress_types", []))

        if not await ChannelManager.initialize(settings["channel"]):
            return 2
        if not await AgentManager.initialize(settings["agent"]):
            return 3

        print("Type Ctrl+C to stop.")

        # Start channels and agents.
        # This will run until completion or cancellation.
        # https://docs.python.org/ja/3/library/asyncio-task.html#task-groups
        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(ChannelManager.start_all())
            task2 = tg.create_task(AgentManager.start_all())

    except asyncio.CancelledError:
        await log("trace", "Cancel detected. Stopping...")
    except KeyboardInterrupt:
        await log("trace", "KeyboardInterrupt detected. Stopping...")
    except ExceptionGroup as eg:
        return_code = 4
        msg = f"Exceptions occurred in TaskGroup: {eg}"
        await log("error", msg)
        print(msg)
        error_trace = traceback.format_exc()
        await log("exception_trace", error_trace)
    except Exception as e:
        return_code = 5
        msg = f"An unhandled exception occurred: {e}"
        await log("error", msg)
        print(msg)
        error_trace = traceback.format_exc()
        await log("exception_trace", error_trace)
    finally:
        await log("trace", "Finalizing...")
        await ChannelManager.finalize()
        await log("trace", "Channels finalized.")
        await AgentManager.finalize()
        await log("trace", "Agents finalized.")
        await log("info", "YaClaw stopped.")
        close_log()

    return return_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
