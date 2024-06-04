import hashlib
import json
import threading
import typing
import uuid
from contextlib import contextmanager
from functools import lru_cache
from time import time

from loguru import logger

from daras_ai_v2 import settings

T = typing.TypeVar("T")

threadlocal = threading.local()


@lru_cache
def get_redis():
    import redis

    return redis.Redis.from_url(settings.REDIS_URL)


def realtime_clear_subs():
    threadlocal.channels = []


def get_subscriptions() -> list[str]:
    try:
        return threadlocal.channels
    except AttributeError:
        threadlocal.channels = []
        return threadlocal.channels


def run_in_thread(
    fn: typing.Callable,
    *,
    args: typing.Sequence = None,
    kwargs: typing.Mapping = None,
    placeholder: str = "...",
    cache: bool = False,
    ex=60,
):
    from .state import session_state
    from .components import write

    channel_key = f"--thread/{fn}"
    try:
        channel = session_state[channel_key]
    except KeyError:
        channel = session_state[channel_key] = (
            f"gooey-thread-fn/{fn.__name__}/{uuid.uuid1()}"
        )

        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        def target():
            realtime_push(channel, dict(y=fn(*args, **kwargs)), ex=ex)

        threading.Thread(target=target).start()

    try:
        return session_state[channel]
    except KeyError:
        pass

    result = realtime_pull([channel])[0]
    if result:
        ret = result["y"]
        if cache:
            session_state[channel] = ret
        else:
            session_state.pop(channel_key)
        return ret
    elif placeholder:
        write(placeholder)


def realtime_pull(channels: list[str]) -> list[typing.Any]:
    channels = [f"gooey-gui/state/{channel}" for channel in channels]
    threadlocal.channels = channels
    r = get_redis()
    out = [
        json.loads(value) if (value := r.get(channel)) else None for channel in channels
    ]
    return out


def realtime_push(channel: str, value: typing.Any = "ping", ex=None):
    from fastapi.encoders import jsonable_encoder

    channel = f"gooey-gui/state/{channel}"
    msg = json.dumps(jsonable_encoder(value))
    r = get_redis()
    r.set(channel, msg, ex=ex)
    r.publish(channel, json.dumps(time()))
    if isinstance(value, dict):
        run_status = value.get("__run_status")
        logger.info(f"publish {channel=} {run_status=}")
    else:
        logger.info(f"publish {channel=}")


@contextmanager
def realtime_subscribe(channel: str) -> typing.Generator:
    channel = f"gooey-gui/state/{channel}"
    r = get_redis()
    pubsub = r.pubsub()
    pubsub.subscribe(channel)
    logger.info(f"subscribe {channel=}")
    try:
        yield _realtime_sub_gen(channel, pubsub)
    finally:
        logger.info(f"unsubscribe {channel=}")
        pubsub.unsubscribe(channel)
        pubsub.close()


def _realtime_sub_gen(channel: str, pubsub: "redis.client.PubSub") -> typing.Generator:
    while True:
        message = pubsub.get_message(timeout=10)
        if not (message and message["type"] == "message"):
            continue
        r = get_redis()
        value = json.loads(r.get(channel))
        if isinstance(value, dict):
            run_status = value.get("__run_status")
            logger.info(f"realtime_subscribe: {channel=} {run_status=}")
        else:
            logger.info(f"realtime_subscribe: {channel=}")
        yield value


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
