import hashlib
import json
import threading
import typing
from time import time

import redis
from fastapi.encoders import jsonable_encoder

from daras_ai_v2 import settings

T = typing.TypeVar("T")

threadlocal = threading.local()
r = redis.Redis.from_url(settings.REDIS_URL)


def realtime_clear_subs():
    threadlocal.channels = []


def get_subscriptions() -> list[str]:
    try:
        return threadlocal.channels
    except AttributeError:
        threadlocal.channels = []
        return threadlocal.channels


def realtime_pull(channels: list[str]) -> list[typing.Any]:
    channels = [f"gooey-gui/state/{channel}" for channel in channels]
    threadlocal.channels = channels
    out = [
        json.loads(value) if (value := r.get(channel)) else None for channel in channels
    ]
    return out


def realtime_push(channel: str, value: typing.Any = "ping"):
    channel = f"gooey-gui/state/{channel}"
    msg = json.dumps(jsonable_encoder(value))
    r.set(channel, msg)
    r.publish(channel, json.dumps(time()))
    print(f"publish {channel!r}")


# def use_state(
#     value: T = None, *, key: str = None
# ) -> tuple[T, typing.Callable[[T], None]]:
#     if key is None:
#         # use the session id & call stack to generate a unique key
#         key = md5_values(get_session_id(), *traceback.format_stack()[:-1])
#
#     key = f"gooey-gui/state-hooks/{key}"
#
#     hooks = get_hooks()
#     hooks.setdefault(key, value)
#     state = hooks[key]
#
#     def set_state(value: T):
#         publish_state(key, value)
#
#     return state, set_state
#
#
# def publish_state(key: str, value: typing.Any):
#     r = get_redis()
#     jsonval = json.dumps(jsonable_encoder(value))
#     r.set(key, jsonval)
#     r.publish(key, jsonval)
#
#
# def set_hooks(hooks: typing.Dict[str, typing.Any]):
#     old = get_hooks()
#     old.clear()
#     old.update(hooks)
#
#
# def get_hooks() -> typing.Dict[str, typing.Any]:
#     try:
#         return threadlocal.hooks
#     except AttributeError:
#         threadlocal.hooks = {}
#         return threadlocal.hooks
#
#
# def get_session_id() -> str | None:
#     try:
#         return threadlocal.session_id
#     except AttributeError:
#         threadlocal.session_id = None
#         return threadlocal.session_id
#
#
# def set_session_id(session_id: str):
#     threadlocal.session_id = session_id


def md5_values(*values) -> str:
    strval = ".".join(map(repr, values))
    return hashlib.md5(strval.encode()).hexdigest()
