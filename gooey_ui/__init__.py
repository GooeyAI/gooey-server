from functools import lru_cache

from .components import *
from .state import *


def __getattr__(name):
    if name == "session_state":
        return get_session_state()
    else:
        raise AttributeError(name)


def cache_data(fn=None, *args, **kwargs):
    if not fn:
        return lru_cache
    return lru_cache(fn)


def cache_resource(fn=None, *args, **kwargs):
    if not fn:
        return lru_cache
    return lru_cache(fn)
