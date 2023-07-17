import threading

from time import perf_counter

threadlocal = threading.local()


def start_perf_timer():
    threadlocal._perf_timer_start = perf_counter()


def perf_timer():
    try:
        start = threadlocal._perf_timer_start
    except AttributeError:
        start = 0
    ms = (perf_counter() - start) * 1000
    return f"{ms:.2f}ms"
