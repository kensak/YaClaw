from datetime import datetime
import asyncio
import json
import re

current_date_str = ""
f = None
lock = asyncio.Lock()
compiloed_patterns = []


def initialize_log(suppress_types):
    for pattern in suppress_types:
        c_pattern = re.compile(pattern)
        compiloed_patterns.append(c_pattern)


async def log(type_, message):
    global f, current_date_str, lock

    for c_pattern in compiloed_patterns:
        if c_pattern.fullmatch(type_):
            return

    async with lock:
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        if date_str != current_date_str:
            if f:
                f.close()
            f = open(f"log/log-{date_str}.json", "at", encoding="utf-8")
            current_date_str = date_str

        log_entry = {
            "time": now.strftime("%H:%M:%S.%f")[:-3],
            "type": type_,
            "message": message,
        }
        # `json.dumps` will escape special characters in the message.
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        # log_entry = f'{{"time": "{now.strftime("%H:%M:%S.%f")[:-3]}", "type": "{type_}", "message": "{message}"}}'
        # f.write(log_entry + "\n")

        f.flush()


def close_log():
    global f
    if f:
        f.close()
