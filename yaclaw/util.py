import os
import re

# 7-bit and 8-bit C1 ANSI sequences
# https://en.wikipedia.org/wiki/ANSI_escape_code
# https://stackoverflow.com/a/14693789
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
# ansi_escape_8bit = re.compile(r'(?:\x1B[@-Z\\-_]|[\x80-\x9A\x9C-\x9F]|(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~])')  

ansi_escape_at_beginning = re.compile(r'^\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
more_than_one_ansi_escapes_at_beginning = re.compile(r'^(?:\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]))+')

def strip_ansi_escape_codes(text):
  return ansi_escape.sub('', text)

def first_non_escape_part(text):
  return more_than_one_ansi_escapes_at_beginning.sub('', text).split('\x1B', 1)[0]

  """
  curent_str = text
  while True:
    (curent_str, number_of_subs_made) = ansi_escape_at_beginning.subn('', curent_str, count=1)
    if number_of_subs_made == 0:
      break
  return curent_str.split('\x1B', 1)[0]
 """

def eval_env_var(s):
  # Pattern to replace: `${VAR_NAME}`
  # Escape with `$${VAR}` for a literal `${VAR}`.
  pattern = re.compile(r'\$\{([^}]+)\}')

  def replacer(match):
    var_name = match.group(1)
    value = os.getenv(var_name, None)
    if value is None:
      raise Exception(f"Environment variable '{var_name}' not found for substitution in string: {s}")
    return value

  return pattern.sub(replacer, s)
