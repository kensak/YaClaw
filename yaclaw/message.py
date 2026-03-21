from typing import List, Optional, Any
from pydantic import BaseModel


class Message(BaseModel):
    from_: str
    to_: str | List[str]
    reply_to: Optional[str] = None
    via: Optional[str | List[str]] = None
    body: str | Any


def is_message(obj):
    try:
        Message(**obj)
        return True
    except Exception:
        return False
