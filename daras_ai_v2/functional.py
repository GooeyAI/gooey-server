import typing
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

T = typing.TypeVar("T")
R = typing.TypeVar("R")


def flatapply_parallel(
    fn: typing.Callable[..., list[R]],
    *iterables,
    max_workers: int = None,
    message: str = "",
) -> typing.Generator[str, None, list[R]]:
    ret = yield from apply_parallel(
        fn, *iterables, max_workers=max_workers, message=message
    )
    return flatten(ret)


def apply_parallel(
    fn: typing.Callable[..., R],
    *iterables,
    max_workers: int = None,
    message: str = "",
) -> typing.Generator[str, None, list[R]]:
    assert iterables, "apply_parallel() requires at least one iterable"
    max_workers = max_workers or max(map(len, iterables))
    if not max_workers:
        yield
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fs = [pool.submit(fn, *args) for args in zip(*iterables)]
        length = len(fs)
        ret = [None] * length
        it = as_completed(fs)
        for i in range(length):
            yield f"[{i + 1}/{length}] {message}"
            ret[i] = next(it).result()
        return ret


def fetch_parallel(
    fn: typing.Callable[..., R],
    *iterables,
    max_workers: int = None,
) -> typing.Generator[R, None, None]:
    assert iterables, "fetch_parallel() requires at least one iterable"
    max_workers = max_workers or max(map(len, iterables))
    if not max_workers:
        return
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fs = [pool.submit(fn, *args) for args in zip(*iterables)]
        for fut in as_completed(fs):
            yield fut.result()


def flatmap_parallel(
    fn: typing.Callable[..., list[R]],
    *iterables,
    max_workers: int = None,
) -> list[R]:
    return flatten(map_parallel(fn, *iterables, max_workers=max_workers))


def map_parallel(
    fn: typing.Callable[..., R],
    *iterables,
    max_workers: int = None,
) -> list[R]:
    assert iterables, "map_parallel() requires at least one iterable"
    max_workers = max_workers or max(map(len, iterables))
    if not max_workers:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(fn, *iterables))


def flatten(l1: typing.Iterable[typing.Iterable[T]]) -> list[T]:
    return [it for l2 in l1 for it in l2]


def shape(seq: typing.Sequence | np.ndarray) -> tuple[int, ...]:
    if isinstance(seq, np.ndarray):
        return seq.shape
    elif isinstance(seq, typing.Sequence):
        return (len(seq),) + shape(seq[0])
    else:
        return ()
