import hashlib
import os.path
import pickle
import typing
from contextlib import contextmanager
from functools import wraps, lru_cache

from daras_ai_v2 import settings

LOCK_TIMEOUT_SEC = 10 * 60


@lru_cache
def get_redis_cache():
    import redis

    return redis.Redis.from_url(settings.REDIS_CACHE_URL)


F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])


def redis_cache_decorator(fn: F | None = None, ex=None) -> F:
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):

            # hash the args and kwargs so they are not too long
            args_hash = hashlib.sha256(f"{args}{kwargs}".encode()).hexdigest()
            # create a readable cache key
            cache_key = f"gooey/redis-cache-decorator/v1/{fn.__name__}/{args_hash}"
            # lock the cache key so that only one thread can run the function
            with redis_lock(cache_key):
                # get the redis cache
                redis_cache = get_redis_cache()
                cache_val = redis_cache.get(cache_key)
                # if the cache exists, return it
                if cache_val:
                    return pickle.loads(cache_val)
                # otherwise, run the function and cache the result
                else:
                    result = fn(*args, **kwargs)
                    cache_val = pickle.dumps(result)
                    redis_cache.set(cache_key, cache_val, ex=ex)
                    return result

        return wrapper

    if fn is None:
        return decorator
    else:
        return decorator(fn)


@contextmanager
def redis_lock(key: str, timeout: int = LOCK_TIMEOUT_SEC):
    import redis

    redis_cache = get_redis_cache()
    lock = redis_cache.lock(name=os.path.join(key, "lock"), timeout=timeout)
    try:
        try:
            lock.acquire()
        except redis.exceptions.LockError:
            pass
        yield
    finally:
        try:
            lock.release()
        except redis.exceptions.LockError:
            pass
