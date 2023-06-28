import threading

from time import perf_counter

local = threading.local()


def start_perf_timer():
    local._perf_timer_start = perf_counter()


def perf_timer():
    try:
        start = local._perf_timer_start
    except AttributeError:
        start = 0
    ms = (perf_counter() - start) * 1000
    return f"{ms:.2f}ms"
