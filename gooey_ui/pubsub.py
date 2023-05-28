import hashlib
import json
import threading
import traceback
import typing
from functools import lru_cache

import redis
from fastapi.encoders import jsonable_encoder

from daras_ai_v2 import settings

threadlocal = threading.local()


@lru_cache
def get_redis():
    return redis.Redis.from_url(settings.REDIS_URL)


T = typing.TypeVar("T")


def get_subscriptions() -> list[str]:
    try:
        return threadlocal.channels
    except AttributeError:
        threadlocal.channels = []
        return threadlocal.channels


def subscibe(channels: list[str]) -> list[typing.Any]:
    channels = [f"gooey-gui/{channel}" for channel in channels]
    threadlocal.channels = channels
    r = get_redis()
    return [
        json.loads(value) if (value := r.get(channel)) else None for channel in channels
    ]


def publish(channel: str, value: typing.Any = "ping"):
    channel = f"gooey-gui/{channel}"
    r = get_redis()
    msg = json.dumps(jsonable_encoder(value))
    r.publish(channel, msg)
    r.set(channel, msg)


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
