import hashlib
import os.path
import pickle
import typing
from functools import wraps, lru_cache

import redis

from daras_ai_v2 import settings


@lru_cache
def get_redis_cache():
    return redis.Redis.from_url(settings.REDIS_CACHE_URL)


F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def redis_cache_decorator(fn: F) -> F:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # hash the args and kwargs so they are not too long
        args_hash = hashlib.sha256(f"{args}{kwargs}".encode()).hexdigest()
        # create a readable cache key
        cache_key = f"gooey/redis-cache-decorator/v1/{fn.__name__}/{args_hash}"
        # get the redis cache
        redis_cache = get_redis_cache()
        # lock the cache key so that only one thread can run the function
        with redis_cache.lock(os.path.join(cache_key, "lock")):
            cache_val = redis_cache.get(cache_key)
            # if the cache exists, return it
            if cache_val:
                return pickle.loads(cache_val)
            # otherwise, run the function and cache the result
            else:
                result = fn(*args, **kwargs)
                cache_val = pickle.dumps(result)
                redis_cache.set(cache_key, cache_val)
                return result

    return wrapper
