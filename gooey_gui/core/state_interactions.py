import hashlib
import threading
import typing
import uuid
from functools import wraps

import gooey_gui.components as gui
from .pubsub import realtime_pull, realtime_push
from .state import threadlocal, get_session_state

F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def cache_in_session_state(fn: F | None = None, key="__cache__") -> F:
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # hash the args and kwargs so they are not too long
            args_hash = hashlib.sha256(f"{args}{kwargs}".encode()).hexdigest()
            # create a readable cache key
            cache_key = fn.__name__ + ":" + args_hash
            session_state = get_session_state()
            try:
                # if the cache exists, return it
                result = session_state[key][cache_key]
            except KeyError:
                # otherwise, run the function and cache the result
                result = fn(*args, **kwargs)
                session_state.setdefault(key, {})[cache_key] = result
            return result

        return wrapper

    if fn:
        return decorator(fn)
    else:
        return decorator


def run_in_thread(
    fn: typing.Callable,
    *,
    args: typing.Sequence | None = None,
    kwargs: typing.Mapping | None = None,
    placeholder: str = "...",
    cache: bool = False,
    key: str | None = None,
    ex=60,
):
    """
    Creates a new thread to run `fn(*args, **kwargs)`.

    Returns:
    - `None` until the function call is executing.
    - The returned value of `fn(*args, **kwargs)` on the next call.
      If `cache=True`, the same value will be cached in the `session_state`.
      Further calls to `run_in_thread(fn, ...)` will return the same value
      until the `session_state` is reset (e.g. with a page refresh).

    Note that `fn.__name__` is used in the cache key. Because of this,
    it won't work with `lambda`s and closures that don't have a fixed
    value for `__name__`.
    """

    if key is None:
        key = f"{run_in_thread.__name__}/{fn}"

    session_state = get_session_state()
    try:
        channel = session_state[key]
    except KeyError:
        channel = session_state[key] = (
            f"{run_in_thread.__name__}/{fn.__name__}/{uuid.uuid1()}"
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
    if result and "y" in result:
        ret = result["y"]
        if cache:
            session_state[channel] = ret
        else:
            session_state.pop(key)
        return ret
    elif placeholder:
        gui.write(placeholder)


def use_state(initval, *, key: str | None = None, ex=60):
    if key is None:
        threadlocal.use_state_count += 1
        key = f"{use_state.__name__}/{threadlocal.use_state_count}"

    session_state = get_session_state()
    channel = session_state.setdefault(key, f"{use_state.__name__}/{uuid.uuid1()}")

    result = realtime_pull([channel])[0]
    if result and "y" in result:
        retval = session_state[channel] = result["y"]
    else:
        retval = session_state.setdefault(channel, initval)

    def set_state(val):
        realtime_push(channel, dict(y=val), ex=60)

    return retval, set_state
