import typing
from concurrent.futures import ThreadPoolExecutor

T = typing.TypeVar("T")
R = typing.TypeVar("R")


def flatmap_parallel(
    fn: typing.Callable[[T], list[R]], it: typing.Sequence[T]
) -> list[R]:
    return flatten(map_parallel(fn, it))


def flatten(l1: typing.Iterable[typing.Iterable[T]]) -> list[T]:
    return [it for l2 in l1 for it in l2]


def map_parallel(
    fn: typing.Callable[[T], R], *iterables: typing.Sequence[T], max_workers: int = None
) -> list[R]:
    assert iterables, "map_parallel() requires at least one iterable"
    max_workers = max_workers or max(map(len, iterables))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(fn, *iterables))
