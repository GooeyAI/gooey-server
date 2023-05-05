from functools import lru_cache

from components import *
from state import *
from tree import *


def stop():
    exit(0)


def cache_data(fn=None, *args, **kwargs):
    if not fn:
        return lru_cache
    return lru_cache(fn)


def cache_resource(fn=None, *args, **kwargs):
    if not fn:
        return lru_cache
    return lru_cache(fn)
