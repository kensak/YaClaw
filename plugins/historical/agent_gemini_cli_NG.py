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
"""
Agent plugin for Google Gemini CLI
https://github.com/google-gemini/gemini-cli
"""

class HandlerImplCodexCli(Agent):
  pattern_color = re.compile(r'\x1B\[[0-9;]+m')
  pattern_delete_line = re.compile(r'\x1b\[2K')

  @classmethod
  def __clean_str(cls, s):
    s = cls.pattern_color.sub('', s)
    orig_lines = s.splitlines()
    lines = []
    for line in orig_lines:
      # Count number of "\x1b[2K" (delete line)
      delete_line_count = len(cls.pattern_delete_line.findall(line))
      if delete_line_count == 0:
        lines.append(line)
      elif delete_line_count > 1 and (delete_line_count-1) <= len(lines):
        del lines[1-delete_line_count:]
      if delete_line_count > 0:
        spl = line.rsplit("\x1b[2K", 1)
        lines.append(spl[1])
    s = "\n".join(lines)
    #s = s.split("\x1b[39m\r\n\r\n \x1b[37m", 1)[0]
    s = strip_ansi_escape_codes(s).strip()
    return s

  async def initialize(self, agent_name, agent_settings):
    self.process = None
    self.prev_output = ""
    return True

  async def read_llm_response(self):
    prev_str = "$$$dummy$$$"
    while True:
      # `before` holds the output received since the last **non-timeout** expect call.
      index = await self.process.expect(["💬", "\r\nModel:", pexpect.TIMEOUT], timeout=5, async_=True)
      if index == 0:
        await log("gemini_cli", "found '💬' (Thinking...). Continue...")
        before_str = self.process.before
        await log("gemini_cli", f"output: {before_str}")
      if index == 1:
        await log("gemini_cli", "found 'Model:'. Continue...")
        before_str = self.process.before
        await log("gemini_cli", f"output: {before_str}")
      elif index == 2:
        await log("gemini_cli", "timeout")
        before_str = self.process.before
        await log("gemini_cli", f"output: {before_str}")
        if before_str == prev_str:
          break
      prev_str = before_str
    self.llm_response_is_ready = True
    return self.__clean_str(before_str)

  async def start_handler(self):
    # https://geminicli.com/docs/reference/configuration/#command-line-arguments
    # --model gemini-3-pro-preview
    try:
      self.process = pexpect.spawn("gemini --yolo --resume latest --screen-reader", cwd=self.settings["work_dir"], echo=False, encoding='utf-8')
    except pexpect.exceptions.ExceptionPexpect as e:
      print(f"Failed to start gemini-cli process: {e}")
      raise

    await log("gemini_cli", f"{self.agent_name}: gemini-cli process started with PID: {self.process.pid}")

    # 開始のメッセージを読み捨てる
    await log("gemini_cli", f"{self.agent_name}: Reading initial output from gemini-cli...")
    llm_resp = await self.read_llm_response()
    await log("gemini_cli", f"output at start: {llm_resp}")

    msg = f"Agent {self.agent_name}: gemini-cli is ready to receive prompts."
    await log("gemini_cli", msg)
    print(msg)

  async def continue_to_send_typing_indicator(self, request):
    response = await self.create_response_skeleton(request)
    response["body"] = "[...]"
    while not self.llm_response_is_ready:
      await self.handle_response_message(response)
      await asyncio.sleep(5)
      
  async def handle_request_message(self, request):
    self.process.sendline(request["body"])
    await log("gemini_cli", f"input: {request['body']}")

    # Types 'Enter'.
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
      await log("gemini_cli", f"Agent {self.agent_name}: gemini-cli process stopped. pexpect process exit status: {self.process.exitstatus}, signal status: {self.process.signalstatus}")
      self.process = None

  async def finalize(self):
    pass
