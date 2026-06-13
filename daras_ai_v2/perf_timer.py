import threading

from time import perf_counter

from loguru import logger

threadlocal = threading.local()


def perf_timeit(f):
    def wrapper(*args, **kwargs):
        s = perf_counter()
        result = f(*args, **kwargs)
        logger.debug(f"{f.__name__} took {(perf_counter() - s) * 1000:.2f}ms")
        return result

    return wrapper
