import os
import sys
import re
import asyncio
import signal
import pexpect # https://github.com/pexpect/pexpect
sys.path.append('../')
from yaclaw.agent import Agent
from yaclaw.util import strip_ansi_escape_codes, first_non_escape_part
from yaclaw.log import log

class HandlerImplCodexCli(Agent):
  pattern_OSC = re.compile(r'\x1b\]10;\?\x1b\\')
  pattern_color = re.compile(r'\x1B\[[0-9;]+m')
  pattern_footer = re.compile(r'›\x1B\[[0-9]+;[0-9]+H.*?\x1B\[[0-9]+;[0-9]+H.*?% left.*?\x1B\[[0-9]+;[0-9]+H')
  pattern_cursor_move = re.compile(r'\x1B\[[0-9]+;[0-9]+H')
  pattern_duplicate_return = re.compile(r'[\n\r][\n\r]+')

  @classmethod
  def __clean_str(cls, s):
    s = cls.pattern_OSC.sub('', s)
    s = cls.pattern_color.sub('', s)
    s = cls.pattern_footer.sub('', s)
    s = cls.pattern_cursor_move.sub('\n', s)
    s = strip_ansi_escape_codes(s)
    s = cls.pattern_duplicate_return.sub('\n', s).strip()
    return s

  async def initialize(self, agent_name, agent_settings):
    self.process = None
    return True

  async def read_llm_response(self):
    prev_str = "$$$dummy$$$"
    while True:
      # `before` holds the output received since the last **non-timeout** expect call.
      index = await self.process.expect(["• ", pexpect.TIMEOUT], timeout=2, async_=True)
      if index == 0:
        await log("codex_cli", "found '• '. Continue...")
        before_str = self.process.before
        await log("codex_cli", f"output: {before_str}")
      elif index == 1:
        await log("codex_cli", "timeout")
        before_str = self.process.before
        await log("codex_cli", f"output: {before_str}")
        if before_str == prev_str:
          break
      prev_str = before_str
    self.llm_response_is_ready = True
    return self.__clean_str(before_str)

  async def start_handler(self):
    # codex resume --last --no-alt-screen --model gpt-5.3-codex --dangerously-bypass-approvals-and-sandbox
    self.process = pexpect.spawn("codex --model gpt-5.3-codex --dangerously-bypass-approvals-and-sandbox", cwd=self.settings["work_dir"], echo=False, encoding='utf-8')
    await log("codex_cli", f"{self.agent_name}: codex-cli process started with PID: {self.process.pid}")

    # 開始のメッセージを読む
    await log("codex_cli", f"{self.agent_name}: Reading initial output from codex-cli...")
    llm_resp = await self.read_llm_response()
    await log("codex_cli", f"output at start: {llm_resp}")

    # Creates a response message and 'handles' it.
    dest_channel = self.settings.get("default_channel", None)
    if dest_channel is not None:
      response = {"from": self.agent_name, "to": dest_channel, "body": llm_resp}
      await self.handle_response_message(response)

    msg = f"Agent {self.agent_name}: codex-cli is ready to receive prompts."
    await log("codex_cli", msg)
    print(msg)

  async def continue_to_send_typing_indicator(self, request):
    response = await self.create_response_skeleton(request)
    response["body"] = "[...]"
    while not self.llm_response_is_ready:
      await self.handle_response_message(response)
      await asyncio.sleep(5)

  async def handle_request_message(self, request):
    self.process.sendline(request["body"])
    await log("codex_cli", f"input: {request['body']}")

    # https://en.wikipedia.org/wiki/Control_character
    await asyncio.sleep(0.5)
    self.process.sendcontrol('m') # send Enter

    # Waits for the llm response. While waiting, continues to send typing indicators every 5 seconds.
    self.llm_response_is_ready = False
    async with asyncio.TaskGroup() as tg:
      task1 = tg.create_task(self.continue_to_send_typing_indicator(request))
      task2 = tg.create_task(self.read_llm_response())
    llm_resp = task2.result()

    # Creates a response message and 'handles' it.
    response = await self.create_response_skeleton(request)
    response["body"] = llm_resp
    await self.handle_response_message(response)

  async def stop(self):
    if self.process:
      self.process.close()
      await log("codex_cli", f"Agent {self.agent_name}: codex-cli process stopped. pexpect process exit status: {self.process.exitstatus}, signal status: {self.process.signalstatus}")
      self.process = None

  async def finalize(self):
    pass
